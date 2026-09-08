import os
import base64
import asyncio
import hashlib
import re
import json
import shutil
import subprocess
import threading
import time
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor
import numpy as np
import cv2
import torch
import torch.nn.functional as F
import folder_paths
from server import PromptServer
from aiohttp import web
from comfy_api.latest import io
import av

# ========== 缓存与常量 ==========
WAVEFORM_POINTS = 1500

_node_metadata_cache = OrderedDict()
_auto_cuts_cache = {}  

_preview_cache = OrderedDict()
_preview_cache_lock = threading.Lock()
MAX_PREVIEW_CACHE = 400  

_preview_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="esd-preview")

_audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esd-audio")  
_audio_media_cache = OrderedDict()
_audio_media_lock = threading.Lock()
MAX_AUDIO_MEDIA_CACHE = 2


def _extract_audio_media(video_path: str):
    """提取整条音轨为浏览器可播放格式：ffmpeg→mp3 优先，缺失时回退 PyAV→WAV(16bit 单声道)。返回 (content_type, bytes) 或 None（无音轨）。"""
    if shutil.which("ffmpeg"):
        try:
            proc = subprocess.run([
                "ffmpeg", "-nostdin", "-y", "-loglevel", "error",
                "-i", video_path,
                "-vn", "-ac", "2", "-ar", "44100",
                "-c:a", "libmp3lame", "-b:a", "128k",
                "-f", "mp3", "pipe:1",
            ], capture_output=True, timeout=180)
            if proc.returncode == 0 and proc.stdout:
                return ("audio/mpeg", proc.stdout)
        except Exception:
            pass
    try:
        import io as _io
        import wave as _wave
        with av.open(video_path) as container:
            astream = next((s for s in container.streams.audio), None)
            if astream is None:
                return None
            rate = int(astream.rate or 44100)
            buf = _io.BytesIO()
            got = False
            with _wave.open(buf, "wb") as wf:
                wf.setnchannels(1)
                wf.setsampwidth(2)
                wf.setframerate(rate)
                for frame in container.decode(astream):
                    arr = frame.to_ndarray()
                    ch = frame.layout.nb_channels if frame.layout else (arr.shape[0] if arr.ndim == 2 else 1)
                    if arr.ndim == 1:
                        arr = arr.reshape(1, -1)
                    if arr.shape[0] == ch:  
                        mono = arr.mean(axis=0) if ch > 1 else arr[0]
                    else:  
                        mono = arr.reshape(-1, ch).mean(axis=1) if ch > 1 else arr.reshape(-1)
                    if arr.dtype == np.int16:
                        f = mono.astype(np.float32) / 32768.0
                    elif arr.dtype == np.int32:
                        f = mono.astype(np.float32) / 2147483648.0
                    elif arr.dtype == np.uint8:
                        f = (mono.astype(np.float32) - 128.0) / 128.0
                    else:
                        f = np.asarray(mono, dtype=np.float32)
                    wf.writeframes((np.clip(f, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
                    got = True
            return ("audio/wav", buf.getvalue()) if got else None
    except Exception as e:
        print(f"[ESD] 音轨提取失败: {e}")
        return None


_last_preview_frame = {}
_warm_generation = {}
_AV_SEQUENTIAL_WINDOW = 24  

# ========== ★ 常驻 AV 容器：BGR uint8 快速解码 ==========
_av_lock = threading.Lock()
_av_state = {"path": None, "container": None, "stream": None, "fps": 24.0, "last_idx": -1}


def _av_reset_locked():
    if _av_state["container"] is not None:
        try:
            _av_state["container"].close()
        except Exception:
            pass
    _av_state.update(path=None, container=None, stream=None, last_idx=-1)


def _decode_frame_bgr(video_path: str, frame_idx: int) -> np.ndarray:
    """返回 BGR uint8 ndarray。
    常驻容器只 open 一次；目标帧在当前位置前方 _AV_SEQUENTIAL_WINDOW 帧内时
    直接顺序解码（拖动预览的大多数请求命中此路径），跳变/回退才 seek。
    全程 uint8、无 torch、无色彩转换。失败时复位容器并抛出，由上层回退。"""
    with _av_lock:
        try:
            if _av_state["path"] != video_path or _av_state["container"] is None:
                _av_reset_locked()
                container = av.open(video_path)
                stream = container.streams.video[0]
                fps = float(stream.average_rate) if stream.average_rate else 24.0
                _av_state.update(path=video_path, container=container, stream=stream, fps=fps, last_idx=-1)
            container, stream = _av_state["container"], _av_state["stream"]
            fps, tb = _av_state["fps"], stream.time_base
            sequential = 0 <= _av_state["last_idx"] < frame_idx <= _av_state["last_idx"] + _AV_SEQUENTIAL_WINDOW
            if not sequential:
                seek_time = max(0.0, frame_idx / fps - 0.1)
                container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)
                _av_state["last_idx"] = -1
            img = None
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                cur = round(float(frame.pts * tb) * fps)
                _av_state["last_idx"] = cur
                if cur >= frame_idx:
                    img = frame.to_ndarray(format="bgr24")
                    break
            if img is None:
                raise ValueError(f"Frame {frame_idx} not found")
            return img
        except Exception:
            _av_reset_locked()
            raise


def _decode_frame_bgr_fallback(video_path: str, frame_idx: int) -> np.ndarray:
    """保守回退：独立 open 一次的 AV 读取；仍失败再用 cv2（天然 BGR）。"""
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate) if stream.average_rate else 24.0
            tb = stream.time_base
            seek_time = max(0.0, frame_idx / fps - 0.1)
            container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                if round(float(frame.pts * tb) * fps) >= frame_idx:
                    return frame.to_ndarray(format="bgr24")
            raise ValueError(f"Frame {frame_idx} not found")
    except Exception:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频: {video_path}")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 0 and frame_idx >= total:
            frame_idx = total - 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read()
        cap.release()
        if not ret or frame is None:
            raise ValueError(f"Frame {frame_idx} 读取失败")
        return frame


def build_preview_jpeg(video_path: str, frame_idx: int, size: int) -> bytes:
    """★ 纯 CPU 快路径：解码(BGR uint8) → cv2.resize → JPEG 编码 → bytes"""
    try:
        img = _decode_frame_bgr(video_path, frame_idx)
    except Exception:
        img = _decode_frame_bgr_fallback(video_path, frame_idx)
    h, w = img.shape[:2]
    scale = size / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 82])
    if not ok:
        raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def _cache_put(key, body):
    with _preview_cache_lock:
        _preview_cache[key] = body
        _preview_cache.move_to_end(key)
        while len(_preview_cache) > MAX_PREVIEW_CACHE:
            _preview_cache.popitem(last=False)


def _warm_one(path, frame, size, gen):
    """后台预热：代际不匹配（用户已跳走）或已缓存则直接返回。"""
    if _warm_generation.get(path) != gen:
        return
    key = (path, frame, size)
    with _preview_cache_lock:
        if key in _preview_cache:
            return
    try:
        body = build_preview_jpeg(path, frame, size)
        if _warm_generation.get(path) != gen:
            return
        _cache_put(key, body)
    except Exception:
        pass


def _schedule_warm(path, frame, size):
    """按最近拖动方向预取接下来 3 帧。
    ★ 方案A：队列有积压时直接放弃本轮预热——预热任务会占住 _av_lock 与 worker，
    与用户实时预览请求抢锁是预览长尾延迟（偶发卡一下）的来源之一。"""
    try:
        if _preview_executor._work_queue.qsize() > 2:
            return
    except Exception:
        pass
    prev = _last_preview_frame.get(path)
    direction = 1 if (prev is None or frame >= prev) else -1
    _last_preview_frame[path] = frame
    _warm_generation[path] = gen = _warm_generation.get(path, 0) + 1
    for i in range(1, 4):  
        t = frame + direction * i
        if t < 0:
            break
        _preview_executor.submit(_warm_one, path, t, size, gen)

def _read_single_frame_rgb(video_path: str, frame_idx: int, target_long_edge: int = 0) -> torch.Tensor:
    """解码单个源帧，返回 [1, H, W, 3] float32 RGB（可选缩放）。av 失败回退 cv2。"""
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate) if stream.average_rate else 24.0
            tb = stream.time_base
            seek_time = max(0.0, frame_idx / fps - 0.1)
            container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)
            for frame in container.decode(stream):
                if frame.pts is None:
                    continue
                if round(float(frame.pts * tb) * fps) >= frame_idx:
                    arr = frame.to_ndarray(format="rgb24")
                    arr = _downscale_frame(arr, target_long_edge)
                    return torch.from_numpy(arr).float().div_(255.0).unsqueeze(0)
            raise ValueError(f"Frame {frame_idx} not found")
    except Exception:
        pass
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"无法打开视频: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
    ret, frame = cap.read()
    cap.release()
    if not ret or frame is None:
        raise ValueError(f"Frame {frame_idx} 读取失败")
    arr = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
    arr = _downscale_frame(arr, target_long_edge)
    return torch.from_numpy(arr).float().div_(255.0).unsqueeze(0)


def _downscale_frame(arr: np.ndarray, target_long_edge: int) -> np.ndarray:
    """等比缩放 uint8 RGB 帧使长边 = target_long_edge（缩小用 INTER_AREA，放大用 INTER_CUBIC）。
    target_long_edge <= 0 表示不缩放。"""
    if not target_long_edge or target_long_edge <= 0:
        return arr
    h, w = arr.shape[:2]
    long_edge = max(h, w)
    if long_edge == target_long_edge:
        return arr
    scale = target_long_edge / long_edge
    nw = max(1, int(round(w * scale)))
    nh = max(1, int(round(h * scale)))
    interp = cv2.INTER_AREA if scale < 1.0 else cv2.INTER_CUBIC   
    return cv2.resize(arr, (nw, nh), interpolation=interp)


def _read_audio_range(video_path: str, start_frame: int, end_frame: int, fps: float):
    """★ 只解码 [start_frame, end_frame) 对应的音频区间（秒级 seek + 采样级裁剪）。
    返回 (float32 tensor [1,1,S] 或 None, sample_rate)。替代原来"整条音轨全量解码再切"。"""
    try:
        with av.open(video_path) as container:
            astream = None
            for s_ in container.streams.audio:
                astream = s_
                break
            if astream is None:
                return None, 44100
            sr = int(astream.rate or 44100)
            tb = float(astream.time_base)
            fps = float(fps) if fps and fps > 0 else 24.0
            t0 = start_frame / fps
            t1 = end_frame / fps
            try:
                container.seek(max(0, int(t0 / tb)), stream=astream, backward=True)
            except Exception:
                container.seek(0)
            chunks = []
            for fr in container.decode(astream):
                if fr.pts is None:
                    continue
                t_start = float(fr.pts * tb)
                n_samples = int(getattr(fr, "samples", 0) or 0)
                t_end = t_start + (n_samples / sr if n_samples else 0.0)
                if t_end <= t0:
                    continue          
                if t_start >= t1:
                    break             
                ch = len(fr.layout.channels) if fr.layout else 1
                arr = fr.to_ndarray()
                if arr.ndim == 1:
                    arr = arr.reshape(1, -1)
                is_planar = getattr(fr.format, "is_planar", True)
                if is_planar:
                    arr = arr[:, :n_samples] if n_samples else arr
                    mono = arr.reshape(ch, -1).mean(axis=0) if ch > 1 else arr.reshape(-1)
                else:
                    arr = arr.reshape(-1, ch)  
                    mono = arr.mean(axis=1) if ch > 1 else arr.reshape(-1)
                s0, s1 = 0, mono.shape[0]
                if t_start < t0:
                    s0 = int(round((t0 - t_start) * sr))
                if t_end > t1:
                    s1 = int(round((t1 - t_start) * sr))
                s0 = max(0, min(s0, mono.shape[0]))
                s1 = max(s0, min(s1, mono.shape[0]))
                if s1 > s0:
                    chunks.append(mono[s0:s1])
            if not chunks:
                return None, sr
            flat = np.concatenate(chunks)
            if flat.dtype == np.int16:
                flat = flat.astype(np.float32) / 32768.0
            elif flat.dtype == np.int32:
                flat = flat.astype(np.float32) / 2147483648.0
            elif flat.dtype == np.uint8:
                flat = (flat.astype(np.float32) - 128.0) / 128.0
            else:
                flat = flat.astype(np.float32)
            return torch.from_numpy(flat).unsqueeze(0).unsqueeze(0), sr
    except Exception as e:
        print(f"[ElementVideoClip] audio range read failed: {e}")
        return None, 44100

def read_frame_range(video_path: str, start_frame: int, end_frame: int,
                     subsampling: int = 1, target_long_edge: int = 0) -> torch.Tensor:
    """读取 [start_frame, end_frame) 区间并按 subsampling 抽帧，返回 [N, H, W, 3] float32 RGB。
    target_long_edge > 0 时把每帧长边缩放到该值（只降不升）。"""
    subsampling = max(1, int(subsampling))
    target_long_edge = max(0, int(target_long_edge or 0))
    try:
        return _read_frames_range_av(video_path, start_frame, end_frame, subsampling, target_long_edge)
    except Exception:
        return _read_frames_range_cv2(video_path, start_frame, end_frame, subsampling, target_long_edge)


def _read_frames_range_av(video_path: str, start_frame: int, end_frame: int,
                          subsampling: int = 1, target_long_edge: int = 0) -> torch.Tensor:
    subsampling = max(1, int(subsampling))
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 24.0
        tb = stream.time_base
        try:
            stream.thread_type = "AUTO"
        except Exception:
            pass
        seek_time = max(0.0, start_frame / fps - 0.1)
        container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)

        n_est = max(1, (end_frame - start_frame + subsampling - 1) // subsampling) + 4
        out = None          
        kept = 0
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            cur = round(float(frame.pts * tb) * fps)
            if cur < start_frame:
                continue
            if cur >= end_frame:
                break
            if kept % subsampling == 0:
                arr = frame.to_ndarray(format="rgb24")            
                arr = _downscale_frame(arr, target_long_edge)     
                if out is None:
                    out = torch.empty((n_est, arr.shape[0], arr.shape[1], 3), dtype=torch.float32)
                elif kept // subsampling >= out.shape[0]:         
                    grown = torch.empty((out.shape[0] * 2, *out.shape[1:]), dtype=torch.float32)
                    grown[: out.shape[0]] = out
                    out = grown
                elif arr.shape[0] != out.shape[1] or arr.shape[1] != out.shape[2]:
                    arr = cv2.resize(arr, (out.shape[2], out.shape[1]), interpolation=cv2.INTER_AREA)
                out[kept // subsampling].copy_(torch.from_numpy(arr))
            kept += 1
        if out is None:
            raise ValueError("未读取到任何帧")
        out = out[:(kept + subsampling - 1) // subsampling]
        out.div_(255.0)
        return out


def _read_frames_range_cv2(video_path: str, start_frame: int, end_frame: int,
                           subsampling: int = 1, target_long_edge: int = 0) -> torch.Tensor:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"无法打开视频: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []
    kept = 0
    for _ in range(start_frame, end_frame):
        ret, frame = cap.read()
        if not ret:
            break
        if kept % subsampling == 0:
            frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
            frame_rgb = _downscale_frame(frame_rgb, target_long_edge)
            frames.append(torch.from_numpy(frame_rgb.astype(np.float32) / 255.0))
        kept += 1
    cap.release()
    if not frames:
        raise ValueError("未读取到任何帧")
    return torch.stack(frames, dim=0)



def detect_scenes_direct(video_path: str, threshold: float) -> list:
    """直接对源视频运行 PySceneDetect（官方标准用法，算法零改动）。
    返回切点帧号列表（= 新镜头第一帧），与 cv2 帧号体系一致。"""
    try:
        from scenedetect import SceneManager, ContentDetector, open_video
    except ImportError:
        print("[ESD] PySceneDetect not installed （请 pip install scenedetect）")
        return []
    video = None
    cuts = []
    try:
        video = open_video(video_path)
        try:
            total_frames = video.duration.get_frames() if video.duration else 0
        except Exception:
            total_frames = 0
        scene_manager = SceneManager()
        scene_manager.add_detector(ContentDetector(threshold=float(threshold)))
        scene_manager.detect_scenes(video, show_progress=False)
        scenes = scene_manager.get_scene_list()
        cuts = [scene[0].get_frames() for scene in scenes[1:]]
        if total_frames > 0:
            cuts = [c for c in cuts if 0 < c < total_frames]
        else:
            cuts = [c for c in cuts if c > 0]
        cuts = sorted(set(cuts))
        print(f"[ESD] Detected {len(cuts)} cuts (direct PySceneDetect)")
    except Exception as e:
        print(f"[ESD] Scene detection error: {e}")
        cuts = []
    finally:
        if video is not None:
            try:
                video.close()
            except Exception:
                pass
    return cuts


def audio_to_waveform(audio_tensor: torch.Tensor, target_points: int = WAVEFORM_POINTS) -> list:
    if audio_tensor is None:
        return []
    if not isinstance(audio_tensor, torch.Tensor):
        try:
            audio_tensor = torch.tensor(audio_tensor, dtype=torch.float32)
        except Exception:
            return []
    audio_tensor = audio_tensor.float()
    if audio_tensor.dim() == 3:
        audio_tensor = audio_tensor[0]
    if audio_tensor.dim() == 2:
        if audio_tensor.shape[0] == 1 or audio_tensor.shape[1] == 1:
            audio_tensor = audio_tensor.flatten()
        elif audio_tensor.shape[0] < audio_tensor.shape[1]:
            audio_tensor = torch.mean(audio_tensor, dim=0)
        else:
            audio_tensor = torch.mean(audio_tensor, dim=1)
    if audio_tensor.dim() != 1:
        audio_tensor = audio_tensor.flatten()
    if audio_tensor.shape[0] > target_points:
        audio_reshaped = audio_tensor.view(1, 1, -1)
        downsampled = F.interpolate(audio_reshaped, size=target_points, mode='linear', align_corners=False)
        peaks = downsampled.squeeze().cpu().tolist()
    else:
        peaks = audio_tensor.cpu().tolist()
    if len(peaks) < target_points:
        indices = np.linspace(0, len(peaks) - 1, target_points)
        peaks = np.interp(indices, np.arange(len(peaks)), peaks).tolist()
    peaks = [abs(v) for v in peaks]
    max_val = max(peaks) if peaks else 1.0
    if max_val > 0:
        peaks = [min(1.0, v / max_val) for v in peaks]
    return peaks


def get_video_info(video_path: str) -> dict:
    """获取视频信息，返回 total_frames, fps, width, height, waveform"""
    total_frames = 0
    fps = 24.0
    waveform = []
    video_duration = 0
    width = 0
    height = 0
    try:
        with av.open(video_path) as container:
            video_stream = None
            for stream in container.streams.video:
                video_stream = stream
                break
            if video_stream is None:
                raise ValueError("No video stream found")
            width = int(getattr(video_stream, "width", 0) or 0)
            height = int(getattr(video_stream, "height", 0) or 0)
            if video_stream.frames and video_stream.frames > 0:
                total_frames = video_stream.frames
            else:
                duration = float(video_stream.duration * video_stream.time_base) if video_stream.duration else 0
                avg_frame_rate = video_stream.average_rate
                if avg_frame_rate:
                    fps = float(avg_frame_rate)
                    total_frames = int(round(duration * fps))
                else:
                    cap = cv2.VideoCapture(video_path)
                    if cap.isOpened():
                        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
                        fps = cap.get(cv2.CAP_PROP_FPS)
                        width = width or int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                        height = height or int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                        cap.release()
                    else:
                        raise IOError("Cannot open video with cv2")

            if video_stream.average_rate:
                fps = float(video_stream.average_rate)
            else:
                duration = float(video_stream.duration * video_stream.time_base) if video_stream.duration else 0
                if duration > 0 and total_frames > 0:
                    fps = total_frames / duration
                else:
                    fps = 24.0

            if fps > 0 and total_frames > 0:
                video_duration = total_frames / fps
            else:
                video_duration = float(video_stream.duration * video_stream.time_base) if video_stream.duration else 0

            audio_stream = None
            for stream in container.streams.audio:
                audio_stream = stream
                break
            if audio_stream:
                try:
                    audio_data = []
                    sample_rate = audio_stream.rate if audio_stream.rate else 44100
                    for frame in container.decode(audio_stream):
                        arr = frame.to_ndarray()
                        if arr.ndim == 1:
                            arr = arr.reshape(1, -1)
                        if arr.shape[0] > 1:
                            arr = np.mean(arr, axis=0)
                        audio_data.append(arr)
                    if audio_data:
                        audio_flat = np.concatenate(audio_data)
                        audio_tensor = torch.from_numpy(audio_flat.astype(np.float32))
                        if video_duration > 0:
                            max_samples = int(video_duration * sample_rate)
                            if max_samples > 0 and audio_tensor.shape[0] > max_samples:
                                audio_tensor = audio_tensor[:max_samples]
                        waveform = audio_to_waveform(audio_tensor, WAVEFORM_POINTS)
                        print(f"[ESD] Audio extracted: {len(waveform)} points, Duration: {video_duration:.2f}s")
                except Exception as e:
                    print(f"[ESD] 提取音频波形失败: {e}")
                    waveform = []
    except Exception as e:
        print(f"[ESD] get_video_info 错误, 回退到 cv2: {e}")
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened():
            raise IOError(f"无法打开视频: {video_path}")
        total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        fps = cap.get(cv2.CAP_PROP_FPS)
        width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        cap.release()
        video_duration = total_frames / fps if fps > 0 else 0
        try:
            with av.open(video_path) as container:
                if container.streams.audio:
                    audio_stream = container.streams.audio[0]
                    sample_rate = audio_stream.rate if audio_stream.rate else 44100
                    audio_data = []
                    for frame in container.decode(audio_stream):
                        arr = frame.to_ndarray()
                        if arr.ndim == 1:
                            arr = arr.reshape(1, -1)
                        if arr.shape[0] > 1:
                            arr = np.mean(arr, axis=0)
                        audio_data.append(arr)
                    if audio_data:
                        audio_flat = np.concatenate(audio_data)
                        audio_tensor = torch.from_numpy(audio_flat.astype(np.float32))
                        max_samples = int(video_duration * sample_rate)
                        if max_samples > 0 and audio_tensor.shape[0] > max_samples:
                            audio_tensor = audio_tensor[:max_samples]
                        waveform = audio_to_waveform(audio_tensor, WAVEFORM_POINTS)
        except Exception:
            pass
    return {"total_frames": total_frames, "fps": fps, "width": width, "height": height, "waveform": waveform}


# def split_audio_by_ranges(audio_tensor: torch.Tensor, ranges: list, total_frames: int) -> list:
    # """按"片段源区间列表"切分音频（支持重排/修剪后的任意区间，与视频片段一一对应）"""
    # if audio_tensor is None:
        # return [None] * len(ranges)
    # if audio_tensor.dim() == 2:
        # audio_tensor = audio_tensor.unsqueeze(0)
    # elif audio_tensor.dim() == 1:
        # audio_tensor = audio_tensor.unsqueeze(0).unsqueeze(0)
    # total_samples = audio_tensor.shape[-1]
    # total_frames = max(1, int(total_frames))
    # out = []
    # for (s, e) in ranges:
        # a = int(round(s / total_frames * total_samples))
        # b = int(round(e / total_frames * total_samples))
        # a = max(0, min(total_samples, a))
        # b = max(a, min(total_samples, b))
        # out.append(audio_tensor[..., a:b] if b > a else None)
    # return out


def _parse_ranges(raw) -> list:
    """解析前端送来的片段区间列表（支持 [{start,end}] 或 [[s,e]] 两种形式）"""
    ranges = []
    if isinstance(raw, list) and raw:
        for s in raw:
            try:
                if isinstance(s, dict):
                    a, b = int(s.get("start")), int(s.get("end"))
                else:
                    a, b = int(s[0]), int(s[1])
                if b > a:
                    ranges.append((a, b))
            except Exception:
                continue
    return ranges


# ========== info 类型（ElementSceneDetection → 下游节点） ==========
def _make_info_type():
    """优先 io.Custom("ESD_INFO")；旧版 API 回退 STRING（info 值为 JSON 字符串），行为一致。"""
    try:
        t = io.Custom("ESD_INFO")
        if hasattr(t, "Input") and hasattr(t, "Output"):
            return t
    except Exception:
        pass
    return None


_ESD_INFO = _make_info_type()


def _info_input(name="info", tooltip=""):
    if _ESD_INFO is not None:
        return _ESD_INFO.Input(name, tooltip=tooltip)
    return io.String.Input(name, default="{}", tooltip=tooltip)


def _info_output(name="info"):
    if _ESD_INFO is not None:
        return _ESD_INFO.Output(name)
    return io.String.Output(name)


def _parse_info(info) -> dict:
    if isinstance(info, dict):
        return info
    if isinstance(info, str):
        try:
            v = json.loads(info)
            return v if isinstance(v, dict) else {}
        except Exception:
            return {}
    return {}


def _pack_info(d: dict):
    if _ESD_INFO is not None:
        return d
    try:
        return json.dumps(d)
    except Exception:
        return "{}"


def _probe_video_size(video_path: str) -> tuple:
    """只读 header，不解码：返回"""
    try:
        with av.open(video_path) as c:
            vs = c.streams.video[0]
            return int(getattr(vs, "width", 0) or 0), int(getattr(vs, "height", 0) or 0)
    except Exception:
        pass
    cap = cv2.VideoCapture(video_path)
    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH)) if cap.isOpened() else 0
    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT)) if cap.isOpened() else 0
    cap.release()
    return w, h


# ========== 节点主类 ==========
class ElementSceneDetection(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [
            io.Int.Input("force_rate", default=0, min=0, max=240, step=1,
                         tooltip="Force output fps. 0 = keep source fps (see video_info line for the real rate)."),
            io.Int.Input("subsampling", default=1, min=1, max=100, step=1,
                         tooltip="Keep every Nth frame (like VHS select_every_nth). 1 = keep all."),
            io.String.Input("clips_data", default="{}", tooltip="Internal UI state (hidden)"),
        ]
        outputs = [_info_output("info")]
        common = dict(
            node_id="ElementSceneDetection",
            display_name="Element Scene Detection",
            category="Element_easy/video",
            description="Scene detection & timeline editing. Outputs an info bundle for "
                        "Element Video Clip / Element Video Info.",
        )
        try:
            return io.Schema(inputs=inputs, hidden=[io.Hidden.unique_id], outputs=outputs, **common)
        except TypeError:
            return io.Schema(inputs=inputs, outputs=outputs, **common)

    @classmethod
    def execute(cls, force_rate=0, subsampling=1, clips_data="{}"):
        try:
            state = json.loads(clips_data) if isinstance(clips_data, str) else (clips_data or {})
        except Exception:
            state = {}

        node_id = None
        try:
            node_id = cls.hidden.unique_id
        except Exception:
            pass
        if node_id is None:
            node_id = state.get("_node_id")
        try:
            node_id = int(node_id)
        except Exception:
            node_id = None
        if node_id is None:
            print("[ESD] Warning: node_id unavailable, cut-sync degraded")

        force_two_parts = state.get("force_two_parts", False)
        fps = float(state.get("fps") or 0) or 24.0
        cuts = state.get("cuts", [])
        selections = state.get("selected_indices", [])
        total_frames = int(state.get("total_frames") or 0)
        local_video_path = state.get("local_video_path", "")

        if not (local_video_path and os.path.exists(local_video_path)):
            raise RuntimeError(
                "[ESD] No usable video source: import a video in the node UI first. "
                "If imported earlier, the file may have been moved or deleted — re-import."
            )

        width, height = _probe_video_size(local_video_path)

        if node_id is not None:
            _node_metadata_cache[node_id] = {
                "path": local_video_path,
                "total_frames": total_frames,
                "fps": fps,
                "waveform": [],
            }

        def get_segments_from_cuts(cuts_list, tf):
            segs = []
            start = 0
            for cut in cuts_list:
                if cut > start:
                    segs.append((start, cut))
                start = cut
            if start < tf:
                segs.append((start, tf))
            return segs

        seg_ranges = _parse_ranges(state.get("segments"))
        if len(seg_ranges) == 1 and seg_ranges[0][0] == 0 and seg_ranges[0][1] == max(1, total_frames):
            seg_ranges = []

        if not seg_ranges and not cuts and bool(state.get("auto_detect_exec", False)):
            thr = float(state.get("cut_threshold") or 27.0)
            print(f"[ESD] Auto scene detection on execute: threshold={thr}")
            cuts = detect_scenes_direct(local_video_path, thr)
            print(f"[ESD] Auto-detected {len(cuts)} cuts")
            if node_id is not None:
                _auto_cuts_cache[node_id] = list(cuts)
            if cuts and node_id is not None:
                try:
                    PromptServer.instance.send_sync("esd_auto_cuts", {"node_id": node_id, "cuts": cuts})
                except Exception as e:
                    print(f"[ESD] websocket cut sync failed (frontend will fall back to HTTP): {e}")
        else:
            if node_id is not None:
                _auto_cuts_cache.pop(node_id, None)

        if not seg_ranges:
            seg_ranges = get_segments_from_cuts(cuts, total_frames)
        if not seg_ranges:
            seg_ranges = [(0, total_frames)]

        if force_two_parts and len(seg_ranges) == 1:
            s, e = seg_ranges[0]
            mid = (s + e) // 2
            if mid > s and mid < e:
                seg_ranges = [(s, mid), (mid, e)]

        try:
            selections = [i for i in selections if 0 <= int(i) < len(seg_ranges)]
        except Exception:
            selections = []

        info = {
            "version": 1,
            "node_id": node_id,
            "video_path": local_video_path,
            "total_frames": int(total_frames),
            "fps": float(fps),
            "width": int(width or 0),
            "height": int(height or 0),
            "force_rate": max(0, int(force_rate or 0)),
            "subsampling": max(1, int(subsampling or 1)),
            "segments": [[int(s), int(e)] for (s, e) in seg_ranges],
            "selected_indices": [int(i) for i in selections],
            "cuts": [int(c) for c in cuts],
        }
        return io.NodeOutput(_pack_info(info))


class ElementVideoClip(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [
            _info_input("info", "Connect from Element Scene Detection 'info' output."),
            io.Int.Input("SegNum", default=1, min=1, tooltip="Segment index (1-based, timeline order) — used when clip_select = segnum"),
            io.Combo.Input("clip_select", options=["select clip", "segnum", "first clip", "last clip", "all"],
                           default="select clip", tooltip="Which timeline segment(s) to output"),
            io.Int.Input("target_long_edge", default=1366, min=0, max=7680, step=2,
                         tooltip="Scale frames so the LONG edge = this value (aspect kept). "
                                 "Values smaller than source downscale; larger values upscale. "
                                 "0 = keep source resolution. Affects images (and first/last when scale_first_last is on)."),
            io.Boolean.Input("scale_first_last", default=False,
                             tooltip="ON: first_image/last_image follow target_long_edge (same size as images). "
                                     "OFF (default): first_image/last_image stay at SOURCE resolution regardless of scaling."),
        ]
        outputs = [
            io.Image.Output("images"),
            io.Audio.Output("audio"),
            io.Int.Output("frame_count"),
            io.Float.Output("seconds"),
            io.Image.Output("first_image"),
            io.Image.Output("last_image"),
            _info_output("info"),
        ]
        return io.Schema(
            node_id="ElementVideoClip",
            display_name="Element Video Clip",
            category="Element_easy/video",
            description="Outputs images/audio/frame_count/seconds for the selected clip, plus an info bundle "
                        "describing what was actually output (effective fps, size, source ranges). "
                        "Its info output can feed Element Video Info.",
            inputs=inputs,
            outputs=outputs,
        )


    @classmethod
    def execute(cls, info, SegNum=1, clip_select="select clip", target_long_edge=1366, scale_first_last=False):
        data = _parse_info(info)
        video_path = data.get("video_path") or data.get("local_video_path") or ""
        if not (video_path and os.path.exists(video_path)):
            raise RuntimeError("[ElementVideoClip] No usable video source in info — re-run Element Scene Detection.")
        segments = _parse_ranges(data.get("segments"))
        if not segments:
            raise RuntimeError("[ElementVideoClip] info contains no segments — re-run Element Scene Detection.")
        total_frames = int(data.get("total_frames") or max(e for _, e in segments))
        src_fps = float(data.get("fps") or 0) or 24.0
        n = max(1, int(data.get("subsampling") or 1))
        force_rate = int(data.get("force_rate") or 0)
        out_fps = float(force_rate) if force_rate > 0 else src_fps / n
        out_fps = max(0.01, out_fps)

        mode = (clip_select or "select clip").strip()
        if mode == "all":
            chosen = list(range(len(segments)))
        else:
            if mode == "segnum":
                idx = max(0, min(int(SegNum or 1) - 1, len(segments) - 1))
            elif mode == "first clip":
                idx = 0
            elif mode == "last clip":
                idx = len(segments) - 1
            else:
                sel = []
                for i in (data.get("selected_indices") or []):
                    try:
                        i = int(i)
                        if 0 <= i < len(segments):
                            sel.append(i)
                    except Exception:
                        pass
                idx = sel[0] if sel else 0
            chosen = [idx]
        ranges = [segments[i] for i in chosen]

        # ---------- 视频：预分配 + 分段写入 ----------
        plan, total = [], 0
        for (s, e) in ranges:
            plan.append((s, e, total))
            total += (e - s + n - 1) // n
        if not plan:
            raise RuntimeError("[ElementVideoClip] No segments to load")
        images = None
        for (s, e, off) in plan:
            try:
                t = read_frame_range(video_path, s, e,
                                     subsampling=n, target_long_edge=target_long_edge)
            except Exception as err:
                raise RuntimeError(f"[ElementVideoClip] Failed to load segment ({s}-{e} frames): {err}")
            if images is None:
                images = torch.empty((total, t.shape[1], t.shape[2], 3), dtype=torch.float32)
            if t.shape[1] != images.shape[1] or t.shape[2] != images.shape[2]:
                t = F.interpolate(t.permute(0, 3, 1, 2),
                                  size=(images.shape[1], images.shape[2]),
                                  mode="bilinear", align_corners=False).permute(0, 2, 3, 1)
            m = min(t.shape[0], total - off)
            images[off: off + m] = t[:m]
            del t

        if scale_first_last:
            first_image = images[0:1].clone()   
            last_image = images[-1:].clone()
        else:
            s0 = plan[0][0]                                          
            s_last, e_last = plan[-1][0], plan[-1][1]                
            cnt_last = (e_last - s_last + n - 1) // n
            src_last = min(s_last + (cnt_last - 1) * n, e_last - 1)  
            first_image = _read_single_frame_rgb(video_path, s0, target_long_edge=0)
            last_image = _read_single_frame_rgb(video_path, src_last, target_long_edge=0)

        frame_count = int(images.shape[0])
        seconds = frame_count / out_fps

        # ---------- 音频：按片段 seek 解码 ----------
        audio_out = None
        sample_rate = 44100
        parts = []
        for (s, e) in ranges:
            at, sr = _read_audio_range(video_path, s, e, src_fps)
            if at is not None:
                parts.append(at)
                sample_rate = sr
        if parts:
            audio_out = torch.cat(parts, dim=-1) if len(parts) > 1 else parts[0]

        # ---------- info：继承上游字段，再覆盖为"本次实际输出"的真实值 ----------
        clip_info = dict(data) if isinstance(data, dict) else {}
        clip_info.update({
            "kind": "clip",                     
            "producer": "ElementVideoClip",
            "video_path": video_path,
            "total_frames": int(total_frames),
            "fps": float(out_fps),              
            "frame_count": frame_count,
            "seconds": float(seconds),
            "width": int(images.shape[2]),      
            "height": int(images.shape[1]),
            "subsampling": n,
            "force_rate": force_rate,
            "target_long_edge": max(0, int(target_long_edge or 0)),
            "scale_first_last": bool(scale_first_last),
            "segments": [[int(s), int(e)] for (s, e) in ranges],
            "selected_indices": [int(i) for i in chosen],
            "sample_rate": int(sample_rate),
            "has_audio": bool(audio_out is not None),
        })

        def wrap_audio(tensor):
            if tensor is None:
                return None
            return {"waveform": tensor, "sample_rate": sample_rate}

        return io.NodeOutput(images, wrap_audio(audio_out), frame_count, float(seconds),
                             first_image, last_image, _pack_info(clip_info))



class ElementVideoInfo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [
            _info_input("info", "Connect from Element Scene Detection OR Element Video Clip 'info' output."),
        ]
        outputs = [io.Float.Output("FPS"), io.Int.Output("Width"), io.Int.Output("Height")]
        return io.Schema(
            node_id="ElementVideoInfo",
            display_name="Element Video Info",
            category="Element_easy/video",
            description="Effective output FPS and video size. Accepts info from Element Scene Detection "
                        "(source resolution) or Element Video Clip (actual output size after downscaling).",
            inputs=inputs,
            outputs=outputs,
        )

    @classmethod
    def execute(cls, info):
        data = _parse_info(info)
        if not data:
            raise RuntimeError("[ElementVideoInfo] Empty info — connect from Element Scene Detection or Element Video Clip.")

        if (data.get("kind") or "").strip().lower() == "clip" or "frame_count" in data:
            fps = float(data.get("fps") or 0) or 24.0
            width = int(data.get("width") or 0)
            height = int(data.get("height") or 0)
            return io.NodeOutput(float(max(0.01, fps)), int(width), int(height))

        fps = float(data.get("fps") or 0) or 24.0
        n = max(1, int(data.get("subsampling") or 1))
        force_rate = int(data.get("force_rate") or 0)
        out_fps = float(force_rate) if force_rate > 0 else fps / n
        width = int(data.get("width") or 0)
        height = int(data.get("height") or 0)
        if not width or not height:
            vp = data.get("video_path") or ""
            if vp and os.path.exists(vp):
                width, height = _probe_video_size(vp)
        return io.NodeOutput(float(max(0.01, out_fps)), int(width), int(height))


# ========== 注册节点 ==========
NODE_CLASS_MAPPINGS = {
    "ElementSceneDetection": ElementSceneDetection,
    "ElementVideoClip": ElementVideoClip,
    "ElementVideoInfo": ElementVideoInfo,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "ElementSceneDetection": "Element Scene Detection",
    "ElementVideoClip": "Element Video Clip",
    "ElementVideoInfo": "Element Video Info",
}

# ========== API 路由 ==========
def _sha256_of_file(path: str, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for block in iter(lambda: f.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def _safe_upload_name(filename: str) -> str:
    """清洗上传文件名：取 basename、替换非法字符，保证落盘到 input 目录安全。"""
    base = os.path.basename((filename or "").strip()) or "video"
    stem, ext = os.path.splitext(base)
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]', "_", stem).strip() or "video"
    ext = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]', "", ext) or ".mp4"
    return stem + ext


@PromptServer.instance.routes.post("/element_scene_detection/upload_video")
async def upload_video_handler(request):
    try:
        data = await request.post()
        file = data.get("video_file")
        if not file:
            return web.json_response({"error": "No file"}, status=400)
        esd_dir = os.path.join(folder_paths.get_input_directory(), "element_scene_detection")
        os.makedirs(esd_dir, exist_ok=True)
        target = os.path.join(esd_dir, _safe_upload_name(file.filename))
        part = f"{target}.{os.getpid()}_{time.time_ns()}.part"
        try:
            h = hashlib.sha256()
            total = 0
            with open(part, "wb") as out:
                while True:
                    block = file.file.read(1 << 20)
                    if not block:
                        break
                    out.write(block)
                    h.update(block)
                    total += len(block)
            if total == 0:
                raise ValueError("Empty upload")
            digest = h.hexdigest()
            if os.path.exists(target) and _sha256_of_file(target) == digest:
                os.remove(part)   
            else:
                if os.path.exists(target):
                    stem, ext = os.path.splitext(target)
                    i = 1
                    while os.path.exists(f"{stem}_{i}{ext}"):
                        i += 1
                    target = f"{stem}_{i}{ext}"
                os.replace(part, target)  
        except Exception:
            try:
                os.remove(part)
            except Exception:
                pass
            raise
        print(f"[ESD] Uploaded: {target}")
        info = get_video_info(target)
        info["file_path"] = target
        return web.json_response(info)
    except Exception as e:
        print(f"[ESD] Upload error: {e}")
        return web.json_response({"error": str(e)}, status=500)



@PromptServer.instance.routes.post("/element_scene_detection/detect")
async def detect_handler(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        video_path = data.get("video_path")
        threshold = data.get("threshold", 15.0)
        if not node_id or not video_path:
            return web.json_response({"error": "Missing params"}, status=400)
        if not os.path.exists(video_path):
            return web.json_response({"error": "视频文件不存在"}, status=404)
        cuts = detect_scenes_direct(video_path, float(threshold))
        return web.json_response({"cuts": cuts})
    except Exception as e:
        print(f"[ESD] Detect error: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get("/esd/preview")
async def esd_preview_get_handler(request):
    """★ 预览主端点：GET + 二进制 JPEG 直出 + 浏览器/服务端双缓存 + 后台预取。"""
    try:
        q = request.rel_url.query
        video_path = q.get("p", "")
        try:
            frame_idx = max(0, int(q.get("f", "0")))
            size = max(32, min(1024, int(q.get("s", "256"))))
        except ValueError:
            return web.Response(status=400, text="bad params")
        if not video_path or not os.path.exists(video_path):
            return web.Response(status=404, text="video not found")
        key = (video_path, frame_idx, size)
        with _preview_cache_lock:
            body = _preview_cache.get(key)
            if body is not None:
                _preview_cache.move_to_end(key)
        if body is None:
            loop = asyncio.get_running_loop()
            body = await loop.run_in_executor(_preview_executor, build_preview_jpeg, video_path, frame_idx, size)
            _cache_put(key, body)
            _schedule_warm(video_path, frame_idx, size)
        return web.Response(body=body, content_type="image/jpeg",
                            headers={"Cache-Control": "private, max-age=300"})
    except Exception as e:
        print(f"[ESD] preview(get) error: {e}")
        return web.Response(status=500, text=str(e))


@PromptServer.instance.routes.get("/esd/auto_cuts")
async def esd_auto_cuts_handler(request):
    try:
        nid = int(request.rel_url.query.get("node_id", "-1"))
    except ValueError:
        nid = -1
    cuts = _auto_cuts_cache.get(nid, [])
    return web.json_response({"cuts": cuts})


@PromptServer.instance.routes.post("/element_scene_detection/preview")
async def preview_handler(request):
    """旧版 POST 端点：保留兼容（返回 base64 data_url）。"""
    try:
        data = await request.json()
        node_id = data.get("node_id")
        frame_idx = int(data.get("frame_index", 0))
        preview_size = int(data.get("preview_size", 320))
        preview_size = max(32, min(1024, preview_size))
        video_path = data.get("video_path", "")
        if not video_path or not os.path.exists(video_path):
            meta = _node_metadata_cache.get(node_id, {})
            video_path = meta.get("path", "")
            if not video_path or not os.path.exists(video_path):
                return web.json_response({"error": "视频文件不存在"}, status=404)
        key = (video_path, frame_idx, preview_size)
        with _preview_cache_lock:
            body = _preview_cache.get(key)
            if body is not None:
                _preview_cache.move_to_end(key)
        if body is None:
            loop = asyncio.get_running_loop()
            body = await loop.run_in_executor(_preview_executor, build_preview_jpeg, video_path, frame_idx, preview_size)
            _cache_put(key, body)
        return web.json_response({"data_url": "data:image/jpeg;base64," + base64.b64encode(body).decode("ascii")})
    except Exception as e:
        print(f"[ESD] Preview error: {e}")
        return web.json_response({"error": str(e)}, status=500)


_nvenc_ok = None
def _has_nvenc() -> bool:
    global _nvenc_ok
    if _nvenc_ok is None:
        try:
            r = subprocess.run(["ffmpeg", "-hide_banner", "-encoders"],
                               capture_output=True, text=True, timeout=15)
            _nvenc_ok = "h264_nvenc" in (r.stdout or "")
        except Exception:
            _nvenc_ok = False
    return _nvenc_ok

def _export_clip_with_audio(video_path, start_frame, end_frame, fps, out_path):
    """★ 优先 GPU：CUDA 解码 + NVENC 编码；失败自动回退 libx264。
       ffmpeg 是独立进程，进程退出显存自动归还，无需手动 empty_cache。"""
    try:
        fps = float(fps) if fps and fps > 0 else 24.0
        start_t = start_frame / fps
        dur = (end_frame - start_frame) / fps
        tail = ["-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", out_path]
        variants = []
        if _has_nvenc():
            variants.append(["-hwaccel", "cuda", "-ss", f"{start_t:.6f}", "-i", video_path,
                             "-t", f"{dur:.6f}",
                             "-c:v", "h264_nvenc", "-preset", "p4", "-rc", "vbr",
                             "-cq", "19", "-b:v", "0"])
        variants.append(["-ss", f"{start_t:.6f}", "-i", video_path, "-t", f"{dur:.6f}",
                         "-c:v", "libx264", "-preset", "veryfast", "-crf", "18"])
        for head in variants:
            try:
                subprocess.run(["ffmpeg", "-y", "-loglevel", "error", *head, *tail],
                               check=True, capture_output=True, timeout=1800)
                if os.path.exists(out_path):
                    return True
            except subprocess.CalledProcessError:
                continue   
        return False
    except Exception as e:
        print(f"[ESD] ffmpeg export failed: {e}")
        return False

@PromptServer.instance.routes.post("/element_scene_detection/export")
async def export_handler(request):
    try:
        data = await request.json()
        node_id = data.get("node_id")
        video_path = data.get("video_path")
        cuts = data.get("cuts", [])
        total_frames = data.get("total_frames", 0)
        fps = data.get("fps", 24.0)
        export_all = data.get("export_all", False)
        selected_indices = data.get("selected_indices", [])
        output_dir = data.get("output_dir", "")
        if not output_dir:
            output_dir = os.path.join(folder_paths.get_output_directory(), "video")
        os.makedirs(output_dir, exist_ok=True)
        if not video_path or not os.path.exists(video_path):
            return web.json_response({"error": "视频文件不存在"}, status=404)
        segments = _parse_ranges(data.get("segments"))
        if not segments:
            segments = []
            start = 0
            for cut in cuts:
                if cut > start:
                    segments.append((start, cut))
                start = cut
            if start < total_frames:
                segments.append((start, total_frames))
        if not segments:
            return web.json_response({"error": "没有片段可导出"}, status=400)
        if export_all:
            export_indices = list(range(len(segments)))
        else:
            export_indices = [i for i in selected_indices if 0 <= i < len(segments)]
        if not export_indices:
            return web.json_response({"error": "没有选中的片段"}, status=400)
        fps = float(fps) if fps and fps > 0 else 24.0
        use_ffmpeg = shutil.which("ffmpeg") is not None
        cap = None
        w = h = 0
        fourcc = None
        ts = int(time.time())
        safe_node_id = str(node_id if node_id is not None else "unknown")
        exported_files = []
        for idx in export_indices:
            s, e = segments[idx]
            out_path = os.path.join(output_dir, f"clip_{safe_node_id}_{idx+1:03d}_{ts}.mp4")
            ok = False
            if use_ffmpeg:
                ok = _export_clip_with_audio(video_path, s, e, fps, out_path)
            if not ok:
                if cap is None:
                    cap = cv2.VideoCapture(video_path)
                    if not cap.isOpened():
                        return web.json_response({"error": "无法打开视频文件"}, status=500)
                    w = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
                    h = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
                    fourcc = cv2.VideoWriter_fourcc(*'mp4v')
                writer = cv2.VideoWriter(out_path, fourcc, fps, (w, h))
                if writer.isOpened():
                    cap.set(cv2.CAP_PROP_POS_FRAMES, s)
                    for _ in range(s, e):
                        ret, frame = cap.read()
                        if not ret:
                            break
                        writer.write(frame)
                    writer.release()
                    ok = True
            if ok:
                exported_files.append(out_path)
        if cap is not None:
            cap.release()
        return web.json_response({"exported": exported_files})
    except Exception as e:
        print(f"[ESD] Export error: {e}")
        return web.json_response({"error": str(e)}, status=500)


@PromptServer.instance.routes.get("/esd/audio")
async def esd_audio_handler(request):
    """★ 音轨端点：整条音轨转发给前端 <audio> 播放；支持 Range 分段请求（音频 currentTime 拖动可靠）。"""
    try:
        video_path = request.rel_url.query.get("p", "")
        if not video_path or not os.path.exists(video_path):
            return web.Response(status=404, text="video not found")
        hit, cached = None, False
        with _audio_media_lock:
            if video_path in _audio_media_cache:
                hit = _audio_media_cache[video_path]
                _audio_media_cache.move_to_end(video_path)
                cached = True
        if not cached:
            hit = await asyncio.get_running_loop().run_in_executor(_audio_executor, _extract_audio_media, video_path)
            with _audio_media_lock:
                _audio_media_cache[video_path] = hit
                _audio_media_cache.move_to_end(video_path)
                while len(_audio_media_cache) > MAX_AUDIO_MEDIA_CACHE:
                    _audio_media_cache.popitem(last=False)
        if hit is None:
            return web.Response(status=404, text="no audio stream")
        ctype, body = hit
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        rng = request.headers.get("Range", "")
        if rng.startswith("bytes=") and body:
            total = len(body)
            try:
                spec = rng[6:].split(",")[0].strip()
                a_s, _, b_s = spec.partition("-")
                if not a_s and b_s:  # bytes=-N → 末尾 N 字节
                    a, b = max(0, total - int(b_s)), total - 1
                else:
                    a = int(a_s) if a_s else 0
                    b = int(b_s) if b_s else total - 1
                b = min(b, total - 1)
                if a > b or a >= total:
                    return web.Response(status=416, headers={"Content-Range": f"bytes */{total}"})
                headers["Content-Range"] = f"bytes {a}-{b}/{total}"
                return web.Response(status=206, body=body[a:b + 1], content_type=ctype, headers=headers)
            except ValueError:
                pass
        return web.Response(body=body, content_type=ctype, headers=headers)
    except Exception as e:
        print(f"[ESD] audio(get) error: {e}")
        return web.Response(status=500, text=str(e))
