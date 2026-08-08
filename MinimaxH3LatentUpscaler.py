import torch
import comfy.utils
from comfy import nested_tensor


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

    def _compute_target_size(self, ref_tensor, width, height, spatial_compression):
        if width == 0:
            height = max(spatial_compression, height)
            width = max(spatial_compression, round(ref_tensor.shape[-1] * height / ref_tensor.shape[-2]))
        elif height == 0:
            width = max(spatial_compression, width)
            height = max(spatial_compression, round(ref_tensor.shape[-2] * width / ref_tensor.shape[-1]))
        else:
            width = max(spatial_compression, width)
            height = max(spatial_compression, height)
        return width, height

    def _upscale_video_5d(self, tensor, latent_width, latent_height, upscale_method, crop):
        b, c, t_frames, h, w = tensor.shape
        t_flat = tensor.permute(0, 2, 1, 3, 4).reshape(b * t_frames, c, h, w)
        upscaled_flat = comfy.utils.common_upscale(
            t_flat, latent_width, latent_height, upscale_method, crop
        )
        new_h, new_w = upscaled_flat.shape[-2], upscaled_flat.shape[-1]
        return upscaled_flat.reshape(b, t_frames, c, new_h, new_w).permute(0, 2, 1, 3, 4)

    def latentUpscale(self, samples, upscale_method, width, height, crop):
        spatial_compression = 16

        if width == 0 and height == 0:
            return (samples,)

        s = samples.copy()
        latent = samples["samples"]

        is_comfy_nested = False

        if hasattr(latent, "is_nested") and latent.is_nested:
            latent_list = list(latent.unbind())
            is_comfy_nested = True
        elif isinstance(latent, (list, tuple)):
            latent_list = list(latent)
        else:
            latent_list = None  # 普通张量

        if latent_list is not None:
            ref_tensor = None
            for t in latent_list:
                if len(t.shape) == 5:
                    ref_tensor = t
                    break

            if ref_tensor is None:
                raise ValueError("No video tensor (5D) found in latent.")

            width, height = self._compute_target_size(ref_tensor, width, height, spatial_compression)
            latent_width = width // spatial_compression
            latent_height = height // spatial_compression

            processed = []
            for t in latent_list:
                if len(t.shape) == 5:
                    processed.append(
                        self._upscale_video_5d(t, latent_width, latent_height, upscale_method, crop)
                    )
                else:
                    processed.append(t)

            if is_comfy_nested:
                s["samples"] = nested_tensor.NestedTensor(processed)
            elif isinstance(latent, tuple):
                s["samples"] = tuple(processed)
            elif isinstance(latent, list):
                try:
                    s["samples"] = nested_tensor.NestedTensor(processed)
                except Exception:
                    s["samples"] = processed
            else:
                s["samples"] = processed

        else:
            ref_tensor = latent
            width, height = self._compute_target_size(ref_tensor, width, height, spatial_compression)
            latent_width = width // spatial_compression
            latent_height = height // spatial_compression

            if len(ref_tensor.shape) == 5:
                s["samples"] = self._upscale_video_5d(
                    ref_tensor, latent_width, latent_height, upscale_method, crop
                )
            else:
                s["samples"] = comfy.utils.common_upscale(
                    ref_tensor, latent_width, latent_height, upscale_method, crop
                )

        return (s,)


NODE_CLASS_MAPPINGS = {
    "MinimaxH3LatentUpscaler": MinimaxH3LatentUpscaler,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "MinimaxH3LatentUpscaler": "Minimax_H3-LatentUpscaler",
}