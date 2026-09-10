# Element_multi_ref.py
# Element Multi REF (拖拽素材槽位面板) + Element ref convert (21+1 端口转换)
import os, json, math, time, hashlib, re, shutil, subprocess, threading, asyncio
import io as _io
import wave as _wave
from collections import OrderedDict
from concurrent.futures import ThreadPoolExecutor   
import numpy as np
import cv2
import torch
import av
import folder_paths
from server import PromptServer
from aiohttp import web
from comfy_api.latest import io

# ================= 常量与缓存 =================
WAVEFORM_POINTS = 1500
MAX_OUT_FRAMES = 1200          # 单视频槽输出帧数硬上限
IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp", ".bmp"}
VID_EXTS = {".mp4", ".mov", ".avi", ".mkv", ".webm", ".m4v"}
AUD_EXTS = {".mp3", ".wav", ".flac", ".ogg", ".oga", ".m4a", ".m4b", ".aac", ".opus",
            ".wma", ".aif", ".aiff", ".aifc", ".mka", ".weba", ".caf"}

_probe_cache = OrderedDict()          
_probe_lock = threading.Lock()
MAX_PROBE_CACHE = 24

_preview_cache = OrderedDict()
_preview_lock = threading.Lock()
MAX_PREVIEW_CACHE = 400
_preview_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="emr-preview")

_audio_media_cache = OrderedDict()
_audio_media_lock = threading.Lock()
MAX_AUDIO_MEDIA_CACHE = 2
_audio_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="emr-audio")

_frames_cache = OrderedDict()          
_frames_lock = threading.Lock()
_frames_bytes = 0
MAX_FRAMES_CACHE_BYTES = 600_000_000

# ================= 媒体探测 =================
def _kind_of(ext: str):
    if ext in IMG_EXTS: return "image"
    if ext in VID_EXTS: return "video"
    if ext in AUD_EXTS: return "audio"
    return None

def _audio_to_waveform(tensor: torch.Tensor, target_points: int = WAVEFORM_POINTS) -> list:
    if tensor is None: return []
    if not isinstance(tensor, torch.Tensor):
        try: tensor = torch.tensor(tensor, dtype=torch.float32)
        except Exception: return []
    tensor = tensor.float()
    if tensor.dim() == 3: tensor = tensor[0]
    if tensor.dim() == 2:
        if tensor.shape[0] == 1 or tensor.shape[1] == 1: tensor = tensor.flatten()
        elif tensor.shape[0] < tensor.shape[1]: tensor = torch.mean(tensor, dim=0)
        else: tensor = torch.mean(tensor, dim=1)
    if tensor.dim() != 1: tensor = tensor.flatten()
    if tensor.shape[0] > target_points:
        import torch.nn.functional as F
        d = F.interpolate(tensor.view(1, 1, -1), size=target_points, mode="linear", align_corners=False)
        peaks = d.squeeze().cpu().tolist()
    else:
        peaks = tensor.cpu().tolist()
    if len(peaks) < target_points:
        idx = np.linspace(0, len(peaks) - 1, target_points)
        peaks = np.interp(idx, np.arange(len(peaks)), peaks).tolist()
    peaks = [abs(v) for v in peaks]
    mx = max(peaks) if peaks else 1.0
    if mx > 0: peaks = [min(1.0, v / mx) for v in peaks]
    return peaks

def _decode_audio_wave(path: str, max_seconds: float = 0.0):
    """整轨解码 → (waveform list, sr, duration)。
    ★ 按 pts 对齐到容器时间轴：开头偏移补静音、流内 pts 空洞补静音，
      保证 波形位置 == 视频画面位置 == 提取音频的播放位置。"""
    with av.open(path) as c:
        astream = next((s for s in c.streams.audio), None)
        if astream is None:
            return [], 44100, 0.0
        sr = int(astream.rate or 44100)
        tb = float(astream.time_base)
        dur = float(astream.duration * astream.time_base) if astream.duration else 0.0
        chunks = []          # (start_sec, mono float32)
        cursor = None
        for fr in c.decode(astream):
            arr = fr.to_ndarray()
            if arr.ndim == 1:
                arr = arr.reshape(1, -1)
            if arr.dtype == np.int16:
                arr = arr.astype(np.float32) / 32768.0        
            elif arr.dtype == np.int32:
                arr = arr.astype(np.float32) / 2147483648.0
            elif arr.dtype == np.uint8:
                arr = (arr.astype(np.float32) - 128.0) / 128.0
            elif arr.dtype != np.float32:
                arr = arr.astype(np.float32)
            if arr.shape[0] > 1:
                arr = np.mean(arr, axis=0)
            mono = arr.reshape(-1)
            pt = float(fr.pts * tb) if fr.pts is not None else None
            start = pt if pt is not None else (cursor if cursor is not None else 0.0)
            if start < 0:                                    
                skip = int(round(-start * sr))
                if skip >= mono.shape[0]:
                    cursor = start + mono.shape[0] / sr
                    continue
                mono = mono[skip:]; start = 0.0
            chunks.append((start, mono))
            cursor = start + mono.shape[0] / sr
            if max_seconds and max_seconds > 0 and cursor >= max_seconds:
                break
        if not chunks:
            return [], sr, dur
        end_t = max(s + m.shape[0] / sr for s, m in chunks)
        total = int(round(end_t * sr))
        if total <= 0:
            return [], sr, dur
        pcm = np.zeros(total, dtype=np.float32)               
        for start, mono in chunks:
            i0 = int(round(start * sr)); i1 = min(total, i0 + mono.shape[0])
            if i1 > i0:
                pcm[i0:i1] = mono[: i1 - i0]
        if max_seconds and max_seconds > 0 and total > int(max_seconds * sr):
            pcm = pcm[: int(max_seconds * sr)]
        return _audio_to_waveform(torch.from_numpy(pcm)), sr, dur

def _decode_audio_wave_ffmpeg(path: str, max_seconds: float = 600.0):
    """PyAV 打不开/解不出音频时的 ffmpeg CLI 兜底（flac、alac、奇特封装等）。"""
    if not shutil.which("ffmpeg"):
        return [], 44100, 0.0
    dur = 0.0
    if shutil.which("ffprobe"):
        try:
            out = subprocess.run(
                ["ffprobe", "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=nw=1:nk=1", path], capture_output=True, timeout=60)
            dur = float(out.stdout.decode(errors="ignore").strip() or 0.0)
        except Exception:
            pass
    args = ["ffmpeg", "-nostdin", "-v", "error"]
    if max_seconds and max_seconds > 0:
        args += ["-t", str(max_seconds)]
    args += ["-i", path, "-vn", "-ac", "1", "-ar", "44100", "-f", "f32le", "-"]
    proc = subprocess.run(args, capture_output=True, timeout=300)
    if proc.returncode != 0 or not proc.stdout:
        print(f"[EMR] ffmpeg audio decode failed: {proc.stderr[:300]!r}")
        return [], 44100, dur
    pcm = np.frombuffer(proc.stdout, dtype=np.float32).copy()
    return _audio_to_waveform(torch.from_numpy(pcm)), 44100, dur


def _probe_media(path: str) -> dict:
    ext = os.path.splitext(path)[1].lower()
    kind = _kind_of(ext)
    if kind is None: raise ValueError(f"unsupported: {ext}")
    if kind == "image":
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None: raise IOError("cannot read image")
        h, w = img.shape[:2]
        return {"kind": "image", "media": {"w": int(w), "h": int(h)}}
    if kind == "video":
        with av.open(path) as c:
            vs = next((s for s in c.streams.video), None)
            if vs is None:
                raise ValueError("no video stream")
            w = int(getattr(vs, "width", 0) or 0); h = int(getattr(vs, "height", 0) or 0)
            fps = float(vs.average_rate) if vs.average_rate else 24.0
            dur = float(vs.duration * vs.time_base) if vs.duration else 0.0
            total = int(vs.frames) if vs.frames else int(round(dur * fps))
            v_start = float(vs.start_time * vs.time_base) if getattr(vs, "start_time", None) is not None else 0.0
            # ★ fps 元数据校验：标称帧率与 帧数/时长 不符时用真实值（否则越到后面越偏）
            if total > 0 and dur > 0.5:
                fps_real = total / dur
                if abs(fps_real - fps) / max(fps, 1e-6) > 0.02:
                    print(f"[EMR] fps mismatch {os.path.basename(path)}: container={fps:.3f} -> real={fps_real:.3f}")
                    fps = fps_real
            has_audio = len(c.streams.audio) > 0
            sr = int(c.streams.audio[0].rate or 44100) if has_audio else 44100
            a_start = a_dur = 0.0
            if has_audio:
                _ast = c.streams.audio[0]
                a_start = float(_ast.start_time * _ast.time_base) if getattr(_ast, "start_time", None) is not None else 0.0
                a_dur = float(_ast.duration * _ast.time_base) if _ast.duration else 0.0
            print(f"[EMR] probe {os.path.basename(path)}: video[start={v_start:.3f}s dur={dur:.3f}s fps={fps:.3f} frames={total}] "
                  f"audio[start={a_start:.3f}s dur={a_dur:.3f}s]")
            wf = []
            if has_audio:
                try:
                    wf, _, _ = _decode_audio_wave(path)
                except Exception as e:
                    print(f"[EMR] video wave err: {e}")
            return {"kind": "video", "media": {"w": w, "h": h, "fps": fps, "total_frames": total,
                                               "duration": dur, "has_audio": has_audio, "sr": sr,
                                               "v_start": v_start, "a_start": a_start, "audio_duration": a_dur},
                    "waveform": wf}

    # audio
    try:
        wf, sr, dur = _decode_audio_wave(path)
    except Exception as e:
        print(f"[EMR] PyAV audio probe failed ({os.path.basename(path)}): {e}")
        wf, sr, dur = [], 44100, 0.0
    if not wf and dur <= 0:                       
        wf, sr, dur = _decode_audio_wave_ffmpeg(path)
        if not wf and dur <= 0:
            raise ValueError(f"cannot decode audio: {os.path.basename(path)} (PyAV & ffmpeg both failed)")
    return {"kind": "audio", "media": {"sr": sr, "duration": dur}, "waveform": wf}


def _probe_media_cached(path: str) -> dict:
    try: mt = os.path.getmtime(path)
    except Exception: mt = 0
    with _probe_lock:
        hit = _probe_cache.get(path)
        if hit and hit[0] == mt:
            _probe_cache.move_to_end(path); return hit[1]
    payload = _probe_media(path)
    with _probe_lock:
        _probe_cache[path] = (mt, payload)
        while len(_probe_cache) > MAX_PROBE_CACHE: _probe_cache.popitem(last=False)
    return payload

# ================= 帧预览（视频帧 / 整图） =================
_AV_LOCK = threading.Lock()
_AV_STATE = {"path": None, "container": None, "stream": None, "fps": 24.0, "last_idx": -1}

def _av_reset_locked():
    if _AV_STATE["container"] is not None:
        try: _AV_STATE["container"].close()
        except Exception: pass
    _AV_STATE.update(path=None, container=None, stream=None, last_idx=-1)

def _decode_frame_bgr(video_path: str, frame_idx: int) -> np.ndarray:
    with _AV_LOCK:
        try:
            if _AV_STATE["path"] != video_path or _AV_STATE["container"] is None:
                _av_reset_locked()
                container = av.open(video_path)
                stream = container.streams.video[0]
                fps = float(stream.average_rate) if stream.average_rate else 24.0
                _AV_STATE.update(path=video_path, container=container, stream=stream, fps=fps, last_idx=-1)
            container, stream = _AV_STATE["container"], _AV_STATE["stream"]
            fps, tb = _AV_STATE["fps"], stream.time_base
            sequential = 0 <= _AV_STATE["last_idx"] < frame_idx <= _AV_STATE["last_idx"] + 24
            if not sequential:
                seek_time = max(0.0, frame_idx / fps - 0.1)
                container.seek(int(seek_time / tb), stream=stream, any_frame=False, backward=True)
                _AV_STATE["last_idx"] = -1
            img = None
            for frame in container.decode(stream):
                if frame.pts is None: continue
                cur = round(float(frame.pts * tb) * fps)
                _AV_STATE["last_idx"] = cur
                if cur >= frame_idx:
                    img = frame.to_ndarray(format="bgr24"); break
            if img is None: raise ValueError(f"Frame {frame_idx} not found")
            return img
        except Exception:
            _av_reset_locked(); raise

def _decode_frame_bgr_fallback(video_path: str, frame_idx: int) -> np.ndarray:
    try:
        with av.open(video_path) as container:
            stream = container.streams.video[0]
            fps = float(stream.average_rate) if stream.average_rate else 24.0
            tb = stream.time_base
            container.seek(int(max(0.0, frame_idx / fps - 0.1) / tb), stream=stream,
                           any_frame=False, backward=True)
            for frame in container.decode(stream):
                if frame.pts is None: continue
                if round(float(frame.pts * tb) * fps) >= frame_idx:
                    return frame.to_ndarray(format="bgr24")
            raise ValueError(f"Frame {frame_idx} not found")
    except Exception:
        cap = cv2.VideoCapture(video_path)
        if not cap.isOpened(): raise IOError(f"无法打开视频: {video_path}")
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if total > 0 and frame_idx >= total: frame_idx = total - 1
        cap.set(cv2.CAP_PROP_POS_FRAMES, frame_idx)
        ret, frame = cap.read(); cap.release()
        if not ret or frame is None: raise ValueError(f"Frame {frame_idx} 读取失败")
        return frame

def _build_preview(path: str, frame_idx: int, size: int,
                   crop=None, overlay: str = None, alpha: bool = False) -> bytes:
    """alpha=True → 返回带透明通道的 PNG（用于笔刷层）；否则 JPEG。
    crop=(x,y,w,h) 先合成 overlay 再裁剪；overlay 约定为整图坐标系。"""
    if alpha:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if img is None: raise IOError("cannot read overlay")
        h, w = img.shape[:2]
        scale = size / max(h, w)
        if scale < 1.0:
            img = cv2.resize(img, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                             interpolation=cv2.INTER_AREA)
        ok, buf = cv2.imencode(".png", img, [int(cv2.IMWRITE_PNG_COMPRESSION), 1])
        if not ok: raise RuntimeError("PNG encode failed")
        return buf.tobytes()
    ext = os.path.splitext(path)[1].lower()
    if _kind_of(ext) == "image" or frame_idx < 0:
        img = cv2.imdecode(np.fromfile(path, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None: raise IOError("cannot read image")
    else:
        total = 0
        try:
            with av.open(path) as c:
                vs = c.streams.video[0]
                fps = float(vs.average_rate) if vs.average_rate else 24.0
                dur = float(vs.duration * vs.time_base) if vs.duration else 0
                total = int(vs.frames) if vs.frames else int(round(dur * fps))
        except Exception: pass
        if total > 0: frame_idx = max(0, min(frame_idx, total - 1))
        try: img = _decode_frame_bgr(path, frame_idx)
        except Exception: img = _decode_frame_bgr_fallback(path, frame_idx)
    if overlay and os.path.exists(overlay):
        ov = cv2.imdecode(np.fromfile(overlay, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if ov is not None:
            H, W = img.shape[:2]
            if ov.shape[:2] != (H, W):
                ov = cv2.resize(ov, (W, H), interpolation=cv2.INTER_NEAREST)
            if ov.ndim == 3 and ov.shape[2] == 4:
                a = ov[:, :, 3:4].astype(np.float32) / 255.0
                img = (ov[:, :, :3].astype(np.float32) * a
                       + img.astype(np.float32) * (1 - a)).astype(np.uint8)
    if crop:
        x, y, w, h = [int(round(float(v))) for v in crop[:4]]
        H, W = img.shape[:2]
        x = max(0, min(x, W - 1)); y = max(0, min(y, H - 1))
        w = max(1, min(w, W - x)); h = max(1, min(h, H - y))
        img = img[y:y + h, x:x + w]
    h, w = img.shape[:2]
    scale = size / max(h, w)
    if scale < 1.0:
        img = cv2.resize(img, (max(1, int(round(w * scale))), max(1, int(round(h * scale)))),
                         interpolation=cv2.INTER_AREA)
    ok, buf = cv2.imencode(".jpg", img, [int(cv2.IMWRITE_JPEG_QUALITY), 85])
    if not ok: raise RuntimeError("JPEG encode failed")
    return buf.tobytes()


def _cache_put(key, body):
    with _preview_lock:
        _preview_cache[key] = body; _preview_cache.move_to_end(key)
        while len(_preview_cache) > MAX_PREVIEW_CACHE: _preview_cache.popitem(last=False)

# ================= 音轨整轨转发 =================
_PREVIEW_SR = 22050  

def _resample_linear(pcm: np.ndarray, src: int, dst: int) -> np.ndarray:
    if src == dst or pcm.size == 0:
        return pcm.astype(np.float32)
    n_out = max(1, int(round(pcm.size * dst / src)))
    idx = np.linspace(0, pcm.size - 1, n_out)
    return np.interp(idx, np.arange(pcm.size), pcm).astype(np.float32)

def _extract_audio_media(video_path: str):
    """★ 与波形/输出切片共用同一套 pts 对齐逻辑：PyAV 整轨重建 WAV。
    放弃 mp3 转码（编码延迟/选轨差异是音画错位的来源之一）。"""
    try:
        with av.open(video_path) as c:
            astream = next((s for s in c.streams.audio), None)
            if astream is None:
                return None
            rate = int(astream.rate or 44100)
            tb = float(astream.time_base)
            chunks, cursor = [], None
            for fr in c.decode(astream):
                arr = fr.to_ndarray()
                if arr.ndim == 1:
                    arr = arr.reshape(1, -1)
                if arr.dtype == np.int16:
                    arr = arr.astype(np.float32) / 32768.0
                elif arr.dtype == np.int32:
                    arr = arr.astype(np.float32) / 2147483648.0
                elif arr.dtype == np.uint8:
                    arr = (arr.astype(np.float32) - 128.0) / 128.0
                elif arr.dtype != np.float32:
                    arr = arr.astype(np.float32)
                if arr.shape[0] > 1:
                    arr = np.mean(arr, axis=0)
                mono = arr.reshape(-1)
                pt = float(fr.pts * tb) if fr.pts is not None else None
                start = pt if pt is not None else (cursor if cursor is not None else 0.0)
                if start < 0:
                    skip = int(round(-start * rate))
                    if skip >= mono.shape[0]:
                        cursor = start + mono.shape[0] / rate
                        continue
                    mono = mono[skip:]; start = 0.0
                chunks.append((start, mono))
                cursor = start + mono.shape[0] / rate
            if not chunks:
                return None
            end_t = max(s + m.shape[0] / rate for s, m in chunks)
            total = int(round(end_t * rate))
            if total <= 0:
                return None
            pcm = np.zeros(total, dtype=np.float32)   
            for start, mono in chunks:
                i0 = int(round(start * rate)); i1 = min(total, i0 + mono.shape[0])
                if i1 > i0:
                    pcm[i0:i1] = mono[: i1 - i0]
            pcm = _resample_linear(pcm, rate, _PREVIEW_SR)
            buf = _io.BytesIO()
            with _wave.open(buf, "wb") as wf:
                wf.setnchannels(1); wf.setsampwidth(2); wf.setframerate(_PREVIEW_SR)
                wf.writeframes((np.clip(pcm, -1.0, 1.0) * 32767.0).astype("<i2").tobytes())
            return ("audio/wav", buf.getvalue())
    except Exception as e:
        print(f"[EMR] pyav preview wav failed: {e}")
    if shutil.which("ffmpeg"):
        try:
            proc = subprocess.run(
                ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", video_path,
                 "-map", "0:a:0", "-vn", "-ac", "1", "-ar", str(_PREVIEW_SR),
                 "-af", "aresample=async=1:first_pts=0",
                 "-c:a", "pcm_s16le", "-f", "wav", "pipe:1"],
                capture_output=True, timeout=300)
            if proc.returncode == 0 and proc.stdout:
                return ("audio/wav", proc.stdout)
        except Exception:
            pass
    return None



# ================= 片段级音频读取 =================
def _read_audio_range(video_path: str, start_frame: int, end_frame: int, fps: float):
    """只解码 [start_frame, end_frame) 的音频。★ 输出长度恒为 (t1-t0)*sr：
    按 pts 写入预分配缓冲（空洞=静音），与视频帧共用同一容器时间轴。"""
    try:
        with av.open(video_path) as container:
            astream = next((s for s in container.streams.audio), None)
            if astream is None:
                return None, 44100
            sr = int(astream.rate or 44100)
            tb = float(astream.time_base)
            fps = float(fps) if fps and fps > 0 else 24.0
            t0, t1 = start_frame / fps, end_frame / fps
            need = max(1, int(round((t1 - t0) * sr)))
            out = np.zeros(need, dtype=np.float32)
            got = False
            try:
                container.seek(max(0, int(t0 / tb)), stream=astream, backward=True)
            except Exception:
                container.seek(0)
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
                if arr.dtype == np.int16:                      
                    arr = arr.astype(np.float32) / 32768.0
                elif arr.dtype == np.int32:
                    arr = arr.astype(np.float32) / 2147483648.0
                elif arr.dtype == np.uint8:
                    arr = (arr.astype(np.float32) - 128.0) / 128.0
                elif arr.dtype != np.float32:
                    arr = arr.astype(np.float32)
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
                s0 = max(0, min(s0, mono.shape[0])); s1 = max(s0, min(s1, mono.shape[0]))
                if s1 <= s0:
                    continue
                i0 = int(round((t_start - t0) * sr)) + s0
                i1 = min(need, i0 + (s1 - s0))
                a = max(0, i0)
                if i1 > a:
                    out[a:i1] = mono[s0 + (a - i0): s0 + (a - i0) + (i1 - a)]
                    got = True
            if not got:
                return torch.zeros((1, 1, need)), sr
            return torch.from_numpy(out).unsqueeze(0).unsqueeze(0), sr
    except Exception as e:
        print(f"[EMR] audio range read failed: {e}")
        return None, 44100


# ================= 视频区间索引解码（含 LRU） =================
def _decode_range(path: str, s: int, e: int) -> dict:
    """解码 [s,e) 全部帧 → {idx: rgb24 uint8 ndarray}。"""
    got = {}
    with av.open(path) as c:
        st = c.streams.video[0]
        fps = float(st.average_rate) if st.average_rate else 24.0
        tb = st.time_base
        try: st.thread_type = "AUTO"
        except Exception: pass
        container_seek = max(0.0, s / fps - 0.1)
        c.seek(int(container_seek / tb), stream=st, any_frame=False, backward=True)
        need = set(range(s, e))
        for fr in c.decode(st):
            if fr.pts is None: continue
            cur = round(float(fr.pts * tb) * fps)
            if cur < s: continue
            if cur > e - 1: break
            if cur in need and cur not in got:
                got[cur] = fr.to_ndarray(format="rgb24")
            if len(got) == len(need): break
    return got

def _decode_range_cached(path: str, s: int, e: int) -> dict:
    key = (path, s, e)
    global _frames_bytes
    with _frames_lock:
        if key in _frames_cache:
            _frames_cache.move_to_end(key); return _frames_cache[key]
    got = _decode_range(path, s, e)
    size = sum(a.nbytes for a in got.values())
    if got and size <= 60_000_000:  
        with _frames_lock:
            _frames_cache[key] = got; _frames_cache.move_to_end(key)
            _frames_bytes += size
            while _frames_bytes > MAX_FRAMES_CACHE_BYTES and len(_frames_cache) > 1:
                _, old = _frames_cache.popitem(last=False)
                _frames_bytes -= sum(a.nbytes for a in old.values())
    return got

# ================= info 类型（EMR_REF） =================
def _make_ref_type():
    try:
        t = io.Custom("EMR_REF")
        if hasattr(t, "Input") and hasattr(t, "Output"): return t
    except Exception: pass
    return None
_EMR_REF = _make_ref_type()

def _ref_input(name="info", tooltip=""):
    if _EMR_REF is not None: return _EMR_REF.Input(name, tooltip=tooltip)
    return io.String.Input(name, default="{}", tooltip=tooltip)

def _ref_output(name="REF_ALL_IN_ONE"):
    if _EMR_REF is not None: return _EMR_REF.Output(name)
    return io.String.Output(name)

def _parse_ref(info) -> dict:
    if isinstance(info, dict): return info
    if isinstance(info, str):
        try:
            v = json.loads(info); return v if isinstance(v, dict) else {}
        except Exception: return {}
    return {}

def _pack_ref(d: dict):
    if _EMR_REF is not None: return d
    try: return json.dumps(d)
    except Exception: return "{}"

# ================= 槽位定义（与 convert 输出端口一一对应） =================
SLOT_ORDER = (
    ["first_frame", "last_frame"]
    + [f"ref_image_{i}" for i in range(9)]
    + [f"ref_video_{i}" for i in range(3)]
    + [f"ref_video_audio_{i}" for i in range(3)]
    + [f"ref_audio_{i}" for i in range(3)]
    + ["drive_audio"]
)
_IMAGE_SLOTS = set(["first_frame", "last_frame"] + [f"ref_image_{i}" for i in range(9)]
                   + [f"ref_video_{i}" for i in range(3)])


def _load_image_slot(mat: dict, edit: dict) -> torch.Tensor:
    paint = edit.get("paint_file")
    if paint and os.path.exists(paint):                 
        img = cv2.imdecode(np.fromfile(paint, dtype=np.uint8), cv2.IMREAD_COLOR)
        if img is None: raise IOError(f"cannot read image: {paint}")
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        ow, oh = int(edit.get("out_w") or 0), int(edit.get("out_h") or 0)
        if ow > 0 and oh > 0 and (ow, oh) != (img.shape[1], img.shape[0]):
            img = cv2.resize(img, (ow, oh),
                interpolation=cv2.INTER_AREA if ow < img.shape[1] else cv2.INTER_CUBIC)
        return torch.from_numpy(img).float().div_(255.0).unsqueeze(0)
    img = cv2.imdecode(np.fromfile(mat["path"], dtype=np.uint8), cv2.IMREAD_COLOR)
    if img is None: raise IOError(f"cannot read image: {mat['path']}")
    h, w = img.shape[:2]
    div = max(1, int(edit.get("div_by") or 32))
    strokes_p = edit.get("strokes_file")
    has_ov = bool(strokes_p and os.path.exists(strokes_p))
    if has_ov:                                          
        ov = cv2.imdecode(np.fromfile(strokes_p, dtype=np.uint8), cv2.IMREAD_UNCHANGED)
        if ov is not None:
            if ov.shape[:2] != (h, w):
                ov = cv2.resize(ov, (w, h), interpolation=cv2.INTER_NEAREST)
            if ov.ndim == 3 and ov.shape[2] == 4:
                a = ov[:, :, 3:4].astype(np.float32) / 255.0
                img = (ov[:, :, :3].astype(np.float32) * a
                       + img.astype(np.float32) * (1 - a)).astype(np.uint8)
    crop = edit.get("crop")
    if crop:
        x, y, cw, chh = [int(round(float(v))) for v in crop[:4]]
        cw -= cw % div; chh -= chh % div
        cw = max(div, min(cw, w)); chh = max(div, min(chh, h))
        x = max(0, min(x, w - cw)); y = max(0, min(y, h - chh))
        img = img[y:y + chh, x:x + cw]
    ow, oh = int(edit.get("out_w") or 0), int(edit.get("out_h") or 0)
    if ow > 0 and oh > 0 and (ow, oh) != (img.shape[1], img.shape[0]):
        img = cv2.resize(img, (ow, oh),
            interpolation=cv2.INTER_AREA if ow < img.shape[1] else cv2.INTER_CUBIC)
    return torch.from_numpy(cv2.cvtColor(img, cv2.COLOR_BGR2RGB)).float().div_(255.0).unsqueeze(0)


def _load_video_slot(mat: dict, edit: dict):
    """★ 帧按最近 pts 落槽；音频复用 _read_audio_range（与波形/试听同一实现）。"""
    import av, torch
    path = mat["path"]; media = mat.get("media") or {}
    src_fps = float(media.get("fps") or 24.0)
    total_f = int(media.get("total_frames") or 0)
    trim = edit.get("trim") or [0, max(1, total_f)]
    s_f, e_f = float(trim[0]), float(trim[1])
    if not (e_f > s_f):
        e_f = s_f + 1
    start_sec, end_sec = s_f / src_fps, e_f / src_fps
    out_fps = float(edit.get("fps") or 0) or src_fps
    ow, oh = int(edit.get("out_w") or 0), int(edit.get("out_h") or 0)

    def collect(do_seek):
        step_t = 1.0 / out_fps
        grid_n = max(1, int(math.ceil((end_sec - start_sec) * out_fps - 1e-6)))  # ★ 自建，不依赖外部 grid
        slots = [None] * grid_n
        with av.open(path) as c:
            vs = c.streams.video[0]; vs.thread_type = "AUTO"; vtb = vs.time_base
            v_st = int(vs.start_time) if getattr(vs, "start_time", None) is not None else 0
            if do_seek:
                try:
                    c.seek(max(0, int((start_sec - 0.5) / vtb)) + v_st, stream=vs, any_frame=False, backward=True)
                except Exception:
                    c.seek(0)
            else:
                c.seek(0)
            for fr in c.decode(vs):
                ft = float(fr.pts * vtb) if fr.pts is not None else None
                if ft is None:
                    continue
                if ft < start_sec - step_t:
                    continue
                if ft >= end_sec + step_t:
                    break
                k = int(round((ft - start_sec) * out_fps))
                if 0 <= k < grid_n and slots[k] is None:
                    img = fr.to_ndarray(format="bgr24")
                    if ow > 0 and oh > 0 and img.shape[1] != ow:
                        img = cv2.resize(img, (ow, oh), interpolation=cv2.INTER_AREA if ow < img.shape[1] else cv2.INTER_CUBIC)
                    slots[k] = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        if all(s is None for s in slots):
            return []
        last = None
        for k in range(grid_n):          
            if slots[k] is None:
                slots[k] = last
            else:
                last = slots[k]
        return slots

    taken = collect(True)
    if not taken:
        taken = collect(False)
    frames = torch.from_numpy(np.stack(taken)).float().div_(255.0) if taken else None
    t, sr = _read_audio_range(path, int(round(s_f)), int(round(e_f)), src_fps)  
    audio = {"waveform": t, "sample_rate": int(sr)}
    return frames, audio


def _load_audio_slot(mat: dict, edit: dict) -> dict:
    media = mat.get("media") or {}
    dur = float(media.get("duration") or 0.0)
    tr = edit.get("trim") or [0.0, dur]
    s = float(tr[0] or 0.0)
    e = float(tr[1]) if (len(tr) > 1 and tr[1]) else dur
    if dur > 0: e = max(s + 1e-3, min(e, dur))
    else: e = max(e, s + 1e-3)
    ref_fps = float(edit.get("ref_fps") or 24.0) or 24.0
    div = int(edit.get("div_by") or 0); a = int(edit.get("a") or 0)
    sf, ef = s * ref_fps, e * ref_fps
    if edit.get("quant") and div > 0:
        n = math.floor((ef - sf - a) / div + 1e-6); n = max(0, n)
        ef = sf + a + n * div
    t, sr = _read_audio_range(mat["path"], int(round(sf)), int(round(ef)), ref_fps)
    if t is None: t = torch.zeros((1, 1, 44100)); sr = 44100
    return {"waveform": t, "sample_rate": sr}

def _video_paired_audio(mat: dict, slot: dict) -> dict:
    media = mat.get("media") or {}
    src_fps = float(media.get("fps") or 24.0)
    total = int(media.get("total_frames") or 0)
    tr = (slot.get("edit") or {}).get("trim") or [0, total]
    s = int(tr[0] or 0); e = int(tr[1] or total)
    t, sr = _read_audio_range(mat["path"], s, e, src_fps)
    if t is None: t = torch.zeros((1, 1, 44100)); sr = 44100
    return {"waveform": t, "sample_rate": sr}

# ================= 节点：ElementMultiRef =================
class ElementMultiRef(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [io.String.Input("refs_data", default="{}", tooltip="Internal UI state (hidden)")]
        outputs = [_ref_output("REF_ALL_IN_ONE")]
        common = dict(
            node_id="ElementMultiRef", display_name="Element Multi REF",
            category="Element_easy",
            description="Multi-reference material slots for MiniMax-H3 style video models. "
                        "Outputs an info bundle consumed by Element ref convert.",
        )
        try: return io.Schema(inputs=inputs, hidden=[io.Hidden.unique_id], outputs=outputs, **common)
        except TypeError: return io.Schema(inputs=inputs, outputs=outputs, **common)

    @classmethod
    def execute(cls, refs_data="{}"):
        try: state = json.loads(refs_data) if isinstance(refs_data, str) else (refs_data or {})
        except Exception: state = {}
        node_id = None
        try: node_id = cls.hidden.unique_id
        except Exception: pass
        if node_id is None: node_id = state.get("_node_id")
        try: node_id = int(node_id)
        except Exception: node_id = None
        materials = state.get("materials") or {}
        slots = state.get("slots") or {}
        missing = [mid for mid, m in materials.items()
                   if not (m.get("path") and os.path.exists(m["path"]))]
        info = {"version": 2, "node_id": node_id, "materials": materials,
                "slots": slots, "missing": missing}
        return io.NodeOutput(_pack_ref(info))

# ================= 节点：ElementRefConvert =================
class ElementRefConvert(io.ComfyNode):
    @classmethod
    def define_schema(cls) -> io.Schema:
        inputs = [
            _ref_input("info", "Connect from Element Multi REF 'REF_ALL_IN_ONE'."),
        ]
        outputs = (
            [io.Image.Output("first_frame"), io.Image.Output("last_frame")]
            + [io.Image.Output(f"ref_image_{i}") for i in range(9)]
            + [io.Image.Output(f"ref_video_{i}") for i in range(3)]
            + [io.Audio.Output(f"ref_video_audio_{i}") for i in range(3)]
            + [io.Audio.Output(f"ref_audio_{i}") for i in range(3)]
            + [io.Audio.Output("drive_audio"), io.String.Output("info")]
        )
        return io.Schema(
            node_id="ElementRefConvert",
            display_name="Element ref convert",
            category="Element_easy",
            description="Convert REF_ALL_IN_ONE into 21 typed outputs. "
                        "Empty slots output black image / silence; 'info' carries per-slot manifest.",
            inputs=inputs,
            outputs=outputs,
        )

    @classmethod
    def execute(cls, info):
        data = _parse_ref(info)
        materials = data.get("materials") or {}
        slots = data.get("slots") or {}

        def slot_val(sid):
            v = slots.get(sid)
            return v if isinstance(v, dict) and v.get("mat") else None

        imgs, auds, manifest, missing_slots = [], [], {}, []
        for sid in SLOT_ORDER:
            slot = slot_val(sid)
            paired = False
            if slot is None and sid.startswith("ref_video_audio_"):
                vs = slot_val(f"ref_video_{sid[-1]}")
                if vs:
                    vm = materials.get(vs.get("mat")) or {}
                    if vs.get("with_audio") and (vm.get("media") or {}).get("has_audio"):
                        slot, paired = vs, True
            entry = {"has": False, "kind": "image" if sid in _IMAGE_SLOTS else "audio"}
            out_img, out_aud = None, None   
            try:
                if slot is None:
                    raise KeyError("empty slot")
                mat = materials.get(slot.get("mat"))
                if not mat or not os.path.exists(mat.get("path") or ""):
                    raise FileNotFoundError("material file missing")
                edit = slot.get("edit") or {}
                if paired:
                    out_aud = _video_paired_audio(mat, slot)
                    entry = {"has": True, "kind": "audio", "paired": True,
                             "seconds": round(out_aud["waveform"].shape[-1] / out_aud["sample_rate"], 3)}
                elif sid in ("first_frame", "last_frame") or sid.startswith("ref_image_"):
                    out_img = _load_image_slot(mat, edit)
                    entry = {"has": True, "kind": "image", "w": int(out_img.shape[2]), "h": int(out_img.shape[1])}
                elif sid.startswith("ref_video_"):
                    vt, _va = _load_video_slot(mat, edit)   
                    if vt is None or not torch.is_tensor(vt) or vt.ndim != 4:
                        raise RuntimeError("no frames decoded")
                    out_img = vt
                    entry = {"has": True, "kind": "video",
                             "frames": int(vt.shape[0]), "w": int(vt.shape[2]), "h": int(vt.shape[1])}
                else:
                    out_aud = _load_audio_slot(mat, edit)
                    entry = {"has": True, "kind": "audio",
                             "seconds": round(out_aud["waveform"].shape[-1] / out_aud["sample_rate"], 3)}
            except Exception as ex:
                print(f"[ElementRefConvert] slot '{sid}' empty/failed ({ex}) → placeholder")
                missing_slots.append(sid)
                if sid in _IMAGE_SLOTS:
                    out_img = torch.zeros((1, 64, 64, 3))
                else:
                    out_aud = {"waveform": torch.zeros((1, 1, 44100)), "sample_rate": 44100}
            if out_img is not None:
                imgs.append(out_img)
            if out_aud is not None:
                auds.append(out_aud)
            manifest[sid] = entry

        info_out = json.dumps({"version": 1, "producer": "ElementRefConvert",
                               "slots": manifest, "missing": missing_slots})
        return io.NodeOutput(*imgs, *auds, info_out)


NODE_CLASS_MAPPINGS = {"ElementMultiRef": ElementMultiRef, "ElementRefConvert": ElementRefConvert}
NODE_DISPLAY_NAME_MAPPINGS = {"ElementMultiRef": "Element Multi REF",
                              "ElementRefConvert": "Element ref convert"}

# ================= API 路由 =================
def _safe_media_name(filename: str) -> str:
    base = os.path.basename((filename or "").strip()) or "media"
    stem, ext = os.path.splitext(base)
    stem = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]', "_", stem).strip() or "media"
    ext = re.sub(r'[\\/:*?"<>|\x00-\x1f\r\n\t]', "", ext).lower()
    return stem + ext

def _emr_input_dir():
    d = os.path.join(folder_paths.get_input_directory(), "element_multi_ref")
    os.makedirs(d, exist_ok=True)
    return d

@PromptServer.instance.routes.post("/element_multi_ref/upload")
async def emr_upload_handler(request):
    try:
        data = await request.post()
        file = data.get("file")
        if not file: return web.json_response({"error": "No file"}, status=400)
        base = _safe_media_name(file.filename)
        ext = os.path.splitext(base)[1].lower()
        kind = _kind_of(ext)
        if kind is None:
            return web.json_response({"error": f"unsupported type: {ext}"}, status=400)
        d = _emr_input_dir()
        part = os.path.join(d, f".upload.{os.getpid()}.{time.time_ns()}.part")
        h = hashlib.sha256()
        try:
            with open(part, "wb") as out:
                while True:
                    block = file.file.read(1 << 20)
                    if not block: break
                    out.write(block); h.update(block)
            digest = h.hexdigest()
            idx_path = os.path.join(d, "_index.json")
            index = {}
            try:
                with open(idx_path, "r", encoding="utf-8") as f: index = json.load(f)
            except Exception: index = {}
            prev = index.get(digest)
            if prev and os.path.exists(os.path.join(d, prev)):
                target = os.path.join(d, prev)
                try: os.remove(part)
                except Exception: pass
            else:
                target = os.path.join(d, base)
                if os.path.exists(target):
                    stem, e2 = os.path.splitext(base); i = 1
                    while os.path.exists(os.path.join(d, f"{stem}_{i}{e2}")): i += 1
                    target = os.path.join(d, f"{stem}_{i}{e2}")
                os.replace(part, target)
                index[digest] = os.path.basename(target)
                with open(idx_path, "w", encoding="utf-8") as f: json.dump(index, f)
        except Exception:
            try: os.remove(part)
            except Exception: pass
            raise
        payload = _probe_media_cached(target)
        payload["path"] = target
        return web.json_response(payload)
    except Exception as e:
        print(f"[EMR] Upload error: {e}")
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/element_multi_ref/media_info")
async def emr_media_info_handler(request):
    try:
        p = request.rel_url.query.get("p", "")
        if not p or not os.path.exists(p):
            return web.json_response({"error": "not found"}, status=404)
        payload = _probe_media_cached(p); payload["path"] = p
        return web.json_response(payload)
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.post("/element_multi_ref/save_paint")
async def emr_save_paint_handler(request):
    try:
        data = await request.post()
        file = data.get("paint_file")
        if not file: return web.json_response({"error": "No file"}, status=400)
        d = os.path.join(folder_paths.get_output_directory(), "element_multi_ref", "paint")
        os.makedirs(d, exist_ok=True)
        name = f"paint_{int(time.time() * 1000)}_{os.getpid() % 10000}.png"
        target = os.path.join(d, name)
        with open(target, "wb") as out:
            while True:
                block = file.file.read(1 << 20)
                if not block: break
                out.write(block)
        return web.json_response({"path": target})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

def _detect_cuts(path: str, threshold: float = 40.0, sample_per_sec: float = 4.0) -> list:
    try:                                                # ① PySceneDetect ContentDetector
        from scenedetect import open_video, SceneManager, ContentDetector
        video = open_video(path)
        sm = SceneManager()
        sm.add_detector(ContentDetector(threshold=float(threshold)))
        sm.detect_scenes(video, show_progress=False)
        cuts = [int(round(s[0].get_frames())) for s in sm.get_scene_list()]
        cuts = sorted({c for c in cuts if c > 0})
        if cuts: return cuts
    except Exception as e:
        print(f"[EMR] scenedetect unavailable, fallback: {e}")
    try:                                                # ② 回退：自写 HSV 差分
        with av.open(path) as c:
            vs = c.streams.video[0]
            fps = float(vs.average_rate) if vs.average_rate else 24.0
            tb = vs.time_base
            step = max(1, int(round(fps / max(0.5, sample_per_sec))))
            prev = None; cuts = []; idx = 0
            c.seek(0, stream=vs, any_frame=False, backward=True)
            for fr in c.decode(vs):
                if fr.pts is None: continue
                cur = round(float(fr.pts * tb) * fps)
                if idx % step == 0:
                    small = cv2.resize(fr.to_ndarray(format="bgr24"), (64, 36))
                    hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)
                    hist = cv2.calcHist([hsv], [0, 1], None, [32, 32], [0, 180, 0, 256])
                    cv2.normalize(hist, hist)
                    if prev is not None:
                        d = float(cv2.compareHist(prev, hist, cv2.HISTCMP_CORREL))
                        if d < 1.0 - threshold / 100.0 and cur > 0: cuts.append(cur)
                    prev = hist
                idx += 1
        return sorted(set(cuts))
    except Exception as e:
        print(f"[EMR] detect_cuts error: {e}")
        return []

@PromptServer.instance.routes.get("/element_multi_ref/detect_cuts")
async def emr_detect_cuts_handler(request):
    try:
        p = request.rel_url.query.get("p", "")
        thr = float(request.rel_url.query.get("threshold", "28"))
        if not p or not os.path.exists(p):
            return web.json_response({"error": "not found"}, status=404)
        return web.json_response({"cuts": _detect_cuts(p, threshold=thr)})
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)

@PromptServer.instance.routes.get("/emr/preview")
async def emr_preview_handler(request):
    try:
        q = request.rel_url.query
        p = q.get("p", "")
        try:
            f = int(float(q.get("f", "-1")))                     
            s = max(32, min(4096, int(float(q.get("s", "192")))))
        except ValueError:
            return web.Response(status=400,
                text=f"bad params: f={q.get('f')!r} s={q.get('s')!r}")
        crop = None
        if q.get("crop"):
            try: crop = [float(v) for v in q.get("crop").split(",")]
            except ValueError: crop = None
        overlay = q.get("strokes") or None
        alpha = q.get("alpha") == "1"
        if not p or not os.path.exists(p):
            return web.Response(status=404, text=f"not found: {p}")
        key = (p, f, s, tuple(crop) if crop else None, overlay, alpha)
        with _preview_lock:
            body = _preview_cache.get(key)
            if body is not None: _preview_cache.move_to_end(key)
        if body is None:
            loop = asyncio.get_running_loop()
            body = await loop.run_in_executor(_preview_executor,
                _build_preview, p, f, s, crop, overlay, alpha)
            _cache_put(key, body)
        ctype = "image/png" if alpha else "image/jpeg"
        return web.Response(body=body, content_type=ctype,
                            headers={"Cache-Control": "private, max-age=300"})
    except Exception as e:
        import traceback; traceback.print_exc()                  
        return web.Response(status=500, text=str(e))


@PromptServer.instance.routes.get("/emr/audio")
async def emr_audio_handler(request):
    try:
        p = request.rel_url.query.get("p", "")
        if not p or not os.path.exists(p): return web.Response(status=404, text="not found")
        hit, cached = None, False
        with _audio_media_lock:
            if p in _audio_media_cache:
                hit = _audio_media_cache[p]; _audio_media_cache.move_to_end(p); cached = True
        if not cached:
            hit = await asyncio.get_running_loop().run_in_executor(_audio_executor, _extract_audio_media, p)
            with _audio_media_lock:
                _audio_media_cache[p] = hit; _audio_media_cache.move_to_end(p)
                while len(_audio_media_cache) > MAX_AUDIO_MEDIA_CACHE:
                    _audio_media_cache.popitem(last=False)
        if hit is None: return web.Response(status=404, text="no audio stream")
        ctype, body = hit
        headers = {"Accept-Ranges": "bytes", "Cache-Control": "private, max-age=3600"}
        rng = request.headers.get("Range", "")
        if rng.startswith("bytes=") and body:
            total = len(body)
            try:
                spec = rng[6:].split(",")[0].strip()
                a_s, _, b_s = spec.partition("-")
                if not a_s and b_s: a, b = max(0, total - int(b_s)), total - 1
                else:
                    a = int(a_s) if a_s else 0
                    b = int(b_s) if b_s else total - 1
                b = min(b, total - 1)
                if a > b or a >= total:
                    return web.Response(status=416, headers={"Content-Range": f"bytes */{total}"})
                headers["Content-Range"] = f"bytes {a}-{b}/{total}"
                return web.Response(status=206, body=body[a:b + 1], content_type=ctype, headers=headers)
            except ValueError: pass
        return web.Response(body=body, content_type=ctype, headers=headers)
    except Exception as e:
        return web.Response(status=500, text=str(e))
