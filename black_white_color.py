# black_white_color.py
import torch
import torch.nn.functional as F

class BlackWhiteColor:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "image": ("IMAGE",),
                "contrast": ("FLOAT", {"default": 1.0, "min": 0.0, "max": 10.0, "step": 0.1}),
                "threshold": ("FLOAT", {"default": 0.5, "min": 0.0, "max": 1.0, "step": 0.01}),
                "invert_mask_grow": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "MASK")
    RETURN_NAMES = ("image", "mask", "invert_mask")
    FUNCTION = "process"
    CATEGORY = "Element_easy/image"
    
    def process(self, image, contrast, threshold, invert_mask_grow):
        # Grayscale conversion (GPU optimized)
        gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
        
        # Contrast adjustment (GPU optimized)
        gray = torch.clamp((gray - 0.5) * contrast + 0.5, 0, 1)
        
        # Threshold mask (GPU optimized)
        mask = (gray > threshold).float()
        invert_mask = 1.0 - mask
        
        # Grow invert mask (GPU optimized)
        if invert_mask_grow > 0:
            b, h, w = invert_mask.shape
            kernel_size = invert_mask_grow * 2 + 1
            # Reshape to (B, 1, H, W) for max_pool2d
            invert_mask = F.max_pool2d(
                invert_mask.view(b, 1, h, w),
                kernel_size,
                stride=1,
                padding=invert_mask_grow
            ).view(b, h, w)
        
        # Create output image (GPU optimized)
        result = mask.unsqueeze(-1).expand(-1, -1, -1, 3)
        
        return (result, mask, invert_mask)
