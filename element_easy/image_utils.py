# element_easy/image_utils.py
"""张量 ↔ 图像的通用转换与颜色/文件扫描工具。

tensor_frame_to_pil 以 Element_ImageCurve 的 _tensor_frame_to_pil 为基线；
parse_color_str 收敛 empty_image_rgb 与 image_pad_blur 两份颜色解析
（统一为超集：#RRGGBB / #RGB / R,G,B / 灰度数值，0-255 int 列表）；
scan_sorted_images 收敛 Load_image_Preview 中 API 路由与类方法内的两份
重复扫描排序逻辑（并修复类内版本丢失 glob 通配符 "*" 的 bug）。
"""
import glob
import os

import numpy as np
import torch
from PIL import Image


def tensor_frame_to_pil(t):
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


def parse_color_str(color_code):
    """解析颜色字符串为 [r, g, b]（0-255 int）。

    支持 #RRGGBB、#RGB、R,G,B、灰度数值；失败时返回黑色并打印告警。
    """
    c = str(color_code).strip().replace(" ", "")
    color = [0, 0, 0]
    try:
        if c.startswith("#"):
            hex_code = c.lstrip("#")
            if len(hex_code) == 6:
                color = [int(hex_code[i:i + 2], 16) for i in (0, 2, 4)]
            elif len(hex_code) == 3:
                color = [int(ch * 2, 16) for ch in hex_code]
        elif "," in c:
            parts = [int(p) for p in c.split(",")[:3]]
            if len(parts) == 3:
                color = [max(0, min(255, p)) for p in parts]
        else:
            val = max(0, min(255, int(float(c))))
            color = [val, val, val]
    except Exception:
        print(f"[Element_easy] Color parse error: {color_code}. Defaulting to black.")
        color = [0, 0, 0]
    return color


IMAGE_GLOB_EXTENSIONS = ["*.png", "*.jpg", "*.jpeg", "*.gif", "*.bmp", "*.webp", "*.tiff"]

_SORT_KEYS = {
    "name_asc": lambda x: os.path.basename(x).lower(),
    "name_desc": lambda x: os.path.basename(x).lower(),
    "newest_first": lambda x: os.path.getctime(x),
    "oldest_first": lambda x: os.path.getctime(x),
    "recently_modified": lambda x: os.path.getmtime(x),
    "oldest_modified": lambda x: os.path.getmtime(x),
}


def scan_sorted_images(folder_path, sort_method="newest_first"):
    """扫描目录下的图片文件并按指定方式排序。"""
    files = []
    for ext in IMAGE_GLOB_EXTENSIONS:
        files.extend(glob.glob(os.path.join(folder_path, ext)))
        files.extend(glob.glob(os.path.join(folder_path, ext.upper())))

    if sort_method in ("name_desc", "newest_first", "recently_modified"):
        files.sort(key=_SORT_KEYS[sort_method], reverse=True)
    else:
        files.sort(key=_SORT_KEYS.get(sort_method, _SORT_KEYS["newest_first"]))
    return files
