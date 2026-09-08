import os
import base64
import asyncio
import tempfile
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
_auto_cuts_cache = {}  # node_id(int) → 最近一次执行期自动检测的切点列表

# ★ 预览 JPEG 字节缓存：key=(video_path, frame, size) → bytes
_preview_cache = OrderedDict()
_preview_cache_lock = threading.Lock()
MAX_PREVIEW_CACHE = 400  # 400 × ~35KB ≈ 14MB 内存

# ★ 解码线程池：重 CPU 工作移出 aiohttp 事件循环，避免阻塞整个 server
_preview_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="esd-preview")

# ========== ★ 音轨播放：整条音轨转码缓存（供前端 <audio> 播放） ==========
_audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="esd-audio")  # 独立线程池，不占预览解码 worker
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
        # 回退：PyAV 逐帧解码 → 内存 WAV
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
                    if arr.shape[0] == ch:  # planar: (ch, N)
                        mono = arr.mean(axis=0) if ch > 1 else arr[0]
                    else:  # packed: (1, N*ch)
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


# 预取（warm）方向与代际：用户跳走后旧预取任务立即作废
_last_preview_frame = {}
_warm_generation = {}
_AV_SEQUENTIAL_WINDOW = 24  # 常驻容器顺序解码窗口（拖动方向前方 N 帧内免 seek）

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
    for i in range(1, 4):  # ★ 方案A：6 帧 → 3 帧，降低对实时请求的挤占
        t = frame + direction * i
        if t < 0:
            break
        _preview_executor.submit(_warm_one, path, t, size, gen)


def read_frame_range(video_path: str, start_frame: int, end_frame: int) -> torch.Tensor:
    """读取视频从 start_frame (含) 到 end_frame (不含) 的帧序列，返回 [N, H, W, 3] float32 RGB tensor。
    ★ av 顺序解码优先（一次 open + 一次 seek），失败回退 cv2。"""
    try:
        return _read_frames_range_av(video_path, start_frame, end_frame)
    except Exception:
        return _read_frames_range_cv2(video_path, start_frame, end_frame)


def _read_frames_range_av(video_path: str, start_frame: int, end_frame: int) -> torch.Tensor:
    frames = []
    with av.open(video_path) as container:
        stream = container.streams.video[0]
        fps = float(stream.average_rate) if stream.average_rate else 24.0
        tb = stream.time_base
        seek_time = max(0.0, start_frame / fps - 0.1)
        container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)
        for frame in container.decode(stream):
            if frame.pts is None:
                continue
            cur = round(float(frame.pts * tb) * fps)
            if cur < start_frame:
                continue
            if cur >= end_frame:
                break
            frames.append(torch.from_numpy(frame.to_ndarray(format="rgb24")).float() / 255.0)
            if len(frames) >= (end_frame - start_frame):
                break
    if not frames:
        raise ValueError("未读取到任何帧")
    return torch.stack(frames, dim=0)


def _read_frames_range_cv2(video_path: str, start_frame: int, end_frame: int) -> torch.Tensor:
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise IOError(f"无法打开视频: {video_path}")
    cap.set(cv2.CAP_PROP_POS_FRAMES, start_frame)
    frames = []
    for _ in range(start_frame, end_frame):
        ret, frame = cap.read()
        if not ret:
            break
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        tensor = torch.from_numpy(frame_rgb.astype(np.float32) / 255.0)
        frames.append(tensor)
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


def split_audio_by_ranges(audio_tensor: torch.Tensor, ranges: list, total_frames: int) -> list:
    """按"片段源区间列表"切分音频（支持重排/修剪后的任意区间，与视频片段一一对应）"""
    if audio_tensor is None:
        return [None] * len(ranges)
    if audio_tensor.dim() == 2:
        audio_tensor = audio_tensor.unsqueeze(0)
    elif audio_tensor.dim() == 1:
        audio_tensor = audio_tensor.unsqueeze(0).unsqueeze(0)
    total_samples = audio_tensor.shape[-1]
    total_frames = max(1, int(total_frames))
    out = []
    for (s, e) in ranges:
        a = int(round(s / total_frames * total_samples))
        b = int(round(e / total_frames * total_samples))
        a = max(0, min(total_samples, a))
        b = max(a, min(total_samples, b))
        out.append(audio_tensor[..., a:b] if b > a else None)
    return out


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


# ========== ★ info 类型（ElementSceneDetection → 下游节点） ==========
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
            # ★ V3 API：声明 hidden 后可在 execute 中用 cls.hidden.unique_id 取节点 id
            return io.Schema(inputs=inputs, hidden=[io.Hidden.unique_id], outputs=outputs, **common)
        except TypeError:
            return io.Schema(inputs=inputs, outputs=outputs, **common)

    @classmethod
    def execute(cls, force_rate=0, subsampling=1, clips_data="{}"):
        try:
            state = json.loads(clips_data) if isinstance(clips_data, str) else (clips_data or {})
        except Exception:
            state = {}

        # node_id：hidden 优先，clips_data._node_id 兜底，统一转 int
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

        # ★ 唯一视频源：时间线中导入的本地文件。
        # 无源时直接在本节点报清晰错误，而不是把 None 传给下游节点引发难懂的崩溃
        if not (local_video_path and os.path.exists(local_video_path)):
            raise RuntimeError(
                "[ESD] No usable video source: import a video in the node UI first. "
                "If imported earlier, the temp file may have been cleaned up — re-import."
            )

        # 只读 header 拿分辨率（不解码画面，本节点执行极轻）
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

        # ★ 解析前端时间线；"平凡时间线"（单段覆盖全片）视为"没有剪辑决定"，
        # 否则勾选了自动分割也永远检测不到入口（前端导入后总是保存整片单段）
        seg_ranges = _parse_ranges(state.get("segments"))
        if len(seg_ranges) == 1 and seg_ranges[0][0] == 0 and seg_ranges[0][1] == max(1, total_frames):
            seg_ranges = []

        if not seg_ranges and not cuts and bool(state.get("auto_detect_exec", False)):
            thr = float(state.get("cut_threshold") or 27.0)
            print(f"[ESD] Auto scene detection on execute: threshold={thr}")
            cuts = detect_scenes_direct(local_video_path, thr)
            print(f"[ESD] Auto-detected {len(cuts)} cuts")
            # ★ 无论检测结果是否为空都覆盖缓存，防止前端兜底拉到过期切点
            if node_id is not None:
                _auto_cuts_cache[node_id] = list(cuts)
            if cuts and node_id is not None:
                try:
                    PromptServer.instance.send_sync("esd_auto_cuts", {"node_id": node_id, "cuts": cuts})
                except Exception as e:
                    print(f"[ESD] websocket cut sync failed (frontend will fall back to HTTP): {e}")
        else:
            # ★ 本轮未做自动检测——清掉旧缓存，防止前端兜底把过期切点套到不一致的时间线上
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
            io.Int.Input("SegNum", default=1, min=1,
                         tooltip="Segment index (1-based, timeline order) — used when clip_select = segnum"),
            io.Combo.Input("clip_select", options=["select clip", "segnum", "first clip", "last clip", "all"],
                           default="select clip",
                           tooltip="Which timeline segment(s) to output"),
        ]
        outputs = [
            io.Image.Output("images"),
            io.Audio.Output("audio"),
            io.Int.Output("frame_count"),
            io.Float.Output("seconds"),
            io.Image.Output("first_image"), 
            io.Image.Output("last_image"),
        ]
        return io.Schema(
            node_id="ElementVideoClip",
            display_name="Element Video Clip",
            category="Element_easy/video",
            description="Outputs images/audio/frame_count/seconds for the selected clip. "
                        "frame_count & seconds follow force_rate/subsampling of the source node.",
            inputs=inputs, outputs=outputs,
        )

    @classmethod
    def execute(cls, info, SegNum=1, clip_select="select clip"):
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
            ranges = list(segments)
        else:
            if mode == "segnum":
                # ★ SegNum 现在是本节点自己的参数；越界时钳制到最后一段
                idx = max(0, min(int(SegNum or 1) - 1, len(segments) - 1))
            elif mode == "first clip":
                idx = 0
            elif mode == "last clip":
                idx = len(segments) - 1
            else:  # select clip：用时间线上选中的片段（未选中则回退第一段）
                sel = []
                for i in (data.get("selected_indices") or []):
                    try:
                        i = int(i)
                        if 0 <= i < len(segments):
                            sel.append(i)
                    except Exception:
                        pass
                idx = sel[0] if sel else 0
            ranges = [segments[idx]]

        # 读取画面（按片段源区间），再按 subsampling 抽帧
        clips = []
        for (s, e) in ranges:
            try:
                t = read_frame_range(video_path, s, e)
            except Exception as err:
                raise RuntimeError(f"[ElementVideoClip] Failed to load segment ({s}-{e} frames): {err}")
            if n > 1:
                t = t[::n]
            clips.append(t)
        images = torch.cat(clips, dim=0) if len(clips) > 1 else clips[0]
        first_image = images[0:1]   # ★ [1,H,W,C]，保持 batch 维
        last_image = images[-1:]    # ★
        frame_count = int(images.shape[0])
        seconds = frame_count / out_fps

        # 音频：整轨解码一次，按片段切分（不随 subsampling 抽帧）
        audio_tensor = None
        sample_rate = 44100
        try:
            with av.open(video_path) as container:
                if container.streams.audio:
                    astream = container.streams.audio[0]
                    audio_data = []
                    for aframe in container.decode(astream):
                        arr = aframe.to_ndarray()
                        if arr.ndim == 1:
                            arr = arr.reshape(1, -1)
                        if arr.shape[0] > 1:
                            arr = np.mean(arr, axis=0)
                        audio_data.append(arr)
                    if audio_data:
                        audio_flat = np.concatenate(audio_data)
                        audio_tensor = torch.from_numpy(audio_flat.astype(np.float32)).unsqueeze(0).unsqueeze(0)
                        sample_rate = int(astream.rate or 44100)
        except Exception as e:
            print(f"[ElementVideoClip] Failed to extract audio: {e}")

        audio_out = None
        if audio_tensor is not None:
            slices = [x for x in split_audio_by_ranges(audio_tensor, ranges, total_frames) if x is not None]
            if slices:
                audio_out = torch.cat(slices, dim=-1) if len(slices) > 1 else slices[0]

        def wrap_audio(tensor):
            if tensor is None:
                return None
            return {"waveform": tensor, "sample_rate": sample_rate}

        return io.NodeOutput(images, wrap_audio(audio_out), frame_count, float(seconds), first_image, last_image)


class ElementVideoInfo(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [_info_input("info", "Connect from Element Scene Detection 'info' output.")]
        outputs = [io.Float.Output("FPS"), io.Int.Output("Width"), io.Int.Output("Height")]
        return io.Schema(
            node_id="ElementVideoInfo",
            display_name="Element Video Info",
            category="Element_easy/video",
            description="Effective output FPS (after force_rate/subsampling) and video size.",
            inputs=inputs, outputs=outputs,
        )

    @classmethod
    def execute(cls, info):
        data = _parse_info(info)
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
@PromptServer.instance.routes.post("/element_scene_detection/upload_video")
async def upload_video_handler(request):
    try:
        data = await request.post()
        file = data.get("video_file")
        if not file:
            return web.json_response({"error": "No file"}, status=400)
        ext = os.path.splitext(file.filename)[1] or ".mp4"
        with tempfile.NamedTemporaryFile(suffix=ext, delete=False) as tmp:
            tmp.write(file.file.read())
            tmp_path = tmp.name
        print(f"[ESD] Uploaded: {tmp_path}")
        info = get_video_info(tmp_path)
        info["file_path"] = tmp_path
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
    # ★ 排查打印——确认前端查询的 nid 与后端缓存键是否一致（定位后可删）
    #print(f"[ESD] auto_cuts 查询 nid={nid} | 缓存键={list(_auto_cuts_cache.keys())} | 命中={len(cuts)}")
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


def _export_clip_with_audio(video_path, start_frame, end_frame, fps, out_path):
    """cv2.VideoWriter 写不出音轨；用 ffmpeg 重编码导出（帧级精确且携带音频）"""
    try:
        fps = float(fps) if fps and fps > 0 else 24.0
        start_t = start_frame / fps
        dur = (end_frame - start_frame) / fps
        subprocess.run([
            "ffmpeg", "-y", "-loglevel", "error",
            "-ss", f"{start_t:.6f}", "-i", video_path,
            "-t", f"{dur:.6f}",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "18", "-pix_fmt", "yuv420p",
            "-c:a", "aac", "-b:a", "192k",
            out_path,
        ], check=True, capture_output=True)
        return os.path.exists(out_path)
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
