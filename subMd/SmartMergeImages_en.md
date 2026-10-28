# Smart Merge Images User Guide

Put AI-edited local images back into the original image at the correct position and size, and clean up seams and color differences. Input can be a single image or multiple crops (each crop can have a different size). Each run outputs one merged image.

![node] Category: `Element_easy/image`, Output: `Merged_Image` (IMAGE)

---

## Minimal Wiring

```
Original image ─────────────► original_image
AI-edited crop ─────────────► edited_crop_B
Pre-edit original crop (optional) ──► original_crop_A     ← strongly recommended; most stable
ElementTileSplit grid (optional) ► split_grid  ← connect when using TileSplit
```

- **Connect `original_crop_A`**: the node knows exactly where each crop originally was in the image. Alignment is most accurate, and local deformation can be corrected automatically.
- **Connect `split_grid`**: the gradients/rounded edges at crop borders match TileSplit exactly, so multi-crop stitching has no hard edges.
- If neither is connected, the node will still try to find positions automatically on the background, but on complex images it may occasionally place crops incorrectly. Crops that fail alignment are **skipped** (the original image is kept; they will not be forced into the center of the image).

**Recommended initial parameters**

| Parameter | Recommendation |
|---|---|
| Deformation correction `warp_method` | On |
| Optical flow mode `optical_flow` | On (slower) / Off (faster) |
| TPS `use_tps` | On |
| Color `color_match` | `Patch_based_color` or `Edge_Weighted_Color` |
| Feathering `feather_kernel` | 20–40 (increase to 40–60 when seams are obvious) |
| `use_gpu` | On |

---

## Effect of Each Parameter on Results

### 1. Deformation correction `warp_method` (default: off)

Determines whether to correct local deformation caused by AI repainting when compositing.

- **Off**: only global positioning; pure geometry; fastest and most stable.
- **On**: after positioning, further correct fine misalignments (expressions, clothing folds, slight edge deformation).

> Effect: On → better fit, at the cost of speed; can be turned off when the image has no local deformation.

### 2. Optical flow mode `optical_flow` (default: off; only effective when `warp_method` is on)

- **Off = Farneback**: CPU algorithm, fastest.
- **On = DIS**: better quality, cleaner edges, recommended.

> Effect: only affects the precision and speed of "refinement", not moment/position. Toggling it will not trigger realignment.

### 3. Non-rigid correction `use_tps` (default: on)

- **On**: allows slight bending/stretching to fit the background. This fixes the common AI repaint issue where "the content is right but the shape is slightly off".
- **Off**: only global translation, scaling, and rotation; fastest.

> Effect: On → local deformation can be corrected; Off → deformation will be pasted back as-is.

### 4. Refinement smoothing `warp_smooth` (default: 1.0, range 0–4)

Only works in the final "whole-image refinement" step; controls the smoothness of correction displacement.

- **Increase**: corrections are smoother and more conservative, with almost no local twisting.
- **Decrease / 0**: allows finer displacement corrections; may fit better, but is also more prone to slight jitter.

> Note: when the alignment error of each crop is already very small (<0.8px), the node automatically skips whole-image refinement, and this parameter has no effect.

### 5. Color strategy `color_match` (default: `Patch_based_color`)

This is the parameter with the greatest impact on the final visual result. **The six modes form a gradient from "changes colors" to "does not change colors"**:

| Mode | Effect | Suitable for | Notes |
|---|---|---|---|
| `Patch_based_color` | Corrects color differences per patch, aligning tone to the background region by region; with weakened protection for AI-edited areas | Large and uneven color differences (half warm, half cool); multi-crop stitching | Slowest; edited content will not be pulled back to the background color, but a small amount of correction is still applied |
| `Edge_Weighted_Color` | Uses unchanged edge regions to unify tone | Overall color cast while needing to **preserve colors changed by AI** (e.g., changing clothes to red) | Global single-direction correction; local multi-color differences are handled less well than with Patch |
| `LAB_Mean` | Aligns the whole crop to the background by mean/variance | Single color difference; quick output | Areas with large content changes may be washed out overall |
| `Laplacian Pyramid Blend` | Multi-band blending; only addresses seams | Colors are already correct, only seams look bad | **Does not perform color correction** |
| `SeamlessClone (PS Auto Blend)` | Poisson blending | Content is basically unchanged; only want to remove seams | **Areas with large content changes will fade/turn gray; use with caution** |
| `Alpha Soft Blend` | Feather blending only | Almost no color difference; fastest | Does not handle color differences at all |

> Practical conclusions:
> - If **gray patches / washed-out colors** appear → switch to `Edge_Weighted_Color`, or avoid SeamlessClone.
> - If only the seams need to look good and colors already match → `Laplacian Pyramid Blend`.
> - If you want the fastest way to check composition → `Alpha Soft Blend`.

### 6. Feathering `feather_kernel` (default: 20, range 0–256)

The soft transition width at paste edges; also determines the "patch size" for color correction.

- **Increase**: seams are softer and more invisible; color transitions are smoother. But it consumes more original image content, details may be softened, and it is slower.
- **Decrease**: edges are sharper and more original detail is preserved; too small may reveal boundaries or color steps at seams.
- **0**: hard-edge paste; only for cases that do not need blending.

> Experience: normal repaint 20–30; multi-crop stitching/large images 40–60; TileSplit workflows generally match its overlap.

### 7. Merge mode `merge_mode` (default: All to One)

- **All to One**: all edited crops are pasted back in order onto the **first** background, outputting 1 image (multi-element collage).
- **One to One**: backgrounds are paired one-to-one with edited crops; output count equals the number of backgrounds (batch processing multiple images).

### 8. `use_gpu` (default: on)

Uses GPU acceleration for matching/optical flow. If VRAM is insufficient or CUDA is unavailable, turn it off; functionality is the same, just slower.

### 9. `force_recompute` (default: off)

The node caches the previous alignment results (up to 4 groups). When rerunning with the same input:

- Changing parameters that do not affect position, such as **color mode, feathering, optical flow mode, smoothing** → **no realignment**; output in seconds.
- Check `force_recompute` → force clear the cache and realign from scratch (useful for comparing different alignment results).

---

## Quick Troubleshooting

| Symptom | Solution |
|---|---|
| Gray patches / AI-changed colors are washed out | Do not use `SeamlessClone`; switch to `Edge_Weighted_Color` |
| Seams are visible | Increase feathering to 30–50; or switch to `Laplacian Pyramid Blend` |
| Crops are misplaced or missing | Connect `original_crop_A`; when using TileSplit, connect `split_grid`; the log will indicate which crop was skipped |
| Local deformation is not corrected well | Turn on `use_tps` + turn on `warp_method` |
| Horizontal/vertical stripes or misalignment at stitching | Check whether `split_grid` comes from the same split operation |
| Too slow | Turn off `optical_flow`; switch to a lightweight color mode; do not check `force_recompute` frequently |
| Color-changed objects are "corrected" back to their original color | Use `Patch_based_color` or `Edge_Weighted_Color`; avoid `LAB_Mean` / `SeamlessClone` |

---

## Input/Output Description

- All three image ports support **single image / batch / list**; no additional "Image List To Image Batch" node is needed.
- Each edited crop can have a different size; the node processes at each crop's original resolution.
- `original_crop_A` count/size does not need to strictly match B; they are paired in order.
- Output: `All to One` outputs 1 image; `One to One` outputs a batch with the same count as the backgrounds.
- Crops that cannot be reliably positioned will be skipped and listed in the log; the corresponding regions keep the original image content.