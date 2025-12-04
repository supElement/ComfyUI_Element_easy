from .random_chars import RandomCharacterGenerator
from .empty_image_rgb import EmptyImageRGB
from .text_line_break import TextLineBreak

# ==============================================================================
# 关键修改：告诉 ComfyUI 前端文件在哪里
# "." 表示当前目录，"./js" 表示当前目录下的 js 文件夹
# ==============================================================================
WEB_DIRECTORY = "./js"

NODE_CLASS_MAPPINGS = {
    "RandomCharacterGenerator": RandomCharacterGenerator,
    "EmptyImageRGB_Element": EmptyImageRGB,
    "TextLineBreak_Element": TextLineBreak
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "RandomCharacterGenerator": "Random Chars (Append)",
    "EmptyImageRGB_Element": "Empty Image RGB",
    "TextLineBreak_Element": "Text Line Break"
}

# 记得把 WEB_DIRECTORY 加到这里
__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS", "WEB_DIRECTORY"]