# Element_HueSat.py —— Hue→Saturation 曲线节点
# 共享实现（HSV 转换 / LUT / 批处理 / live 预览）见 element_easy/curve_core.py。
import torch

from .element_easy.curve_core import (
    HueCurveNodeBase,
    hsv_to_rgb,
    make_hue_live_compute,
    register_live_preview_route,
)


class ElementHueSat(HueCurveNodeBase):
    FILE_TAG = "huesat"

    @classmethod
    def APPLY_LUT(cls, h, s, v, idx0, idx1, w, lut_tensor):
        sat_mult = lut_tensor[idx0] * (1.0 - w) + lut_tensor[idx1] * w
        new_s = torch.clamp(s * sat_mult, 0.0, 1.0)

        new_hsv = torch.stack([h, new_s, v], dim=-1)
        return hsv_to_rgb(new_hsv)


register_live_preview_route(
    "/element_huesat/live_preview",
    ElementHueSat.FILE_TAG,
    make_hue_live_compute(ElementHueSat),
)
