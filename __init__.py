# __init__.py
__version__ = "0.0.8" 

from .random_chars import RandomCharacterGenerator
from .empty_image_rgb import EmptyImageRGB
from .text_line_break import TextLineBreak
from .mask_stroke import MaskStrokeElement
from .mask_noise_element import MaskNoiseInjectionElement
from .image_pad_blur import ImagePadBlur

WEB_DIRECTORY = "js"

NODE_CLASS_MAPPINGS = {
    "RandomCharacterGenerator": RandomCharacterGenerator,
    "EmptyImageRGB_Element": EmptyImageRGB,
    "TextLineBreak_Element": TextLineBreak,
    "MaskStroke_Element": MaskStrokeElement,
    "MaskNoiseInjection_Element": MaskNoiseInjectionElement,
    "ImagePadBlur_Element": ImagePadBlur
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomCharacterGenerator": "Random Chars (Append)",
    "EmptyImageRGB_Element": "Empty Image RGB",
    "TextLineBreak_Element": "Text Line Break",
    "MaskStroke_Element": "Mask Stroke",
    "MaskNoiseInjection_Element": "Image Noise Using Mask",
    "ImagePadBlur_Element": "Image Pad & Blur"
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]

