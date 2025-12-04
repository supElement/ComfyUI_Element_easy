import torch
import numpy as np

class EmptyImageRGB:
    """
    Empty Image RGB
    功能：根据RGB/Hex颜色生成纯色图像，支持自动尺寸整除修正。
    并在节点上显示实际生成的尺寸信息。
    """
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "width": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "height": ("INT", {"default": 512, "min": 1, "max": 16384, "step": 1}),
                "divisible_by": ("INT", {"default": 1, "min": 1, "max": 512, "step": 1}),
                "color_code": ("STRING", {"multiline": False, "default": "#000000"}),
            },
        }

    # 必须定义输出类型
    RETURN_TYPES = ("IMAGE", "INT", "INT")
    RETURN_NAMES = ("IMAGE", "actual_width", "actual_height")
    FUNCTION = "generate"
    
    # 你的分类
    CATEGORY = "Element_easy/image"

    def generate(self, width, height, divisible_by, color_code):
        # --- 1. 尺寸计算逻辑 ---
        div = max(1, divisible_by)
        
        # 计算最接近的倍数
        actual_w = int(round(width / div) * div)
        actual_h = int(round(height / div) * div)

        if actual_w == 0: actual_w = div
        if actual_h == 0: actual_h = div

        # --- 2. 颜色解析逻辑 ---
        color = [0, 0, 0] 
        try:
            c = color_code.strip()
            if c.startswith("#"):
                c = c.lstrip("#")
                if len(c) == 6:
                    color = [int(c[i:i+2], 16) for i in (0, 2, 4)]
                elif len(c) == 3:
                    color = [int(c[i]*2, 16) for i in (0, 1, 2)]
            elif "," in c:
                parts = c.split(",")
                if len(parts) >= 3:
                    color = [int(parts[0]), int(parts[1]), int(parts[2])]
            else:
                val = int(c)
                color = [val, val, val]
        except:
            print(f"[Element_easy] Color parse error: {color_code}. Defaulting to black.")
            color = [0, 0, 0]

        # --- 3. 生成图像 ---
        r, g, b = color[0] / 255.0, color[1] / 255.0, color[2] / 255.0
        
        image_tensor = torch.zeros((1, actual_h, actual_w, 3), dtype=torch.float32)
        image_tensor[0, :, :, 0] = r
        image_tensor[0, :, :, 1] = g
        image_tensor[0, :, :, 2] = b

        # --- 4. UI 反馈信息 (关键部分) ---
        info_text = (
            f"Color: RGB{tuple(color)}\n"
            # f"Set Size: {width} x {height}\n"
            # f"Divisible by: {div}\n"
            f"▶ Actual: {actual_w} x {actual_h}"
        )

        # ★★★ 重点：这里必须返回一个字典，包含 "ui" 和 "result" ★★★
        # "ui": {"text":List[string]} 是传给 JS 的
        # "result": Tuple 是传给下一个节点的
        return {
            "ui": {"text": [info_text]}, 
            "result": (image_tensor, actual_w, actual_h)
        }