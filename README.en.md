<div align="center">

[![Chinese](https://img.shields.io/badge/Language-Chinese-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

A ComfyUI extension primarily focused on **visual interface and convenient interaction**. The nodes in this package are different: instead of a slider paired with a number, the entire tool is moved directly into the node.

## What You Can Get

**🎬 Video Editing (Element Load and Edit Video)**
Edit videos directly on the node without leaving ComfyUI: automatically detects scene cut points, or manually cut, trim, and reorder segments; preview while editing, and output both video and audio directly after finishing.

**🗂 Multi Reference Material Panel (Element Multi REF)**
A material station for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference video + audio" input:
- 21 typed slots: reference images ×9, reference videos ×3, and start/end frames, various audio types, and Prompt cards;
- Each card comes with an independent simple image editor (crop, brush annotation) and audio/video timeline editor (quantized alignment based on rules like 17n+5, 8n+1);
- Supports storage, recall, load, and export of multiple presets, as well as organizing all references and prompts;
- `run_preset_NUM` parameter corresponds to the preset list index; when paired with sampling inference nodes, it enables continuous generation or editing of multiple images/videos based on prompt queue changes;
- The bottom bar of the panel has 4 area switch icons (reference images, start/end frames, audio/video, Prompts), allowing flexible combinations to suit different needs, and even usable as a Prompt preset node.

The auxiliary node **Element ref convert** is used for reference data format conversion.

<img width="1691" height="874" alt="Element Multi REF" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

---

<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 new addition

Detailed instructions: [Chinese](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

Designed for video/image models like MiniMax-H3, LTXV, Wan, Klein, Qwen that require multi-reference input:
- 21 typed slots: reference images ×9, reference videos ×3, start/end frames, various audio types, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotation) and audio/video timeline editor (quantized alignment based on rules like 17n+5, 8n+1);
- Supports storage, recall, load, and export of multiple presets, as well as organizing all references and prompts;
- `run_preset_NUM` parameter corresponds to the preset list index; when paired with sampling inference nodes, it enables continuous generation or editing of multiple images/videos based on prompt queue changes;
- The bottom bar of the panel has 4 area switch icons (reference images, start/end frames, audio/video, Prompts), allowing flexible combinations to suit different needs, and even usable as a Prompt preset node.

The auxiliary node **Element ref convert** is used for reference data format conversion.

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>v1.5.4 new addition · 

Detailed instructions: [Chinese](subMd.Element_scene_detection.zh.md) | [English](subMd/Element_scene_detection.en.md)</sub>

A visual single-track video editor node:
- PySceneDetect automatically detects scene cut points, or manually split, trim, and reorder segments on an interactive timeline;
- Synchronous preview of video and audio;
- Directly outputs segment frame sequences with precise corresponding audio, supporting export of audio-enabled mp4 (requires ffmpeg).

The auxiliary nodes **Element Video Clip**, **Element Video Info** are used together.

<img width="2147" height="1104" alt="Element Load and Edit Video" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

---

<a id="minimax_h3-latentupscaler"></a>
## Minimax_H3-LatentUpscaler

<sub>v1.5.0 new addition · Added alongside Adv version</sub>

A dedicated node that only upscales video latent space, does not process audio, and outputs Minimax H3 latent.

**Adv version** includes validation and introduces three conditional scaling modes:

| Mode | Behavior |
|---|---|
| pass_through | Ignores validation and passes through directly |
| NO_refs | Aligns but does not upscale |
| refs | Upscales (best quality) |

---

<a id="element-imagecurve"></a>
<a id="element-huesat"></a>
<a id="element-huebright"></a>
<a id="element-huehue"></a>
## Curves Color Adjustment Series

<sub>v1.2.7 ~ v1.3.1 added sequentially · v1.6.0 optimized</sub>

All four nodes use the same interaction method: **draw curves directly on images for real-time preview, single-click to add points, right-click to remove points**, supporting both single and sequence-frame images.

| Node | Curve Type |
|---|---|
| Element ImageCurve | RGB / R / G / B channel curves |
| Element HueSat | Hue → Saturation |
| Element HueBright | Hue → Brightness |
| Element HueHue | Hue → Hue |

> ⚠️ Except for Element ImageCurve, do not add points at both ends of the curve simultaneously: the curves at both ends are closed loops, adding points at both ends will make one point invalid; in fact, one endpoint is sufficient to complete the color adjustment.

<img width="1695" height="891" alt="Element HueSat" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />
<img width="1767" height="1008" alt="Element ImageCurve" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

---

<a id="loadimage_preview"></a>
## LoadImage_Preview

<sub>v1.3.5 new addition · v1.6.0 optimized</sub>

Browse image files under a specified path, select, and enter the editing panel for simple edits: freely draw lines, masks, rectangles, circles, and crop images.

- `Shift + Left click`: Draw straight lines, squares, or circles
- `L-alpha`: Load image alpha channel to canvas
- `Return`: Switch between zoom panel and editing panel
- Supports `Ctrl+V` to paste images, and directly drag from web or file explorer
- The ComfyUI input directory is permanently stored in the node; the folder path specified as an additional directory

<img width="1453" height="913" alt="LoadImage_Preview" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>v1.4.3 new addition · v1.4.8 optimized</sub>

When two images have enough common features, intelligently merge images, suitable for stitching the results of local redraw back into the original image:
- **Optimal input scheme**: original_image + edited_crop_B + original_crop_A. Here, original_crop_A is the part of the original image that has not been modified or distorted, and edited_crop_B is the edited or redrawn image;
- Supports block merging: when multiple images are input to the edited_crop_B port, the output is a single image of the final merged result. Note that the input must be **Batch, not list**; if it's a list, it needs to be converted using the Image List To Batch node.

<img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>v1.1.3 new addition</sub>

A style conversion node for black-and-white partitioning, used to suppress pixel offset issues after style conversion in qwenEdit: first convert the style of the mask area, then convert the invert mask area; try to make the black-and-white areas roughly equal in size to reduce tonal inconsistencies.

The mask at the input port will be ADDed with the mask generated by the node.

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>v0.0.8 new addition (Image Noise Using Mask)</sub>

Conveniently add random noise to the mask area of an image.

<img width="1724" height="878" alt="Screenshot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 new addition</sub>

Mask stroke: individual control of inner and outer stroke widths and blur, supports adding overall weight to non-stroke areas (ensuring the output mask has no areas with weight 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 new addition · v1.6.0 refactored</sub>

A visual interactive image padding node, optionally feather the edges of the original image, customize the background, freely or proportionally scale the image within the canvas, and specify the background color.

- The node's attribute parameters retain `target width / target height`, and add `div` to assist in setting valid resolutions.
- The 3x3 button group corresponds to 9 alignment modes (center, left, right, top, bottom, top-left, top-right, bottom-left, bottom-right)
- pad mode: constant / reflect / edge / stretch

Detailed instructions: [Chinese](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 new addition · v1.5.3 added P button</sub>

Draw custom sigma curves directly on the node: single-click to add points, right-click to remove points.

**P button**: Rearrange the x-coordinates of control points — when the number of points is less than `steps+1`, the first `n-1` points' x are reordered to 0, 1/steps, ..., (n-2)/steps, y remains unchanged, and the last point is kept as is; when the number of points is at least `steps+1`, take the first `steps+1` points evenly distributed. Simply put: **without changing the step size of the earlier steps, to add sampling steps (increase detail) in the later segment**.

<img width="1176" height="794" alt="Element_SigmaGraph" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

---

<a id="chessboard"></a>
## chessboard

<sub>v0.0.9 new addition (ChessboardPattern)</sub>

Create a black-and-white checkerboard image.

<img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />

---

<a id="empty_image_rgb"></a>
## empty_image_rgb

<sub>v0.0.6 new addition, v1.5.9 optimized </sub>

Create a monochrome image, with color selected from the color wheel, brightness controlled by a slider; the eyedropper can pick color from any position on the screen, but if the browser is not Chrome / Edge 96+, the eyedropper may not work, and the color wheel button next to it can be used instead.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 new addition, v1.5.9 optimized </sub>

A frame count calculation node, providing minimax H3, ltx2, wan presets, and customizable via `div_by` and `offset`.

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>v1.2.3 new addition</sub>

Size alignment calculation.

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="random_chars"></a>
## random_chars

<sub>v0.0.6 new addition (Random Chars Append)</sub>

Append invalid special characters to the input text (customizable characters and count).

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6 new addition, v1.5.9 optimized</sub>

Break the input text into lines based on character count, supporting punctuation avoidance at the start/end, punctuation squeezing, and hanging. The final effect depends on the output carrier.

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---

## Installation

### Manager Installation

Search for **ComfyUI_Element_easy** in the ComfyUI Manager and install.

### Manual Installation

Enter `./ComfyUI/custom_nodes` directory and run:

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt
### Optional Dependency: ffmpeg

The node's **video export (with audio)** feature requires ffmpeg to be installed on the system. Windows users can download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/) and add the bin directory to PATH after extraction.

All other features work normally without ffmpeg; only video export will be silent video.