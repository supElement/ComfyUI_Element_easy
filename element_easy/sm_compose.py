# -*- coding: utf-8 -*-
# 融合与混合 / compositing & blending

import cv2
import numpy as np


_BG_KINDS = {"gap", "fallback", "unified"}


def _is_bg(tile_info):
    """背景块：锁定带里是同一底图的低增强版本，不能当“未编辑”内容剔除。"""
    return tile_info.get("kind") in _BG_KINDS


def _lock_band(tile_info, edge):
    bands = tile_info.get("edit_bands") or tile_info.get("lock_bands")
    if not bands:
        return 0.0
    try:
        return max(0.0, float(bands[edge]))
    except (TypeError, IndexError, ValueError):
        return 0.0


def _blend_pads(tiles):
    """同层相邻手绘块每边的 (near, far)，与 ElementTileMerge._blend_pads 一致。

    near = 本块该边锁定带宽度，far = 对侧同层邻块朝本块的锁定带宽度。过渡带
    因此只落在两块都真正重绘过的区间里；背景块不剔除，pads 恒为 0。
    """
    n = len(tiles)
    if n == 0:
        return []
    own = [tuple(0.0 if _is_bg(t) else _lock_band(t, e) for e in range(4)) for t in tiles]
    out = []
    for i, t in enumerate(tiles):
        xi, yi, wi, hi = t["x"], t["y"], t["width"], t["height"]
        pads = [(own[i][e], 0.0) for e in range(4)]
        best = [None] * 4
        for j, o in enumerate(tiles):
            if j == i or _is_bg(t) or _is_bg(o):
                continue
            if t.get("layer") != o.get("layer"):
                continue
            xj, yj, wj, hj = o["x"], o["y"], o["width"], o["height"]
            y_over = min(yi + hi, yj + hj) - max(yi, yj)
            x_over = min(xi + wi, xj + wj) - max(xi, xj)
            if x_over <= 0 or y_over <= 0:
                continue
            cands = []
            if xj > xi:
                cands.append((2, y_over, own[j][0]))
            if xj < xi:
                cands.append((0, y_over, own[j][2]))
            if yj > yi:
                cands.append((3, x_over, own[j][1]))
            if yj < yi:
                cands.append((1, x_over, own[j][3]))
            for edge, olap, far_b in cands:
                if best[edge] is None or olap > best[edge][0] + 1e-6:
                    best[edge] = (olap, far_b)
        for edge in range(4):
            if best[edge] is not None:
                pads[edge] = (own[i][edge], best[edge][1])
        out.append(tuple((float(a), float(b)) for a, b in pads))
    return out


def _ramp_side(dist, fade, pads, frac):
    """单侧权重：50% 落在 fade/2（手绘框边），向外止于 near、向内止于 fade-far。"""
    fade = float(fade)
    if fade <= 0:
        return np.ones_like(dist, dtype=np.float32)
    near = max(0.0, float(pads[0]))
    far = max(0.0, float(pads[1]))
    if near + far > fade:
        s = fade / (near + far) if fade > 0 else 0.0
        near, far = near * s, far * s
    mid = fade * 0.5
    a_out = max(0.0, mid - near)
    a_in = max(0.0, fade - far - mid)
    x = dist - mid
    if frac <= 1e-6:
        return (x >= 0).astype(np.float32)
    hw = np.where(x >= 0, a_in, a_out) * frac
    t = np.clip(0.5 + x / (2.0 * np.maximum(hw, 1e-6)), 0.0, 1.0)
    return (t * t * (3.0 - 2.0 * t)).astype(np.float32)


def _axis_weight(pos, start, size, fade_start, fade_end, pads_start, pads_end, frac):
    size = float(size)
    fade_start = float(fade_start)
    fade_end = float(fade_end)
    if fade_start + fade_end > size:
        s = size / (fade_start + fade_end)
        fade_start *= s
        fade_end *= s
        pads_start = tuple(p * s for p in pads_start)
        pads_end = tuple(p * s for p in pads_end)
    d_start = (pos + 0.5) - start
    d_end = (start + size) - (pos + 0.5)
    return (_ramp_side(d_start, fade_start, pads_start, frac) *
            _ramp_side(d_end, fade_end, pads_end, frac))


def _tile_weight_etm(tile_info, bbox, frac):
    """ElementTileMerge 的居中斜坡：两条轴向斜坡的乘积，50% 落在 fade/2。"""
    xmin, ymin, xmax, ymax = bbox
    xs = np.arange(xmin, xmax, dtype=np.float32)[None, :]
    ys = np.arange(ymin, ymax, dtype=np.float32)[:, None]
    tx = float(tile_info.get("x", 0))
    ty = float(tile_info.get("y", 0))
    tw = float(tile_info.get("width", 1))
    th = float(tile_info.get("height", 1))
    pads = tile_info.get("blend_pads") or ((0.0, 0.0),) * 4
    ramp_x = _axis_weight(xs, tx, tw, tile_info.get("fade_left", 0),
                          tile_info.get("fade_right", 0), pads[0], pads[2], frac)
    ramp_y = _axis_weight(ys, ty, th, tile_info.get("fade_top", 0),
                          tile_info.get("fade_bottom", 0), pads[1], pads[3], frac)
    return (ramp_y * ramp_x)[:, :, None]


def _restore_canvas_inset(tile_info, overlap):
    """手绘框离画布边还有外扩留白时补回该边过渡：宽度 = 2 × 留白。"""
    lr = tile_info.get("layer_region")
    if not lr:
        return
    x = float(tile_info.get("x", 0))
    y = float(tile_info.get("y", 0))
    w = float(tile_info.get("width", 1))
    h = float(tile_info.get("height", 1))
    lx, ly, lw, lh = (float(v) for v in lr)
    for key, inset in (("fade_left", lx - x), ("fade_top", ly - y),
                       ("fade_right", (x + w) - (lx + lw)),
                       ("fade_bottom", (y + h) - (ly + lh))):
        if tile_info.get(key, 0) <= 0 and inset > 1:
            tile_info[key] = min(float(overlap), 2.0 * inset)


def _corner_ramp_etm(weight, tile_info, bbox, overlap, frac):
    """圆角权重：内部角按到圆弧的距离径向渐变（与直边同一套 a_in/a_out），
    贴画布边的角用外扩软轮廓模糊后取最小。"""
    lr = tile_info.get("layer_region")
    radii = [int(tile_info.get(k, 0) or 0) for k in
             ("radius_tl", "radius_tr", "radius_bl", "radius_br")]
    if not lr or max(radii) <= 0:
        return weight
    if float(overlap) * 0.5 <= 0.0:
        return weight

    xmin, ymin, xmax, ymax = bbox
    lx, ly, lw, lh = (float(v) for v in lr)
    bx2, by2 = lx + lw, ly + lh
    f = max(0.0, min(1.0, float(frac)))
    pads = tile_info.get("blend_pads") or ((0.0, 0.0),) * 4
    fades = [float(tile_info.get(k, 0) or 0) for k in
             ("fade_left", "fade_top", "fade_right", "fade_bottom")]

    def avail(edge):
        # 与 _centered_axis_ramp 同宽：手绘边到剔除边界的距离
        fade = fades[edge]
        near, far = float(pads[edge][0]), float(pads[edge][1])
        mid = fade * 0.5
        return max(0.0, mid - near), max(0.0, fade - far - mid)

    cf = float(tile_info.get("corner_feather", 0) or 0)
    if cf > 1e-6:
        sil_feather = max(1.0, cf)
    else:
        sil_feather = max(1.0, 0.5 * max(fades) * f, 0.5 * float(overlap) * f)
    sil_sigma = sil_feather / 3.0
    sil_pad = max(1, int(round(sil_sigma * 3.0)))

    corners = (
        (radii[0], lx + radii[0], ly + radii[0], 0, 1, "tl"),
        (radii[1], bx2 - radii[1], ly + radii[1], 2, 1, "tr"),
        (radii[2], lx + radii[2], by2 - radii[2], 0, 3, "bl"),
        (radii[3], bx2 - radii[3], by2 - radii[3], 2, 3, "br"),
    )
    for r, cx, cy, e_h, e_v, where in corners:
        if r <= 0:
            continue

        if fades[e_h] <= 0 and fades[e_v] <= 0:
            # 贴画布边：手绘圆弧按 tile mask 的 sigma 模糊，边界补 0，50% 落在手绘弧上
            wide = r + sil_feather + sil_pad + 2
            if where in ("tl", "bl"):
                x_lo, x_hi = cx - wide, cx + sil_pad + 2
            else:
                x_lo, x_hi = cx - sil_pad - 2, cx + wide
            if where in ("tl", "tr"):
                y_lo, y_hi = cy - wide, cy + sil_pad + 2
            else:
                y_lo, y_hi = cy - sil_pad - 2, cy + wide
            wx0, wx1 = int(x_lo), int(x_hi) + 1
            wy0, wy1 = int(y_lo), int(y_hi) + 1
            x0, x1 = max(xmin, wx0), min(xmax, wx1)
            y0, y1 = max(ymin, wy0), min(ymax, wy1)
            if x0 >= x1 or y0 >= y1:
                continue

            yy = np.arange(wy0, wy1, dtype=np.float32)[:, None] + 0.5
            xx = np.arange(wx0, wx1, dtype=np.float32)[None, :] + 0.5
            dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
            keep = (dist <= float(r)).astype(np.float32)
            keep = cv2.copyMakeBorder(keep, sil_pad, sil_pad, sil_pad, sil_pad,
                                      cv2.BORDER_CONSTANT, value=0.0)
            if sil_sigma >= 0.5:
                # ksize 与 ETM 的 radius = round(3σ) 对齐，保证两边像素等价
                keep = cv2.GaussianBlur(keep, (2 * sil_pad + 1, 2 * sil_pad + 1), sil_sigma)
            keep = keep[sil_pad + (y0 - wy0):sil_pad + (y1 - wy0),
                        sil_pad + (x0 - wx0):sil_pad + (x1 - wx0)]

            yy = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
            xx = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5

            if where == "tl":
                cond = (xx < cx) & (yy < cy)
            elif where == "tr":
                cond = (xx > cx) & (yy < cy)
            elif where == "bl":
                cond = (xx < cx) & (yy > cy)
            else:
                cond = (xx > cx) & (yy > cy)
            a = np.where(cond, keep, 1.0).astype(np.float32)
            weight[y0 - ymin:y1 - ymin, x0 - xmin:x1 - xmin, 0] = np.minimum(
                weight[y0 - ymin:y1 - ymin, x0 - xmin:x1 - xmin, 0], a)
            continue

        ah, av = avail(e_h), avail(e_v)
        if fades[e_h] <= 0:
            ah = av
        elif fades[e_v] <= 0:
            av = ah
        reach = r + max(ah[0], av[0])
        x0 = max(xmin, int(cx - reach) - 2)
        x1 = min(xmax, int(cx + reach) + 3)
        y0 = max(ymin, int(cy - reach) - 2)
        y1 = min(ymax, int(cy + reach) + 3)
        if x0 >= x1 or y0 >= y1:
            continue

        yy = np.arange(y0, y1, dtype=np.float32)[:, None] + 0.5
        xx = np.arange(x0, x1, dtype=np.float32)[None, :] + 0.5
        dist = np.sqrt((xx - cx) ** 2 + (yy - cy) ** 2)
        xin = r - dist
        if f <= 1e-6:
            alpha = (xin >= 0).astype(np.float32)
        else:
            # 两个切点各用自己的直边宽度，沿圆弧插值，切线处才接得上
            u = np.abs(xx - cx)
            v = np.abs(yy - cy)
            s = v / np.maximum(u + v, 1e-6)
            s = s * s * (3.0 - 2.0 * s)
            w_in = ah[1] + (av[1] - ah[1]) * s
            w_out = ah[0] + (av[0] - ah[0]) * s
            hw = np.where(xin >= 0, w_in, w_out) * f
            t = np.clip(0.5 + xin / (2.0 * np.maximum(hw, 1e-6)), 0.0, 1.0)
            alpha = t * t * (3.0 - 2.0 * t)

        if where == "tl":
            cond = (xx < cx) & (yy < cy)
        elif where == "tr":
            cond = (xx > cx) & (yy < cy)
        elif where == "bl":
            cond = (xx < cx) & (yy > cy)
        else:
            cond = (xx > cx) & (yy > cy)

        region = weight[y0 - ymin:y1 - ymin, x0 - xmin:x1 - xmin, 0]
        weight[y0 - ymin:y1 - ymin, x0 - xmin:x1 - xmin, 0] = np.where(cond, alpha, region)
    return weight

def _feather_tile_mask_like_etm(crop_mask_float, bbox, h_bg, w_bg,
                                 fade_t, fade_b, fade_l, fade_r,
                                 overlap, feather_frac, feather_px=None):
    """复刻 ETM 的 tile_mask 羽化：贴画布边 replicate pad → 高斯模糊 → 切回 bbox。"""
    xmin, ymin, xmax, ymax = bbox
    h_crop, w_crop = ymax - ymin, xmax - xmin

    if feather_px is None:
        max_fade = max(float(fade_t), float(fade_b), float(fade_l), float(fade_r))
        if max_fade > 0:
            feather_px = max(1.0, max_fade * feather_frac)
        else:
            feather_px = max(1.0, float(overlap) * feather_frac)

    # 贴画布边 pad（与 ETM 一致：replicate overlap 深度）
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


def _grid_tile_weight( tile_info, bbox, crop_mask, h_bg, w_bg, overlap, feather_kernel):
    """grid 分块权重：直接沿用 ElementTileMerge 的 alpha / feather 几何。

    - fade 一律按 `overlap` 计，斜坡以 `overlap/2` 为中心（手动模式每块外扩
      `overlap/2`，所以 50% 正好落在手绘框边）。
    - 同层相邻手绘块按 `blend_pads` 把过渡限制在两块锁定带之间。
    - 手绘框倒角走以手绘圆弧为 50% 的径向斜坡，不用外扩轮廓硬切。
    - 背景块不剔除锁定带（带里是同一底图的另一增强版本），只参与加权归一。
    feather_kernel 0~100 线性对应 ETM 的 feather 0~1.0，100 为最大值。
    """
    ti = dict(tile_info)
    bg = _is_bg(ti)
    if overlap > 0:
        for k in ("fade_top", "fade_bottom", "fade_left", "fade_right"):
            if ti.get(k, 0) > 0:
                ti[k] = overlap
        if not bg:
            _restore_canvas_inset(ti, overlap)

    frac = max(0.0, min(1.0, float(feather_kernel) / 100.0))
    weight = _tile_weight_etm(ti, bbox, frac)
    if not bg:
        weight = _corner_ramp_etm(weight, ti, bbox, overlap, frac)

    # 圆角轮廓的模糊宽度用 Split 导出的 corner_feather（与 ETM 一致）
    cf = float(ti.get("corner_feather", 0) or 0)
    mask_f = _feather_tile_mask_like_etm(
        crop_mask, bbox, h_bg, w_bg,
        ti.get("fade_top", 0), ti.get("fade_bottom", 0),
        ti.get("fade_left", 0), ti.get("fade_right", 0), overlap, frac,
        feather_px=max(1.0, cf) if cf > 0 else None)
    weight = weight * mask_f

    if not bg:
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

