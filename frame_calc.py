import math

MODEL_PRESETS = {
    "MiniMax H3": {"div": 17, "offset": 5, "fps": 24},
    "LTX-2":      {"div": 8,  "offset": 1, "fps": 24},
    "Wan":        {"div": 4,  "offset": 1, "fps": 16},
    "Custom":     None,
}

class FrameCalculator:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Model": (list(MODEL_PRESETS.keys()), {"default": "Custom"}),
                "Type": (["Seconds", "Frames"], {"default": "Seconds"}),
                "Time": ("INT", {"default": 5, "min": 1, "max": 99999, "step": 1, "display": "number"}),
                "Div_by": ("INT", {"default": 17, "min": 1, "max": 1024, "step": 1, "display": "number"}),
                "Offset": ("INT", {"default": 5, "min": 0, "max": 1024, "step": 1, "display": "number"}),
                "Fps": ("INT", {"default": 24, "min": 1, "max": 240, "step": 1, "display": "number"}),
                "Rounding": (["Ceil", "Floor"], {"default": "Ceil"}),
            }
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT", "FLOAT", "INT")
    RETURN_NAMES = ("Frame Count", "FPS(Int)", "FPS(Float)", "Seconds(Float)", "Seconds(Int)")
    FUNCTION = "calculate"
    CATEGORY = "Element_easy"
    OUTPUT_NODE = True

    def calculate(self, Model, Type, Time, Div_by, Offset, Fps, Rounding):
        if MODEL_PRESETS[Model] is not None:
            div = MODEL_PRESETS[Model]["div"]
            offset = MODEL_PRESETS[Model]["offset"]
        else:
            div = Div_by
            offset = Offset

        if Type == "Seconds":
            base_frames = Time * Fps
        else:
            base_frames = Time

        if base_frames <= offset:
            k = 0
        else:
            k_float = (base_frames - offset) / div
            k = math.ceil(k_float) if Rounding == "Ceil" else math.floor(k_float)
        final_frames = k * div + offset

        diff = final_frames - base_frames
        if diff > 0:
            diff_str = f"+{diff}"
        elif diff < 0:
            diff_str = f"{diff}"
        else:
            diff_str = "0"

        seconds_float = round(final_frames / Fps, 2)
        seconds_int = int(round(final_frames / Fps))

        ui_text = (
            f"Model: {Model}\n"
            f"Final Frames: {final_frames} ({diff_str})\n"
            f"Seconds: {seconds_float}"
        )

        return {
            "ui": {"text": [ui_text]},
            "result": (final_frames, Fps, float(Fps), seconds_float, seconds_int),
        }
