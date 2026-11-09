# Element_value_remap.py
# 把任意数值（常见为 seed）稳定映射到 [min, max] 区间；未接输入时随机取值。
import hashlib
import math
import random
import time


def _unit(value):
    """按数值哈希取 [0, 1) 内的稳定位置；整数值与等值浮点数结果一致。"""
    if isinstance(value, bool):
        value = int(value)
    if isinstance(value, float) and value.is_integer():
        value = int(value)
    key = f"i:{value}" if isinstance(value, int) else f"f:{float(value)!r}"
    digest = hashlib.blake2b(key.encode("utf-8"), digest_size=8).digest()
    return int.from_bytes(digest, "big") / 2 ** 64


def _display_float(value):
    text = f"{value:.6f}".rstrip("0").rstrip(".")
    return "0" if text in ("", "-0") else text


class ElementValueRemap:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "min": ("FLOAT", {"default": 0.0, "min": -1e12, "max": 1e12, "step": 0.01}),
                "max": ("FLOAT", {"default": 1.0, "min": -1e12, "max": 1e12, "step": 0.01}),
            },
            "optional": {
                "value": ("INT,FLOAT", {"forceInput": True}),
            },
        }

    RETURN_TYPES = ("FLOAT", "INT")
    RETURN_NAMES = ("float", "int")
    FUNCTION = "remap"
    CATEGORY = "Element_easy"

    @classmethod
    def IS_CHANGED(cls, **kwargs):
        if kwargs.get("value") is None:
            return time.time_ns()
        return ""

    def remap(self, min, max, value=None):
        lo, hi = (min, max) if min <= max else (max, min)
        unit = random.random() if value is None else _unit(value)
        mapped = lo + unit * (hi - lo)

        int_value = int(round(mapped))
        lo_i, hi_i = math.ceil(lo), math.floor(hi)
        if lo_i <= hi_i:
            if int_value < lo_i:
                int_value = lo_i
            elif int_value > hi_i:
                int_value = hi_i
        float_value = float(mapped)
        return {
            "ui": {"value_text": [_display_float(float_value), str(int_value)]},
            "result": (float_value, int_value,),
        }


NODE_CLASS_MAPPINGS = {"Element_Value_Remap": ElementValueRemap}
NODE_DISPLAY_NAME_MAPPINGS = {"Element_Value_Remap": "Element_random_value_remap"}
