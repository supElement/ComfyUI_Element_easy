# Element_ModelMergeCurve.py —— 通用模型合并曲线节点。
# 曲线节点本身就是合并节点：model1/model2 在节点上，extras 通过可选端口接入，
# 不再有额外的 merge 连接节点。

import json
import os

from aiohttp import web
from server import PromptServer

from ..element_easy.merge_common import FAMILIES, merge_models, widget_name

DEFAULT_GRAPH = json.dumps({
    "points": [{"x": 0.0, "y": 1.0}, {"x": 1.0, "y": 1.0}],
    "mode": "curve",
})


def _weight_input():
    return ("FLOAT", {"default": 1.0, "min": 0.0, "max": 1.0, "step": 0.01})


class Element_ModelMergeCurve:
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model1": ("MODEL",),
                "model2": ("MODEL",),
                "model_type": (list(FAMILIES.keys()), {"default": "Krea2"}),
                "graph_data": ("STRING", {"default": DEFAULT_GRAPH, "multiline": True}),
            },
            "optional": {
                "extras": ("EE_MM_EXTRAS",),
            },
        }

    RETURN_TYPES = ("MODEL",)
    RETURN_NAMES = ("model",)
    FUNCTION = "merge"
    CATEGORY = "Element_easy/model"
    DESCRIPTION = (
        "按归一化深度曲线合并 diffusion_model 权重；y = model1 占比。"
        "非 block 层与小旁支 block 组由对应的 *_Extras 节点提供，未连接时全为 1.0。"
    )

    def merge(self, model1, model2, model_type="Krea2", graph_data=DEFAULT_GRAPH, extras=None):
        return (merge_models(model1, model2, model_type, graph_data, extras),)


def _make_extras_node(model_type, spec):
    prefixes = spec["extras"]
    names = [widget_name(p) for p in prefixes]

    class _ExtrasNode:
        @classmethod
        def INPUT_TYPES(cls):
            return {"required": {name: _weight_input() for name in names}}

        RETURN_TYPES = ("EE_MM_EXTRAS",)
        RETURN_NAMES = ("extras",)
        FUNCTION = "build"
        CATEGORY = "Element_easy/model"
        DESCRIPTION = f"{spec['label']} 的非 block 层比例（1.0 = 只取 model1）。"

        def build(self, **values):
            return ({
                "model_type": model_type,
                "ratios": {
                    prefix: float(values[name])
                    for prefix, name in zip(prefixes, names)
                },
            },)

    _ExtrasNode.__name__ = f"Element_ModelMerge{model_type}_Extras"
    _ExtrasNode.__qualname__ = _ExtrasNode.__name__
    return _ExtrasNode


NODE_CLASS_MAPPINGS = {
    "Element_ModelMergeCurve": Element_ModelMergeCurve,
}
NODE_DISPLAY_NAME_MAPPINGS = {
    "Element_ModelMergeCurve": "Model Merge (Curve)",
}

for _model_type, _spec in FAMILIES.items():
    _node_id = f"Element_ModelMerge{_model_type}_Extras"
    NODE_CLASS_MAPPINGS[_node_id] = _make_extras_node(_model_type, _spec)
    NODE_DISPLAY_NAME_MAPPINGS[_node_id] = f"Model Merge {_spec['label']} Extras"


# ==========================================
# 预设文件存储 API（独立于 ListGraph 预设）
# ==========================================

base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
presets_dir = os.path.join(base_dir, "presets")
presets_file = os.path.join(presets_dir, "Model_Merge_Curve_presets.json")

if not os.path.exists(presets_dir):
    os.makedirs(presets_dir, exist_ok=True)


@PromptServer.instance.routes.get("/element_easy/model_merge_curve_presets")
async def get_model_merge_presets(request):
    if os.path.exists(presets_file):
        try:
            with open(presets_file, "r", encoding="utf-8") as f:
                data = json.load(f)
            return web.json_response(data)
        except Exception as e:
            print(f"[Element_ModelMergeCurve] 读取预设文件失败: {e}")
    return web.json_response([])


@PromptServer.instance.routes.post("/element_easy/model_merge_curve_presets")
async def save_model_merge_presets(request):
    try:
        data = await request.json()
        with open(presets_file, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=4)
        return web.json_response({"status": "success"})
    except Exception as e:
        print(f"[Element_ModelMergeCurve] 保存预设文件失败: {e}")
        return web.json_response({"status": "error", "message": str(e)}, status=500)
