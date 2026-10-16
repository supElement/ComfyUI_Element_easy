# MinimaxH3LatentUpscaler.py —— 基础版（共享实现见 element_easy/latent_utils.py）
from .element_easy.latent_utils import upscale_latents


class MinimaxH3LatentUpscaler:
    """
    Latent spatial upscaler dedicated to MiniMax H3.
    MiniMax H3 VisualVAE uses a spatial compression factor of 16x,
    unlike the standard 8x used by most image diffusion models.
    This node correctly scales H3 latents by dividing pixel dimensions by 16.

    Supports ComfyUI's NestedTensor format (mixed video 5D + audio 4D).
    """

    upscale_methods = ["nearest-exact", "bilinear", "area", "bicubic", "bislerp"]
    crop_methods = ["disabled", "center"]

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "samples": ("LATENT",),
                "upscale_method": (s.upscale_methods,),
                "width": ("INT", {"default": 512, "min": 0, "max": 16384, "step": 16}),
                "height": ("INT", {"default": 512, "min": 0, "max": 16384, "step": 16}),
                "crop": (s.crop_methods,),
            }
        }

    RETURN_TYPES = ("LATENT",)
    FUNCTION = "latentUpscale"
    CATEGORY = "Element_easy/latent"
    DESCRIPTION = (
        "Upscales MiniMax H3 latents using the correct 16x spatial compression factor. "
        "Input width/height are in pixels."
    )

    def latentUpscale(self, samples, upscale_method, width, height, crop):
        if width == 0 and height == 0:
            return (samples,)
        s, _, _ = upscale_latents(
            samples, width, height, upscale_method, crop,
            chunk_size=0, safe_precision=False,
        )
        return (s,)


NODE_CLASS_MAPPINGS = {
    "MinimaxH3LatentUpscaler": MinimaxH3LatentUpscaler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MinimaxH3LatentUpscaler": "Minimax_H3-LatentUpscaler",
}
