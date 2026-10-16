# element_easy —— ComfyUI_Element_easy 内部共享库
#
# 该包只被本扩展的各节点模块通过相对导入使用（from .element_easy import ...），
# 不对外暴露 NODE_CLASS_MAPPINGS，ComfyUI 不会把它当作独立自定义节点加载。
