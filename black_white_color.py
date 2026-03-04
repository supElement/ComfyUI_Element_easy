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
            },
            "optional": {
                "mask": ("MASK",),
            }
        }
    
    RETURN_TYPES = ("IMAGE", "MASK", "MASK", "MASK", "MASK")
    RETURN_NAMES = ("image", "mask", "invert_mask", "mask_grow", "invert_mask_grow")
    FUNCTION = "process"
    CATEGORY = "Element_easy/image"
    
    def process(self, image, contrast, threshold, mask_grow, invert_mask_grow, mask=None):
        # Grayscale conversion
        gray = 0.299 * image[..., 0] + 0.587 * image[..., 1] + 0.114 * image[..., 2]
        
        # Contrast adjustment
        gray = torch.clamp((gray - 0.5) * contrast + 0.5, 0, 1)
        
        # Create mask from threshold
        generated_mask = (gray > threshold).float()
        
        # Add optional mask (resize to match if needed)
        if mask is not None:
            b, h, w = generated_mask.shape
            
            # Ensure mask is 4D for interpolate (B, 1, H, W)
            if mask.dim() == 2:
                mask = mask.unsqueeze(0).unsqueeze(0)
            elif mask.dim() == 3:
                mask = mask.unsqueeze(1)
            
            # Resize mask if dimensions don't match
            if mask.shape[2] != h or mask.shape[3] != w:
                mask = F.interpolate(mask, size=(h, w), mode="bilinear", align_corners=False)
            
            # Expand batch dim if needed
            if mask.shape[0] != b:
                mask = mask.expand(b, -1, -1, -1)
            
            # Squeeze back to (B, H, W) and add
            mask = mask.squeeze(1)
            generated_mask = torch.clamp(generated_mask + mask, 0, 1)
        
        # Create invert mask
        invert_mask = 1.0 - generated_mask
        
        # Grow masks
        mask_grown = self._grow_mask(generated_mask, mask_grow)
        invert_mask_grown = self._grow_mask(invert_mask, invert_mask_grow)
        
        # Create output image
        result = generated_mask.unsqueeze(-1).expand(-1, -1, -1, 3)
        
        return (result, generated_mask, invert_mask, mask_grown, invert_mask_grown)
    
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
