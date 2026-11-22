# element_easy/merge_common.py —— 模型合并曲线共享核心。
# 曲线只覆盖有序 block 栈；非 block 层与小旁支 block 组由 *_Extras 节点提供，
# 未提供的层按 1.0（只取 model1）。

import json
import math
import re

_DIFFUSION = "diffusion_model."
_INDEX_RE = re.compile(r"^(\d+)\.")

FAMILIES = {
    "Krea2": {
        "label": "Krea2",
        "segments": [("blocks.", 28)],
        "extras": [
            "first.", "tmlp.", "txtmlp.", "tproj.",
            "txtfusion.layerwise_blocks.0.", "txtfusion.layerwise_blocks.1.",
            "txtfusion.projector.",
            "txtfusion.refiner_blocks.0.", "txtfusion.refiner_blocks.1.",
            "last.",
        ],
    },
    "MOSSImage": {
        "label": "MOSS Image",
        "segments": [("layers.", 42)],
        "extras": [
            "video_embedder.", "text_embedder.proj.",
            "text_embedder.blocks.0.", "text_embedder.blocks.1.",
            "time_embedding.", "shared_block_modulation.",
            "final_norm_video.", "final_linear_video.", "video_head_modulation.",
        ],
    },
    "QwenImage": {
        "label": "Qwen Image",
        "segments": [("transformer_blocks.", 60)],
        "extras": [
            "pos_embeds.", "img_in.", "txt_norm.", "txt_in.",
            "time_text_embed.", "proj_out.",
        ],
    },
    "MiniMaxH3": {
        "label": "MiniMax H3",
        "segments": [("blocks.", 50)],
        "extras": [
            "video_patch_proj.", "audio_patch_proj.", "condition_proj.", "time_embedder.",
            "token_refiner.blocks.0.", "token_refiner.blocks.1.",
            "token_refiner.final_norm.",
            "final_layer.norm.", "final_layer.adaln_proj.",
            "final_layer.video_out.", "final_layer.audio_out.",
        ],
    },
    "Auraflow": {
        "label": "Auraflow",
        "segments": [("double_layers.", 4), ("single_layers.", 32)],
        "extras": [
            "init_x_linear.", "positional_encoding", "cond_seq_linear.",
            "register_tokens", "t_embedder.", "modF.", "final_linear.",
        ],
    },
    "LTXV": {
        "label": "LTXV",
        "segments": [("transformer_blocks.", 28)],
        "extras": [
            "patchify_proj.", "adaln_single.", "caption_projection.",
            "scale_shift_table", "proj_out.",
        ],
    },
    "SDXL": {
        "label": "SDXL",
        "segments": [
            ("input_blocks.", 9),
            ("middle_block.", 3),
            ("output_blocks.", 9),
        ],
        "extras": ["time_embed.", "label_emb.", "out."],
    },
    "WAN2_1": {
        "label": "WAN 2.1",
        "segments": [("blocks.", 40)],
        "extras": [
            "patch_embedding.", "time_embedding.", "time_projection.",
            "text_embedding.", "img_emb.", "head.",
        ],
    },
}


def widget_name(prefix):
    return prefix[:-1] if prefix.endswith(".") else prefix


def _valid_point(point):
    return (
        isinstance(point, dict)
        and isinstance(point.get("x"), (int, float))
        and math.isfinite(point["x"])
        and isinstance(point.get("y"), (int, float))
        and math.isfinite(point["y"])
    )


def sample_curve(graph_data, steps):
    if steps <= 0:
        return []

    # ListGraph 对非法数据会回退到 1→0；合并场景下这等于末段全换成 model2，
    # 因此这里先校验，非法数据按平线 1.0（不合并）处理。
    valid = False
    try:
        data = json.loads(graph_data)
        points = data.get("points") if isinstance(data, dict) else data
        if (isinstance(points, list)
                and len(points) >= 2
                and all(_valid_point(p) for p in points)):
            xs = sorted(float(p["x"]) for p in points)
            valid = any(b - a > 1e-6 for a, b in zip(xs, xs[1:]))
    except (TypeError, ValueError):
        pass
    if not valid:
        print("[Element_ModelMergeCurve] 曲线数据无效，按平线 1.0 处理")
        return [1.0] * steps

    # 惰性导入：避免 element_easy 共享库与 nodes 包互相牵制加载顺序。
    from ..nodes.Element_listGraph_Curve import Element_listGraph_Curve
    values, _ = Element_listGraph_Curve().calculate_values(steps, graph_data, 1.0)
    return values


def _count_blocks(keys, prefix, max_count):
    count = 0
    for key in keys:
        tail = key[len(_DIFFUSION):]
        if not tail.startswith(prefix):
            continue
        match = _INDEX_RE.match(tail[len(prefix):])
        if match:
            count = max(count, int(match.group(1)) + 1)
    return min(count, max_count)


def merge_models(model1, model2, model_type, graph_data, extras=None):
    family = FAMILIES.get(model_type)
    if family is None:
        raise ValueError(f"Unknown model_type: {model_type!r}")

    if extras is not None:
        extras_type = extras.get("model_type")
        if extras_type != model_type:
            raise ValueError(
                f"extras belongs to {extras_type!r}, but model_type is {model_type!r}"
            )

    # 运行时探测每个段实际存在的 block 数（WAN 2.1 的 30/40 自动适配）。
    key_patches = model2.get_key_patches(_DIFFUSION)
    counts = [_count_blocks(key_patches, prefix, limit)
              for prefix, limit in family["segments"]]
    values = sample_curve(graph_data, sum(counts))

    ratios = {}
    offset = 0
    for (prefix, _), count in zip(family["segments"], counts):
        for i in range(count):
            ratios[f"{prefix}{i}."] = values[offset + i]
        offset += count
    if extras is not None:
        for prefix, ratio in extras.get("ratios", {}).items():
            ratios[prefix] = float(ratio)

    merged = model1.clone()
    for key in key_patches:
        tail = key[len(_DIFFUSION):]
        ratio = 1.0
        best = -1
        for prefix, value in ratios.items():
            if len(prefix) > best and tail.startswith(prefix):
                best = len(prefix)
                ratio = value
        if ratio == 1.0:
            continue
        merged.add_patches({key: key_patches[key]}, 1.0 - ratio, ratio)
    return merged
