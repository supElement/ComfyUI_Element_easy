import torch
import comfy.utils
from comfy import nested_tensor


class MinimaxH3LatentUpscaler_Adv:
    """
    Latent spatial upscaler dedicated to MiniMax H3.
    MiniMax H3 VisualVAE uses a spatial compression factor of 16x,
    unlike the standard 8x used by most image diffusion models.
    This node correctly scales H3 latents by dividing pixel dimensions by 16.
    Supports ComfyUI's NestedTensor format (mixed video 5D + audio 4D).
    Optimized for low-VRAM GPUs with chunked processing and safe precision.
    Optionally updates conditioning metadata to match the new resolution,
    avoiding the need for a second MiniMax H3 Image to Video node (no extra TE cost).
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
                "chunk_size": ("INT", {
                    "default": 8,
                    "min": 0,
                    "max": 128,
                    "step": 1,
                    "tooltip": (
                        "Frames per chunk for low-VRAM GPUs (e.g. RTX 3060 8GB). "
                        "0 = process all frames at once (faster but uses more VRAM)."
                    ),
                }),
                "safe_precision": (["enable", "disable"], {
                    "default": "enable",
                    "tooltip": (
                        "Cast to FP32 during interpolation to prevent NaN artifacts "
                        "on FP16/BF16."
                    ),
                }),
                "conditioning_mode": (["pass_through", "NO_refs", "refs"], {
                    "default": "pass_through",
                    "tooltip": (
                        "pass_through = do not touch conditioning (standard H3). "
                        "update_meta = update latent_h/w and REMOVE refs/keyframes "
                        "(fixes fl2va shape mismatch + avoids ghosting, zero TE cost). "
                        "full_sync = update latent_h/w AND upscale refs/keyframes "
                        "(keeps visual references, may cause ghosting)."
                    ),
                }),
            },
            "optional": {
                "conditioning": ("CONDITIONING",),
            }
        }

    RETURN_TYPES = ("LATENT", "CONDITIONING")
    RETURN_NAMES = ("latent", "conditioning")
    FUNCTION = "latentUpscale"
    CATEGORY = "Element_easy/latent"
    DESCRIPTION = (
        "Upscales MiniMax H3 latents (16x compression). "
        "conditioning_mode: pass_through / update_meta / full_sync. "
        "update_meta fixes fl2va shape mismatch without re-running TE."
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

    def _upscale_video_5d(self, tensor, latent_width, latent_height,
                          upscale_method, crop, chunk_size=0, safe_precision=True):
        b, c, t_frames, h, w = tensor.shape
        original_dtype = tensor.dtype
        device = tensor.device

        if chunk_size <= 0:
            chunk_size = t_frames

        out_tensor = torch.empty(
            (b, c, t_frames, latent_height, latent_width),
            dtype=original_dtype, device=device
        )

        for i in range(0, t_frames, chunk_size):
            end_i = min(i + chunk_size, t_frames)
            chunk = tensor[:, :, i:end_i, :, :]
            chunk_flat = chunk.permute(0, 2, 1, 3, 4).contiguous().view(-1, c, h, w)

            if safe_precision and chunk_flat.is_floating_point():
                chunk_flat = chunk_flat.float()

            upscaled_flat = comfy.utils.common_upscale(
                chunk_flat, latent_width, latent_height, upscale_method, crop
            )
            upscaled_flat = upscaled_flat.to(original_dtype)

            upscaled_chunk = upscaled_flat.view(
                b, end_i - i, c, latent_height, latent_width
            ).permute(0, 2, 1, 3, 4)
            out_tensor[:, :, i:end_i, :, :] = upscaled_chunk

        return out_tensor

    def _build_output(self, processed, is_comfy_nested, original_latent):
        if is_comfy_nested:
            try:
                return nested_tensor.NestedTensor(processed)
            except RuntimeError:
                return processed
        if isinstance(original_latent, tuple):
            return tuple(processed)
        if isinstance(original_latent, list):
            try:
                return nested_tensor.NestedTensor(processed)
            except RuntimeError:
                return processed
        return processed

    def _process_conditioning(self, conditioning, latent_width, latent_height,
                              mode, upscale_method, crop):
        """
        pass_through  : 原样返回
        update_meta   : 更新 latent_h/w，删除 refs/keyframes
        full_sync     : 更新 latent_h/w，同步放大 refs/keyframes
        """
        if conditioning is None or mode == "pass_through":
            return conditioning

        out = []
        for entry in conditioning:
            if not isinstance(entry, (list, tuple)) or len(entry) < 2:
                out.append(entry)
                continue

            emb, meta = entry[0], entry[1]
            new_meta = meta.copy()

            new_meta["latent_h"] = latent_height
            new_meta["latent_w"] = latent_width

            if mode == "NO_refs":
                new_meta.pop("minimax_refs", None)
                new_meta.pop("minimax_keyframes", None)

            elif mode == "refs":
                def upscale_lat_dict(d):
                    if not isinstance(d, dict):
                        return d
                    new_d = d.copy()
                    t = d.get("latent")
                    if isinstance(t, torch.Tensor):
                        if len(t.shape) == 4:
                            new_d["latent"] = comfy.utils.common_upscale(
                                t, latent_width, latent_height, upscale_method, crop
                            )
                        elif len(t.shape) == 5:
                            b, c, tf, h, w = t.shape
                            t_flat = t.permute(0, 2, 1, 3, 4).contiguous().view(-1, c, h, w)
                            ups = comfy.utils.common_upscale(
                                t_flat, latent_width, latent_height, upscale_method, crop
                            )
                            nh, nw = ups.shape[-2], ups.shape[-1]
                            new_d["latent"] = ups.view(b, tf, c, nh, nw).permute(0, 2, 1, 3, 4)
                    new_d["latent_h"] = latent_height
                    new_d["latent_w"] = latent_width
                    return new_d

                for key in ["minimax_refs", "minimax_keyframes"]:
                    val = meta.get(key)
                    if val is not None and isinstance(val, list):
                        new_meta[key] = [upscale_lat_dict(item) for item in val]

            out.append([emb, new_meta])

        return out

    def latentUpscale(self, samples, upscale_method, width, height, crop,
                      chunk_size=8, safe_precision="enable",
                      conditioning_mode="pass_through", conditioning=None):
        spatial_compression = 16
        use_safe_precision = (safe_precision == "enable")

        if width == 0 and height == 0:
            return (samples, conditioning)

        s = samples.copy()
        latent = samples["samples"]
        is_comfy_nested = False

        if hasattr(latent, "is_nested") and latent.is_nested:
            latent_list = list(latent.unbind())
            is_comfy_nested = True
        elif isinstance(latent, (list, tuple)):
            latent_list = list(latent)
        else:
            latent_list = None

        if latent_list is not None:
            ref_tensor = None
            for t in latent_list:
                if len(t.shape) == 5:
                    ref_tensor = t
                    break
            if ref_tensor is None:
                raise ValueError("No video tensor (5D) found in latent.")

            width, height = self._compute_target_size(
                ref_tensor, width, height, spatial_compression
            )
            latent_width = width // spatial_compression
            latent_height = height // spatial_compression

            processed = []
            for t in latent_list:
                if len(t.shape) == 5:
                    processed.append(
                        self._upscale_video_5d(
                            t, latent_width, latent_height,
                            upscale_method, crop,
                            chunk_size=chunk_size,
                            safe_precision=use_safe_precision,
                        )
                    )
                else:
                    processed.append(t)

            s["samples"] = self._build_output(processed, is_comfy_nested, latent)

        else:
            ref_tensor = latent
            width, height = self._compute_target_size(
                ref_tensor, width, height, spatial_compression
            )
            latent_width = width // spatial_compression
            latent_height = height // spatial_compression

            if len(ref_tensor.shape) == 5:
                s["samples"] = self._upscale_video_5d(
                    ref_tensor, latent_width, latent_height,
                    upscale_method, crop,
                    chunk_size=chunk_size,
                    safe_precision=use_safe_precision,
                )
            else:
                s["samples"] = comfy.utils.common_upscale(
                    ref_tensor, latent_width, latent_height, upscale_method, crop
                )

        cond_out = self._process_conditioning(
            conditioning, latent_width, latent_height,
            conditioning_mode, upscale_method, crop
        )

        return (s, cond_out)


NODE_CLASS_MAPPINGS = {
    "MinimaxH3LatentUpscaler_Adv": MinimaxH3LatentUpscaler_Adv,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "MinimaxH3LatentUpscaler_Adv": "Minimax_H3-LatentUpscaler_Adv",
}
