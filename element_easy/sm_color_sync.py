# -*- coding: utf-8 -*-
# 色彩匹配 / color synchronization

import cv2
import numpy as np
import torch

from .sm_common import (
    _sm_as_float,
    _sm_log,
    _sm_rgb_to_lab,
    _sm_lab_to_u8,
    _sm_fit,
    _sm_blur_ksize,
    _sm_fast_blur,
    _sm_np_median,
    _sm_median,
    _sm_u8_median,
    _sm_fast_median,
)
from .sm_compose import (
    laplacian_pyramid_blend,
    make_edge_safe_soft_mask,
    seamless_clone_crop,
)
from .sm_config import (
    COLOR_LOCAL_EDITED_SCALE,
    GLOBAL_COLOR_MAX_SHIFT,
    GLOBAL_COLOR_STRENGTH,
    LOWFREQ_COLOR_MAX_SHIFT,
    PATCH_COLOR_EDITED_SCALE,
    PATCH_COLOR_MAD_TAU,
    PATCH_COLOR_MAX_SHIFT,
    PATCH_COLOR_MIN_COVERAGE,
    PATCH_COLOR_PATCH_FRAC,
    PATCH_COLOR_PATCH_MAX,
    PATCH_COLOR_PATCH_MIN,
)


def _estimate_global_lab_shift( bg, prepared_crops, protect_edits=False):
    """从已对齐分块估计共有色偏，各块等权以避免大区域主导统计。"""
    tile_shifts = []
    for warped_fg, warped_mask, edit_mask in prepared_crops.values():
        if warped_fg.shape[:2] != bg.shape[:2] or warped_mask.shape != bg.shape[:2]:
            continue
        valid = warped_mask > 0.5
        if protect_edits and edit_mask is not None and edit_mask.shape == valid.shape:
            valid &= edit_mask > 0.5
        if int(valid.sum()) < 100:
            continue
        ys, xs = np.where(valid)
        x0, x1 = int(xs.min()), int(xs.max()) + 1
        y0, y1 = int(ys.min()), int(ys.max()) + 1
        if x1 - x0 < 8 or y1 - y0 < 8:
            continue

        sample_scale = min(1.0, 256.0 / max(x1 - x0, y1 - y0))
        sw = max(8, int(round((x1 - x0) * sample_scale)))
        sh = max(8, int(round((y1 - y0) * sample_scale)))
        fg_small = cv2.resize(warped_fg[y0:y1, x0:x1], (sw, sh), interpolation=cv2.INTER_AREA)
        bg_small = cv2.resize(bg[y0:y1, x0:x1], (sw, sh), interpolation=cv2.INTER_AREA)
        valid_small = cv2.resize(valid[y0:y1, x0:x1].astype(np.float32),
                                 (sw, sh), interpolation=cv2.INTER_LINEAR) > 0.5
        if int(valid_small.sum()) < 100:
            continue
        lab_fg = cv2.cvtColor(fg_small, cv2.COLOR_RGB2LAB).astype(np.float32)
        lab_bg = cv2.cvtColor(bg_small, cv2.COLOR_RGB2LAB).astype(np.float32)
        differences = (lab_bg - lab_fg)[valid_small]
        tile_shifts.append(np.median(differences, axis=0))

    if not tile_shifts:
        return None
    shift = np.median(np.stack(tile_shifts), axis=0) * GLOBAL_COLOR_STRENGTH
    limit = np.asarray(GLOBAL_COLOR_MAX_SHIFT, dtype=np.float32)
    shift = np.clip(shift, -limit, limit).astype(np.float32)
    return shift if float(np.max(np.abs(shift))) >= 0.25 else None

@torch.no_grad()
def _apply_global_lab_shift( fg, shift, edit_mask=None, *, device):
    dev = device
    lab = _sm_rgb_to_lab(fg, dev)
    shift_t = torch.as_tensor(shift, dtype=lab.dtype, device=dev)
    if edit_mask is None:
        lab = lab + shift_t
    else:
        lab = lab + shift_t * _edited_scale(edit_mask, fg.shape, sigma=8.0, device=device)
    return _sm_lab_to_u8(lab)

@torch.no_grad()
def _lab_mean_color_sync( fg, bg, mask_float, edit_mask=None, *, device):
    """整块按 LAB 均值/方差对齐到背景(色差单一的场景)。"""
    sample = _color_sample_mask(mask_float, edit_mask)
    if sample is None:
        return _luminance_color_sync(fg, bg, mask_float, edit_mask=edit_mask, device=device)
    dev = device
    lab_bg = _sm_rgb_to_lab(bg, dev)
    lab_fg = _sm_rgb_to_lab(fg, dev)
    stats = (_sm_as_float(sample, dev) > 0.5)[..., 0]
    bg_values = lab_bg[stats]
    fg_values = lab_fg[stats]
    mean_bg, mean_fg = bg_values.mean(dim=0), fg_values.mean(dim=0)
    std_bg = (torch.quantile(bg_values, 0.9, dim=0)
              - torch.quantile(bg_values, 0.1, dim=0)) / 2.563103
    std_fg = (torch.quantile(fg_values, 0.9, dim=0)
              - torch.quantile(fg_values, 0.1, dim=0)) / 2.563103
    scale = std_bg.clamp_min(1.0) / std_fg.clamp_min(1.0)
    limits = torch.tensor(((0.5, 2.0), (0.8, 1.25), (0.8, 1.25)),
                          dtype=lab_fg.dtype, device=dev)
    scale = scale.clamp(limits[:, 0], limits[:, 1])
    affine = (lab_fg - mean_fg) * scale + mean_bg
    if edit_mask is not None:
        # 均值/方差只统计未编辑像素; 编辑区保留 AI 自己的颜色, 只留少量整体对齐。
        ps = _edited_scale(edit_mask, fg.shape,
                                base=COLOR_LOCAL_EDITED_SCALE, device=device)
        affine = lab_fg + (affine - lab_fg) * ps
    lab_fg = affine
    # 全局仿射只对齐一个均值/方差; 再补一层低频差场, 覆盖空间不均匀的亮度差。
    lab_fg = _apply_lowfreq_lab_field(
        lab_fg, lab_bg, sample, _lowfreq_sigma(fg.shape),
        LOWFREQ_COLOR_MAX_SHIFT, channels=3, edit_mask=edit_mask, device=device)
    return _sm_lab_to_u8(lab_fg)

@torch.no_grad()
def _luminance_color_sync( fg, bg, mask_float, edit_mask=None, *, device):
    """仅平移 LAB 的 L 通道以匹配中位亮度，保留对比度与 a/b 色相。"""
    sample_mask = _color_sample_mask(mask_float, edit_mask)
    fallback = sample_mask is None and edit_mask is not None
    if fallback:
        sample_mask = np.clip(mask_float.astype(np.float32), 0.0, 1.0)
    if sample_mask is None:
        return fg
    if int((sample_mask > 0.5).sum()) < 100:
        return fg
    dev = device
    lab_fg = _sm_rgb_to_lab(fg, dev)
    lab_bg = _sm_rgb_to_lab(bg, dev)
    sample = (_sm_as_float(sample_mask, dev) > 0.5)[..., 0]
    differences = (lab_bg[..., 0:1] - lab_fg[..., 0:1])[sample]
    shift = _sm_np_median(differences)
    l_only = torch.tensor((1.0, 0.0, 0.0), dtype=lab_fg.dtype, device=dev)
    if fallback:
        # 全块一致的亮度偏移是光照差，不是局部改色；非均匀差异继续保护。
        if float(_sm_np_median((differences - shift).abs())) > 3.0:
            return fg
        lab_fg = lab_fg + shift * l_only
    elif edit_mask is None:
        lab_fg = lab_fg + shift * l_only
    else:
        lab_fg = lab_fg + shift * l_only * _edited_scale(
            edit_mask, fg.shape, base=COLOR_LOCAL_EDITED_SCALE, device=device)
    # 中位平移只修整体亮度; 再补低频 L 差场, 处理空间不均匀的亮度差。
    lab_fg = _apply_lowfreq_lab_field(
        lab_fg, lab_bg, sample_mask, _lowfreq_sigma(fg.shape),
        LOWFREQ_COLOR_MAX_SHIFT, channels=1,
        edit_mask=None if fallback else edit_mask, device=device)
    return _sm_lab_to_u8(lab_fg)

def _apply_color_match( fg, bg, mask_float, mode, feather_kernel,
                       edit_mask, apply_mask, grid_weight=False, canvas_sides=None,
    *, device):
    """返回 (处理后的 fg, 是否已完成背景融合)。"""
    if mode == "Patch_based_color":
        if edit_mask is None:
            patch = max(32, int(feather_kernel) * 2)
            overlap = max(16, int(feather_kernel))
            band_width = max(15, int(feather_kernel))
        else:
            patch = int(np.clip(round(min(fg.shape[:2]) * PATCH_COLOR_PATCH_FRAC),
                                PATCH_COLOR_PATCH_MIN, PATCH_COLOR_PATCH_MAX))
            overlap = max(16, patch // 2)
            band_width = max(15, patch // 3)
        if edit_mask is not None and _color_sample_mask(mask_float, edit_mask) is None:
            fg = _luminance_color_sync(fg, bg, mask_float, edit_mask=edit_mask, device=device)
        fg = boundary_aware_color_sync(
            fg, bg, mask_float, band_width=band_width, edit_mask=edit_mask, device=device)
        try:
            fg = patch_based_color_sync(
                fg, bg, mask_float, patch_size=patch, overlap=overlap,
                edit_mask=edit_mask, apply_mask=apply_mask, grid_weight=grid_weight, device=device)
        except Exception as e:
            print(f"[Smart Merge] Patch 色彩匹配失败: {e}, 降级 Alpha | "
                  f"Patch color sync failed: {e}, downgraded to Alpha")
        return fg, False

    if mode == "LAB_Mean":
        return _lab_mean_color_sync(fg, bg, mask_float, edit_mask=edit_mask, device=device), False

    if mode in ("Laplacian Pyramid Blend", "SeamlessClone (PS Auto Blend)"): 
        fg = _luminance_color_sync(fg, bg, mask_float, edit_mask=edit_mask, device=device)

    if mode == "Laplacian Pyramid Blend":
        levels = 3 if feather_kernel < 16 else (5 if feather_kernel > 64 else 4)
        soft = make_edge_safe_soft_mask(mask_float, feather_kernel)
        # 画布边没有外侧可羽化, 羽化内推会让最粗层选到背景低频、露出浅色带; 这里只给最粗层
        # 在画布侧用未羽化 raw mask 的面积平均做边界条件, 不动 alpha / split grid 形状。
        canvas_mask = (np.clip(mask_float.astype(np.float32), 0.0, 1.0)
                       if canvas_sides is not None and any(canvas_sides) else None)
        try:
            return laplacian_pyramid_blend(
                fg, bg, soft, levels, canvas_mask=canvas_mask,
                canvas_sides=canvas_sides), True
        except Exception as e:
            print(f"[Smart Merge] 拉普拉斯金字塔融合失败: {e}, 降级 Alpha | "
                  f"Laplacian pyramid blend failed: {e}, downgraded to Alpha")
            return fg, False

    if mode == "SeamlessClone (PS Auto Blend)":
        return seamless_clone_crop(fg, bg, mask_float)

    return fg, False

def _color_sample_mask(mask_float, edit_mask=None):
    base = np.clip(mask_float.astype(np.float32), 0.0, 1.0)
    if edit_mask is None:
        return base
    if edit_mask.shape != base.shape:
        return None
    reliable = base * (edit_mask > 0.5).astype(np.float32)
    if float((reliable > 0.5).sum()) < 100.0:
        return None
    return reliable

@torch.no_grad()
def _edited_scale( edit_mask, shape, sigma=8.0, base=None, *, device):
    """未编辑置信度 → 校正强度系数: 未编辑处 1, 已编辑处 base。
    编辑区内的校正估计没有内容对应关系, 满强度施加会把 AI 有意的颜色拉向背景。"""
    if edit_mask is None:
        return None
    h, w = shape[:2]
    em = _sm_as_float(edit_mask, device).clamp(0.0, 1.0)
    em = _sm_fast_blur(_sm_fit(em, h, w), sigma).clamp(0.0, 1.0)
    # 暗部改色的 em 只有 0.01~0.05; 线性映射仍会透出百分之几的 bg 校正, 而阴影处
    # bg-fg 可差 40+ L, 几个百分点就是可见的发灰。明确已编辑段归零, 明确未编辑段
    # 直接到 1, 中间平滑过渡。
    t = ((em - 0.2) / 0.6).clamp(0.0, 1.0)
    t = t * t * (3.0 - 2.0 * t)
    base = float(PATCH_COLOR_EDITED_SCALE if base is None else base)
    return base + (1.0 - base) * t

def _lowfreq_sigma(shape):
    """低频差场的尺度: 跟随裁块短边, 只补缓变色偏而非细节。"""
    h, w = shape[:2]
    return float(np.clip(0.06 * min(h, w), 10.0, 64.0))

@torch.no_grad()
def _apply_lowfreq_lab_field( lab_fg, lab_bg, weight, sigma, limit,
                             channels=3, edit_mask=None,
    *, device):
    """把 fg 的缓变 LAB 分量拉向 bg, 修正空间不均匀的色偏。

    归一化卷积估计 bg-fg 的低频差, 边界不衰减; 再减去常数分量 —— 整体色偏
    已由均值/中位平移处理, 这里只保留空间变化。weight 同时用于排除无效/已编辑
    像素; channels=1 时只改 L。
    """
    sigma = float(max(sigma, 0.0))
    if sigma < 0.5 or weight is None:
        return lab_fg
    dev = lab_fg.device
    ch = 1 if int(channels) == 1 else 3
    w = _sm_as_float(np.clip(weight, 0.0, 1.0), dev)
    wsum = w.sum()
    if float(wsum) < 1.0:
        return lab_fg
    fg_c = lab_fg[..., :ch]
    bg_c = lab_bg[..., :ch]
    num = _sm_fast_blur((bg_c - fg_c) * w, sigma)
    den = _sm_fast_blur(w, sigma)
    field = torch.where(den > 1e-3, num / den.clamp_min(1e-3), torch.zeros_like(num))
    field = field - (field * w).sum(dim=(1, 2), keepdim=True) / wsum
    lim = torch.tensor(tuple(limit[:ch]), dtype=field.dtype, device=dev)
    field = torch.clamp(field, -lim, lim)
    if edit_mask is not None:
        field = field * _edited_scale(
            edit_mask, lab_fg.shape[1:], sigma=max(4.0, sigma / 3.0),
            base=COLOR_LOCAL_EDITED_SCALE, device=device)
    if ch == 1:
        out = lab_fg.clone()
        out[..., 0:1] = lab_fg[..., 0:1] + field
        return out
    return lab_fg + field

@torch.no_grad()
def patch_based_color_sync( fg, bg, mask_float, patch_size=64, overlap=32,
                           edit_mask=None, apply_mask=None, grid_weight=False,
    *, device):
    """默认使用旧版全强度校正；提供 edit_mask 时启用鲁棒的改色保护校正。"""
    h, w = fg.shape[:2]
    protected = edit_mask is not None
    sample_mask = _color_sample_mask(mask_float, edit_mask)
    if sample_mask is None or float(sample_mask.max()) <= 0.01:
        return fg
    sample_bool = sample_mask > 0.5
    mask_bool = mask_float > 0.5
    if int(mask_bool.sum()) < 100 or int(sample_bool.sum()) < 100:
        return fg

    patch_size = max(16, min(int(patch_size), h, w))
    overlap = max(0, min(int(overlap), patch_size - 1))
    step = max(1, patch_size - overlap)

    dev = device
    lab_fg = _sm_rgb_to_lab(fg, dev)
    lab_bg = _sm_rgb_to_lab(bg, dev)
    if protected:
        lp_sigma = max(2.0, patch_size / 4.0)
        diff = _sm_fast_blur(lab_bg, lp_sigma) - _sm_fast_blur(lab_fg, lp_sigma)
        diff = diff[0].cpu().numpy()
    else:
        diff = (lab_bg - lab_fg)[0].cpu().numpy()

    y_positions = list(range(0, h - patch_size + 1, step))
    x_positions = list(range(0, w - patch_size + 1, step))
    if not y_positions or y_positions[-1] + patch_size < h:
        y_positions.append(max(0, h - patch_size))
    if not x_positions or x_positions[-1] + patch_size < w:
        x_positions.append(max(0, w - patch_size))
    y_positions = sorted(set(y_positions))
    x_positions = sorted(set(x_positions))

    # 逐块统计留在 numpy: 每块只有几十个元素的统计, torch/GPU 的调度与同步开销更大
    hann = np.hanning(patch_size)[:, None] * np.hanning(patch_size)[None, :]
    if protected:
        hann = hann.astype(np.float32)
    tau = PATCH_COLOR_MAD_TAU
    weight_map = np.zeros((h, w), dtype=np.float32)
    correction_sum = np.zeros((h, w, 3), dtype=np.float32)
    min_cov = float(PATCH_COLOR_MIN_COVERAGE) if protected else 0.1
    valid_patches = 0

    for y in y_positions:
        for x in x_positions:
            y2, x2 = y + patch_size, x + patch_size
            patch_sel = sample_bool[y:y2, x:x2]
            if float(patch_sel.mean()) < min_cov:
                continue
            if protected:
                sel = patch_sel[::2, ::2]
                if int(sel.sum()) >= 30:
                    diff_patch = diff[y:y2:2, x:x2:2]
                else:
                    diff_patch = diff[y:y2, x:x2]
                    sel = patch_sel
                if int(sel.sum()) < 30:
                    continue
                values = diff_patch[sel]
                patch_correction = np.median(values, axis=0)
                mad = np.median(np.abs(values - patch_correction), axis=0)
                conf = float(np.exp(-(mad / tau) ** 2).min())
                if conf < 0.02:
                    continue
            else:
                values = diff[y:y2, x:x2][patch_sel]
                sorted_diff = np.sort(values, axis=0)
                trim = int(len(sorted_diff) * 0.1)
                trimmed = sorted_diff[trim:-trim] if trim > 0 else sorted_diff
                patch_correction = trimmed.mean(axis=0)
                conf = 1.0
            patch_weight = hann * patch_sel.astype(np.float32) * conf
            correction_sum[y:y2, x:x2] += patch_correction[None, None, :] * patch_weight[:, :, None]
            weight_map[y:y2, x:x2] += patch_weight
            valid_patches += 1

    if valid_patches == 0:
        if protected:
            _sm_log("[Smart Merge] Patch 色彩: 无可信分块, 跳过校正 | no reliable patch, color sync skipped")
            return fg
        stats_mask = (_sm_as_float(mask_float, dev) > 0.5)[..., 0]
        shift = (_sm_np_median(lab_bg[stats_mask])
                 - _sm_np_median(lab_fg[stats_mask]))
        return _sm_lab_to_u8(lab_fg + shift)

    weight_map = torch.from_numpy(weight_map).to(dev)
    correction_sum = torch.from_numpy(correction_sum).to(dev)

    if protected:
        valid = weight_map > 1e-8
        field = (correction_sum / weight_map[..., None].clamp_min(1e-8)).unsqueeze(0)
        fill_sigma = max(4.0, patch_size / 2.0)
        for c in range(3):
            vf = valid[None, ..., None].float()
            num = _sm_fast_blur(field[..., c:c + 1] * vf, fill_sigma)
            den = _sm_fast_blur(vf, fill_sigma)
            filled = torch.where(den > 1e-6, num / den.clamp_min(1e-6), torch.zeros_like(num))
            field[..., c] = torch.where(valid, field[..., c], filled[..., 0])
        field = _sm_fast_blur(field, max(2.0, patch_size / 3.0))
        max_shift = torch.tensor(PATCH_COLOR_MAX_SHIFT, dtype=field.dtype, device=dev)
        field = field.clamp(-max_shift, max_shift)
        edited_scale = _edited_scale(
            edit_mask, fg.shape, sigma=max(4.0, patch_size / 4.0),
            base=COLOR_LOCAL_EDITED_SCALE, device=device)
        if grid_weight:
            field = field * edited_scale
        else:
            apply_w = apply_mask if apply_mask is not None else mask_float
            apply_w = np.clip(np.asarray(apply_w, dtype=np.float32), 0.0, 1.0)
            if apply_w.shape != mask_bool.shape:
                apply_w = mask_bool.astype(np.float32)
            aw = _sm_fit(_sm_as_float(apply_w, dev).clamp(0.0, 1.0), h, w) * edited_scale
            peak = float(aw.max())
            if peak > 1e-6:
                aw = aw / peak
            field = field * aw
        _sm_log(f"[Smart Merge] Patch 色彩: {valid_patches} 有效块, "
                   f"限幅 ±{max_shift.tolist()} | {valid_patches} valid patches")
    else:
        field = (correction_sum / weight_map[..., None].clamp_min(1e-6)).unsqueeze(0)
        field = _sm_median(field, 5)
        ksize = overlap // 2 * 2 + 1
        field = _sm_blur_ksize(field, ksize)
        if grid_weight:
            valid = (weight_map > 1e-6).float()
            num = _sm_blur_ksize(field * valid[None, ..., None], ksize)
            den = _sm_blur_ksize(valid[None, ..., None], ksize)
            filled = num / den.clamp_min(1e-6)
            field = torch.where((den > 1e-6).expand_as(field), filled, field)
        else:
            field = field * _sm_as_float(mask_float, dev).clamp(0.0, 1.0)

    return _sm_lab_to_u8(lab_fg + field)

@torch.no_grad()
def boundary_aware_color_sync( fg, bg, mask_float, band_width=21, strength=1.0, edit_mask=None, *, device):
    h, w = fg.shape[:2]
    protected = edit_mask is not None
    sample_mask = _color_sample_mask(mask_float, edit_mask)
    if sample_mask is None:
        return fg
    if np.sum((np.clip(mask_float, 0, 1) * 255).astype(np.uint8) > 128) < 100:
        return fg

    dev = device
    lab_fg = _sm_rgb_to_lab(fg, dev)
    lab_bg = _sm_rgb_to_lab(bg, dev)
    sel = _sm_as_float(sample_mask, dev) > 0.5

    med_size = max(7, (band_width // 2) | 1)
    if protected:
        med_size = min(med_size, h if h % 2 else h - 1, w if w % 2 else w - 1)
        if med_size >= 3:
            lab_fg_med = _sm_fast_median(lab_fg.clamp(0.0, 255.0).floor(), med_size)
            lab_bg_med = _sm_fast_median(lab_bg.clamp(0.0, 255.0).floor(), med_size)
        else:
            lab_fg_med = lab_fg
            lab_bg_med = lab_bg
    else:
        # 两种实现逐值等价: CPU 上 cv2 直方图中值快两个数量级,
        # GPU 上保留 torch 中值, 避免来回搬运。
        if dev.type == "cpu":
            lab_fg_med = _sm_u8_median(lab_fg.clamp(0.0, 255.0).floor(), med_size)
            lab_bg_med = _sm_u8_median(lab_bg.clamp(0.0, 255.0).floor(), med_size)
        else:
            lab_fg_med = _sm_median(lab_fg.clamp(0.0, 255.0).floor(), med_size)
            lab_bg_med = _sm_median(lab_bg.clamp(0.0, 255.0).floor(), med_size)

    masked_diff = (lab_bg_med - lab_fg_med) * sel.float()
    ksz = min(max(31, (band_width * 3) | 1), 151)
    gsigma = max(2.0, 0.15 * ksz)
    correction_field = torch.zeros_like(lab_fg)

    for c in range(3):
        diff_ch = masked_diff[..., c:c + 1]
        # 差场本身是平滑场: 大 sigma 走降采样模糊, 与全分辨率大核高斯等价
        diff_smooth = _sm_fast_blur(diff_ch, gsigma)
        diff_sqr_smooth = _sm_fast_blur(diff_ch ** 2, gsigma)
        variance = (diff_sqr_smooth - diff_smooth ** 2).clamp_min(0.0)

        pos = variance[:, ::4, ::4, :] if protected else variance
        pos = pos[pos > 0]
        denom = _sm_np_median(pos) if pos.numel() > 0 else torch.tensor(1.0, device=dev)
        reliability = torch.exp(-variance / (denom + 1e-6)) * sel.float()

        weighted_num = _sm_fast_blur(diff_ch * reliability, gsigma)
        weighted_den = _sm_fast_blur(reliability, gsigma) + 1e-6
        correction_field[..., c:c + 1] = weighted_num / weighted_den

    if protected:
        dist = cv2.distanceTransform((mask_float > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        decay = 0.4 + 0.6 * torch.exp(
            -_sm_as_float(dist, dev) / max(float(band_width), 1.0))
        correction_field = correction_field * _edited_scale(
            edit_mask, fg.shape, sigma=max(4.0, band_width / 4.0),
            base=COLOR_LOCAL_EDITED_SCALE, device=device)
        soft_mask = _sm_fast_blur(_sm_as_float(mask_float, dev),
                                  max(2.0, 0.15 * (band_width | 1)))
    else:
        dist = cv2.distanceTransform(1 - (mask_float > 0.5).astype(np.uint8), cv2.DIST_L2, 5)
        max_dist = float(dist.max()) + 1e-6
        decay = (0.4 + 0.6 * (1.0 - _sm_as_float(dist, dev) / max_dist)).clamp(0.4, 1.0)
        soft_ksize = max(3, int(band_width) | 1)
        soft_sigma = max(0.1, 0.3 * ((soft_ksize - 1) * 0.5 - 1.0) + 0.8)
        soft_mask = _sm_fast_blur(_sm_as_float(mask_float, dev), soft_sigma)

    strength_vec = torch.tensor((0.6, 1.0, 1.0), dtype=lab_fg.dtype, device=dev) * strength
    lab_corrected = lab_fg + correction_field * decay * soft_mask * strength_vec
    return _sm_lab_to_u8(lab_corrected)

