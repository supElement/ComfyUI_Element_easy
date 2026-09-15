# Image Pad & Blur

Add margins to an image (outpainting / canvas extension), optionally blur the background, or feather the edges of the original image. All operations are done by dragging directly on the node canvas, with a live preview.

## Inputs / Outputs

| | Name | Description |
|---|---|---|
| Input | `image` | Source image (required) |
| Input | `mask` | Optional mask, see "Mask Usage" below |
| Output | `image` | Processed image |
| Output | `mask` | Output mask (white = filled/extended area, ready for inpaint) |

## Quick Start

1. Connect any image source (Load Image, sampler, etc.);
2. Click the **blue play button** in the top-left corner: it runs only this node and its upstream chain, then refreshes the canvas source. **On first use you must click it once to display the canvas preview and start adjusting**;
3. Drag the image on the canvas to reposition it, drag its edges/corners to resize;
4. Run the workflow as usual to get the result.

## UI Reference

### Top Bar (left to right)

| Control | Function |
|---|---|
| ▶ Play (blue) | Isolated preview: runs only this node + upstream chain and refreshes the canvas, without affecting the rest of the workflow |
| Color swatch | Specifies the background color for the solid-fill mode |
| W × H | Displayed image size on the canvas (values can be typed in directly) |
| ⛶ Fit | Fit image to canvas: resets scale and offsets |
| 🔒 Lock | Lock aspect ratio; hold Shift while dragging to temporarily invert |
| ↺ Reset | Restore all parameters to defaults |
| Edge dots | Choose which edges get feathering (top/bottom/left/right independent toggles) |
| 3×3 grid | Alignment (nine positions); offsets reset to zero on switch |

### Canvas

- **Drag inside the image**: move position (pixel-accurate);
- **Drag edges/corners**: resize the image;
- The bottom-left corner shows the live margins `L/T/R/B`.

### Bottom Bar (left to right)

| Control | Function |
|---|---|
| Four icons | Fill mode: `constant` solid color / `edge` edge extension / `reflect` mirror / `stretch` stretch |
| Feather | Feather width (works with the edge dots in the top bar; per-edge linear gradient) |
| Blur | Background blur strength (blurs the entire fill background) |
| Mask button | When enabled, the masked area reveals the blurred background (see below) |

## Node Property Parameters

`target_width` / `target_height`

- **> 0 (Canvas mode)**: the output canvas is fixed at that size (auto-snapped to multiples of `div`); the image is placed according to the alignment, and dragging changes the offset;
- **= 0 (Margin mode)**: output size = image size + margins on all four sides, and dragging changes the per-side margins.

`div`: helper parameter for valid-resolution settings (the output size is snapped to multiples of `div`).

## Mask Usage

1. After connecting a `mask`, drag/resize operations move and scale it together with the image;
2. Top-bar edge dots: only the selected edges are feathered / affected by the Feather parameter;
3. Bottom-bar mask button (off by default):
   - **Off**: the mask only affects the output `mask` channel (unioned with the feathered area);
   - **On**: the masked area reveals the blurred/filled background in the output image (image content is removed there).

## Tips

- Scale is stored as a **ratio** and offsets as **pixels**: when the source image changes or the sampler's dimensions change, the composition stays intact — no re-adjustment needed;
- If the input image has an alpha channel, it is ignored (treated as opaque RGB);
- The play button works on the very first click after a page refresh — no need to run the full workflow first. Note, however: if there is an inference/sampling node upstream, you must wait for the inference to finish before the canvas refreshes.
