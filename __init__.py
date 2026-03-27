# __init__.py
__version__ = "1.3.2" 

from .random_chars import RandomCharacterGenerator
from .empty_image_rgb import EmptyImageRGB
from .text_line_break import TextLineBreak
from .mask_stroke import MaskStrokeElement
from .mask_noise_element import MaskNoiseInjectionElement
from .image_pad_blur import ImagePadBlur
from .chessboard import ChessboardPattern_Element
from .black_white_color import BlackWhiteColor
from .Element_SigmaGraph import Element_SigmaGraph
from .frame_calc import FrameCalculator
from .Image_Size import ElementEasyImageSize
from .Element_SigmaGraph_Curve import Element_SigmaGraph_Curve
from .Element_ImageCurve import Element_ImageCurve
from .Element_HueSat import ElementHueSat
from .Element_HueHue import ElementHueHue
from .Element_HueBright import ElementHueBright
from .Load_image_Preview import LoadImageWithPreview

WEB_DIRECTORY = "js"

NODE_CLASS_MAPPINGS = {
    "RandomCharacterGenerator": RandomCharacterGenerator,
    "EmptyImageRGB_Element": EmptyImageRGB,
    "TextLineBreak_Element": TextLineBreak,
    "MaskStroke_Element": MaskStrokeElement,
    "MaskNoiseInjection_Element": MaskNoiseInjectionElement,
    "ImagePadBlur_Element": ImagePadBlur,
    "ChessboardPattern_Element": ChessboardPattern_Element,
    "BlackWhiteColor_Element": BlackWhiteColor,
    "Element_SigmaGraph": Element_SigmaGraph,
    "FrameCalculator_Element": FrameCalculator,
    "ElementEasyImageSize": ElementEasyImageSize,
    "Element_SigmaGraph_Curve": Element_SigmaGraph_Curve,
    "Element_ImageCurve": Element_ImageCurve,
    "ElementHueSat": ElementHueSat,
    "ElementHueHue": ElementHueHue,
    "ElementHueBright": ElementHueBright,
    "LoadImageWithPreview": LoadImageWithPreview,

}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomCharacterGenerator": "Random Chars (Append)",
    "EmptyImageRGB_Element": "Empty Image RGB",
    "TextLineBreak_Element": "Text Line Break",
    "MaskStroke_Element": "Mask Stroke",
    "MaskNoiseInjection_Element": "Image Noise Using Mask",
    "ImagePadBlur_Element": "Image Pad & Blur",
    "ChessboardPattern_Element": "chessboard",
    "BlackWhiteColor_Element": "BlackWhiteColor",
    "Element_SigmaGraph": "Element_SigmaGraph",
    "FrameCalculator_Element": "Frame Calculator",
    "ElementEasyImageSize": "ImageSize Div",
    "Element_SigmaGraph_Curve": "Element_SigmaGraph (Curve)",
    "Element_ImageCurve": "Element ImageCurve",
    "ElementHueSat": "Element HueSat",
    "ElementHueHue": "Element HueHue",
    "ElementHueBright": "Element HueBright",
    "LoadImageWithPreview": "LoadImage_Preview",

}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
