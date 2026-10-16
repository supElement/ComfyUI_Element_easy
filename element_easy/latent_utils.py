# element_easy/latent_utils.py
"""Minimax H3 latent 上采样共享实现。

MinimaxH3LatentUpscaler（基础版）原为 MinimaxH3LatentUpscaler_Adv 的无参数
特例（无分块 / 无精度提升 / 不处理 conditioning），两文件约 130 行逐字重复。
现统一以 Adv 的实现为核心：
- compute_target_size：按像素目标尺寸推算（0 = 按比例）
- upscale_video_5d：分块 5D 视频张量上采样（chunk_size=0 即整批，等价基础版）
- upscale_latents：主流程（NestedTensor / list / tuple / 普通张量分发）

行为差异说明：输出包装的异常兜底统一采用基础版更宽容的 except Exception
（原 Adv 版为 except RuntimeError，两者仅在 NestedTensor 构造抛出其他异常时
表现不同；更宽容的兜底不会破坏正常路径）。
"""
import torch
import comfy.utils
from comfy import nested_tensor

SPATIAL_COMPRESSION = 16


def compute_target_size(ref_tensor, width, height, spatial_compression):
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


def upscale_video_5d(tensor, latent_width, latent_height,
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


def build_latent_output(processed, is_comfy_nested, original_latent):
    if is_comfy_nested:
        try:
            return nested_tensor.NestedTensor(processed)
        except Exception:
            return processed
    if isinstance(original_latent, tuple):
        return tuple(processed)
    if isinstance(original_latent, list):
        try:
            return nested_tensor.NestedTensor(processed)
        except Exception:
            return processed
    return processed


def upscale_latents(samples, width, height, upscale_method, crop,
                    chunk_size=0, safe_precision=False):
    """按 MiniMax H3 的 16x 空间压缩率放大 latent，返回 (s, latent_w, latent_h)。

    width/height 为像素目标；chunk_size=0 整批处理；safe_precision 控制
    插值期间是否临时升 FP32。基础版节点以 (0, False) 调用即等价原实现。
    """
    spatial_compression = SPATIAL_COMPRESSION
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

        width, height = compute_target_size(ref_tensor, width, height, spatial_compression)
        latent_width = width // spatial_compression
        latent_height = height // spatial_compression

        processed = []
        for t in latent_list:
            if len(t.shape) == 5:
                processed.append(
                    upscale_video_5d(
                        t, latent_width, latent_height,
                        upscale_method, crop,
                        chunk_size=chunk_size,
                        safe_precision=safe_precision,
                    )
                )
            else:
                processed.append(t)

        s["samples"] = build_latent_output(processed, is_comfy_nested, latent)

    else:
        ref_tensor = latent
        width, height = compute_target_size(ref_tensor, width, height, spatial_compression)
        latent_width = width // spatial_compression
        latent_height = height // spatial_compression

        if len(ref_tensor.shape) == 5:
            s["samples"] = upscale_video_5d(
                ref_tensor, latent_width, latent_height,
                upscale_method, crop,
                chunk_size=chunk_size,
                safe_precision=safe_precision,
            )
        else:
            s["samples"] = comfy.utils.common_upscale(
                ref_tensor, latent_width, latent_height, upscale_method, crop
            )

    return s, latent_width, latent_height
