import torch
import numpy as np
import math
from PIL import Image, ImageDraw

class ChessboardPattern_Element:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "width": ("INT", {"default": 512, "min": 8, "max": 8192, "step": 8}),
                "height": ("INT", {"default": 512, "min": 8, "max": 8192, "step": 8}),
                # 新增：模式选择
                "size_mode": (["by_grid_size", "by_rows_and_cols"], {"default": "by_grid_size"}),
                # 原来的格子大小
                "grid_size": ("INT", {"default": 64, "min": 2, "max": 2048, "step": 1}),
                # 新增：行数和列数
                "rows": ("INT", {"default": 8, "min": 1, "max": 1024, "step": 1}),
                "columns": ("INT", {"default": 8, "min": 1, "max": 1024, "step": 1}),
                "shape": (["square", "circle", "triangle", "diamond"], {"default": "square"}),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK", "MASK")
    RETURN_NAMES = ("image", "mask", "invert mask")
    FUNCTION = "generate"
    CATEGORY = "Element_easy/image"

    def generate(self, width, height, size_mode, grid_size, rows, columns, shape):
        # 创建纯黑背景
        img = Image.new("L", (width, height), "black")
        draw = ImageDraw.Draw(img)

        # 确定网格的行数、列数和每个单元格的确切宽高
        if size_mode == "by_grid_size":
            cell_w = grid_size
            cell_h = grid_size
            num_cols = math.ceil(width / cell_w)
            num_rows = math.ceil(height / cell_h)
        else:
            # 按行列划分
            num_cols = columns
            num_rows = rows
            cell_w = width / num_cols
            cell_h = height / num_rows

        # 遍历所有计算出的网格
        for row in range(num_rows):
            for col in range(num_cols):
                # 棋盘格交替逻辑：当 (行 + 列) 为偶数时，绘制白色形状
                if (row + col) % 2 == 0:
                    # 计算当前格子的绝对坐标 (处理浮点数确保划分均匀，无缝隙)
                    x0 = int(col * cell_w)
                    y0 = int(row * cell_h)
                    x1 = int((col + 1) * cell_w) - 1
                    y1 = int((row + 1) * cell_h) - 1
                    
                    bbox = [x0, y0, x1, y1]
                    
                    if shape == "square":
                        draw.rectangle(bbox, fill="white")
                        
                    elif shape == "circle":
                        draw.ellipse(bbox, fill="white")
                        
                    elif shape == "triangle":
                        # 向上指的三角形
                        p1 = ((x0 + x1) / 2.0, y0)
                        p2 = (x0, y1)
                        p3 = (x1, y1)
                        draw.polygon([p1, p2, p3], fill="white")
                        
                    elif shape == "diamond":
                        # 菱形
                        p1 = ((x0 + x1) / 2.0, y0)
                        p2 = (x1, (y0 + y1) / 2.0)
                        p3 = ((x0 + x1) / 2.0, y1)
                        p4 = (x0, (y0 + y1) / 2.0)
                        draw.polygon([p1, p2, p3, p4], fill="white")

        # 将 PIL 图像转换为 numpy 数组并归一化到 0.0 - 1.0
        img_np = np.array(img).astype(np.float32) / 255.0
        
        # 构建 ComfyUI 标准 Mask 张量，形状[B, H, W]
        mask = torch.from_numpy(img_np).unsqueeze(0)
        
        # 反转 Mask
        invert_mask = 1.0 - mask
        
        # 构建 ComfyUI 标准 Image 张量，形状 [B, H, W, C]
        image = mask.unsqueeze(-1).repeat(1, 1, 1, 3)

        return (image, mask, invert_mask)