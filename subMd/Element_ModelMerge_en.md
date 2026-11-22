# Model Merge (Curve) Usage

A depth curve decides how much of model1 each block keeps, blending model2 into model1 by depth.

**Category**: `Element_easy/model`, output: `model` (MODEL)

---

## 1. Nodes and wiring

    model1 ──┐
    model2 ──┴─► Model Merge (Curve) ──► model
                  model_type = matching family
                  optional: Model Merge <family> Extras ──► extras

- **Model Merge (Curve)**: the merge node itself; the curve node performs the merge, no extra connector node is needed.
- **8 Extras nodes**: `Model Merge Krea2 / MOSS Image / Qwen Image / MiniMax H3 / Auraflow / LTXV / SDXL / WAN 2.1 Extras`, providing ratios for non-block layers and small auxiliary block groups.

## 2. Reading the curve

- X axis: normalized depth, 0 = closest to input, 1 = closest to output (blocks are laid out in the family's order).
- Y axis: share of **model1** at that depth. `1.0` = all model1, `0` = all model2, `0.5` = half and half.
- Default is a flat 1.0 line, i.e. no merging; pull the whole line to 0.5 for a uniform 50/50 merge.
- The two dashed lines are references: horizontal y=0.5 and vertical x=0.5.

**Controls**

| Action | Effect |
|---|---|
| Left-click empty area | Insert a point on the curve and start dragging it |
| Drag a point | Adjust the ratio at that depth (end points only move in y) |
| Right-click a middle point | Delete that point |
| `Ctrl+Z` | Undo the last step |
| `curve` / `straight` | Switch between curve and linear mode |
| `reset` | Restore the default flat 1.0 line |

The preview box below the curve lists the sampled ratios in real time.

## 3. Extras and non-block layers

Non-block layers have no depth order, so they are not on the curve; the Extras node sets their ratios:

- Without `extras` connected, these layers all use 1.0 (model1 only).
- Each slider is 0–1, same meaning as the curve's y (1.0 = model1 only).
- When Extras is connected, `model_type` must be the same family; a mismatch raises an error.

## 4. Coverage per family

| Family | Block stack driven by the curve | Extras node |
|---|---|---|
| Krea2 | `blocks` (up to 28) | Model Merge Krea2 Extras |
| MOSS Image | `layers` (up to 42) | Model Merge MOSS Image Extras |
| Qwen Image | `transformer_blocks` (up to 60) | Model Merge Qwen Image Extras |
| MiniMax H3 | `blocks` (up to 50) | Model Merge MiniMax H3 Extras |
| Auraflow | `double_layers` + `single_layers` | Model Merge Auraflow Extras |
| LTXV | `transformer_blocks` (up to 28) | Model Merge LTXV Extras |
| SDXL | `input_blocks` → `middle_block` → `output_blocks` | Model Merge SDXL Extras |
| WAN 2.1 | `blocks` (30 / 40 detected) | Model Merge WAN 2.1 Extras |

- Block counts are detected from model2's actual keys at runtime; WAN 2.1's 30/40 needs no manual choice. The preview box always shows 40 for WAN 2.1.
- Keys not covered (including auxiliary groups when Extras is not connected) stay at 1.0, i.e. taken from model1 unchanged.

## 5. Presets

- Click `REC` to enter save mode (the button turns red), then click a number 1–8 to save the current curve into that slot.
- Click a number directly to load that slot.
- Presets are stored in `presets/Model_Merge_Curve_presets.json`; all Model Merge (Curve) nodes share the same 8 slots.

## 6. Notes

- If the curve data is corrupt or invalid, the node falls back to a flat 1.0 line (no merge) instead of accidentally replacing later blocks with model2.
- The output is produced via `add_patches`, same as ComfyUI's native merge nodes, and can be fed into LoRA loaders or further merges.
