# Smart Merge Images User Guide

Pastes AI-edited local images back into the original image at the correct position and size, and cleans up seams and color differences.
Input can be a single image or multiple blocks (each block may have a different size). One execution outputs one or more merged images (depending on `merge_mode`).

**Category**: `Element_easy/image`, Output: `Merged_Image` (IMAGE)

---

## 1. Minimal Wiring

    original image ─────────────► original_image
    AI-edited block ────────────► edited_crop_B
    pre-edit crop (optional) ───► original_crop_A     ← strongly recommended, most reliable
    ElementTileSplit grid (optional) ► split_grid     ← connect when using TileSplit

- **Connect `original_crop_A`**: the node knows where each block originally sat in the frame — most accurate placement, and it enables bridge-style non-rigid correction (TPS bridge: LoFTR matches B↔A, then the A→BG homography maps those points into background space).
- **Connect `split_grid`**: compositing follows the tile's fade (smoothstep) ramp + gaussian-feathered rounded-corner mask, matching the grid produced by the TileSplit node in the ComfyUI-Element_TileEdit extension. If the grid carries `work_w`/`work_h`, the original image is first resized to that working canvas size before compositing.
- Neither is required: the node will auto-locate positions on the background. On complex scenes it may occasionally paste off-target; blocks that fail placement are **skipped** (the original content is kept — it never forces a paste into the middle of the frame).

**Recommended starting parameters**

| Parameter | Recommendation |
|---|---|
| Optical-flow refinement `Optical_Flow` | ON |
| TPS `use_tps` | ON |
| Second-pass refinement `second_pass` | OFF (turn on when slight local misalignment remains) |
| Smoothing `warp_smooth` | Default 1.0; raise slightly if wavy local distortion appears |
| Color matching `color_match` | `Patch_based_color` |
| Color protection `color_protection` | OFF (default). When ON, edited regions are no longer pulled toward the background color; if there is no intentional hue edit, keep it OFF. |
| Feathering `feather_kernel` | 20~40 (raise to 40~60 when seams are obvious; see 2.7 for split_grid semantics) |
| `use_gpu` | ON (default) |

---

## 2. Effect of Each Parameter

### 1. Optical-flow refinement `Optical_Flow` (default OFF)
It does **not** control TPS; it only decides whether optical flow runs after geometric alignment. The widget is named `Optical_Flow`; the switch shows `on` / `off`.
- **OFF**: placement only (bridge homography / auto homography). If `use_tps` is ON, TPS non-rigid correction still runs; no optical flow at all.
- **ON**: adds two optical-flow layers on top of placement/TPS:
  1. Per-crop flow: each crop is locally aligned to the background, capped at 10 px on the bridge path with `original_crop_A` / 15 px on the auto path without it; the auto path skips this step when the post-placement residual is already below 1.2 px;
  2. Global polish: the whole merged image is corrected once against the original, capped at 12 px, smoothed by `warp_smooth`.
- Flow backend is automatic: DIS first, Farneback fallback when unavailable — there is no separate switch.
- With `original_crop_A` connected, flow is estimated at the content's native resolution (scaled by the A/B width ratio, long side limited to 2048), so accuracy follows the content rather than the canvas.

> **Note**: optical flow (both per-crop and global) is physically only suited for **fine adjustment** (about 10–15 px per crop, 12 px global cap). Large misalignment cannot be rescued by optical flow — use TPS or connect `original_crop_A`.

### 2. Non-rigid correction `use_tps` (default ON)
- **ON**: allows mild bending/stretching to fit the background. The common AI-redraw case of "content right but shape slightly off" is fixed by this. The bridge path uses LoFTR correspondences; the auto path (no A) uses DISK features.
- **OFF**: homography only (translation/scale/rotation/perspective); if `Optical_Flow` is ON, optical-flow refinement still applies.

### 3. Second-pass refinement `second_pass` (default OFF)
Only effective with bridge alignment and `use_tps` ON.
- **ON**: after TPS, each crop runs one more LoFTR match for residual displacement and applies a small-displacement (16 px cap) TPS tweak. The result is **applied directly** — there is no score-based check.
- **OFF (default)**: skips the step, saving one LoFTR match (about 4~8 s per crop).
- Use it when slight local misalignment remains after alignment/TPS (edges, thin lines, text).
- Caveat: it reshapes the whole displacement field of that crop, so in some cases a straight edge near the tile border can bend slightly. If edges get worse with it ON, turn it off.

### 4. Polish smoothing `warp_smooth` (default 1.0, range 0~4)
Only affects the final "global polish" step (which runs only when `Optical_Flow` is ON), controlling how smooth the correction displacement is.
- **0 ~ 1.0 (mild)**: allows finer displacement corrections — may fit better, but can also show slight jitter.
- **1.0 ~ 2.0 (strong)**: the most conservative smoothing of the old version; corrections are smoother.
- **2.0 ~ 4.0 (very strong)**: forces the flow field to low frequency; almost no local wiggling is produced.

### 5. Color strategy `color_match` (default `Patch_based_color`)
The parameter with the biggest influence on final appearance. **Except `Alpha Soft Blend`, every mode first applies a gentle global LAB correction** (per-crop median LAB shift × 0.35, capped at 10/4/4, skipped when below 0.25), then runs the selected per-crop pass. So even the "luminance-only" modes still get a slight global a/b nudge.

| Mode | Effect | Suited for | Caveats |
|---|---|---|---|
| `Patch_based_color` | Boundary-band sync first, then a patch-grid color sync, aligning tone to the background region by region | Large/uneven color casts; multi-block stitching | Slowest; block size depends on `feather_kernel` / `color_protection` (see 2.7) |
| `LAB_Mean` | Aligns the whole block to the background in LAB by mean + robust std (10–90 percentile), then adds a low-frequency LAB difference field (clipped to 24/10/10) for spatially uneven casts | Uniform or uneven color cast, quick output | Heavily changed content may be washed out globally |
| `Laplacian Pyramid Blend` | Per-crop pass shifts the L-channel median plus a low-frequency L field, then multi-band blending fixes seams | Colors already close, only need luminance matching + seam cleanup | No a/b correction at the per-crop level (the global coarse pass still nudges a/b); 3–5 levels depending on feathering |
| `SeamlessClone (PS Auto Blend)` | Per-crop luminance matching (median + low-frequency L field), then Poisson blending | Content basically unchanged, only need to remove seams | Heavily changed content will fade/gray — use with caution |
| `Alpha Soft Blend` | Feather blending only | Almost no color cast, fastest | The only mode that also skips the global LAB correction |

### 6. Color protection `color_protection` (default OFF)
**Only affects the color-matching chain** (global coarse LAB correction + per-crop fine correction). Alignment / TPS / optical flow / feathering are unchanged.
- **OFF (default)**: color matching does not distinguish edited from un-edited pixels; the whole block is unified to the background tone, and edited regions are pulled toward the background color too — strongest correction.
- **ON**: only un-edited pixels are used to estimate the color shift; edited regions keep about 25% of the global coarse correction, while per-crop local color correction is not applied to edited regions at all (0%); un-edited regions keep full strength with a smooth ramp. AI recolors are fully preserved, but the color difference between edited region and background is preserved as well.

### 7. Feathering `feather_kernel` (default 20, range 0~256)
The soft transition width at the paste edge; it also affects the scale of color correction:
- **color_protection OFF**: the `Patch_based_color` block size ≈ `max(32, 2×feather)`, and the boundary band width also follows feather — larger feather means coarser and slower color correction.
- **color_protection ON**: block size becomes 12% of the crop short side (clamped 48~160) and no longer follows feather.
- **With `split_grid` connected**: feather is interpreted relative to overlap (fade width fraction = feather / overlap, max 1.0), so effective feathering never exceeds overlap.
- **Larger (30~60)**: softer seams; the most direct and safest way to hide hard cuts/offsets.
- **Smaller**: sharper edges, but pixel-level misalignment cuts become visible.

### 8. Merge mode `merge_mode` (default All to One)
- **All to One**: all edited blocks are pasted sequentially onto the **first** background; outputs 1 image.
- **One to One**: backgrounds and edited blocks are paired by count (each background gets `crops/backgrounds` blocks using integer division, at least 1); outputs the same number of images as backgrounds. When the crop count is not divisible by the background count, the leftover crops at the end are not merged.

### 9. `use_gpu` and `force_recompute`
- **`use_gpu`** (default ON): accelerates feature matching (DISK/LoFTR) and the per-pixel LAB math in color matching (torch; the global color-shift estimate runs on CPU with numpy/OpenCV). OpenCV steps (optical flow, TPS/warp, seamless clone) still run on CPU.
- **`force_recompute`** (default OFF): clears the alignment cache and re-aligns from scratch. The cache holds 4 entries (LRU); its key covers input image fingerprints, the grid fingerprint, `Optical_Flow`, `second_pass`, `use_tps` and `merge_mode` — changing color mode, feathering or `use_gpu` does not re-run alignment.

### 10. Optional inputs `original_crop_A` / `split_grid`
- **`original_crop_A`**: pre-edit crops with the same viewpoint/content as B. Paired with B by index; if there are fewer A than B, the extra B blocks fall back to auto matching. Improves placement reliability and enables bridge-style TPS.
- **`split_grid`**: the grid output of ElementTileSplit. When connected, its tile positions, fades, rounded corners and overlap drive the over-compositing. Grid coordinates serve as layout anchor and fallback: TPS / optical flow still run when a bridge-A or reliable features are available, otherwise the grid placement is used as-is. Color-matching order is identical to non-grid mode.

---

## 3. Quick Troubleshooting

| Symptom | Solution |
|---|---|
| **Hard cuts / offsets at the edge** | 1. Raise `feather_kernel` to 40+ <br>2. Turn OFF `color_protection` (when ON, edited-region color is not corrected, so the color difference remains) <br>3. Make sure `Optical_Flow` is ON so optical flow can engage. |
| **Distant local regions (e.g. a face near the frame edge) not aligned** | TPS has distance falloff and displacement caps to protect the image from tearing. If distant misalignment is severe:<br>1. Connect `original_crop_A` to use the bridge path.<br>2. Lower `warp_smooth` appropriately to allow optical-flow fine adjustment. |
| **Local deformation not fixed** | Ensure `use_tps` is ON (`Optical_Flow` is unrelated to TPS — turning it off only disables optical flow). |
| **Colors washed out / grayish** | Switch to `Patch_based_color`; avoid `SeamlessClone`. |

---

## 4. Inputs and Outputs

- All three image ports support **single / batch / list**; no extra "Image List To Image Batch" node is needed.
- Each edited image may have a different size; the node processes each at its native resolution.
- `original_crop_A` does not need to match B in count or size exactly; pairing is by order.
- Output: `All to One` → 1 image; `One to One` → a batch with the same count as backgrounds (zero-padded to the largest size if they differ).
- Blocks that cannot be reliably placed are skipped; the corresponding regions keep the original content.
