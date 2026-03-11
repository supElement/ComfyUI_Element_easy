import math

class FrameCalculator:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "Type": (["Seconds", "Frames"], {"default": "Seconds"}),
                "Time": ("INT", {"default": 5, "min": 1, "max": 99999, "step": 1, "display": "number"}),
                "Div_by": ("INT", {"default": 8, "min": 1, "max": 1024, "step": 1, "display": "number"}),
                "Fps": ("INT", {"default": 24, "min": 1, "max": 240, "step": 1, "display": "number"}),
                "Rounding": (["Ceil", "Floor"], {"default": "Ceil"}),
            }
        }

    RETURN_TYPES = ("INT", "INT", "FLOAT")
    RETURN_NAMES = ("Frame Count", "FPS(Int)", "FPS(Float)")
    FUNCTION = "calculate"
    CATEGORY = "Element_easy"
    
    OUTPUT_NODE = True

    def calculate(self, Type, Time, Div_by, Fps, Rounding):
        if Type == "Seconds":
            base_frames = Time * Fps
        else:
            base_frames = Time

        k_float = (base_frames - 1) / Div_by

        if Rounding == "Ceil":
            k_int = math.ceil(k_float)
        else:
            k_int = math.floor(k_float)

        final_frames = k_int * Div_by + 1

        diff = final_frames - base_frames
        if diff > 0:
            diff_str = f"+{diff}"
        elif diff < 0:
            diff_str = f"{diff}"
        else:
            diff_str = "0"
            
        final_seconds = round(final_frames / Fps, 2)

        ui_text = (
            # f"Base Frames: {base_frames}\n"
            f"Final Frames: {final_frames} ({diff_str})\n"
            f"Seconds: {final_seconds}"
        )
        
        float_Fps = float(Fps)

        return {"ui": {"text": [ui_text]}, "result": (final_frames, Fps, float_Fps)}