# Smart Merge Images User Guide

Pastes AI-edited local images back into the original image at the correct position and size, and cleans up seams and color differences.
Input can be a single image or multiple blocks (each block may have a different size); one execution merges all blocks into one image.

**Category**: `Element_easy/image`, Output: `Merged_Image` (IMAGE)

---

## 1. Minimal Wiring

    original image ─────────────► original_image
    AI-edited block ────────────► edited_crop_B
    pre-edit crop (optional) ───► original_crop_A     ← strongly recommended, most reliable
    ElementTileSplit grid (optional) ► split_grid     ← connect when using TileSplit

- **Connect `original_crop_A`**: the node knows where each block originally sat in the frame — most accurate placement, and it enables bridge-style non-rigid correction (TPS bridge: LoFTR matches B↔A, then the A→BG homography maps those points into background space).
- **Connect `split_grid`**: alpha / feathering follows Element Tile Merge's tile geometry in ComfyUI-Element_TileEdit pixel-for-pixel — hand-drawn box position and 50% point, same-layer lock-band exclusion, radial rounded-corner ramp, and canvas-edge handling. `feather_kernel` is then interpreted as that node's feather (0~100 → 0~1.0, 100 = maximum). If the grid carries `exact_w`/`exact_h` (the real output size from the newer Split), the canvas uses that size directly; grids without these fields fall back to the `work_w`/`work_h` working canvas.
- Neither is required: the node will auto-locate positions on the background. On complex scenes it may occasionally paste off-target; blocks that fail placement are **skipped** (the original content is kept — it never forces a paste into the middle of the frame).

**Recommended starting parameters**

| Parameter | Recommendation |
|---|---|
| TPS `use_tps` | ON |
| Per-crop flow `Optical_Flow` | ON |
| Second-pass refinement `second_pass` | OFF (turn on when slight local misalignment remains after the first flow pass) |
| Global flow polish `Full_Optical_Flow` | ON (turn off if you only want per-crop refinement) |
| Smoothing `warp_smooth` | Default 1.0; raise slightly if wavy local distortion appears |
| Color matching `color_match` | `Patch_based_color` |
| Color protection `color_protection` | OFF (default). When ON, edited regions are no longer pulled toward the background color; the edited-color threshold is `Color_p_threshold` (default 20). |
| Color threshold `Color_p_threshold` | 20 (matches previous behavior); raise it when the recolor is strong |
| Feathering `feather_kernel` | 20~40 (raise to 40~60 when seams are obvious); with split_grid it is a 0~100 scale — see 2.9 |
| `use_gpu` | ON (default) |

---

## 2. Effect of Each Parameter

### 1. Non-rigid correction `use_tps` (default ON)
- **ON**: allows mild bending/stretching to fit the background. The common AI-redraw case of "content right but shape slightly off" is fixed by this. The bridge path uses LoFTR correspondences; the auto path (no A) uses DISK features.
- **OFF**: homography only (translation/scale/rotation/perspective); if `Optical_Flow` is ON, per-crop flow still applies (global polish is controlled separately by `Full_Optical_Flow`).

### 2. Per-crop flow `Optical_Flow` (default OFF)
It does **not** control TPS; it only enables the per-crop flow pass — global polish has its own switch, `Full_Optical_Flow`. The widget is named `Optical_Flow`; the switch shows `on` / `off`.
- **OFF**: placement only (bridge homography / auto homography). If `use_tps` is ON, TPS non-rigid correction still runs; per-crop flow is skipped (`second_pass` ON still runs one separate 4 px small per-crop flow pass).
- **ON**: each crop is locally aligned to the background, capped at 10 px on the bridge path with `original_crop_A` / 15 px on the auto path without it; the auto path skips this step when the post-placement residual is already below 1.2 px.
- Flow backend is automatic: DIS first, Farneback fallback when unavailable — there is no separate switch.
- With `original_crop_A` connected, flow is estimated at the content's native resolution (scaled by the A/B width ratio, long side capped at 1536), so accuracy follows the content rather than the canvas.

> **Note**: optical flow (both per-crop and global) is physically only suited for **fine adjustment** (about 10–15 px per crop, 12 px global cap). Large misalignment cannot be rescued by optical flow — use TPS or connect `original_crop_A`.

### 3. Second-pass refinement `second_pass` (default OFF)
Independent of TPS: it runs one more small-amplitude per-crop flow pass after the first per-crop flow.
- **ON**: each crop runs the per-crop flow once more on the current result with a 4 px displacement cap (first pass: 10 px on the bridge route, 15 px on the auto route) and the result is **applied directly** — there is no score-based check.
- **OFF (default)**: skips this step.
- It does not require `use_tps`; it also runs on its own when `Optical_Flow` is OFF.
- Use it when slight local misalignment remains after the first flow pass (edges, thin lines, text).
- Caveat: it only applies small geometric corrections. If edges get worse with it ON, turn it off.

### 4. Global flow polish `Full_Optical_Flow` (default OFF)
After compositing, the whole merged image is corrected once against the original, capped at 12 px and smoothed by `warp_smooth`.
- Independent of `Optical_Flow` and `second_pass`: turning only this on still runs the global pass.
- **OFF**: skips the step; compositing/color matching is the last stage.
- **ON**: useful when the whole frame is still slightly offset; adds one global flow pass per run, whose cost grows with canvas size.

### 5. Polish smoothing `warp_smooth` (default 1.0, range 0~4)
Only affects the final "global polish" step (which runs only when `Full_Optical_Flow` is ON), controlling how smooth the correction displacement is.
- **0 ~ 1.0 (mild)**: allows finer displacement corrections — may fit better, but can also show slight jitter.
- **1.0 ~ 2.0 (strong)**: the most conservative smoothing of the old version; corrections are smoother.
- **2.0 ~ 4.0 (very strong)**: forces the flow field to low frequency; almost no local wiggling is produced.

### 6. Color strategy `color_match` (default `Patch_based_color`)
The parameter with the biggest influence on final appearance. **Except `Alpha Soft Blend`, every mode first applies a gentle global LAB correction** (per-crop median LAB shift × 0.35, capped at 10/4/4, skipped when below 0.25), then runs the selected per-crop pass. So even the "luminance-only" modes still get a slight global a/b nudge.

| Mode | Effect | Suited for | Caveats |
|---|---|---|---|
| `Patch_based_color` | Boundary-band sync first, then a patch-grid color sync, aligning tone to the background region by region | Large/uneven color casts; multi-block stitching | Slowest; block size depends on `feather_kernel` / `color_protection` (see 2.9) |
| `LAB_Mean` | Aligns the whole block to the background in LAB by mean + robust std (10–90 percentile), then adds a low-frequency LAB difference field (clipped to 24/10/10) for spatially uneven casts | Uniform or uneven color cast, quick output | Heavily changed content may be washed out globally |
| `Laplacian Pyramid Blend` | Per-crop pass shifts the L-channel median plus a low-frequency L field, then multi-band blending fixes seams | Colors already close, only need luminance matching + seam cleanup | No a/b correction at the per-crop level (the global coarse pass still nudges a/b); 3–5 levels depending on feathering |
| `SeamlessClone (PS Auto Blend)` | Per-crop luminance matching (median + low-frequency L field), then Poisson blending | Content basically unchanged, only need to remove seams | Heavily changed content will fade/gray — use with caution |
| `Alpha Soft Blend` | Feather blending only | Almost no color cast, fastest | The only mode that also skips the global LAB correction |

### 7. Color protection `color_protection` (default OFF)
**Only affects the color-matching chain** (global coarse LAB correction + per-crop fine correction). Alignment / TPS / optical flow / feathering are unchanged.
- **OFF (default)**: color matching does not distinguish edited from un-edited pixels; the whole block is unified to the background tone, and edited regions are pulled toward the background color too — strongest correction.
- **ON**: only un-edited pixels are used to estimate the color shift; edited regions keep about 25% of the global coarse correction, while per-crop local color correction is not applied to edited regions at all (0%); un-edited regions keep full strength with a smooth ramp. AI recolors are fully preserved, but the color difference between edited region and background is preserved as well.
- Which pixels count as "edited color" is decided by `Color_p_threshold` below.

### 8. Color threshold `Color_p_threshold` (default 20, range 3~120)
Only active when `color_protection` is ON; it decides which pixels count as "edited color":
- Color difference of crop B vs pre-edit crop A / original image **below the threshold**: treated as un-edited, so it takes part in the color-shift estimate and correction as usual;
- **Above the threshold**: treated as edited and protected by `color_protection`; the transition is smooth between the threshold and 3× the threshold.
- Only affects color matching (global coarse LAB correction + per-crop fine correction); alignment / TPS / optical flow and the lock-band decision used for compositing keep the default threshold.
- Default 20 is exactly the previous behavior; smaller = wider protection (slight recolors are kept too), larger = only obvious recolors are protected.

### 9. Feathering `feather_kernel` (default 20, range 0~256)
The soft transition width at the paste edge; it also affects the scale of color correction:
- **With `split_grid` connected**: alpha / feathering switches to Element Tile Merge's feather semantics — **0~100 maps to 0~1.0, 100 = maximum** (values above 100 are clamped to 1.0). Straight-edge ramp widths, radial corner ramps and the tile-mask feather width all scale by that fraction; the color-match block size still uses the number as pixels.
- **Tile overlaps without `split_grid`**: overlap bands on each side are derived from the intersection of the tile mask bboxes, and a complementary smoothstep inside each band gives weights that always sum to 1 (normalized compositing, so the background never shows through); feather controls the band width (half-width = feather/2, capped at half the overlap depth).
- **Larger (30~60 without grid)**: softer seams; the most direct and safest way to hide hard cuts/offsets.
- **Smaller**: sharper edges, but pixel-level misalignment cuts become visible.

### 10. `use_gpu`, caching and debug log
- **`use_gpu`** (default ON): accelerates feature matching (DISK/LoFTR) and the per-pixel LAB math in color matching (torch; the global color-shift estimate runs on CPU with numpy/OpenCV). OpenCV steps (optical flow, TPS/warp, seamless clone) still run on CPU.
- **`force_recompute`** (default OFF): clears the cache and re-aligns from scratch. Alignment results are cached per stage (placement H → TPS → per-crop flow → second pass); each key chains "input images + grid + the switch it depends on", so flipping one switch only re-runs that stage and the ones after it. The cache holds 5 entries (LRU). Changing color mode, feathering, `warp_smooth` or `use_gpu` does not re-run alignment; global polish has its own 2-entry cache keyed on those compose parameters.
- **Stage timings**: with `SmartMergeImages.DEBUG` enabled, one extra `stage timings` line is printed at the end (placement / TPS / flow / second pass / compose / polish, with bridge / photometric / warp / mask sub-timings under placement). With it disabled, only cache-hit messages and the progress bar are shown.

### 11. Optional inputs `original_crop_A` / `split_grid`
- **`original_crop_A`**: pre-edit crops with the same viewpoint/content as B. Paired with B by index; if there are fewer A than B, the extra B blocks fall back to auto matching. Improves placement reliability and enables bridge-style TPS.
- **`split_grid`**: the grid output of ElementTileSplit. When connected, its tile positions, lock bands, rounded corners and overlap drive the over-compositing, with alpha/feathering pixel-identical to Element Tile Merge (`feather_kernel` then becomes a 0~100 scale). Grid coordinates serve as layout anchor and fallback: TPS / optical flow still run when a bridge-A or reliable features are available, otherwise the grid placement is used as-is. Color-matching order is identical to non-grid mode.

---

## 3. Quick Troubleshooting

| Symptom | Solution |
|---|---|
| **Hard cuts / offsets at the edge** | 1. Raise `feather_kernel` (40+ without split_grid; on the 0~100 scale with split_grid, e.g. 50~80) <br>2. Turn OFF `color_protection` (when ON, edited-region color is not corrected, so the color difference remains) <br>3. Make sure `Optical_Flow` is ON so optical flow can engage. |
| **Distant local regions (e.g. a face near the frame edge) not aligned** | TPS has distance falloff and displacement caps to protect the image from tearing. If distant misalignment is severe:<br>1. Connect `original_crop_A` to use the bridge path.<br>2. Lower `warp_smooth` appropriately to allow optical-flow fine adjustment. |
| **Local deformation not fixed** | Ensure `use_tps` is ON (`Optical_Flow` is unrelated to TPS — turning it off only disables optical flow). |
| **Colors washed out / grayish** | Switch to `Patch_based_color`; avoid `SeamlessClone`. |

---

## 4. Inputs and Outputs

- All three image ports support **single / batch / list**; no extra "Image List To Image Batch" node is needed.
- Each edited image may have a different size; the node processes each at its native resolution.
- `original_crop_A` does not need to match B in count or size exactly; pairing is by order.
- Only the first `original_image` is used; all edited blocks are pasted onto it and one merged image is output per run.
- Blocks that cannot be reliably placed are skipped; the corresponding regions keep the original content.
