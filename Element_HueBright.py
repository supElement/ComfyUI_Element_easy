import torch
import json
import os
import folder_paths
import server
from aiohttp import web
import uuid
from PIL import Image
import numpy as np
import comfy.utils
import comfy.model_management as mm

GLOBAL_IMAGE_CACHE = {}

# CUDA FP16 加速否？
USE_FP16_ON_CUDA = False


def _get_processing_device():
    try:
        return mm.get_torch_device()
    except Exception:
        return torch.device("cuda" if torch.cuda.is_available() else "cpu")


def _get_processing_dtype(device, input_dtype):
    if device.type == "cuda" and USE_FP16_ON_CUDA:
        return torch.float16
    return input_dtype


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


def _build_lut_tensor(curve_data_str, device, dtype):
    try:
        data = json.loads(curve_data_str)
        lut = data.get("lut", [1.0] * 512)
        if not isinstance(lut, list) or len(lut) < 2:
            lut = [1.0] * 512
    except Exception:
        lut = [1.0] * 512

    return torch.tensor(lut, dtype=dtype, device=device)


def compute_HueBright_logic(image, curve_data_str=None, lut_tensor=None, preview_mode=False, preview_size=512):
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
        lut_tensor = _build_lut_tensor(curve_data_str or "{}", image.device, image.dtype)

    hsv_image = rgb_to_hsv(image)
    h, s, v = hsv_image[..., 0], hsv_image[..., 1], hsv_image[..., 2]

    lut_len = lut_tensor.shape[0]
    h_pos = (h % 1.0) * (lut_len - 1)
    idx0 = torch.floor(h_pos).long()
    idx1 = (idx0 + 1) % lut_len
    w = h_pos - idx0.to(h_pos.dtype)

    w = w * w * (3.0 - 2.0 * w)
    
    bright_val = lut_tensor[idx0] * (1.0 - w) + lut_tensor[idx1] * w
    bright_val = torch.clamp(bright_val, min=1e-5)
    
    is_dark = bright_val < 1.0

    v_dark = v * bright_val
    
    gamma_power = 1.0 / bright_val
    v_bright = torch.pow(v + 1e-7, gamma_power)
    
    adjusted_v = torch.where(is_dark, v_dark, v_bright)
    
    # 引入饱和度 (S) 权重遮罩
    # 灰度图的 s=0，所以调整强度必须为 0；色彩越纯，调整越强。
    new_v = v + s * (adjusted_v - v)
    
    new_v = torch.clamp(new_v, 0.0, 1.0)
    
    new_hsv = torch.stack([h, s, new_v], dim=-1)
    return hsv_to_rgb(new_hsv)


class ElementHueBright:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "curve_data": ("STRING", {"default": "{}", "multiline": True}),
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

    def apply_curve(self, image, curve_data, preview_size, frame_index, output_mode, unique_id):
        batch_size = image.shape[0]

        GLOBAL_IMAGE_CACHE[unique_id] = {
            "image": image.cpu(),
            "preview_size": preview_size,
            "batch_size": batch_size
        }

        proc_device = _get_processing_device()
        proc_dtype = _get_processing_dtype(proc_device, image.dtype)
        out_dtype = image.dtype

        with torch.no_grad():
            if not output_mode:
                idx = max(0, min(frame_index, batch_size - 1))
                frame = image[idx:idx + 1].to(device=proc_device, non_blocking=True)

                lut_tensor = _build_lut_tensor(curve_data, proc_device, frame.dtype)
                out_tensor = compute_HueBright_logic(frame, lut_tensor=lut_tensor, preview_mode=False)

                if out_tensor.dtype != out_dtype:
                    out_tensor = out_tensor.to(dtype=out_dtype)
            else:
                pbar = comfy.utils.ProgressBar(batch_size)
                lut_tensor = _build_lut_tensor(curve_data, proc_device, proc_dtype)

                chunk_size = 16 if proc_device.type == "cuda" else 2

                out_chunks = []
                for start in range(0, batch_size, chunk_size):
                    end = min(start + chunk_size, batch_size)
                    chunk = image[start:end].to(device=proc_device, non_blocking=True)

                    processed = compute_HueBright_logic(chunk, lut_tensor=lut_tensor, preview_mode=False)
                    if processed.dtype != out_dtype:
                        processed = processed.to(dtype=out_dtype)

                    out_chunks.append(processed)
                    pbar.update(end - start)

                out_tensor = torch.cat(out_chunks, dim=0) if out_chunks else torch.empty_like(image[:0]).to(proc_device)

        results = []
        temp_dir = folder_paths.get_temp_directory()
        if out_tensor.shape[0] > 0:
            t = out_tensor[0].detach().to("cpu", dtype=torch.float32)
            img_np = (255.0 * t.numpy()).clip(0, 255).astype(np.uint8)
            img_pil = Image.fromarray(img_np)
            filename = f"huebright_preview_{uuid.uuid4().hex[:8]}.png"
            img_pil.save(os.path.join(temp_dir, filename))
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        return {"ui": {"bg_image": results, "batch_size": [batch_size]}, "result": (out_tensor,)}


@server.PromptServer.instance.routes.post("/element_huebright/live_preview")
async def huebright_live_preview(request):
    try:
        data = await request.json()
        unique_id = data.get("node_id")

        if unique_id not in GLOBAL_IMAGE_CACHE:
            return web.json_response({"error": "No image cached"}, status=400)

        cache_data = GLOBAL_IMAGE_CACHE[unique_id]
        image = cache_data["image"]  # CPU cache
        batch_size = cache_data.get("batch_size", 1)

        curve_data_str = data.get("curve_data", "{}")
        preview_size = data.get("preview_size", cache_data.get("preview_size", 512))
        frame_index = data.get("frame_index", 0)

        idx = max(0, min(frame_index, batch_size - 1))
        image_frame = image[idx:idx + 1]

        proc_device = _get_processing_device()
        proc_dtype = _get_processing_dtype(proc_device, image_frame.dtype)

        with torch.no_grad():
            frame_gpu = image_frame.to(device=proc_device, non_blocking=True)
            lut_tensor = _build_lut_tensor(curve_data_str, proc_device, frame_gpu.dtype)

            out_tensor = compute_HueBright_logic(
                frame_gpu,
                lut_tensor=lut_tensor,
                preview_mode=True,
                preview_size=preview_size
            )

        temp_dir = folder_paths.get_temp_directory()
        img_np = (255.0 * out_tensor[0].detach().to("cpu", dtype=torch.float32).numpy()).clip(0, 255).astype(np.uint8)
        img_pil = Image.fromarray(img_np)

        filename = f"huebright_live_{unique_id}.png"
        filepath = os.path.join(temp_dir, filename)
        img_pil.save(filepath)

        return web.json_response({
            "filename": filename,
            "subfolder": "",
            "type": "temp"
        })
    except Exception as e:
        return web.json_response({"error": str(e)}, status=500)
