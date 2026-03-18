from aiohttp import web
import torch
import torch.nn.functional as F
import json
import numpy as np
from scipy.interpolate import PchipInterpolator
import folder_paths
import os
import random
import time
import uuid
from PIL import Image
from threading import Lock

try:
    from server import PromptServer
except Exception:
    PromptServer = None

try:
    from comfy.utils import ProgressBar
except Exception:
    ProgressBar = None


GLOBAL_IMAGE_CACHE = {}
CACHE_LOCK = Lock()

USE_FP16_ON_CUDA = False


def _get_processing_dtype(device, input_dtype):
    if device.type == "cuda" and USE_FP16_ON_CUDA:
        return torch.float16
    return input_dtype


def _get_processing_device(image, use_gpu=True):
    if not use_gpu:
        return image.device
    if image.device.type != "cpu":
        return image.device
    if torch.cuda.is_available():
        return torch.device("cuda")
    return image.device


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

        # 按 x 排序
        pts = pts[pts[:, 0].argsort()]
        x = pts[:, 0]
        y = pts[:, 1]

        # 去重（PCHIP 要求 x 严格递增）
        x_unique, idx = np.unique(x, return_index=True)
        x = x_unique
        y = y[idx]

        if len(x) < 2:
            return x_eval

        # 补齐端点
        if x[0] > 0:
            x = np.insert(x, 0, 0.0)
            y = np.insert(y, 0, y[0])
        if x[-1] < 1:
            x = np.append(x, 1.0)
            y = np.append(y, y[-1])

        interpolator = PchipInterpolator(x, y)
        y_eval = interpolator(x_eval)
        return np.clip(y_eval, 0.0, 1.0).astype(np.float32)
    except Exception:
        return x_eval


def _tensor_frame_to_pil(t):
    """
    t: [H,W,C], float tensor in [0,1]
    """
    if t.is_cuda:
        torch.cuda.synchronize(t.device)
    t = t.detach().to("cpu", dtype=torch.float32).contiguous()
    arr = (255.0 * t.numpy()).clip(0, 255).astype(np.uint8)

    if arr.ndim == 2:
        return Image.fromarray(arr, mode="L")

    if arr.shape[-1] == 1:
        return Image.fromarray(arr[..., 0], mode="L")
    elif arr.shape[-1] >= 3:
        # Comfy IMAGE 一般是 RGB，这里只取前3通道做预览
        return Image.fromarray(arr[..., :3], mode="RGB")
    else:
        # 异常情况兜底
        return Image.fromarray(np.zeros((arr.shape[0], arr.shape[1], 3), dtype=np.uint8), mode="RGB")


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

    process_device = _get_processing_device(image, use_gpu=use_gpu)
    process_dtype = _get_processing_dtype(process_device, original_dtype)

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
                "image": ("IMAGE",),
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
            "hidden": {
                "unique_id": "UNIQUE_ID"
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "apply_curve"
    CATEGORY = "Element_easy/image"
    OUTPUT_NODE = True

    def apply_curve(self, image, curve_data, saturation, preview_size, frame_index, output_mode, unique_id):
        batch_size = int(image.shape[0])

        with CACHE_LOCK:
            GLOBAL_IMAGE_CACHE[unique_id] = {
                "image": image.detach().to("cpu", dtype=torch.float32).contiguous(),
                "preview_size": int(preview_size),
                "batch_size": batch_size
            }

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
            img_pil = _tensor_frame_to_pil(out_tensor[0])
            filename = f"curve_preview_{int(time.time()*1000)}_{random.randint(1, 1000000)}.png"
            img_pil.save(os.path.join(temp_dir, filename))
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        return {"ui": {"bg_image": results, "batch_size": [batch_size]}, "result": (out_tensor,)}


if PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
    @PromptServer.instance.routes.post("/element_image_curve/live_preview")
    async def live_preview(request):
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "Invalid JSON"}, status=400)

        unique_id = data.get("node_id")
        if not unique_id:
            return web.json_response({"error": "Missing node_id"}, status=400)

        with CACHE_LOCK:
            cache_data = GLOBAL_IMAGE_CACHE.get(unique_id)

        if cache_data is None:
            return web.json_response({"error": "No image cached"}, status=400)

        image = cache_data["image"]
        batch_size = int(cache_data.get("batch_size", 1))
        default_preview_size = int(cache_data.get("preview_size", 512))

        curve_data_str = data.get("curve_data", "{}")
        saturation = float(data.get("saturation", 1.0))
        preview_size = int(data.get("preview_size", default_preview_size))
        frame_index = int(data.get("frame_index", 0))

        idx = max(0, min(frame_index, batch_size - 1)) if batch_size > 0 else 0
        image_frame = image[idx:idx + 1] if batch_size > 0 else image

        out_tensor = compute_curve_logic(
            image_frame,
            curve_data_str,
            saturation,
            preview_mode=True,
            preview_size=preview_size,
            use_gpu=True
        )

        temp_dir = folder_paths.get_temp_directory()
        os.makedirs(temp_dir, exist_ok=True)

        # 关键：每次唯一文件名，避免前端缓存导致首帧黑图
        filename = f"curve_live_{unique_id}_{int(time.time()*1000)}_{uuid.uuid4().hex[:8]}.png"
        filepath = os.path.join(temp_dir, filename)

        img_pil = _tensor_frame_to_pil(out_tensor[0])
        img_pil.save(filepath)

        return web.json_response({
            "filename": filename,
            "subfolder": "",
            "type": "temp"
        })
