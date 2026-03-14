from server import PromptServer
from aiohttp import web
import torch
import json
import numpy as np
from scipy.interpolate import PchipInterpolator
import folder_paths
import os
import random
from PIL import Image

GLOBAL_IMAGE_CACHE = {}

def compute_curve_logic(image, curve_data_str, saturation, preview_mode=False, preview_size=512):
    """
    preview_mode: 为True时，将图像缩放至最长边preview_size
    """
    # 如果是预览模式且图像较大，先缩放
    if preview_mode:
        h, w = image.shape[1], image.shape[2]
        max_side = max(h, w)
        if max_side > preview_size:
            scale = preview_size / max_side
            new_h, new_w = int(h * scale), int(w * scale)
            
            image = torch.nn.functional.interpolate(
                image.permute(0, 3, 1, 2),
                size=(new_h, new_w),
                mode='bilinear',
                align_corners=False
            ).permute(0, 2, 3, 1)
    
    try:
        data = json.loads(curve_data_str)
    except:
        data = {"RGB":[[0.0,0.0],[1.0,1.0]],"R":[[0.0,0.0],[1.0,1.0]],"G":[[0.0,0.0],[1.0,1.0]],"B":[[0.0,0.0],[1.0,1.0]]}
    
    x_eval = np.linspace(0, 1, 256)
    
    def get_lut(points):
        pts = np.array(points)
        if len(pts) < 2:
            return x_eval
        pts = pts[pts[:, 0].argsort()]
        x = pts[:, 0]
        y = pts[:, 1]
        if x[0] > 0:
            x = np.insert(x, 0, 0.0)
            y = np.insert(y, 0, y[0])
        if x[-1] < 1:
            x = np.append(x, 1.0)
            y = np.append(y, y[-1])
        interpolator = PchipInterpolator(x, y)
        y_eval = interpolator(x_eval)
        return np.clip(y_eval, 0.0, 1.0)
    
    lut_rgb = get_lut(data.get("RGB", [[0, 0], [1, 1]]))
    lut_r = get_lut(data.get("R", [[0, 0], [1, 1]]))
    lut_g = get_lut(data.get("G", [[0, 0], [1, 1]]))
    lut_b = get_lut(data.get("B", [[0, 0], [1, 1]]))
    
    final_r = np.clip(np.interp(lut_rgb, x_eval, lut_r), 0, 1)
    final_g = np.clip(np.interp(lut_rgb, x_eval, lut_g), 0, 1)
    final_b = np.clip(np.interp(lut_rgb, x_eval, lut_b), 0, 1)
    
    device = image.device
    lut_tensor = torch.tensor(np.stack([final_r, final_g, final_b]), dtype=image.dtype, device=device)
    
    out_images = []
    for img in image:
        out_img = img.clone()
        idx = (out_img[..., :3] * 255).clamp(0, 255).to(torch.int64)
        
        out_img[..., 0] = lut_tensor[0][idx[..., 0]]
        out_img[..., 1] = lut_tensor[1][idx[..., 1]]
        out_img[..., 2] = lut_tensor[2][idx[..., 2]]
        
        if saturation != 1.0:
            L = 0.299 * out_img[..., 0] + 0.587 * out_img[..., 1] + 0.114 * out_img[..., 2]
            L = L.unsqueeze(-1)
            out_img[..., :3] = L + (out_img[..., :3] - L) * saturation
            out_img[..., :3] = out_img[..., :3].clamp(0.0, 1.0)
            
        out_images.append(out_img)

    return torch.stack(out_images)


class Element_ImageCurve:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "curve_data": ("STRING", {"default": '{"RGB":[[0.0,0.0],[1.0,1.0]],"R":[[0.0,0.0],[1.0,1.0]],"G":[[0.0,0.0],[1.0,1.0]],"B":[[0.0,0.0],[1.0,1.0]]}'}),
                "saturation": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 2.0, "step": 0.01}),
                "preview_size": ("INT", {"default": 512, "min": 256, "max": 4096, "step": 64}),
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

    def apply_curve(self, image, curve_data, saturation, preview_size, unique_id):
        # 缓存图像和预览尺寸
        GLOBAL_IMAGE_CACHE[unique_id] = {
            "image": image.cpu(),
            "preview_size": preview_size
        }
        
        # 主流程：保持原始分辨率
        out_tensor = compute_curve_logic(image, curve_data, saturation, preview_mode=False)
        
        results = []
        temp_dir = folder_paths.get_temp_directory()
        for t in out_tensor:
            img_np = (255.0 * t.cpu().numpy()).clip(0, 255).astype(np.uint8)
            img_pil = Image.fromarray(img_np)
            filename = f"curve_preview_{random.randint(1, 1000000)}.png"
            img_pil.save(os.path.join(temp_dir, filename))
            results.append({"filename": filename, "subfolder": "", "type": "temp"})

        return { "ui": { "bg_image": results }, "result": (out_tensor,) }


@PromptServer.instance.routes.post("/element_image_curve/live_preview")
async def live_preview(request):
    data = await request.json()
    unique_id = data.get("node_id")
    
    if unique_id not in GLOBAL_IMAGE_CACHE:
        return web.json_response({"error": "No image cached"}, status=400)
        
    cache_data = GLOBAL_IMAGE_CACHE[unique_id]
    image = cache_data["image"]
    preview_size = cache_data.get("preview_size", 512)
    
    curve_data_str = data.get("curve_data", "{}")
    saturation = data.get("saturation", 1.0)
    preview_size = data.get("preview_size", preview_size)
    
    # 预览模式：使用用户设置的preview_size
    out_tensor = compute_curve_logic(image, curve_data_str, float(saturation), preview_mode=True, preview_size=preview_size)
    
    temp_dir = folder_paths.get_temp_directory()
    img_np = (255.0 * out_tensor[0].cpu().numpy()).clip(0, 255).astype(np.uint8)
    img_pil = Image.fromarray(img_np)
    
    filename = f"curve_live_{unique_id}.png"
    filepath = os.path.join(temp_dir, filename)
    img_pil.save(filepath)
    
    return web.json_response({
        "filename": filename,
        "subfolder": "",
        "type": "temp"
    })