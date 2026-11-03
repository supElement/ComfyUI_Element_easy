import torch
import torch.nn.functional as F

class MaskNoiseInjectionElement:
    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "image": ("IMAGE",),
                "mask": ("MASK",),
                "strength": ("FLOAT", {
                    "default": 0.5, 
                    "min": 0.0, 
                    "max": 1.0, 
                    "step": 0.01,
                    "display": "number"
                }),
                "seed": ("INT", {"default": 0, "min": 0, "max": 0xffffffffffffffff}),
                # 修改点：类型改为 FLOAT，步长改为 0.01
                "noise_scale": ("FLOAT", {
                    "default": 1.0, 
                    "min": 0.25, 
                    "max": 128.0, 
                    "step": 0.01,    # 允许精细调节，如 1.5, 2.35 等
                    "display": "number"
                }), 
                "monochrome": ("BOOLEAN", {"default": False}),
            }
        }

    RETURN_TYPES = ("IMAGE",)
    RETURN_NAMES = ("image",)
    FUNCTION = "inject_noise"
    CATEGORY = "Element_easy/image"

    def inject_noise(self, image, mask, strength, seed, noise_scale, monochrome):
        torch.manual_seed(seed)
        
        B, H, W, C = image.shape
        noise_channels = 1 if monochrome else C
        
        # 修改点：使用浮点除法，然后强制转为 int
        # 即使 noise_scale 是 1.5，这里也能算出正确的缩小尺寸
        h_noise = int(H / noise_scale)
        w_noise = int(W / noise_scale)

        # 兜底防止尺寸变为0
        h_noise = max(1, h_noise)
        w_noise = max(1, w_noise)
        
        # 生成小尺寸噪点
        noise = torch.rand((B, h_noise, w_noise, noise_channels), device=image.device, dtype=image.dtype)
        
        # 只要尺寸不一致，就进行缩放插值
        if h_noise != H or w_noise != W:
            noise = noise.permute(0, 3, 1, 2)
            
            # mode="nearest" 保持硬边的马赛克感
            # mode="bilinear" 会让噪点边缘模糊（如果你想要云雾效果可以改这个）
            noise = F.interpolate(noise, size=(H, W), mode="nearest")
            
            noise = noise.permute(0, 2, 3, 1)

        if mask.dim() == 3:
            mask = mask.unsqueeze(-1)
        
        mask = mask.expand_as(image)
        
        noised_image = (image * (1.0 - strength)) + (noise * strength)
        final_image = image * (1.0 - mask) + noised_image * mask
        final_image = torch.clamp(final_image, 0.0, 1.0)
        
        return (final_image,)