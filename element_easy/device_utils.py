# element_easy/device_utils.py
"""设备 / 精度选择与节点图像缓存。

原先这段逻辑在 Element_HueSat / Element_HueHue / Element_HueBright /
Element_ImageCurve 等文件中各复制了一份，现统一收敛到此处。
"""
import threading
from collections import OrderedDict

import torch

try:
    import comfy.model_management as mm
except Exception:
    mm = None

# CUDA FP16 加速否？
USE_FP16_ON_CUDA = False


def get_managed_device():
    """ComfyUI 管理的主设备（Hue 系节点原 _get_processing_device 的语义）。"""
    try:
        return mm.get_torch_device()
    except Exception:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def get_processing_device(image, use_gpu=True):
    """跟随输入图像的设备（Element_ImageCurve 原 _get_processing_device 的语义，
    本共享库以该实现为基线）。"""
    if not use_gpu:
        return image.device
    if image.device.type != "cpu":
        return image.device
    if torch.cuda.is_available():
        return torch.device("cuda")
    return image.device


def get_processing_dtype(device, input_dtype):
    if device.type == "cuda" and USE_FP16_ON_CUDA:
        return torch.float16
    return input_dtype


class NodeImageCache:
    """按 unique_id 缓存节点最近一次的输入图像，供 live 预览接口使用。

    原各模块使用独立的裸 dict（无淘汰、无锁，存在内存无限增长与并发读写风险），
    这里统一为带锁 LRU。node id 在同一工作流内唯一，跨节点类型共享一份缓存是安全的。
    """

    def __init__(self, max_entries: int = 128):
        self._lock = threading.Lock()
        self._cache = OrderedDict()
        self._max_entries = max_entries

    def put(self, node_id, entry):
        with self._lock:
            self._cache.pop(node_id, None)
            self._cache[node_id] = entry
            while len(self._cache) > self._max_entries:
                self._cache.popitem(last=False)

    def get(self, node_id):
        with self._lock:
            return self._cache.get(node_id)

    def pop(self, node_id):
        with self._lock:
            return self._cache.pop(node_id, None)


node_image_cache = NodeImageCache()
