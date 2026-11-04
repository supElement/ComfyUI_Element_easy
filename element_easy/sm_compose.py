# -*- coding: utf-8 -*-
# 融合与混合 / compositing & blending

import cv2
import numpy as np


def _tile_weight_local(tile_info, bbox, feather_frac):
    """fade 使用 smoothstep 过渡，保持宽度与互补性并柔化两端。"""
    xmin, ymin, xmax, ymax = bbox
    bh, bw = ymax - ymin, xmax - xmin

    tx = int(tile_info.get("x", 0))
    ty = int(tile_info.get("y", 0))
    tw = int(tile_info.get("width", 1))
    th = int(tile_info.get("height", 1))

    ffr = float(max(0.0, min(1.0, feather_frac)))
    ft = float(tile_info.get("fade_top", 0))    * ffr
    fb = float(tile_info.get("fade_bottom", 0)) * ffr
    fl = float(tile_info.get("fade_left", 0))   * ffr
    fr = float(tile_info.get("fade_right", 0))  * ffr

    weight = np.ones((bh, bw), dtype=np.float32)
    ys = np.arange(ymin, ymax, dtype=np.float32)[:, None] + 0.5
    xs = np.arange(xmin, xmax, dtype=np.float32)[None, :] + 0.5

    def _softstep(t):
        t = np.clip(t, 0.0, 1.0)
        return t * t * (3.0 - 2.0 * t)

    if ft > 0:
        weight = np.minimum(weight, _softstep((ys - ty) / ft))
    if fb > 0:
        weight = np.minimum(weight, _softstep((ty + th - ys) / fb))
    if fl > 0:
        weight = np.minimum(weight, _softstep((xs - tx) / fl))
    if fr > 0:
        weight = np.minimum(weight, _softstep((tx + tw - xs) / fr))

    return weight[:, :, None]

def _feather_tile_mask_like_etm(crop_mask_float, bbox, h_bg, w_bg,
                                 fade_t, fade_b, fade_l, fade_r,
                                 overlap, feather_frac):
    """精确复刻 ElementTileMerge 的 tile_mask 羽化 (nodes_merge.py L321-350)：
      1) 贴画布边侧 pad replicate (深度=overlap)
      2) 高斯模糊 (sigma = feather_px / 3)
      3) 切回 bbox 尺寸
    feather_px = max_fade * feather_frac if max_fade>0 else overlap * feather_frac
    返回 (h_crop, w_crop, 1) float32。"""
    xmin, ymin, xmax, ymax = bbox
    h_crop, w_crop = ymax - ymin, xmax - xmin

    max_fade = max(float(fade_t), float(fade_b), float(fade_l), float(fade_r))
    if max_fade > 0:
        feather_px = max(1.0, max_fade * feather_frac)
    else:
        feather_px = max(1.0, float(overlap) * feather_frac)

    # 贴画布边 pad（同 nodes_merge.py L325-328: x<=0 / x+w>=work_w 等条件）
    pad_l = int(overlap) if xmin <= 0    else 0
    pad_r = int(overlap) if xmax >= w_bg else 0
    pad_t = int(overlap) if ymin <= 0    else 0
    pad_b = int(overlap) if ymax >= h_bg else 0

    m = crop_mask_float.astype(np.float32)
    if pad_l or pad_r or pad_t or pad_b:
        m = cv2.copyMakeBorder(m, pad_t, pad_b, pad_l, pad_r, cv2.BORDER_REPLICATE)

    if feather_px > 1.0:
        sigma = feather_px / 3.0
        m = cv2.GaussianBlur(m, (0, 0), sigma)

    if pad_l or pad_r or pad_t or pad_b:
        m = m[pad_t:pad_t + h_crop, pad_l:pad_l + w_crop]

    return m[:, :, np.newaxis]

def _place_edit_mask(edit_mask, tile_info, bbox):
    """把分块空间的锁边 edit_mask 贴到 bbox 画布上（与 fade 权重同一 grid 锚点）。

    edit_mask 里 0 = 采样时未重绘的锁定带，合成时必须剔除。这里按 grid 矩形
    重采样后硬切，不参与高斯羽化——羽化会把锁定带内容重新漏回来。
    """
    em = np.asarray(edit_mask, dtype=np.float32)
    if em.ndim != 2 or em.size == 0:
        return None
    if float(em.min()) >= 0.999:
        return None

    xmin, ymin, xmax, ymax = bbox
    bw, bh = xmax - xmin, ymax - ymin
    if bw <= 0 or bh <= 0:
        return None

    tw = max(1, int(round(float(tile_info.get("width", em.shape[1])))))
    th = max(1, int(round(float(tile_info.get("height", em.shape[0])))))
    if em.shape[1] != tw or em.shape[0] != th:
        em = cv2.resize(em, (tw, th), interpolation=cv2.INTER_LINEAR)

    out = np.ones((bh, bw), dtype=np.float32)
    gx = int(round(float(tile_info.get("x", 0)) - xmin))
    gy = int(round(float(tile_info.get("y", 0)) - ymin))
    sx0, sy0 = max(0, -gx), max(0, -gy)
    dx0, dy0 = max(0, gx), max(0, gy)
    dx1, dy1 = min(bw, gx + tw), min(bh, gy + th)
    if dx1 <= dx0 or dy1 <= dy0:
        return out[:, :, None]
    dh, dw = dy1 - dy0, dx1 - dx0
    out[dy0:dy1, dx0:dx1] = em[sy0:sy0 + dh, sx0:sx0 + dw]
    return out[:, :, None]


def _grid_tile_weight( tile_info, bbox, crop_mask, h_bg, w_bg, overlap, feather_px):
    """grid 分块权重 = 贴边 fade 渐变 × 分块 mask 羽化 × 锁边剔除。

    feather_px 是过渡带的**像素宽度**: 内部桥接到 ETM 的 feather 比例
    (feather = feather_px / overlap), 两种模式含义一致。
    """
    ti = dict(tile_info)
    if overlap > 0:
        for k in ("fade_top", "fade_bottom", "fade_left", "fade_right"):
            if ti.get(k, 0) > 0:
                ti[k] = overlap

    frac = max(0.0, min(1.0, float(feather_px) / float(max(overlap, 1))))
    fade_w = _tile_weight_local(ti, bbox, frac)
    mask_f = _feather_tile_mask_like_etm(
        crop_mask, bbox, h_bg, w_bg,
        ti.get("fade_top", 0), ti.get("fade_bottom", 0),
        ti.get("fade_left", 0), ti.get("fade_right", 0), overlap, frac)
    weight = fade_w * mask_f
    edit_w = _place_edit_mask(ti.get("edit_mask"), ti, bbox)
    if edit_w is not None:
        weight = weight * edit_w
    return weight

def _alpha_blend_crop( fg, bg, mask_float, feather_kernel):
    """羽化 alpha 混合: 分块与背景按软 mask 过渡。"""
    soft = make_edge_safe_soft_mask(mask_float, feather_kernel)[:, :, None]
    blended = fg.astype(np.float32) * soft + bg.astype(np.float32) * (1.0 - soft)
    return np.clip(blended, 0, 255).astype(np.uint8)

def make_edge_safe_soft_mask( mask_float, feather_kernel):
    h, w = mask_float.shape[:2]
    mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)

    if feather_kernel <= 0:
        return mask_float.astype(np.float32)

    pad = max(feather_kernel * 3, 30)
    padded = cv2.copyMakeBorder(mask_8u, pad, pad, pad, pad, cv2.BORDER_REPLICATE)

    erode_size = max(3, int(feather_kernel))
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
    eroded = cv2.erode(padded, kernel, iterations=1)

    blur_size = (int(feather_kernel) * 2) | 1
    blurred = cv2.GaussianBlur(eroded.astype(np.float32) / 255.0, (blur_size, blur_size), 0)

    soft = blurred[pad:pad + h, pad:pad + w]
    soft = np.minimum(soft, mask_float.astype(np.float32))
    return soft

def seamless_clone_crop(fg, bg, mask_float):
    mask_8u = (np.clip(mask_float, 0, 1) * 255).astype(np.uint8)
    mask_8u = cv2.erode(mask_8u, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    bx, by, bw, bh = cv2.boundingRect(mask_8u)
    h, w = mask_8u.shape
    safe_pad = 5
    if not (bw > 10 and bh > 10 and bx > safe_pad and by > safe_pad
            and bx + bw < w - safe_pad and by + bh < h - safe_pad):
        return fg, False
    x1, y1 = bx - safe_pad, by - safe_pad
    x2, y2 = bx + bw + safe_pad, by + bh + safe_pad
    center = ((x2 - x1) // 2, (y2 - y1) // 2)
    try:
        cloned = cv2.seamlessClone(
            fg[y1:y2, x1:x2], bg[y1:y2, x1:x2], mask_8u[y1:y2, x1:x2],
            center, cv2.NORMAL_CLONE
        )
    except Exception as e:
        print(f"[Smart Merge] 泊松融合失败: {e} | Poisson seamless clone failed: {e}")
        return fg, False
    result = bg.copy()
    result[y1:y2, x1:x2] = cloned
    return result, True

def laplacian_pyramid_blend( img1, img2, mask, num_levels=4,
                            canvas_mask=None, canvas_sides=None):
    h, w = img1.shape[:2]
    divisor = 2 ** num_levels
    pad_h = (divisor - h % divisor) % divisor
    pad_w = (divisor - w % divisor) % divisor

    if pad_h > 0 or pad_w > 0:
        img1 = cv2.copyMakeBorder(img1, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        img2 = cv2.copyMakeBorder(img2, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        mask = cv2.copyMakeBorder(mask, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)
        if canvas_mask is not None:
            canvas_mask = cv2.copyMakeBorder(canvas_mask, 0, pad_h, 0, pad_w, cv2.BORDER_REFLECT)

    if mask.dtype != np.float32:
        mask = mask.astype(np.float32)
    if mask.max() > 1.0:
        mask = mask / 255.0
    if len(mask.shape) == 3:
        mask = mask[:, :, 0]

    img1_f = img1.astype(np.float32)
    img2_f = img2.astype(np.float32)

    gp1, gp2 = [img1_f], [img2_f]
    for i in range(num_levels):
        gp1.append(cv2.pyrDown(gp1[-1]))
        gp2.append(cv2.pyrDown(gp2[-1]))

    lp1 = [gp1[num_levels]]
    lp2 = [gp2[num_levels]]
    for i in range(num_levels, 0, -1):
        size = (gp1[i - 1].shape[1], gp1[i - 1].shape[0])
        G1_up = cv2.pyrUp(gp1[i], dstsize=size)
        G2_up = cv2.pyrUp(gp2[i], dstsize=size)
        lp1.append(gp1[i - 1] - G1_up)
        lp2.append(gp2[i - 1] - G2_up)

    lp_blend = []
    for i in range(num_levels + 1):
        l1 = lp1[i]
        l2 = lp2[i]
        m = cv2.resize(mask, (l1.shape[1], l1.shape[0]))
        if i == 0:
            if canvas_mask is not None and canvas_sides is not None:
                # 画布侧最粗格改用 raw mask 的面积平均: 只看点采样会在离边 1~2px
                # 处取到羽化/掉边后的低值, 面积平均才反映这一格里内容是否贴到边。
                m_raw = cv2.resize(canvas_mask, (l1.shape[1], l1.shape[0]),
                                   interpolation=cv2.INTER_AREA)
                l_cut, t_cut, r_cut, b_cut = canvas_sides
                if l_cut:
                    m[:, :1] = np.maximum(m[:, :1], m_raw[:, :1])
                if t_cut:
                    m[:1, :] = np.maximum(m[:1, :], m_raw[:1, :])
                if r_cut:
                    m[:, -1:] = np.maximum(m[:, -1:], m_raw[:, -1:])
                if b_cut:
                    m[-1:, :] = np.maximum(m[-1:, :], m_raw[-1:, :])
            if m.ndim == 2:
                m = m[:, :, np.newaxis]
            blended = l1 * m + l2 * (1.0 - m)
        else:
            m_hard = (m > 0.5).astype(np.float32)
            if m_hard.ndim == 2:
                m_hard = m_hard[:, :, np.newaxis]
            blended = np.where(m_hard > 0.5, l1, l2)
        lp_blend.append(blended)

    img_blend = lp_blend[0]
    for i in range(1, num_levels + 1):
        size = (lp_blend[i].shape[1], lp_blend[i].shape[0])
        img_blend = cv2.pyrUp(img_blend, dstsize=size) + lp_blend[i]

    img_blend = np.clip(img_blend, 0, 255).astype(np.uint8)

    if pad_h > 0 or pad_w > 0:
        img_blend = img_blend[:h, :w]

    return img_blend

