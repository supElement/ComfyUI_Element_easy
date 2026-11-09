# __init__.py
__version__ = "1.5.5" 

from .nodes.random_chars import RandomCharacterGenerator
from .nodes.empty_image_rgb import EmptyImageRGB
from .nodes.text_line_break import TextLineBreak
from .nodes.mask_stroke import MaskStrokeElement
from .nodes.mask_noise_element import MaskNoiseInjectionElement
from .nodes.image_pad_blur import ImagePadBlur
from .nodes.chessboard import ChessboardPattern_Element
from .nodes.black_white_color import BlackWhiteColor
from .nodes.frame_calc import FrameCalculator
from .nodes.Image_Size import ElementEasyImageSize
from .nodes.Element_SigmaGraph_Curve import Element_SigmaGraph_Curve
from .nodes.Element_listGraph_Curve import Element_listGraph_Curve
from .nodes.Element_ImageCurve import Element_ImageCurve
from .nodes.Element_HueSat import ElementHueSat
from .nodes.Element_HueHue import ElementHueHue
from .nodes.Element_HueBright import ElementHueBright
from .nodes.Load_image_Preview import LoadImageWithPreview
from .nodes.Smart_merge_images import SmartMergeImages

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
    "FrameCalculator_Element": FrameCalculator,
    "ElementEasyImageSize": ElementEasyImageSize,
    "Element_SigmaGraph_Curve": Element_SigmaGraph_Curve,
    "Element_listGraph_Curve": Element_listGraph_Curve,
    "Element_ImageCurve": Element_ImageCurve,
    "ElementHueSat": ElementHueSat,
    "ElementHueHue": ElementHueHue,
    "ElementHueBright": ElementHueBright,
    "LoadImageWithPreview": LoadImageWithPreview,
    "SmartMergeImages": SmartMergeImages,

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
    "FrameCalculator_Element": "Frame Calculator",
    "ElementEasyImageSize": "ImageSize Div",
    "Element_SigmaGraph_Curve": "Element_SigmaGraph",
    "Element_listGraph_Curve": "Element_ListGraph",
    "Element_ImageCurve": "Element ImageCurve",
    "ElementHueSat": "Element HueSat",
    "ElementHueHue": "Element HueHue",
    "ElementHueBright": "Element HueBright",
    "LoadImageWithPreview": "LoadImage_Preview",
    "SmartMergeImages": "Smart merge images",

}

# ---- 动态注册（单模块失败只跳过自身，不影响其它节点） ----
import importlib
import traceback

def _register_module(module):
    NODE_CLASS_MAPPINGS.update(getattr(module, "NODE_CLASS_MAPPINGS", {}))
    NODE_DISPLAY_NAME_MAPPINGS.update(getattr(module, "NODE_DISPLAY_NAME_MAPPINGS", {}))

def _try_register(module_name: str) -> bool:
    try:
        mod = importlib.import_module(".nodes." + module_name, __name__)
        _register_module(mod)
        return True
    except Exception as e:
        print(f"\n[Element_easy] 模块 {module_name} 加载失败，已跳过: "
              f"{type(e).__name__}: {e}")
        traceback.print_exc()   
        print(f"[Element_easy] 其余节点继续正常加载。\n")
        return False

_try_register("MinimaxH3LatentUpscaler")
_try_register("MinimaxH3LatentUpscaler_Adv")
_try_register("Element_scene_detection")
_try_register("Element_multi_ref")
_try_register("Element_prompt_presets")
_try_register("Element_value_remap")


#-----------------

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]
