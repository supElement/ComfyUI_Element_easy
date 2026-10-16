# Element_HueBright.py —— Hue→Brightness 曲线节点
# 共享实现（HSV 转换 / LUT / 批处理 / live 预览）见 element_easy/curve_core.py。
import torch

from .element_easy.curve_core import (
    HueCurveNodeBase,
    hsv_to_rgb,
    make_hue_live_compute,
    register_live_preview_route,
)


class ElementHueBright(HueCurveNodeBase):
    FILE_TAG = "huebright"

    @classmethod
    def APPLY_LUT(cls, h, s, v, idx0, idx1, w, lut_tensor):
        w = w * w * (3.0 - 2.0 * w)

        raw_bright = lut_tensor[idx0] * (1.0 - w) + lut_tensor[idx1] * w

        MAX_GAIN = 5.0  # 最大亮度

        is_brightening = raw_bright >= 1.0

        bright_strength = 1.0 + (raw_bright - 1.0) * (MAX_GAIN - 1.0)

        dark_strength = torch.pow(raw_bright, 3) # 最小亮度 1.5

        final_strength = torch.where(is_brightening, bright_strength, dark_strength)
        final_strength = torch.clamp(final_strength, min=1e-5)

        v_dark = v * final_strength

        gamma_power = 1.0 / final_strength
        v_bright = torch.pow(v + 1e-7, gamma_power)

        adjusted_v = torch.where(is_brightening, v_bright, v_dark)

        s_influence = torch.pow(s, 0.3) #低饱和影响0.3 数值越小影响越大
        new_v = v + s_influence * (adjusted_v - v)

        new_v = torch.clamp(new_v, 0.0, 1.0)

        new_hsv = torch.stack([h, s, new_v], dim=-1)
        return hsv_to_rgb(new_hsv)


register_live_preview_route(
    "/element_huebright/live_preview",
    ElementHueBright.FILE_TAG,
    make_hue_live_compute(ElementHueBright),
)
