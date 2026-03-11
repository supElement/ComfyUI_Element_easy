import math

class ElementEasyImageSize:
    def __init__(self):
        pass

    @classmethod
    def INPUT_TYPES(s):
        return {
            "required": {
                "Direction": (["Horizontal", "Vertical"], {"default": "Horizontal"}),
                "Length": ("INT", {"default": 1920, "min": 64, "max": 8192, "step": 1}),
                "Short": ("INT", {"default": 1080, "min": 64, "max": 8192, "step": 1}),
                "Div": ("INT", {"default": 1, "min": 1, "max": 256, "step": 1}),
            }
        }

    RETURN_TYPES = ("INT", "INT")
    RETURN_NAMES = ("width", "height")
    FUNCTION = "calculate_dimensions"
    CATEGORY = "Element_easy"

    def calculate_dimensions(self, Direction, Length, Short, Div):
       
        Div = max(1, Div)

        
        if Direction == "Horizontal":
            raw_width = Length
            raw_height = Short
        else:
            raw_width = Short
            raw_height = Length

        
        
        width = math.ceil(raw_width / Div) * Div
        height = math.ceil(raw_height / Div) * Div

        return (width, height)