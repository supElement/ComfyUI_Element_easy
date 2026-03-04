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
                "mask_grow": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
                "invert_mask_grow": ("INT", {"default": 0, "min": 0, "max": 64, "step": 1}),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "MASK", "MASK", "MASK")
    RETURN_NAMES = ("image", "mask", "invert_mask", "mask_grow", "invert_mask_grow")
    FUNCTION = "process"
    CATEGORY = "Element_easy/image"
    
    def process(self, image, contrast, threshold, mask_grow, invert_mask_grow):
        # Grayscale conversion
        gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
        
        # Contrast adjustment
        gray = torch.clamp((gray - 0.5) * contrast + 0.5, 0, 1)
        
        # Create masks
        mask = (gray > threshold).float()
        invert_mask = 1.0 - mask
        
        # Grow masks
        mask_grown = self._grow_mask(mask, mask_grow)
        invert_mask_grown = self._grow_mask(invert_mask, invert_mask_grow)
        
        # Create output image
        result = mask.unsqueeze(-1).expand(-1, -1, -1, 3)
        
        return (result, mask, invert_mask, mask_grown, invert_mask_grown)
    
    def _grow_mask(self, mask, grow_size):
        if grow_size == 0:
            return mask
        
        b, h, w = mask.shape
        kernel_size = grow_size * 2 + 1
        return F.max_pool2d(
            mask.view(b, 1, h, w),
            kernel_size,
            stride=1,
            padding=grow_size
        ).view(b, h, w)
