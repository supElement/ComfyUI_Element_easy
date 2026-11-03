import torch
import torch.nn.functional as F
import torchvision.transforms.functional as TF
import comfy.model_management

class MaskStrokeElement:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "mask": ("MASK",),
                "stroke_in": ("INT", {"default": 5, "min": 0, "max": 500, "step": 1}),
                "stroke_out": ("INT", {"default": 5, "min": 0, "max": 500, "step": 1}),
                "blur_in": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "blur_out": ("FLOAT", {"default": 2.0, "min": 0.0, "max": 100.0, "step": 0.1}),
                "backToWhite": ("FLOAT", {"default": 0.0, "min": 0.0, "max": 1.0, "step": 0.001}),
                "invert_mask": ("BOOLEAN", {"default": False, "label_on": "yes", "label_off": "no"}),
            }
        }

    RETURN_TYPES = ("MASK",)
    FUNCTION = "process_mask"
    CATEGORY = "Element_easy/image"

    def process_mask(self, mask, stroke_in, stroke_out, blur_in, blur_out, backToWhite, invert_mask):
        device = comfy.model_management.get_torch_device()
        mask = mask.to(device)
        
        if mask.dim() == 3:
            mask = mask.unsqueeze(1)
        
        if invert_mask:
            mask = 1.0 - mask       
        # --- 处理外边缘 ---
        if stroke_out > 0:
            kernel_size_out = 2 * stroke_out + 1
            # PyTorch 的 max_pool2d 在 GPU 上极快
            dilated = F.max_pool2d(mask, kernel_size=kernel_size_out, stride=1, padding=stroke_out)
        else:
            dilated = mask

        if blur_out > 0:
            k_size = int(6 * blur_out)
            if k_size % 2 == 0: k_size += 1
            dilated = TF.gaussian_blur(dilated, kernel_size=k_size, sigma=blur_out)

        # --- 处理内边缘 ---
        if stroke_in > 0:
            kernel_size_in = 2 * stroke_in + 1
            eroded = -F.max_pool2d(-mask, kernel_size=kernel_size_in, stride=1, padding=stroke_in)
        else:
            eroded = mask

        if blur_in > 0:
            k_size = int(6 * blur_in)
            if k_size % 2 == 0: k_size += 1
            eroded = TF.gaussian_blur(eroded, kernel_size=k_size, sigma=blur_in)

        # --- 组合 ---
        stroke = dilated - eroded

        # --- 后处理 ---
        if backToWhite > 0.0:
            stroke = stroke + backToWhite

        stroke = torch.clamp(stroke, 0.0, 1.0)
        stroke = stroke.squeeze(1)

        # 将结果移回 CPU，释放显存占用
        # 当这个函数结束，局部变量 dilated, eroded 等 GPU 张量会被 Python 垃圾回收，
        # 显存会自动释放，不需要手动 empty_cache() (那样反而会拖慢速度)。
        return (stroke.cpu(),)