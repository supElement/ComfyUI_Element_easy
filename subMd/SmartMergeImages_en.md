# Smart Merge Images User Guide

Pastes AI-edited local images back into the original image at the correct position and size, and cleans up seams and color differences.
Input can be a single image or multiple blocks (each block may have a different size). One execution outputs one or more merged images (depending on `merge_mode`).

**Category**: `Element_easy/image`，Output: `Merged_Image` (IMAGE)

---

## 1. Minimal Wiring

    original image ─────────────► original_image
    AI-edited block ────────────► edited_crop_B
    pre-edit crop (optional) ───► original_crop_A     ← strongly recommended, most reliable
    ElementTileSplit grid (optional) ► split_grid     ← connect when using TileSplit

- **Connect `original_crop_A`**: the node knows where each block originally sat in the frame — most accurate placement, and it can automatically correct local deformation (TPS bridge).
- **Connect `split_grid`**: the paste edge gradients/rounded corners match the TileSplit node's grid in the ComfyUI-Element_TileEdit extension exactly, so multi-block stitching has no hard edges. If the grid carries `work_w`/`work_h`, the original image is first resized to that working canvas size before compositing.
- Neither is required: the node will auto-locate positions on the background. On complex scenes it may occasionally paste off-target; blocks that fail placement are **skipped** (the original content is kept — it never forces a paste into the middle of the frame).

**Recommended starting parameters**

| Parameter | Recommendation |
|---|---|
| Deformation correction `warp_method` | ON |
| Optical flow mode `optical_flow` | ON (slower) / OFF (faster) |
| TPS `use_tps` | ON |
| Smoothing `warp_smooth` | Default 1.0; raise slightly if wavy local distortion appears |
| Color matching `color_match` | `Patch_based_color` |
| Color protection `color_protection` | OFF (default). When ON, edited regions are no longer pulled toward the background color; if there is no intentional hue edit, keep it OFF. |
| Feathering `feather_kernel` | 20~40 (raise to 40~60 when seams are obvious) |
| `use_gpu` | ON (default) |

---

## 2. Effect of Each Parameter

### 1. Deformation correction `warp_method` (default OFF)
Controls whether local deformation caused by AI redrawing is corrected during paste.
- **OFF**: homography-only placement, pure geometry. If the AI drew lines crooked, nothing fixes them here.
- **ON**: on top of placement, TPS and optical flow further correct fine misalignment (expressions, clothing folds, slight edge deformation).

### 2. Optical flow mode `optical_flow` (default OFF, only effective when `warp_method` is ON)
- **OFF = Farneback**: CPU algorithm.
- **ON = DIS**: better quality, cleaner edges, recommended.

> **Note**: optical flow (both global and local) is physically only suited for **fine adjustment** (local ~10~15 px, global 12 px cap). Large misalignment cannot be rescued by optical flow — it must be handled by TPS first.

### 3. Non-rigid correction `use_tps` (default ON)
- **ON**: allows mild bending/stretching to fit the background. The common AI-redraw case of "content right but shape slightly off" is fixed by this.
- **OFF**: only global translation/scale/rotation (if `warp_method` is ON, optical-flow polish still applies).

### 4. Polish smoothing `warp_smooth` (default 1.0, range 0~4)
Only affects the final "global polish" step, controlling how smooth the correction displacement is.
- **0 ~ 1.0 (mild)**: allows finer displacement corrections — may fit better, but can also show slight jitter.
- **1.0 ~ 2.0 (strong)**: the most conservative smoothing of the old version; corrections are smoother.
- **2.0 ~ 4.0 (very strong)**: forces the flow field to low frequency; almost no local wiggling is produced.

### 5. Color strategy `color_match` (default `Patch_based_color`)
The parameter with the biggest influence on final appearance. **The five modes form a gradient from "will recolor" to "will not recolor"**:

| Mode | Effect | Suited for | Caveats |
|---|---|---|---|
| `Patch_based_color` | Patch-wise color correction, aligning tone to the background region by region | Large/uneven color casts; multi-block stitching | Slowest; but if protection is ON, edited regions are preserved |
| `LAB_Mean` | Aligns the whole block to the background by mean/variance | Uniform color cast, quick output | Heavily changed content may be washed out globally |
| `Laplacian Pyramid Blend` | Luminance matching first, then multi-band blending to fix seams | Colors already close, only need luminance matching + seam cleanup | Luminance matching only (median shift on the L channel); no color (a/b) correction |
| `SeamlessClone (PS Auto Blend)` | Luminance matching first, then Poisson blending | Content basically unchanged, only need to remove seams | Heavily changed content will fade/gray — use with caution |
| `Alpha Soft Blend` | Feather blending only | Almost no color cast, fastest | No color handling at all when a cast exists |

### 6. Color protection `color_protection` (default OFF)
**Only affects the color-matching chain** (global coarse LAB correction + per-patch fine correction).
- **OFF (default)**: color matching does not distinguish edited from un-edited pixels; the whole block is unified to the background tone, and edited regions are pulled toward the background color too — strongest correction.
- **ON**: only un-edited pixels are used to estimate the color shift, and color correction inside edited regions is attenuated. AI recolors are preserved, but the color difference between edited region and background is preserved as well.

### 7. Feathering `feather_kernel` (default 20, range 0~256)
The soft transition width at the paste edge; also determines the "patch size" for color correction.
- **Larger (30~60)**: softer seams. If you see "hard cuts/offsets" at the edge, increasing feathering is the most direct and safest way to hide them.
- **Smaller**: sharper edges, but pixel-level misalignment cuts become visible.

### 8. Merge mode `merge_mode` (default All to One)
- **All to One**: all edited blocks are pasted sequentially onto the **first** background; outputs 1 image.
- **One to One**: backgrounds and edited blocks are paired in equal counts; outputs the same number of images as backgrounds.

### 9. `use_gpu` and `force_recompute`
- **`use_gpu`** (default ON): accelerates feature matching (DISK/LoFTR) and color matching. OpenCV steps (optical flow, TPS/warp, seamless clone) still run on CPU.
- **`force_recompute`** (default OFF): changing color mode/feathering does not re-run alignment (alignment cache holds 4 entries, LRU); check this to force-clear the cache and re-align from scratch.

---

## 3. Quick Troubleshooting

| Symptom | Solution |
|---|---|
| **Hard cuts / offsets at the edge** | 1. Raise `feather_kernel` to 40+ <br>2. Turn OFF `color_protection` (when ON, edited-region color is not corrected, so the color difference remains) <br>3. Make sure `warp_method` is ON so optical flow can engage. |
| **Distant local regions (e.g. a face near the frame edge) not aligned** | The original TPS has distance falloff and displacement caps to protect the image from tearing. If distant misalignment is severe:<br>1. You must connect `original_crop_A` to use the bridge path.<br>2. Lower `warp_smooth` appropriately to allow optical-flow fine adjustment. |
| **Local deformation not fixed** | Ensure `use_tps` is ON + `warp_method` is ON; check the log for `TPS rejected` messages. |
| **Blocks pasted off-target or missing** | Connect `original_crop_A`; the log will report which block was skipped due to no reliable placement. |
| **Colors washed out / grayish** | Switch to `Patch_based_color`; avoid `SeamlessClone`. |

---

## 4. Inputs and Outputs

- All three image ports support **single / batch / list**; no extra "Image List To Image Batch" node is needed.
- Each edited image may have a different size; the node processes each at its native resolution.
- `original_crop_A` does not need to match B in count or size exactly; pairing is by order.
- Output: `All to One` → 1 image; `One to One` → a batch with the same count as backgrounds.
- Blocks that cannot be reliably placed are skipped and listed in the log; the corresponding regions keep the original content.
