# element_easy/video_io.py
"""视频/音频解码与节点信息传递的共享实现。

收敛 Element_scene_detection 与 Element_multi_ref 之间逐字复制的基建
（以 scene_detection 的较新版本为基线——其 AV 解码含 thread_type="AUTO"
多线程优化、顺序解码窗口常量化）：

- AVSequentialDecoder：常驻 AV 容器的 BGR 快速解码 + 独立 open 回退 + cv2 兜底
- lru_put：带锁 OrderedDict LRU 写入
- audio_to_waveform：音轨张量 → 波形采样列表
- TypedInfoIO：comfy_api 自定义类型工厂（ESD_INFO / EMR_REF 同构），
  旧版 API 自动回退 STRING(JSON)

注意：_extract_audio_media（ffmpeg→mp3 vs PyAV→WAV）在两个文件间是有意
分叉（multi_ref 为修音画错位改为 PyAV 整轨 WAV），未收敛，见各自文件。
"""
import json
import threading
from collections import OrderedDict

import numpy as np
import torch
import torch.nn.functional as F

try:
    import av
except Exception:
    av = None
try:
    import cv2
except Exception:
    cv2 = None


# ---------------------------------------------------------------------------
# 常驻 AV 容器顺序解码
# ---------------------------------------------------------------------------

_AV_SEQUENTIAL_WINDOW = 24

_av_lock = threading.Lock()
_av_state = {"path": None, "container": None, "stream": None, "fps": 24.0, "last_idx": -1}


def _av_reset_locked():
    if _av_state["container"] is not None:
        try:
            _av_state["container"].close()
        except Exception:
            pass
    _av_state.update(path=None, container=None, stream=None, last_idx=-1)


def decode_frame_bgr(video_path: str, frame_idx: int) -> np.ndarray:
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
                try:
                    stream.thread_type = "AUTO"
                except Exception:
                    pass
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
                idx = round(float(frame.pts * tb) * fps)
                _av_state["last_idx"] = idx
                if idx >= frame_idx:
                    img = frame.to_ndarray(format="bgr24")
                    break
            if img is None:
                raise ValueError(f"Frame {frame_idx} not found")
            return img
        except Exception:
            _av_reset_locked()
            raise


def decode_frame_bgr_fallback(video_path: str, frame_idx: int) -> np.ndarray:
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


# ---------------------------------------------------------------------------
# 带锁 LRU
# ---------------------------------------------------------------------------

def lru_put(cache: OrderedDict, lock: threading.Lock, key, body, max_entries: int):
    with lock:
        cache[key] = body
        cache.move_to_end(key)
        while len(cache) > max_entries:
            cache.popitem(last=False)


# ---------------------------------------------------------------------------
# 音频波形
# ---------------------------------------------------------------------------

def audio_to_waveform(audio_tensor: torch.Tensor, target_points: int) -> list:
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
        idx = np.linspace(0, len(peaks) - 1, target_points)
        peaks = np.interp(idx, np.arange(len(peaks)), peaks).tolist()
    peaks = [abs(v) for v in peaks]
    mx = max(peaks) if peaks else 1.0
    if mx > 0:
        peaks = [min(1.0, v / mx) for v in peaks]
    return peaks


# ---------------------------------------------------------------------------
# comfy_api 自定义类型工厂（ESD_INFO / EMR_REF 同构）
# ---------------------------------------------------------------------------

class TypedInfoIO:
    """info/ref 跨节点传递的自定义类型封装。

    优先 io.Custom(type_name)（新版 comfy API 的结构化传递）；不可用时
    回退 STRING(JSON)（旧版 API），parse/pack 行为对调用方透明。
    """

    def __init__(self, type_name: str, default_json: str = "{}"):
        self.type_name = type_name
        self.default_json = default_json
        self.custom_type = None
        try:
            from comfy_api.latest import io as _io
            self.io = _io
            t = _io.Custom(type_name)
            if hasattr(t, "Input") and hasattr(t, "Output"):
                self.custom_type = t
        except Exception:
            self.io = None

    def input(self, name="info", tooltip=""):
        if self.custom_type is not None:
            return self.custom_type.Input(name, tooltip=tooltip)
        return self.io.String.Input(name, default=self.default_json, tooltip=tooltip)

    def output(self, name="info"):
        if self.custom_type is not None:
            return self.custom_type.Output(name)
        return self.io.String.Output(name)

    def parse(self, info) -> dict:
        if isinstance(info, dict):
            return info
        if isinstance(info, str):
            try:
                v = json.loads(info)
                return v if isinstance(v, dict) else {}
            except Exception:
                return {}
        return {}

    def pack(self, d: dict):
        if self.custom_type is not None:
            return d
        try:
            return json.dumps(d)
        except Exception:
            return self.default_json
