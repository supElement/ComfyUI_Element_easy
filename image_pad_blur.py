import os
import json
import time
import random
import uuid
import numpy as np
import torch
import torchvision.transforms.functional as TF
import comfy.model_management
import folder_paths
from PIL import Image
from threading import Lock
from aiohttp import web

try:
    from server import PromptServer
except Exception:
    PromptServer = None

_PREVIEW_CACHE = {}
_PREVIEW_LOCK = Lock()
_PREVIEW_MAX_SIDE = 1280  # 源数据PNG的最大边（仅传输用，不影响布局精度）
_PREVIEW_CACHE_MAX = 32   # 最多缓存的节点数（防内存增长）


def _cache_put(node_id, entry):
    with _PREVIEW_LOCK:
        _PREVIEW_CACHE.pop(node_id, None)  
        _PREVIEW_CACHE[node_id] = entry
        while len(_PREVIEW_CACHE) > _PREVIEW_CACHE_MAX:
            _PREVIEW_CACHE.pop(next(iter(_PREVIEW_CACHE)))


def _snap_to_div(v, d):
    try:
        v, d = int(v), int(d)
    except (TypeError, ValueError):
        return v
    if d <= 1 or v <= 0:
        return v
    return max(d, int(round(v / d)) * d)


def _parse_bool(v):
    if isinstance(v, bool):
        return v
    if isinstance(v, (int, float)):
        return v != 0
    return str(v).strip().lower() in ("true", "1", "on", "yes")


def _parse_edges(raw):
    """feather_edges → (边集合, replace标记)；空=全边（旧兼容），'none'=无边"""
    raw = str(raw or "").lower()
    replace = "replace" in raw
    raw = raw.replace("replace", "")
    if "none" in raw:
        return set(), replace
    edges = set()
    for tok in raw.replace(" ", "").split(","):
        if tok in ("left", "l"):
            edges.add("left")
        elif tok in ("right", "r"):
            edges.add("right")
        elif tok in ("top", "t"):
            edges.add("top")
        elif tok in ("bottom", "b", "bot"):
            edges.add("bottom")
    if not edges:
        edges = {"left", "right", "top", "bottom"}
    return edges, replace


def _parse_color(color_str):
    color_str = color_str.strip().replace(" ", "")
    r, g, b = 0, 0, 0
    if color_str.startswith("#"):
        try:
            hex_code = color_str.lstrip('#')
            if len(hex_code) == 6:
                r = int(hex_code[0:2], 16)
                g = int(hex_code[2:4], 16)
                b = int(hex_code[4:6], 16)
        except ValueError:
            pass
    elif "," in color_str:
        try:
            parts = color_str.split(",")
            if len(parts) >= 3:
                r = int(parts[0])
                g = int(parts[1])
                b = int(parts[2])
        except ValueError:
            pass
    return r / 255.0, g / 255.0, b / 255.0


def _safe_pad(input_tensor, pad, mode, value=0):
    left, right, top, bottom = pad
    if mode in ['constant', 'replicate']:
        return torch.nn.functional.pad(input_tensor, pad, mode=mode, value=value)
    current = input_tensor
    while left > 0 or right > 0:
        max_w = current.shape[-1] - 1
        p_l = min(left, max_w)
        p_r = min(right, max_w)
        current = torch.nn.functional.pad(current, (p_l, p_r, 0, 0), mode=mode)
        left -= p_l
        right -= p_r
    while top > 0 or bottom > 0:
        max_h = current.shape[-2] - 1
        p_t = min(top, max_h)
        p_b = min(bottom, max_h)
        current = torch.nn.functional.pad(current, (0, 0, p_t, p_b), mode=mode)
        top -= p_t
        bottom -= p_b
    return current


def _tensor_to_pil(t):
    t = t.detach().to("cpu", dtype=torch.float32).contiguous()
    arr = (255.0 * t.numpy()).clip(0, 255).astype(np.uint8)
    if arr.ndim == 2:
        return Image.fromarray(arr, "L")
    if arr.shape[-1] == 1:
        return Image.fromarray(arr[..., 0], "L")
    return Image.fromarray(arr[..., :3], "RGB")


def _ensure_source_pngs(entry):
    """把缓存张量降采样并编码成源PNG（每轮执行只做一次，之后直接复用）"""
    if "src_img" in entry:
        return
    img = entry["image"][0:1]      # [1,H,W,C]
    mask = entry["mask"]           # [B,H,W] or None
    H0, W0 = int(img.shape[1]), int(img.shape[2])
    k = min(1.0, _PREVIEW_MAX_SIDE / float(max(H0, W0, 1)))
    if k < 1.0:
        nh = max(1, int(round(H0 * k)))
        nw = max(1, int(round(W0 * k)))
        img_s = TF.resize(img.permute(0, 3, 1, 2), [nh, nw], antialias=True).permute(0, 2, 3, 1)
        if mask is not None:
            mask_s = torch.nn.functional.interpolate(
                mask[0:1].unsqueeze(1), size=(nh, nw),
                mode="bilinear", align_corners=False).squeeze(1).clamp(0.0, 1.0)
        else:
            mask_s = None
    else:
        img_s, mask_s = img, (mask[0:1] if mask is not None else None)

    temp_dir = folder_paths.get_temp_directory()
    os.makedirs(temp_dir, exist_ok=True)
    tag = uuid.uuid4().hex[:8]
    name_i = f"padblur_src_{tag}.png"
    _tensor_to_pil(img_s[0]).save(os.path.join(temp_dir, name_i))
    entry["src_img"] = {"filename": name_i, "subfolder": "", "type": "temp"}
    if mask_s is not None:
        arr = (mask_s[0].cpu().numpy() * 255.0).clip(0, 255).astype(np.uint8)
        name_m = f"padblur_srcm_{tag}.png"
        Image.fromarray(arr, "L").save(os.path.join(temp_dir, name_m))
        entry["src_mask"] = {"filename": name_m, "subfolder": "", "type": "temp"}
    entry["src_w"], entry["src_h"] = W0, H0


def _run_pipeline(img_tensor, user_mask, p, device):
    """
    核心管线（execute 专用；前端交互预览由本地canvas承担）。
    img_tensor: [B,C,H,W] on device（已RGB）
    user_mask:  [B,H,W] on device 或 None
    """
    B, C, H, W = img_tensor.shape

    target_width = _snap_to_div(p["target_width"], p["div"])
    target_height = _snap_to_div(p["target_height"], p["div"])

    # --- scale 派生（唯一权威路径）---
    # scale = 基准尺寸 × zoom。基准 = 源图 fit 进 target（只缩不放），否则 = 源图原尺寸。
    # zoom 来自前端 ui_data（相对比例、永不过期），与执行时的真实输入尺寸相乘。
    # ui_data 缺失/解析失败 → zoom=1:1 → 不缩放（明确语义，无任何静默回退）。
    zw = p.get("zoom_w")
    zh = p.get("zoom_h")
    if not (isinstance(zw, (int, float)) and zw > 0):
        zw = 1.0
    if not (isinstance(zh, (int, float)) and zh > 0):
        zh = 1.0
    bw, bh = W, H
    if target_width > 0 and target_height > 0 and (W > target_width or H > target_height):
        k = min(target_width / W, target_height / H)
        bw = max(1, int(round(W * k)))
        bh = max(1, int(round(H * k)))
    scale_width = max(16, min(8192, int(round(bw * zw))))
    scale_height = max(16, min(8192, int(round(bh * zh))))

    if scale_width != W or scale_height != H:
        img_tensor = TF.resize(img_tensor, [int(scale_height), int(scale_width)], antialias=True)
        B, C, H, W = img_tensor.shape
    if user_mask is not None and (user_mask.shape[-2] != H or user_mask.shape[-1] != W):
        user_mask = torch.nn.functional.interpolate(
            user_mask.unsqueeze(1), size=(H, W),
            mode="bilinear", align_corners=False).squeeze(1)

    pad_mode = p["pad_mode"]
    if pad_mode == "symmetric":
        pad_mode = "reflect"
    if pad_mode not in ("constant", "edge", "reflect", "stretch"):
        pad_mode = "constant"
    alignment = p["alignment"]
    x_offset = p["x_offset"]
    y_offset = p["y_offset"]
    left = p["left"]
    top = p["top"]
    right = p["right"]
    bottom = p["bottom"]
    feathering = p["feathering"]
    content_blur = p["content_blur"]
    edges, edges_replace = _parse_edges(p["feather_edges"])
    replace_active = user_mask is not None and (edges_replace or _parse_bool(p["mask_replace"]))

    # --- Padding ---
    pad_left, pad_right = left, right
    pad_top, pad_bottom = top, bottom
    if target_width > 0:
        diff_w = target_width - W
        if alignment in ["left", "top-left", "bottom-left"]:
            base_left = 0
        elif alignment in ["right", "top-right", "bottom-right"]:
            base_left = diff_w
        else:
            base_left = diff_w // 2
        pad_left = base_left + x_offset
        pad_right = diff_w - pad_left
    if target_height > 0:
        diff_h = target_height - H
        if alignment in ["top", "top-left", "top-right"]:
            base_top = 0
        elif alignment in ["bottom", "bottom-left", "bottom-right"]:
            base_top = diff_h
        else:
            base_top = diff_h // 2
        pad_top = base_top + y_offset
        pad_bottom = diff_h - pad_top

    final_H = H + pad_top + pad_bottom
    final_W = W + pad_left + pad_right
    has_fx = (feathering > 0 and len(edges) > 0) or content_blur > 0 or replace_active
    if pad_left == 0 and pad_right == 0 and pad_top == 0 and pad_bottom == 0 and not has_fx:
        out = img_tensor.permute(0, 2, 3, 1).cpu()
        m_out = user_mask.cpu() if user_mask is not None else torch.zeros((B, H, W), device="cpu")
        return out, m_out

    # --- 隐形边距 ---
    margin = (max(feathering, content_blur) + 32) if has_fx else 0
    rp_l = pad_left + margin
    rp_r = pad_right + margin
    rp_t = pad_top + margin
    rp_b = pad_bottom + margin
    temp_H = H + rp_t + rp_b
    temp_W = W + rp_l + rp_r

    # --- 拼贴（不模糊）---
    if pad_mode == "constant":
        r, g, b = _parse_color(p["background_color"])
        canvas = torch.zeros((B, C, temp_H, temp_W), device=device, dtype=torch.float32)
        canvas[:, 0, :, :] = r
        canvas[:, 1, :, :] = g
        canvas[:, 2, :, :] = b
    elif pad_mode == "stretch":
        canvas = torch.nn.functional.interpolate(
            img_tensor, size=(temp_H, temp_W), mode="bilinear", align_corners=False)
    else:
        texture_mode = "replicate" if pad_mode == "edge" else "reflect"
        canvas = _safe_pad(img_tensor, (rp_l, rp_r, rp_t, rp_b), mode=texture_mode)

    # --- 整体 blur ---
    if content_blur > 0 and pad_mode != "constant":
        k_size = content_blur
        if k_size % 2 == 0:
            k_size += 1
        canvas = TF.gaussian_blur(canvas, k_size, sigma=content_blur / 2.0)

    # --- feather（每边独立1D线性渐变，min合成）---
    if feathering > 0 and len(edges) > 0:
        f = float(feathering)
        ys = torch.arange(H, device=device, dtype=torch.float32)
        xs = torch.arange(W, device=device, dtype=torch.float32)
        alpha = torch.ones((B, 1, H, W), device=device, dtype=torch.float32)
        if "left" in edges:
            alpha = torch.minimum(alpha, (xs / f).clamp(0.0, 1.0).view(1, 1, 1, W))
        if "right" in edges:
            alpha = torch.minimum(alpha, ((W - 1 - xs) / f).clamp(0.0, 1.0).view(1, 1, 1, W))
        if "top" in edges:
            alpha = torch.minimum(alpha, (ys / f).clamp(0.0, 1.0).view(1, 1, H, 1))
        if "bottom" in edges:
            alpha = torch.minimum(alpha, ((H - 1 - ys) / f).clamp(0.0, 1.0).view(1, 1, H, 1))
    else:
        alpha = torch.ones((B, 1, H, W), device=device, dtype=torch.float32)

    if replace_active:
        alpha = torch.minimum(alpha, 1.0 - user_mask.unsqueeze(1))

    # --- 贴图 ---
    y1 = max(0, rp_t)
    y2 = min(temp_H, rp_t + H)
    x1 = max(0, rp_l)
    x2 = min(temp_W, rp_l + W)
    img_y1 = max(0, -rp_t)
    img_y2 = img_y1 + (y2 - y1)
    img_x1 = max(0, -rp_l)
    img_x2 = img_x1 + (x2 - x1)
    if y2 > y1 and x2 > x1:
        region = canvas[:, :, y1:y2, x1:x2]
        img_part = img_tensor[:, :, img_y1:img_y2, img_x1:img_x2]
        a = alpha[:, :, img_y1:img_y2, img_x1:img_x2]
        canvas[:, :, y1:y2, x1:x2] = region * (1.0 - a) + img_part * a

    # --- 输出mask ---
    out_mask = torch.ones((B, 1, temp_H, temp_W), device=device, dtype=torch.float32)
    if y2 > y1 and x2 > x1:
        out_mask[:, :, y1:y2, x1:x2] = 1.0 - alpha[:, :, img_y1:img_y2, img_x1:img_x2]
    final_image = canvas[:, :, margin:margin + final_H, margin:margin + final_W]
    output_mask_3d = out_mask[:, :, margin:margin + final_H, margin:margin + final_W].squeeze(1)

    if user_mask is not None:
        combined = torch.zeros((B, final_H, final_W), device=device, dtype=torch.float32)
        mh, mw = user_mask.shape[-2], user_mask.shape[-1]
        dy1 = max(0, pad_top)
        dx1 = max(0, pad_left)
        dy2 = min(final_H, pad_top + mh)
        dx2 = min(final_W, pad_left + mw)
        sy1 = max(0, -pad_top)
        sx1 = max(0, -pad_left)
        sy2 = sy1 + (dy2 - dy1)
        sx2 = sx1 + (dx2 - dx1)
        if dy2 > dy1 and dx2 > dx1:
            combined[:, dy1:dy2, dx1:dx2] = user_mask[:, sy1:sy2, sx1:sx2]
        output_mask_3d = torch.maximum(output_mask_3d, combined)

    return final_image.permute(0, 2, 3, 1).cpu(), output_mask_3d.cpu()


class ImagePadBlur:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "target_width": ("INT", {"default": 1024, "min": 0, "max": 8192, "step": 1}),
                "target_height": ("INT", {"default": 1024, "min": 0, "max": 8192, "step": 1}),
                "div": ("INT", {"default": 8, "min": 1, "max": 512, "step": 1}),
                "alignment": ([
                    "center", "left", "right", "top", "bottom",
                    "top-left", "top-right", "bottom-left", "bottom-right"
                ],),
                "x_offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "y_offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "left": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "top": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "right": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "bottom": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "feathering": ("INT", {"default": 50, "min": 0, "max": 500, "step": 1}),
                "content_blur": ("INT", {"default": 0, "min": 0, "max": 500, "step": 1}),
                "pad_mode": (["constant", "edge", "reflect", "stretch"],),
                "background_color": ("STRING", {"default": "#000000", "multiline": False}),
                "scale_width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "scale_height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "feather_edges": ("STRING", {"default": "left,top,right,bottom", "multiline": False}),
                "mask_replace": ("BOOLEAN", {"default": False}),
            },
            "optional": {
                "mask": ("MASK",),
                "ui_data": ("STRING", {"default": ""}),
            },
            "hidden": {
                "unique_id": "UNIQUE_ID",
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "execute"
    CATEGORY = "Element_easy/image"
    OUTPUT_NODE = True  

    def execute(self, image, target_width, target_height, div, alignment, x_offset, y_offset,
                left, top, right, bottom, feathering, content_blur, pad_mode, background_color,
                scale_width, scale_height, feather_edges, mask_replace,
                unique_id=None, mask=None, ui_data=None):
        device = comfy.model_management.get_torch_device()

        if image.dim() == 4:
            c_in = image.shape[-1]
            if c_in > 3:
                image = image[..., :3]
            elif c_in == 1:
                image = image.repeat(1, 1, 1, 3)

        if unique_id is not None:
            try:
                _cache_put(str(unique_id), {
                    "image": image.detach().to("cpu", dtype=torch.float32).contiguous(),
                    "mask": (mask.detach().to("cpu", dtype=torch.float32).contiguous()
                             if mask is not None else None),
                })
            except Exception:
                pass

        zoom_w = zoom_h = None
        if ui_data:
            try:
                ud = json.loads(ui_data)
                if isinstance(ud, dict):
                    try:
                        zw = float(ud.get("zoom_w"))
                        zh = float(ud.get("zoom_h"))
                    except (TypeError, ValueError):
                        zw = zh = None
                    if zw is not None and zh is not None and zw > 0 and zh > 0:
                        zoom_w, zoom_h = zw, zh
            except Exception:
                pass

        img_tensor = image.permute(0, 3, 1, 2).to(device)
        user_mask = None
        if mask is not None:
            m = mask.to(device=device, dtype=torch.float32)
            if m.dim() == 2:
                m = m.unsqueeze(0)
            elif m.dim() == 4:
                m = m[:, 0]
            user_mask = m

        params = {
            "target_width": target_width,
            "target_height": target_height,
            "div": div,
            "alignment": alignment,
            "x_offset": x_offset,
            "y_offset": y_offset,
            "left": left,
            "top": top,
            "right": right,
            "bottom": bottom,
            "feathering": feathering,
            "content_blur": content_blur,
            "pad_mode": pad_mode,
            "background_color": background_color,
            "feather_edges": feather_edges,
            "mask_replace": mask_replace,
            "zoom_w": zoom_w,
            "zoom_h": zoom_h,
        }

        final_image, output_mask_3d = _run_pipeline(img_tensor, user_mask, params, device)

        results = []
        try:
            if final_image.shape[0] > 0:
                temp_dir = folder_paths.get_temp_directory()
                os.makedirs(temp_dir, exist_ok=True)
                filename = f"padblur_exec_{int(time.time() * 1000)}_{random.randint(1, 1000000)}.png"
                _tensor_to_pil(final_image[0]).save(os.path.join(temp_dir, filename))
                results.append({"filename": filename, "subfolder": "", "type": "temp",
                                "width": int(final_image.shape[2]),
                                "height": int(final_image.shape[1])})
        except Exception:
            pass

        return {"ui": {"preview_image": results}, "result": (final_image, output_mask_3d)}


if PromptServer is not None and getattr(PromptServer, "instance", None) is not None:
    @PromptServer.instance.routes.post("/element_image_pad_blur/get_source")
    async def padblur_get_source(request):
        """前端拉取源数据：真实输入张量的降采样 image + mask PNG（每轮执行只编码一次）"""
        try:
            data = await request.json()
        except Exception:
            return web.json_response({"error": "invalid json"}, status=400)
        node_id = str(data.get("node_id", ""))
        with _PREVIEW_LOCK:
            entry = _PREVIEW_CACHE.get(node_id)
        if entry is None:
            return web.json_response({"error": "no cached image (run workflow once)"}, status=404)
        try:
            _ensure_source_pngs(entry)
        except Exception as e:
            return web.json_response({"error": str(e)}, status=500)
        return web.json_response({
            "image": entry["src_img"],
            "mask": entry.get("src_mask"),
            "width": entry["src_w"],
            "height": entry["src_h"],
        })


NODE_CLASS_MAPPINGS = {"ImagePadBlur_Element": ImagePadBlur}
NODE_DISPLAY_NAME_MAPPINGS = {"ImagePadBlur_Element": "Image Pad & Blur"}
