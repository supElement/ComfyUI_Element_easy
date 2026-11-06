# -*- coding: utf-8 -*-
# 光流与精修 / optical flow & refinement

import cv2
import numpy as np
import torch

from .sm_common import (
    _sm_note,
    _sm_log,
)
from .sm_config import FLOW_DENOISE_PX, MAX_FLOW_PX


def _suppress_tangential_flow(flow, gx, gy, coherence_lo=0.5, min_strength=100.0,
                              blur_k=11):
    """长直边/一维结构上光流只有法向分量可观测, 按各向异性程度衰减切向分量。
    二维纹理区(两方向都有梯度)coherence 低, 流场原样保留。"""
    jxx = cv2.GaussianBlur(gx * gx, (blur_k, blur_k), 0)
    jyy = cv2.GaussianBlur(gy * gy, (blur_k, blur_k), 0)
    jxy = cv2.GaussianBlur(gx * gy, (blur_k, blur_k), 0)
    root = np.sqrt((jxx - jyy) ** 2 + 4.0 * jxy * jxy)
    l1 = 0.5 * (jxx + jyy + root)
    l2 = 0.5 * (jxx + jyy - root)
    coherence = (l1 - l2) / (l1 + l2 + 1e-6)
    theta = 0.5 * np.arctan2(2.0 * jxy, jxx - jyy)   # 主方向 = 法向
    nx, ny = np.cos(theta), np.sin(theta)
    keep_tang = 1.0 - (np.clip((coherence - coherence_lo) / 0.45, 0.0, 1.0)
                       * ((l1 - l2) > min_strength))
    fn = flow[:, :, 0] * nx + flow[:, :, 1] * ny
    ft = (flow[:, :, 1] * nx - flow[:, :, 0] * ny) * keep_tang
    out = np.empty_like(flow)
    out[:, :, 0] = fn * nx - ft * ny
    out[:, :, 1] = fn * ny + ft * nx
    return out

def _fill_flow_from_reliable(flow, confidence, kernel_size=41):
    """低置信区域只继承邻域低频位移，不直接用颜色差驱动变形。"""
    confidence = np.clip(confidence.astype(np.float32), 0.0, 1.0)
    if float(confidence.max()) < 0.05:
        return np.zeros_like(flow)
    den = cv2.GaussianBlur(confidence, (kernel_size, kernel_size), 0)
    filled = np.zeros_like(flow)
    for c in range(2):
        num = cv2.GaussianBlur(flow[:, :, c] * confidence, (kernel_size, kernel_size), 0)
        filled[:, :, c] = num / np.maximum(den, 1e-6)
    fill_weight = np.clip((0.95 - confidence) / 0.95, 0.0, 1.0)
    filled[den <= 1e-6] = 0.0
    return flow * (1.0 - fill_weight[:, :, None]) + filled * fill_weight[:, :, None]

def _flow_kernel(k, s):
    """核尺寸换算到估流域: 物理覆盖范围不随估流分辨率改变。"""
    return max(3, int(round(k * s)) | 1)

def _flow_acceptable(g0_med, g0_p85, g1_med, g1_p85):
    """逐块光流验收: 中位数与尾部(p85)都不变差就采用。
    中位数对局部错位几乎免疫——大部分像素已亚像素对齐时, 少数几处 3–5px 的
    错位在 median 上看不出来, 而它们正是"有些地方没校正"的来源。
    所以判据是"尾部和中位数都不能变差", 而不是"中位数必须明显变好"。"""
    return g1_med <= g0_med + 0.05 and g1_p85 <= g0_p85 + 0.3

def refine_with_optical_flow( warped_fg, warped_mask, train_img,
                             device="cpu", max_flow_px=None, edit_mask=None, flow_scale=1.0):
    """逐块光流精修: 优先 DIS, 不支持时降级 Farneback。
    edit_mask 已不参与门控: 逐块光流只做几何校正, 改色区的畸变同样需要修正。
    只在掩码 bbox(+边距) 内估流; flow_scale<1 时在内容原生分辨率上估流,
    上采样回全分辨率后只做一次重采样。"""
    if max_flow_px is None:
        max_flow_px = MAX_FLOW_PX
    h_t, w_t = train_img.shape[:2]
    mask_u8 = (warped_mask > 0.5).astype(np.uint8)
    ys, xs = np.where(mask_u8 > 0)
    if len(ys) < 100:
        return warped_fg, warped_mask
    margin = 64
    y0 = max(0, int(ys.min()) - margin)
    y1 = min(h_t, int(ys.max()) + margin)
    x0 = max(0, int(xs.min()) - margin)
    x1 = min(w_t, int(xs.max()) + margin)
    sub_fg = np.ascontiguousarray(warped_fg[y0:y1, x0:x1])
    sub_mask = np.ascontiguousarray(warped_mask[y0:y1, x0:x1])
    sub_bg = np.ascontiguousarray(train_img[y0:y1, x0:x1])

    # 估流尺度: 内容原生分辨率比例, 长边上限 2048 兜住超大画布耗时
    sh, sw = sub_fg.shape[:2]
    s = float(flow_scale)
    if not np.isfinite(s) or s <= 0.0:
        s = 1.0
    s = min(s, 1.0, 2048.0 / float(max(sh, sw)))
    if s < 0.999:
        fw, fh = max(8, int(round(sw * s))), max(8, int(round(sh * s)))
        s = fw / float(sw)
        flow_fg = cv2.resize(sub_fg, (fw, fh), interpolation=cv2.INTER_AREA)
        flow_bg = cv2.resize(sub_bg, (fw, fh), interpolation=cv2.INTER_AREA)
        flow_mask = cv2.resize(sub_mask, (fw, fh), interpolation=cv2.INTER_AREA)
        _sm_log(f"[Smart Merge] 逐块光流估域: {sw}x{sh}→{fw}x{fh} (scale {s:.3f}) | "
              f"per-crop flow at content resolution")
    else:
        s = 1.0
        flow_fg, flow_bg, flow_mask = sub_fg, sub_bg, sub_mask

    gray_warped = _to_flow_luma(flow_fg)
    gray_target = _to_flow_luma(flow_bg)

    # 改色免疫预处理: CLAHE 恢复亮度结构 → 直方图匹配消除分布差 → 预平滑保宏观几何
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gray_warped = clahe.apply(gray_warped)
    gray_target = clahe.apply(gray_target)
    gray_warped = _match_histogram(gray_warped, gray_target)
    # 逐块路径同样做虚焦均衡(编辑块通常比原图实)
    gray_warped, _ = _defocus_equalize(gray_warped, gray_target, flow_mask)
    bk = _flow_kernel(11, s)
    gray_warped = cv2.GaussianBlur(gray_warped, (bk, bk), 0)
    gray_target = cv2.GaussianBlur(gray_target, (bk, bk), 0)

    max_flow_local = float(max_flow_px) * s
    try:
        flow = _refine_with_dis(gray_warped, gray_target, flow_mask,
                                     max_flow_px=max_flow_local, scale=s)
    except Exception as e:
        print(f"[Smart Merge] DIS 不可用 ({e}), 降级 Farneback | DIS unavailable, falling back to Farneback")
        flow = _refine_with_farneback(gray_warped, gray_target, flow_mask,
                                           max_flow_px=max_flow_local, scale=s)

    if s < 0.999:
        flow = cv2.resize(flow, (sw, sh), interpolation=cv2.INTER_LINEAR) * (1.0 / s)
    grid_x, grid_y = np.meshgrid(np.arange(sw, dtype=np.float32), np.arange(sh, dtype=np.float32))
    map_x = (grid_x - flow[:, :, 0]).astype(np.float32)
    map_y = (grid_y - flow[:, :, 1]).astype(np.float32)
    r_fg = cv2.remap(sub_fg, map_x, map_y,
                     interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    r_mask = cv2.remap(sub_mask, map_x, map_y,
                       interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_CONSTANT, borderValue=0)
    out_fg = warped_fg.copy()
    out_mask = warped_mask.copy()
    out_fg[y0:y1, x0:x1] = r_fg
    out_mask[y0:y1, x0:x1] = r_mask
    return out_fg, out_mask

def _denoise_flow_field(flow):
    """估算域内的低通: 抹掉估流本身的像素级噪声。
    该噪声随 1/s 上采样放大后, 就是沿长直边出现的台阶/波浪。"""
    return cv2.GaussianBlur(flow, (7, 7), 1.2)

def _constrain_flow_quadratic(flow):
    """把逐块流场约束为二次曲面: 保留整体平移/尺度和二阶形变,
    去掉沿长直边缓慢变化的低频梯度——该梯度正是竖边被拉弯的来源。"""
    h, w = flow.shape[:2]
    if h < 8 or w < 8:
        return flow
    xs = np.linspace(-1.0, 1.0, w, dtype=np.float64)
    ys = np.linspace(-1.0, 1.0, h, dtype=np.float64)
    xn, yn = np.meshgrid(xs, ys)
    basis = np.stack([np.ones(h * w), xn.ravel(), yn.ravel(),
                      xn.ravel() ** 2, (xn * yn).ravel(), yn.ravel() ** 2], 1)
    out = flow.copy()
    for c in range(2):
        coef, *_ = np.linalg.lstsq(basis, flow[:, :, c].ravel().astype(np.float64),
                                   rcond=None)
        out[:, :, c] = (basis @ coef).reshape(h, w).astype(np.float32)
    return out

def _refine_with_dis( gray_warped, gray_target, warped_mask,
                     max_flow_px=15.0, scale=1.0):
    """在光流估域内算前向流场(把 gray_warped 对齐到 gray_target)并返回。
    核半径与像素阈值按 scale 等比缩放, 所以"物理"含义不随估流分辨率改变。"""
    h_f, w_f = gray_warped.shape[:2]
    s = float(scale)
    try:
        dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    except AttributeError:
        dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
    # OpenCV 的 DIS 最高档就是 MEDIUM(finest_scale 已为 0), 再往上只能加变分细化迭代。
    # 逐块估域实测: 2 次估流 9.6ms→13.4ms, 15 块合计约 +60ms。
    dis.setVariationalRefinementIterations(10)

    flow = dis.calc(gray_warped, gray_target, None).astype(np.float32)
    flow_b = dis.calc(gray_target, gray_warped, None).astype(np.float32)
    flow[:, :, 0] = cv2.medianBlur(np.ascontiguousarray(flow[:, :, 0]), 3)
    flow[:, :, 1] = cv2.medianBlur(np.ascontiguousarray(flow[:, :, 1]), 3)

    grid_x, grid_y = np.meshgrid(np.arange(w_f, dtype=np.float32), np.arange(h_f, dtype=np.float32))
    map_x_fwd = grid_x + flow[:, :, 0]
    map_y_fwd = grid_y + flow[:, :, 1]
    bwd_at_fwd = cv2.remap(flow_b, map_x_fwd, map_y_fwd,
                           interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    consistency = np.clip((3.0 * s - np.linalg.norm(flow + bwd_at_fwd, axis=2)) / (1.5 * s),
                          0.0, 1.0)
    ek = _flow_kernel(5, s)
    inner_mask = cv2.erode((warped_mask > 0.5).astype(np.uint8), np.ones((ek, ek), np.uint8))
    reliability = inner_mask.astype(np.float32) * consistency
    # 逐块光流是几何阶段: 只用前后向一致性, 不读改色掩码。
    # 实测改色区内部的畸变同样需要校正, 一旦用改色置信度门控就会整块冻结。

    flow_mag = np.linalg.norm(flow, axis=2)
    scale_factor = np.minimum(flow_mag, float(max_flow_px)) / (flow_mag + 1e-8)
    flow *= (scale_factor * reliability)[:, :, None]
    bd = _flow_kernel(7, s)
    flow[:, :, 0] = cv2.bilateralFilter(np.ascontiguousarray(flow[:, :, 0]), bd,
                                        FLOW_DENOISE_PX * s, 7.0 * s)
    flow[:, :, 1] = cv2.bilateralFilter(np.ascontiguousarray(flow[:, :, 1]), bd,
                                        FLOW_DENOISE_PX * s, 7.0 * s)
    flow = _fill_flow_from_reliable(flow, reliability,
                                         kernel_size=_flow_kernel(41, s))
    return _constrain_flow_quadratic(_denoise_flow_field(flow))

def _refine_with_farneback( gray_warped, gray_target, warped_mask,
                           max_flow_px=15.0, scale=1.0):
    h_f, w_f = gray_warped.shape[:2]
    s = float(scale)

    mask_8u = (warped_mask * 255).astype(np.uint8)
    erode_size = min(_flow_kernel(25, s), min(h_f, w_f) // 4)
    erode_size = max(3, erode_size)
    erode_kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (erode_size, erode_size))
    inner_mask = cv2.erode(mask_8u, erode_kernel, iterations=1)
    inner_mask_f = inner_mask.astype(np.float32) / 255.0

    win = _flow_kernel(7, s)
    flow_fwd = cv2.calcOpticalFlowFarneback(
        gray_warped, gray_target, None,
        0.5, 2, win, 5, 5, 1.1, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
    )
    flow_bwd = cv2.calcOpticalFlowFarneback(
        gray_target, gray_warped, None,
        0.5, 2, win, 5, 5, 1.1, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
    )

    grid_x, grid_y = np.meshgrid(np.arange(w_f, dtype=np.float32), np.arange(h_f, dtype=np.float32))
    map_x_fwd = grid_x + flow_fwd[:, :, 0]
    map_y_fwd = grid_y + flow_fwd[:, :, 1]
    bwd_at_fwd = cv2.remap(flow_bwd, map_x_fwd, map_y_fwd,
                           interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)

    consistency_err = np.linalg.norm(flow_fwd + bwd_at_fwd, axis=2)
    consistency_mask = np.clip((3.0 * s - consistency_err) / (1.5 * s),
                               0.0, 1.0).astype(np.float32)

    # 只依赖前后向一致性, 不额外惩罚低纹理/低锐度
    reliability = inner_mask_f * consistency_mask
    reliability = np.clip(reliability, 0.0, 1.0)

    flow = flow_fwd.copy()
    max_flow = float(max_flow_px)
    flow_mag = np.linalg.norm(flow, axis=2)
    scale_factor = np.minimum(flow_mag, max_flow) / (flow_mag + 1e-8)
    flow[:, :, 0] *= scale_factor
    flow[:, :, 1] *= scale_factor
    
    flow[:, :, 0] *= reliability
    flow[:, :, 1] *= reliability

    bd = _flow_kernel(7, s)
    flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0], bd,
                                        FLOW_DENOISE_PX * s, 7.0 * s)
    flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1], bd,
                                        FLOW_DENOISE_PX * s, 7.0 * s)
    flow = _fill_flow_from_reliable(flow, reliability,
                                         kernel_size=_flow_kernel(41, s))
    return _constrain_flow_quadratic(_denoise_flow_field(flow))

def _to_flow_luma(img):
    """光流输入：提取 Lab 的 L 通道（亮度），配合直方图匹配抵抗偏色。"""
    return cv2.cvtColor(img, cv2.COLOR_RGB2LAB)[:, :, 0]

def _match_histogram(src, ref):
    """把 src 的直方图映射到 ref 的分布。用于消除偏色/改色对光流的结构破坏。"""
    src_vals, src_idx, src_cnt = np.unique(src.ravel(), return_inverse=True, return_counts=True)
    ref_vals, ref_cnt = np.unique(ref.ravel(), return_counts=True)
    src_q = np.cumsum(src_cnt).astype(np.float64)
    src_q /= src_q[-1]
    ref_q = np.cumsum(ref_cnt).astype(np.float64)
    ref_q /= ref_q[-1]
    interp = np.interp(src_q, ref_q, ref_vals)
    return interp[src_idx].reshape(src.shape).astype(np.uint8)

def _match_histogram_masked(src, ref, mask):
    """仅统计 mask 区域内的直方图并匹配: 局部改色时全局直方图会被背景主导。"""
    m = mask > 0.5
    if int(m.sum()) < 1000:
        return _match_histogram(src, ref)
    src_vals, src_cnt = np.unique(src[m], return_counts=True)
    ref_vals, ref_cnt = np.unique(ref[m], return_counts=True)
    src_q = np.cumsum(src_cnt).astype(np.float64)
    src_q /= src_q[-1]
    ref_q = np.cumsum(ref_cnt).astype(np.float64)
    ref_q /= ref_q[-1]
    interp = np.interp(src_q, ref_q, ref_vals)
    lut = np.arange(256, dtype=np.uint8)
    lut[src_vals.astype(np.int64)] = np.clip(np.round(interp), 0, 255).astype(np.uint8)
    return cv2.LUT(src, lut)

def _brighten_for_match(img):
    """匹配前的曲线提亮: 分位拉伸 + gamma。只影响特征匹配, 不参与合成。

    大面积暗色重绘(暗衣服/暗背景)在 8bit 图里局部对比极低, 特征检测器
    几乎没有可用的采样点; 先把亮度曲线拉开再匹配一次, 往往能恢复结构。
    输入本身平坦(完全没有结构)时返回 None, 表示提亮也无济于事。
    """
    g = img.astype(np.float32).mean(axis=2)
    lo = float(np.percentile(g, 1.0))
    hi = float(np.percentile(g, 99.0))
    if hi - lo < 2.0:
        return None
    f = np.clip((img.astype(np.float32) - lo) * (255.0 / (hi - lo)), 0.0, 255.0)
    if float(f.mean()) < 96.0:
        f = 255.0 * np.power(np.clip(f, 0.0, 255.0) / 255.0, 0.65)
    return np.clip(f, 0.0, 255.0).astype(np.uint8)

def _match_histogram_rgb(src, ref):
    """逐通道直方图映射(src→ref)。只用于特征匹配前, 让改色/偏色分块的
    描述子分布靠近背景; 不参与最终像素合成。用 256 级 LUT 实现, 开销可忽略。"""
    out = np.empty_like(src)
    vals = np.arange(256, dtype=np.float64)
    for c in range(3):
        hs = np.bincount(np.ascontiguousarray(src[..., c]).ravel(), minlength=256).astype(np.float64)
        hr = np.bincount(np.ascontiguousarray(ref[..., c]).ravel(), minlength=256).astype(np.float64)
        qs = np.cumsum(hs)
        qs /= max(qs[-1], 1.0)
        qr = np.cumsum(hr)
        qr /= max(qr[-1], 1.0)
        lut = np.clip(np.round(np.interp(qs, qr, vals)), 0, 255).astype(np.uint8)
        out[..., c] = lut[src[..., c]]
    return out

def _defocus_equalize(sharp_l, ref_l, mask):
    """虚焦→实焦均衡: AI 重采样常把虚焦区变实焦, 边缘梯度尺度失配会让光流
    在轮廓处产生系统性位移。把较实一侧模糊到参考侧锐度, 只作用于光流输入。
    返回 (均衡后图像, 实际使用的 sigma); 编辑图不比原图实时返回 sigma=0。"""
    m = mask > 0.5
    if int(m.sum()) < 1000:
        return sharp_l, 0.0
    v_sharp = float(cv2.Laplacian(sharp_l, cv2.CV_32F)[m].var())
    v_ref = float(cv2.Laplacian(ref_l, cv2.CV_32F)[m].var())
    # 编辑图没有明显更实(普通改色/普通重绘) → 不干预, 保持原行为
    if v_ref < 1.0 or v_sharp <= v_ref * 1.15:
        return sharp_l, 0.0
    best_sigma, best_diff = 0.0, abs(np.log(v_sharp + 1.0) - np.log(v_ref + 1.0))
    for s in (1.0, 1.5, 2.0, 3.0, 4.0, 6.0, 8.0):
        cand = cv2.GaussianBlur(sharp_l, (0, 0), s)
        v = float(cv2.Laplacian(cand, cv2.CV_32F)[m].var())
        d = abs(np.log(v + 1.0) - np.log(v_ref + 1.0))
        if d < best_diff:
            best_sigma, best_diff = s, d
    if best_sigma <= 0.0:
        return sharp_l, 0.0
    _sm_log(
        f"[Smart Merge] 虚焦→实焦均衡: 编辑图锐度{v_sharp:.0f} → 原图{v_ref:.0f}, "
        f"sigma={best_sigma} | defocus equalized (flow input only)")
    return cv2.GaussianBlur(sharp_l, (0, 0), best_sigma), best_sigma

def refine_second_pass( warped_fg, warped_mask, train_img, device, max_disp=64.0):
    """二阶段精校: 已warp的块与BG同坐标系、小位移, 再做一次LoFTR稀疏匹配求残差场"""
    from .sm_align import (filter_correspondences_local_affine,
                           match_with_loftr, warp_tps)
    try:
        h_t, w_t = train_img.shape[:2]
        ys, xs = np.where(warped_mask > 0.5)
        if len(ys) < 100:
            return None, None
        pad = 48
        y0, y1 = max(0, ys.min() - pad), min(h_t, ys.max() + pad)
        x0, x1 = max(0, xs.min() - pad), min(w_t, xs.max() + pad)
        if (y1 - y0) < 64 or (x1 - x0) < 64:
            return None, None
        roi_fg = warped_fg[y0:y1, x0:x1]
        roi_bg = train_img[y0:y1, x0:x1]
        pts_w, pts_b = match_with_loftr(roi_fg, roi_bg, device)
        # 各块 ROI 尺寸不同, LoFTR 的激活块会一直滞留; 用完即还给驱动,
        # 否则整轮 15 块的保留显存会累积到十几 GB。
        if "cuda" in str(device):
            torch.cuda.empty_cache()
        if pts_w is None or len(pts_w) < 12:
            return None, None
        pts_w, pts_b = filter_correspondences_local_affine(pts_w, pts_b)
        if len(pts_w) < 12:
            return None, None
        off = np.array([x0, y0], dtype=np.float32)
        pts_w = pts_w + off[None, :]
        pts_b = pts_b + off[None, :]
        return warp_tps(warped_fg, warped_mask, train_img,
                             pts_w, pts_b, reg_lambda=1.5,
                             max_disp=max_disp, max_points=1500)
    except Exception as e:
        print(f"[Smart Merge] 二阶段精校失败: {e}")
        return None, None

def global_flow_polish( merged_img, original_bg, union_mask, max_disp=12.0, edit_mask=None,
                       warp_smooth=1.0, flow_scale=1.0):
    """整图光流精修: 合成图 vs 原图, 补低纹理区残余位移。优先 DIS, 不支持时降级 Farneback。
    flow_scale<1 时在内容原生分辨率上估流(核/阈值等比缩放), 评分与最终合成始终在全分辨率。"""
    h, w = original_bg.shape[:2]
    s = float(flow_scale)
    if not np.isfinite(s) or s <= 0.0:
        s = 1.0
    s = min(s, 1.0, 2048.0 / float(max(h, w)))
    if s < 0.999:
        ph, pw = max(16, int(round(h * s))), max(16, int(round(w * s)))
        s = pw / float(w)
        pm_img = cv2.resize(merged_img, (pw, ph), interpolation=cv2.INTER_AREA)
        pm_bg = cv2.resize(original_bg, (pw, ph), interpolation=cv2.INTER_AREA)
        pm_union = cv2.resize(union_mask, (pw, ph), interpolation=cv2.INTER_AREA)
        pm_edit = (cv2.resize(edit_mask, (pw, ph), interpolation=cv2.INTER_AREA)
                   if edit_mask is not None else None)
        _sm_log(f"[Smart Merge] 整图精修估域: {w}x{h}→{pw}x{ph} (scale {s:.3f}) | "
              f"polish flow at content resolution")
    else:
        s = 1.0
        pm_img, pm_bg, pm_union, pm_edit = merged_img, original_bg, union_mask, edit_mask
    ph, pw = pm_bg.shape[:2]

    gm_l = _to_flow_luma(pm_img)
    go_l = _to_flow_luma(pm_bg)

    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(8, 8))
    gm_l = clahe.apply(gm_l)
    go_l = clahe.apply(go_l)
    # 仅在编辑区内做直方图匹配(全局会被背景主导), 消除残余分布差异
    gm_l = _match_histogram_masked(gm_l, go_l, pm_union)
    # 虚焦→实焦均衡: 把实焦编辑图模糊回原图虚焦尺度,
    gm_l, sigma_eq = _defocus_equalize(gm_l, go_l, pm_union)
    bk = _flow_kernel(11, s)
    gm_l = cv2.GaussianBlur(gm_l, (bk, bk), 0)
    go_l = cv2.GaussianBlur(go_l, (bk, bk), 0)


    try:
        try:
            dis = cv2.DISOpticalFlow_create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        except AttributeError:
            dis = cv2.DISOpticalFlow.create(cv2.DISOPTICAL_FLOW_PRESET_MEDIUM)
        flow = dis.calc(gm_l, go_l, None).astype(np.float32)
        flow_b = dis.calc(go_l, gm_l, None).astype(np.float32)
    except Exception as e:
        _sm_log(f"[Smart Merge] 整图精修 DIS 不可用 ({e}), 降级 Farneback | "
                f"polish DIS unavailable, falling back to Farneback")
        fwin = _flow_kernel(15, s)
        flow = cv2.calcOpticalFlowFarneback(
            gm_l, go_l, None, 0.5, 3, fwin, 5, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        ).astype(np.float32)
        flow_b = cv2.calcOpticalFlowFarneback(
            go_l, gm_l, None, 0.5, 3, fwin, 5, 7, 1.5, cv2.OPTFLOW_FARNEBACK_GAUSSIAN
        ).astype(np.float32)

    # 一维结构(长直边)上切向位移不可观测: 光流只能沿边插值出任意值,
    # 经大核填充和重采样后就是沿边拉长的带状鬼影。按结构张量各向异性把流场投影到
    # 法向, 只保留可观测分量; 二维纹理区不受影响。
    gx_m = cv2.Sobel(gm_l, cv2.CV_32F, 1, 0)
    gy_m = cv2.Sobel(gm_l, cv2.CV_32F, 0, 1)
    flow = _suppress_tangential_flow(flow, gx_m, gy_m, blur_k=bk)
    flow_b = _suppress_tangential_flow(flow_b, gx_m, gy_m, blur_k=bk)

    grid_x, grid_y = np.meshgrid(np.arange(pw, dtype=np.float32), np.arange(ph, dtype=np.float32))
    map_x = grid_x + flow[:, :, 0]
    map_y = grid_y + flow[:, :, 1]
    bwd_at_fwd = cv2.remap(flow_b, map_x, map_y, interpolation=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REPLICATE)
    fb_err = np.linalg.norm(flow + bwd_at_fwd, axis=2)
    # 收紧前后向一致性: 真实几何位移场前后向自洽(fb_err很小);
    consistency_gate = np.clip((2.0 * s - fb_err) / (1.5 * s), 0.0, 1.0)
    texture_m = np.sqrt(gx_m ** 2 + gy_m ** 2)
    texture_o = np.sqrt(cv2.Sobel(go_l, cv2.CV_32F, 1, 0) ** 2
                        + cv2.Sobel(go_l, cv2.CV_32F, 0, 1) ** 2)
    texture_hard = np.maximum(texture_m, texture_o) > 3.0
    tk = _flow_kernel(21, s)
    texture_support = cv2.dilate(texture_hard.astype(np.uint8), np.ones((tk, tk), np.uint8))
    texture_soft = cv2.GaussianBlur(texture_support.astype(np.float32), (tk, tk), 0)

    rk = _flow_kernel(31, s)
    reference_mask = np.ones((ph, pw), dtype=np.float32)
    if pm_edit is not None:
        reference_mask = cv2.erode(
            (pm_edit > 0.95).astype(np.uint8), np.ones((rk, rk), np.uint8)
        ).astype(np.float32)

    mag = np.linalg.norm(flow, axis=2)
    sel = pm_union > 0.5
    reliable_sel = sel & (consistency_gate > 0.1) & (texture_support > 0) & (reference_mask > 0.5)
    if int(reliable_sel.sum()) < 100:
        _sm_note("[Smart Merge] 整图精修: 可靠区域不足, 跳过 | polish skipped (insufficient reliable area)")
        return merged_img
    scale = np.minimum(mag, float(max_disp) * s) / (mag + 1e-8)
    flow[:, :, 0] *= scale
    flow[:, :, 1] *= scale

    um = cv2.GaussianBlur(sel.astype(np.float32), (rk, rk), 0)
    final_gate = um * consistency_gate * texture_soft
    if pm_edit is not None:
        smooth_edit_mask = cv2.GaussianBlur(reference_mask, (rk, rk), 0)
        final_gate *= np.clip(smooth_edit_mask, 0.0, 1.0)
    flow *= final_gate[:, :, None]
    flow = _fill_flow_from_reliable(flow, final_gate,
                                         kernel_size=_flow_kernel(41, s))
    flow *= um[:, :, None]
    # 颜色改变"边界带": 用邻域平滑值【替换】, 而不是置零
    if pm_edit is not None:
        em_f = np.clip(pm_edit.astype(np.float32), 0.0, 1.0)
        band = np.abs(cv2.Laplacian(em_f, cv2.CV_32F, ksize=5))
        # 9/11 是全分辨率基准, 换算到估流域要乘 s; sigma_eq 本身已是估流域像素
        _k1 = max(3, int(round(9 * s + min(sigma_eq, 8.0) * 3)) | 1)
        _k2 = max(3, int(round(11 * s + min(sigma_eq, 8.0) * 2)) | 1)
        band = cv2.dilate(band, cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (_k1, _k1)))
        band = cv2.GaussianBlur(band, (_k2, _k2), 0)
        band = np.clip(band * 4.0, 0.0, 1.0)
        if float(band.max()) > 0.05:
            _k3 = max(3, int(round(21 * s)) | 1, int(sigma_eq * 6) | 1)
            flow_smooth_x = cv2.blur(flow[:, :, 0], (_k3, _k3))
            flow_smooth_y = cv2.blur(flow[:, :, 1], (_k3, _k3))

            flow[:, :, 0] = flow[:, :, 0] * (1.0 - band) + flow_smooth_x * band
            flow[:, :, 1] = flow[:, :, 1] * (1.0 - band) + flow_smooth_y * band
    try:
        ws = float(warp_smooth)
    except (TypeError, ValueError):
        ws = 1.0
    ws = max(0.0, min(4.0, ws))

    # warp_smooth 三档强度: [0,1] 温和 / (1,2] 强力 / (2,4] 极强
    if ws <= 1.0:
        bs_sigma = FLOW_DENOISE_PX * (0.5 + ws)
        gk = int(round(5 + ws * 4)) | 1
        gs = 0.0
        ds_exp = 0.0
    elif ws <= 2.0:
        bs_sigma = FLOW_DENOISE_PX * (1.5 + 3.0 * (ws - 1.0))
        gk = int(round(9 + (ws - 1.0) * 20)) | 1
        gs = (ws - 1.0) * 8.0
        ds_exp = (ws - 1.0) * 2.0
    else:
        bs_sigma = FLOW_DENOISE_PX * (4.5 + 4.5 * (ws - 2.0))
        gk = int(round(29 + (ws - 2.0) * 20)) | 1
        gs = 8.0 + (ws - 2.0) * 8.0
        ds_exp = 2.0 + (ws - 2.0) * 1.0
    bs_sigma = max(0.5, bs_sigma) * s
    gk = _flow_kernel(gk, s)
    gs *= s
    bd = _flow_kernel(7, s)

    flow[:, :, 0] = cv2.bilateralFilter(flow[:, :, 0], bd, bs_sigma, 7.0 * s)
    flow[:, :, 1] = cv2.bilateralFilter(flow[:, :, 1], bd, bs_sigma, 7.0 * s)

    flow[:, :, 0] = cv2.GaussianBlur(flow[:, :, 0], (gk, gk), gs)
    flow[:, :, 1] = cv2.GaussianBlur(flow[:, :, 1], (gk, gk), gs)

    if ds_exp > 0.01:
        ds = 2.0 ** ds_exp
        h_f, w_f = flow.shape[:2]
        nh = max(8, int(round(h_f / ds)))
        nw = max(8, int(round(w_f / ds)))
        if nh < h_f or nw < w_f:
            for c in (0, 1):
                down = cv2.resize(flow[:, :, c], (nw, nh), interpolation=cv2.INTER_AREA)
                flow[:, :, c] = cv2.resize(down, (w_f, h_f), interpolation=cv2.INTER_LINEAR)

    # 流场上采样到全分辨率, 之后只做一次全分辨率重采样
    if s < 0.999:
        flow = cv2.resize(flow, (w, h), interpolation=cv2.INTER_LINEAR) * (1.0 / s)
    grid_x, grid_y = np.meshgrid(np.arange(w, dtype=np.float32), np.arange(h, dtype=np.float32))

    # 算完就应用, 不做采用/拒绝判定(对齐评分对细线/字形局部变化不敏感)
    map_x = grid_x - flow[:, :, 0]
    map_y = grid_y - flow[:, :, 1]
    out = cv2.remap(merged_img, map_x, map_y,
                    interpolation=cv2.INTER_LANCZOS4, borderMode=cv2.BORDER_REPLICATE)
    _sm_note("[Smart Merge] 整图精修已应用 | polish applied")
    return out

