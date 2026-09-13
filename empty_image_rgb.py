import torch
import numpy as np

class EmptyImageRGB:
    """根据 RGB/Hex 颜色生成纯色图像，前端支持色轮 + 屏幕吸管取色。"""

    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "width": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "height": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "divisible_by": ("INT", {"default": 1, "min": 1, "max": 512, "step": 1}),
                "color_code": ("STRING", {
                    "multiline": False,
                    "default": "#808080",
                    "tooltip": "支持 #RRGGBB、#RGB、R,G,B 或灰度数值；可用前端色轮/吸管选取",
                }),
            },
        }

    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "actual_width", "actual_height")
    FUNCTION = "generate"
    CATEGORY = "Element_easy/image"

    def generate(self, width, height, divisible_by, color_code):
        div = max(1, divisible_by)
        actual_w = max(div, int(round(width / div) * div))
        actual_h = max(div, int(round(height / div) * div))

        color = [0, 0, 0]
        try:
            c = str(color_code).strip()
            if c.startswith("#"):
                c = c.lstrip("#")
                if len(c) == 6:
                    color = [int(c[i:i+2], 16) for i in (0, 2, 4)]
                elif len(c) == 3:
                    color = [int(ch * 2, 16) for ch in c]
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

        r, g, b = (x / 255.0 for x in color)
        image_tensor = torch.empty((1, actual_h, actual_w, 3), dtype=torch.float32)
        image_tensor[:, :, :, 0] = r
        image_tensor[:, :, :, 1] = g
        image_tensor[:, :, :, 2] = b

        info_text = f"Color: RGB{tuple(color)}\n▶ Actual: {actual_w} x {actual_h}"
        return {"ui": {"text": [info_text]},
                "result": (image_tensor, actual_w, actual_h)}


NODE_CLASS_MAPPINGS = {"EmptyImageRGB_Element": EmptyImageRGB}
NODE_DISPLAY_NAME_MAPPINGS = {"EmptyImageRGB_Element": "Empty Image RGB (色轮取色)"}
