# Element_HueHue.py —— Hue→Hue（色相环偏移）曲线节点
# 共享实现（HSV 转换 / LUT / 批处理 / live 预览）见 element_easy/curve_core.py。
import torch

from .element_easy.curve_core import (
    HueCurveNodeBase,
    hsv_to_rgb,
    make_hue_live_compute,
    register_live_preview_route,
)


class ElementHueHue(HueCurveNodeBase):
    FILE_TAG = "huehue"

    @classmethod
    def APPLY_LUT(cls, h, s, v, idx0, idx1, w, lut_tensor):
        hue_shift = lut_tensor[idx0] * (1.0 - w) + lut_tensor[idx1] * w
        # 将 0.0~2.0 映射为 -0.5~+0.5 的色相环偏移（1.0为中性点）
        hue_offset = (hue_shift - 1.0) * 0.5
        new_h = (h + hue_offset) % 1.0
        new_hsv = torch.stack([new_h, s, v], dim=-1)
        return hsv_to_rgb(new_hsv)


register_live_preview_route(
    "/element_huehue/live_preview",
    ElementHueHue.FILE_TAG,
    make_hue_live_compute(ElementHueHue),
)
