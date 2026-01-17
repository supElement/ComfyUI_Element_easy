import torch
import torchvision.transforms.functional as TF
import comfy.model_management  

class ImagePadBlur:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                
                # --- 1. 尺寸与对齐 ---
                "target_width": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                "target_height": ("INT", {"default": 0, "min": 0, "max": 8192, "step": 1}),
                
                "alignment": ([
                    "center", 
                    "left", "right", "top", "bottom", 
                    "top-left", "top-right", "bottom-left", "bottom-right"
                ],),
                
                "x_offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),
                "y_offset": ("INT", {"default": 0, "min": -4096, "max": 4096, "step": 1}),

                # --- 2. 手动 Padding ---
                "left": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "top": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "right": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                "bottom": ("INT", {"default": 0, "min": 0, "max": 4096, "step": 1}),
                
                # --- 3. 样式与羽化 ---
                "feathering": ("INT", {"default": 50, "min": 0, "max": 500, "step": 1}),
                "content_blur": ("INT", {"default": 0, "min": 0, "max": 500, "step": 1}),
                
                "pad_mode": (["constant", "edge", "reflect", "symmetric"],),
                
                # --- 4. 颜色控制 ---
                "background_color": ("STRING", {"default": "#000000", "multiline": False}),
            },
            "optional": {
                "mask": ("MASK",),
            }
        }

    RETURN_TYPES = ("IMAGE", "MASK")
    RETURN_NAMES = ("image", "mask")
    FUNCTION = "execute"
    CATEGORY = "Element_easy/image"

    def parse_color(self, color_str):
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


    def safe_pad(self, input_tensor, pad, mode, value=0):
        left, right, top, bottom = pad
        if mode in ['constant', 'replicate']:
            return torch.nn.functional.pad(input_tensor, pad, mode=mode, value=value)
        
        current = input_tensor
        # 水平
        while left > 0 or right > 0:
            max_w = current.shape[-1] - 1 
            p_l = min(left, max_w)
            p_r = min(right, max_w)
            current = torch.nn.functional.pad(current, (p_l, p_r, 0, 0), mode=mode)
            left -= p_l
            right -= p_r
        # 垂直
        while top > 0 or bottom > 0:
            max_h = current.shape[-2] - 1
            p_t = min(top, max_h)
            p_b = min(bottom, max_h)
            current = torch.nn.functional.pad(current, (0, 0, p_t, p_b), mode=mode)
            top -= p_t
            bottom -= p_b
        return current

    def execute(self, image, target_width, target_height, alignment, x_offset, y_offset, left, top, right, bottom, feathering, content_blur, pad_mode, background_color, mask=None):
        
        # [GPU优化] 获取 ComfyUI 管理的 GPU 设备
        device = comfy.model_management.get_torch_device()
        
        # 将输入移动到 GPU
        img_tensor = image.permute(0, 3, 1, 2).to(device)
        B, C, H, W = img_tensor.shape
        
        # --- 1. 计算基础 Padding ---
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

        if pad_left == 0 and pad_right == 0 and pad_top == 0 and pad_bottom == 0:
             # 如果没有任何操作，直接返回
             return (image, mask if mask is not None else torch.zeros((B, H, W), device="cpu"))

        # --- 2. 添加隐形边距 (Margin) ---
        margin = 0
        if feathering > 0 or content_blur > 0:
            margin = max(feathering, content_blur) + 32
        
        real_pad_left = pad_left + margin
        real_pad_right = pad_right + margin
        real_pad_top = pad_top + margin
        real_pad_bottom = pad_bottom + margin

        temp_H = H + real_pad_top + real_pad_bottom
        temp_W = W + real_pad_left + real_pad_right

        # --- 3. 生成纹理层 ---
        texture_mode = pad_mode
        if pad_mode == 'constant': texture_mode = 'reflect'
        elif pad_mode == 'edge': texture_mode = 'replicate'
        elif pad_mode == 'symmetric': texture_mode = 'reflect'
            
        extended_img = self.safe_pad(img_tensor, (real_pad_left, real_pad_right, real_pad_top, real_pad_bottom), mode=texture_mode)

        if content_blur > 0:
            k_size = content_blur
            if k_size % 2 == 0: k_size += 1
            extended_img = TF.gaussian_blur(extended_img, k_size, sigma=content_blur/2.0)

        # --- 4. 贴回原图 ---
        y1 = max(0, real_pad_top)
        y2 = min(temp_H, real_pad_top + H)
        x1 = max(0, real_pad_left)
        x2 = min(temp_W, real_pad_left + W)
        
        img_y1 = max(0, -real_pad_top)
        img_y2 = img_y1 + (y2 - y1)
        img_x1 = max(0, -real_pad_left)
        img_x2 = img_x1 + (x2 - x1)
        
        if y2 > y1 and x2 > x1:
            extended_img[:, :, y1:y2, x1:x2] = img_tensor[:, :, img_y1:img_y2, img_x1:img_x2]

        final_image = extended_img

        # --- 5. 构建 Mask ---
        # 确保 mask 也在 GPU 上创建
        out_mask = torch.ones((B, 1, temp_H, temp_W), device=device, dtype=torch.float32)
        
        hole_y1, hole_y2 = y1, y2
        hole_x1, hole_x2 = x1, x2
        
        if pad_top <= 0: hole_y1 = 0 
        if pad_bottom <= 0: hole_y2 = temp_H
        if pad_left <= 0: hole_x1 = 0
        if pad_right <= 0: hole_x2 = temp_W
        
        if hole_y2 > hole_y1 and hole_x2 > hole_x1:
            out_mask[:, :, hole_y1:hole_y2, hole_x1:hole_x2] = 0.0

        if feathering > 0:
            k_size_f = feathering * 2 + 1
            out_mask = TF.gaussian_blur(out_mask, k_size_f, sigma=feathering)

        # --- 6. 混合背景 ---
        if pad_mode == "constant":
            r, g, b = self.parse_color(background_color)
            solid_bg = torch.zeros((B, C, temp_H, temp_W), device=device, dtype=torch.float32)
            solid_bg[:, 0, :, :] = r
            solid_bg[:, 1, :, :] = g
            solid_bg[:, 2, :, :] = b
            final_image = final_image * (1.0 - out_mask) + solid_bg * out_mask
        
        # --- 7. 裁切 Margin ---
        crop_y1 = margin
        crop_y2 = margin + final_H
        crop_x1 = margin
        crop_x2 = margin + final_W
        
        final_image = final_image[:, :, crop_y1:crop_y2, crop_x1:crop_x2]
        out_mask = out_mask[:, :, crop_y1:crop_y2, crop_x1:crop_x2]

        # --- 8. 用户 Mask ---
        output_mask_3d = out_mask.squeeze(1)
        if mask is not None:
            
            mask = mask.to(device)
            if mask.dim() == 2: mask = mask.unsqueeze(0)
            user_mask_padded = torch.nn.functional.pad(mask, (pad_left, pad_right, pad_top, pad_bottom), mode='constant', value=1)
            output_mask_3d = torch.maximum(output_mask_3d, user_mask_padded)

        # [GPU优化] 计算完成后，将结果移回 CPU

        final_image = final_image.permute(0, 2, 3, 1).cpu()
        output_mask_3d = output_mask_3d.cpu()
        
        return (final_image, output_mask_3d)
