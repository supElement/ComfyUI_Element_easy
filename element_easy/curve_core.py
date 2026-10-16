# element_easy/curve_core.py
"""曲线节点家族（Element_ImageCurve / HueSat / HueHue / HueBright）的共享核心。

基线实现取自 Element_ImageCurve——该家族中演化最完善的版本：
- 线程安全的节点图像缓存（NodeImageCache，取代各文件里的裸 dict + Lock）
- 预览文件名唯一化（时间戳 + 随机数，避免前端缓存导致的黑图）
- tensor_frame_to_pil 统一张量→PIL 转换
- live 路由的参数校验（Invalid JSON / Missing node_id / No image cached）

Hue 三节点保留原批处理行为（chunk 分块 + 进度条），彼此唯一差异是
APPLY_LUT：把按色相采样出的 LUT 值应用回 HSV 通道的方式。
"""
import json
import os
import time
import uuid

import torch
from PIL import Image

import comfy.utils
import folder_paths
from aiohttp import web

from .device_utils import (
    get_managed_device,
    get_processing_dtype,
    node_image_cache,
)
from .image_utils import tensor_frame_to_pil


# ---------------------------------------------------------------------------
# HSV 转换（与原三份拷贝逐字一致）
# ---------------------------------------------------------------------------

def rgb_to_hsv(image):
    max_val, _ = torch.max(image, dim=-1)
    min_val, _ = torch.min(image, dim=-1)
    delta = max_val - min_val

    h = torch.zeros_like(max_val)
    s = torch.where(max_val > 0, delta / torch.clamp(max_val, min=1e-12), torch.zeros_like(max_val))
    v = max_val

    r, g, b = image[..., 0], image[..., 1], image[..., 2]
    non_zero = delta > 1e-12
    safe_delta = torch.where(non_zero, delta, torch.ones_like(delta))

    h_r = ((g - b) / safe_delta) % 6.0
    h_g = ((b - r) / safe_delta) + 2.0
    h_b = ((r - g) / safe_delta) + 4.0

    h = torch.where((r == max_val) & non_zero, h_r, h)
    h = torch.where((g == max_val) & non_zero, h_g, h)
    h = torch.where((b == max_val) & non_zero, h_b, h)
    h = h / 6.0

    return torch.stack([h, s, v], dim=-1)


def hsv_to_rgb(hsv):
    h, s, v = hsv[..., 0], hsv[..., 1], hsv[..., 2]
    i = torch.floor(h * 6.0)
    f = (h * 6.0) - i
    p = v * (1.0 - s)
    q = v * (1.0 - s * f)
    t = v * (1.0 - s * (1.0 - f))
    i = i % 6

    conditions = [i == 0, i == 1, i == 2, i == 3, i == 4, i == 5]

    rgb = torch.zeros_like(hsv)
    rgb[..., 0] = torch.where(
        conditions[0], v,
        torch.where(conditions[1], q,
            torch.where(conditions[2], p,
                torch.where(conditions[3], p,
                    torch.where(conditions[4], t, v)
                )
            )
        )
    )
    rgb[..., 1] = torch.where(
        conditions[0], t,
        torch.where(conditions[1], v,
            torch.where(conditions[2], v,
                torch.where(conditions[3], q,
                    torch.where(conditions[4], p, p)
                )
            )
        )
    )
    rgb[..., 2] = torch.where(
        conditions[0], p,
        torch.where(conditions[1], p,
            torch.where(conditions[2], t,
                torch.where(conditions[3], v,
                    torch.where(conditions[4], v, q)
                )
            )
        )
    )
    return rgb


# ---------------------------------------------------------------------------
# LUT 与 Hue 处理管线
# ---------------------------------------------------------------------------

def build_lut_tensor(curve_data_str, device, dtype):
    try:
        data = json.loads(curve_data_str)
        lut = data.get("lut", [1.0] * 512)
        if not isinstance(lut, list) or len(lut) < 2:
            lut = [1.0] * 512
    except Exception:
        lut = [1.0] * 512

    return torch.tensor(lut, dtype=dtype, device=device)


def run_hue_pipeline(image, apply_lut, curve_data_str=None, lut_tensor=None,
                     preview_mode=False, preview_size=512):
    """Hue 三节点的通用管线：可选预览降采样 → RGB→HSV → 按色相插值采样 LUT
    → apply_lut（节点各自的数学）→ HSV→RGB。设备与精度由调用方管理。"""
    if preview_mode:
        h_dim, w_dim = image.shape[1], image.shape[2]
        max_side = max(h_dim, w_dim)
        if max_side > preview_size:
            scale = preview_size / max_side
            new_h, new_w = int(h_dim * scale), int(w_dim * scale)
            image = torch.nn.functional.interpolate(
                image.permute(0, 3, 1, 2),
                size=(new_h, new_w),
                mode='bilinear',
                align_corners=False
            ).permute(0, 2, 3, 1)

    if lut_tensor is None:
        lut_tensor = build_lut_tensor(curve_data_str or "{}", image.device, image.dtype)

    hsv_image = rgb_to_hsv(image)
    h, s, v = hsv_image[..., 0], hsv_image[..., 1], hsv_image[..., 2]

    lut_len = lut_tensor.shape[0]
    h_pos = (h % 1.0) * (lut_len - 1)
    idx0 = torch.floor(h_pos).long()
    idx1 = (idx0 + 1) % lut_len
    w = h_pos - idx0.to(h_pos.dtype)

    return apply_lut(h, s, v, idx0, idx1, w, lut_tensor)


# ---------------------------------------------------------------------------
# Hue 节点基类
# ---------------------------------------------------------------------------

class HueCurveNodeBase:
    """Hue 系节点基类：分块批处理 + 进度条 + 预览输出。

    子类需定义：
    - FILE_TAG：预览文件名前缀（同时用于 live 路由注册）
    - APPLY_LUT(h, s, v, idx0, idx1, w, lut_tensor)：节点各自的 LUT 数学，
      返回处理后的 RGB 张量。
    - LIVE_ROUTE：live 预览路由路径
    """

    FILE_TAG = "hue"
    LIVE_ROUTE = None

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "curve_data": ("STRING", {"default": "{}", "multiline": True}),
                "preview_size": ("INT", {"default": 512, "min": 256, "max": 4096, "step": 64}),
                "frame_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "output_mode": ("BOOLEAN", {"default": False, "label": "Output"}),
            },
            "optional": {
                # 曲线调参工具：不接图也应能独立运行（ComfyUI 会对未连接的
                # required 输入报错拒绝执行，这里改为可选 + 黑图兜底）
                "image": ("IMAGE",),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID"
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "apply_curve"
    CATEGORY = "Element_easy/image"
    OUTPUT_NODE = True

    @classmethod
    def compute_logic(cls, image, curve_data_str=None, lut_tensor=None,
                      preview_mode=False, preview_size=512):
        return run_hue_pipeline(
            image, cls.APPLY_LUT,
            curve_data_str=curve_data_str, lut_tensor=lut_tensor,
            preview_mode=preview_mode, preview_size=preview_size,
        )

    def apply_curve(self, image=None, curve_data="{}", preview_size=512, frame_index=0,
                    output_mode=False, unique_id=None):
        # image=None 必须是签名默认值：ComfyUI 对未连接的 optional 输入
        # 是从调用中整个省略该参数（不传 None），无默认值会直接
        # TypeError: missing 1 required positional argument 'image'。
        if image is None:
            # rgthree 语义：未连接输入时节点照常执行但零操作。
            # 返回同形态 dict、result 为 None —— ui 发空消息（与 rgthree
            # Image Comparer 一致）；下游若消费本节点输出需自行处理 None
            # （Element 家族下游的 optional 输入收到 None 会同样优雅跳过，
            #  第三方必需 IMAGE 的节点将把错误定位在其自身）。
            return {"ui": {"bg_image": [], "batch_size": []}, "result": (None,)}
        batch_size = image.shape[0]

        node_image_cache.put(unique_id, {
            "image": image.detach().to("cpu", dtype=torch.float32).contiguous(),
            "preview_size": int(preview_size),
            "batch_size": batch_size
        })

        proc_device = get_managed_device()
        proc_dtype = get_processing_dtype(proc_device, image.dtype)
        out_dtype = image.dtype

        with torch.no_grad():
            if not output_mode:
                idx = max(0, min(frame_index, batch_size - 1))
                frame = image[idx:idx + 1].to(device=proc_device, non_blocking=True)

                lut_tensor = build_lut_tensor(curve_data, proc_device, frame.dtype)
                out_tensor = self.compute_logic(frame, lut_tensor=lut_tensor, preview_mode=False)

                if out_tensor.dtype != out_dtype:
                    out_tensor = out_tensor.to(dtype=out_dtype)
            else:
                pbar = comfy.utils.ProgressBar(batch_size)
                lut_tensor = build_lut_tensor(curve_data, proc_device, proc_dtype)

                chunk_size = 16 if proc_device.type == "cuda" else 2

                out_chunks = []
                for start in range(0, batch_size, chunk_size):
                    end = min(start + chunk_size, batch_size)
                    chunk = image[start:end].to(device=proc_device, non_blocking=True)

                    processed = self.compute_logic(chunk, lut_tensor=lut_tensor, preview_mode=False)
                    if processed.dtype != out_dtype:
                        processed = processed.to(dtype=out_dtype)

                    out_chunks.append(processed)
                    pbar.update(end - start)

                out_tensor = torch.cat(out_chunks, dim=0) if out_chunks else torch.empty_like(image[:0]).to(proc_device)

        results = []
        temp_dir = folder_paths.get_temp_directory()
        if out_tensor.shape[0] > 0:
            img_pil = tensor_frame_to_pil(out_tensor[0])
            filename = f"{self.FILE_TAG}_preview_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.png"
            img_pil.save(os.path.join(temp_dir, filename))
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        return {"ui": {"bg_image": results, "batch_size": [batch_size]}, "result": (out_tensor,)}


# ---------------------------------------------------------------------------
# live 预览路由工厂（Element_ImageCurve 基线：参数校验 + 唯一文件名）
# ---------------------------------------------------------------------------

def register_live_preview_route(route_path, file_tag, compute_fn):
    """注册 POST route_path 的 live 预览接口。

    compute_fn(image_frame_cpu, data: dict, preview_size: int) -> out_tensor
    按 ImageCurve 基线约定，设备与精度管理在 compute_fn 内部完成。
    返回已注册的处理函数；PromptServer 不可用时返回 None（静默跳过）。
    """
    try:
        import server
        routes = server.PromptServer.instance.routes
    except Exception:
        return None

    async def live_preview(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        unique_id = data.get("node_id")
        if not unique_id:
            return web.json_response({"error": "Missing node_id"}, status=400)

        cache_data = node_image_cache.get(unique_id)
        if cache_data is None:
            return web.json_response({"error": "No image cached"}, status=400)

        image = cache_data["image"]
        batch_size = int(cache_data.get("batch_size", 1))
        default_preview_size = int(cache_data.get("preview_size", 512))

        preview_size = int(data.get("preview_size", default_preview_size))
        frame_index = int(data.get("frame_index", 0))

        idx = max(0, min(frame_index, batch_size - 1)) if batch_size > 0 else 0
        image_frame = image[idx:idx + 1] if batch_size > 0 else image

        out_tensor = compute_fn(image_frame, data, preview_size)

        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)

        # 每次唯一文件名，避免前端缓存导致首帧黑图
        filename = f"{file_tag}_live_{unique_id}_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(temp_dir, filename)

        img_pil = tensor_frame_to_pil(out_tensor[0])
        img_pil.save(filepath)

        return web.json_response({
            "filename": filename,
            "subfolder": "",
            "type": "temp"
        })

    return routes.post(route_path)(live_preview)


def make_hue_live_compute(node_cls):
    """为 Hue 系节点构造 live 预览的 compute_fn（设备搬运 + LUT 构建 + 计算）。"""
    def compute_fn(image_frame, data, preview_size):
        curve_data_str = data.get("curve_data", "{}")
        proc_device = get_managed_device()
        with torch.no_grad():
            frame_gpu = image_frame.to(device=proc_device, non_blocking=True)
            lut_tensor = build_lut_tensor(curve_data_str, proc_device, frame_gpu.dtype)
            return node_cls.compute_logic(
                frame_gpu,
                lut_tensor=lut_tensor,
                preview_mode=True,
                preview_size=preview_size
            )
    return compute_fn
