# Element_ImageCurve.py —— RGB 四通道曲线节点
# 共享基建（设备/精度选择、节点缓存、张量→PIL、live 路由）见 element_easy/，
# 本文件只保留 RGB 曲线特有逻辑（CubicSpline 插值、主曲线→分通道映射、饱和度）。
import json
import os
import random
import time

import numpy as np
import torch
import torch.nn.functional as F
from scipy.interpolate import CubicSpline

import folder_paths
from .element_easy.device_utils import get_processing_device, get_processing_dtype, node_image_cache
from .element_easy.curve_core import register_live_preview_route
from .element_easy.image_utils import tensor_frame_to_pil

try:
    from comfy.utils import ProgressBar
except Exception:
    ProgressBar = None


def _safe_json_loads(curve_data_str):
    try:
        data = json.loads(curve_data_str)
        if not isinstance(data, dict):
            raise ValueError("curve_data must be a dict")
        return data
    except Exception:
        return {
            "RGB": [[0.0, 0.0], [1.0, 1.0]],
            "R": [[0.0, 0.0], [1.0, 1.0]],
            "G": [[0.0, 0.0], [1.0, 1.0]],
            "B": [[0.0, 0.0], [1.0, 1.0]],
        }


def _get_lut(points, x_eval):
    try:
        pts = np.array(points, dtype=np.float32)
        if pts.ndim != 2 or pts.shape[1] != 2 or len(pts) < 2:
            return x_eval

        pts = pts[pts[:, 0].argsort()]
        x = pts[:, 0]
        y = pts[:, 1]

        x_unique, idx = np.unique(x, return_index=True)
        x = x_unique
        y = y[idx]

        if len(x) < 2:
            return x_eval

        if x[0] > 0:
            x = np.insert(x, 0, 0.0)
            y = np.insert(y, 0, y[0])
        if x[-1] < 1:
            x = np.append(x, 1.0)
            y = np.append(y, y[-1])

        # bc_type='natural'
        interpolator = CubicSpline(x, y, bc_type='natural')

        y_eval = interpolator(x_eval)
        return np.clip(y_eval, 0.0, 1.0).astype(np.float32)
    except Exception as e:
        print(f"Curve Interpolation Error: {e}")
        return x_eval


@torch.inference_mode()
def compute_curve_logic(
    image,
    curve_data_str,
    saturation,
    preview_mode=False,
    preview_size=512,
    progress_bar=None,
    use_gpu=True
):
    original_device = image.device
    original_dtype = image.dtype

    process_device = get_processing_device(image, use_gpu=use_gpu)
    process_dtype = get_processing_dtype(process_device, original_dtype)

    if image.device != process_device or image.dtype != process_dtype:
        image = image.to(device=process_device, dtype=process_dtype)

    # 预览模式下先缩图，减少延迟
    if preview_mode:
        h, w = int(image.shape[1]), int(image.shape[2])
        max_side = max(h, w)
        preview_size = max(1, int(preview_size))
        if max_side > preview_size:
            scale = preview_size / max_side
            new_h = max(1, int(h * scale))
            new_w = max(1, int(w * scale))
            image = F.interpolate(
                image.permute(0, 3, 1, 2),
                size=(new_h, new_w),
                mode="bilinear",
                align_corners=False
            ).permute(0, 2, 3, 1)

    data = _safe_json_loads(curve_data_str)
    x_eval = np.linspace(0, 1, 256, dtype=np.float32)

    lut_rgb = _get_lut(data.get("RGB", [[0, 0], [1, 1]]), x_eval)
    lut_r = _get_lut(data.get("R", [[0, 0], [1, 1]]), x_eval)
    lut_g = _get_lut(data.get("G", [[0, 0], [1, 1]]), x_eval)
    lut_b = _get_lut(data.get("B", [[0, 0], [1, 1]]), x_eval)

    final_r = np.clip(np.interp(lut_rgb, x_eval, lut_r), 0, 1).astype(np.float32)
    final_g = np.clip(np.interp(lut_rgb, x_eval, lut_g), 0, 1).astype(np.float32)
    final_b = np.clip(np.interp(lut_rgb, x_eval, lut_b), 0, 1).astype(np.float32)

    lut_tensor = torch.from_numpy(np.stack([final_r, final_g, final_b], axis=0)).to(
        device=process_device, dtype=process_dtype
    )

    out_img = image.clone()
    idx = (out_img[..., :3] * 255.0).clamp(0, 255).to(torch.int64)

    out_img[..., 0] = lut_tensor[0][idx[..., 0]]
    out_img[..., 1] = lut_tensor[1][idx[..., 1]]
    out_img[..., 2] = lut_tensor[2][idx[..., 2]]

    if saturation != 1.0:
        L = 0.299 * out_img[..., 0] + 0.587 * out_img[..., 1] + 0.114 * out_img[..., 2]
        L = L.unsqueeze(-1)
        out_img[..., :3] = L + (out_img[..., :3] - L) * saturation
        out_img[..., :3] = out_img[..., :3].clamp(0.0, 1.0)

    out_img = torch.nan_to_num(out_img, nan=0.0, posinf=1.0, neginf=0.0).clamp(0.0, 1.0)

    if progress_bar is not None:
        for _ in range(int(out_img.shape[0])):
            progress_bar.update(1)

    # 关键：这里不要 non_blocking，避免首帧读到未完成数据
    if out_img.device != original_device or out_img.dtype != original_dtype:
        out_img = out_img.to(device=original_device, dtype=original_dtype)

    return out_img


class Element_ImageCurve:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "curve_data": (
                    "STRING",
                    {
                        "default": '{"RGB":[[0.0,0.0],[1.0,1.0]],"R":[[0.0,0.0],[1.0,1.0]],"G":[[0.0,0.0],[1.0,1.0]],"B":[[0.0,0.0],[1.0,1.0]]}'
                    }
                ),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "preview_size": ("INT", {"default": 512, "min": 256, "max": 4096, "step": 64}),
                "frame_index": ("INT", {"default": 0, "min": 0, "max": 9999, "step": 1}),
                "output_mode": ("BOOLEAN", {"default": False, "label": "Output"}),
            },
            "optional": {
                # 曲线调参工具：不接图也应能独立运行（required 未连接会被
                # ComfyUI 拒绝执行，改为可选 + 黑图兜底）
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

    def apply_curve(self, image=None, curve_data=None, saturation=1.0, preview_size=512,
                    frame_index=0, output_mode=False, unique_id=None):
        # image=None 必须是签名默认值：ComfyUI 对未连接的 optional 输入
        # 是从调用中整个省略该参数（不传 None），无默认值会直接
        # TypeError: missing 1 required positional argument 'image'。
        if image is None:
            # rgthree 语义：未连接输入时节点照常执行但零操作。
            # 返回同形态 dict、result 为 None —— ui 发空消息；下游若消费
            # 本节点输出需自行处理 None（Element 家族下游会优雅跳过，
            # 第三方必需 IMAGE 的节点将把错误定位在其自身）。
            return {"ui": {"bg_image": [], "batch_size": []}, "result": (None,)}
        batch_size = int(image.shape[0])

        node_image_cache.put(unique_id, {
            "image": image.detach().to("cpu", dtype=torch.float32).contiguous(),
            "preview_size": int(preview_size),
            "batch_size": batch_size
        })

        if not output_mode:
            idx = max(0, min(int(frame_index), batch_size - 1)) if batch_size > 0 else 0
            image_to_process = image[idx:idx + 1] if batch_size > 0 else image
            progress_bar = None
        else:
            image_to_process = image
            progress_bar = ProgressBar(int(image_to_process.shape[0])) if ProgressBar is not None else None

        out_tensor = compute_curve_logic(
            image_to_process,
            curve_data,
            saturation,
            preview_mode=False,
            progress_bar=progress_bar,
            use_gpu=True
        )

        results = []
        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)

        if out_tensor.shape[0] > 0:
            img_pil = tensor_frame_to_pil(out_tensor[0])
            filename = f"curve_preview_{int(time.time()*1000)}_{random.randint(1, 1000000)}.png"
            img_pil.save(os.path.join(temp_dir, filename))
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        return {"ui": {"bg_image": results, "batch_size": [batch_size]}, "result": (out_tensor,)}


def _image_curve_live_compute(image_frame, data, preview_size):
    curve_data_str = data.get("curve_data", "{}")
    saturation = float(data.get("saturation", 1.0))
    return compute_curve_logic(
        image_frame,
        curve_data_str,
        saturation,
        preview_mode=True,
        preview_size=preview_size,
        use_gpu=True
    )


register_live_preview_route(
    "/element_image_curve/live_preview",
    "curve",
    _image_curve_live_compute,
)
