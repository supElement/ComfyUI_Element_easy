<div align="center">

[![Chinese](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

An extension for ComfyUI focused on **visual interface and convenient interaction**. The nodes in this package are different: instead of a slider paired with a number, the entire tool is moved directly into the node.

## What You Can Get

**🎬 Video Editing (Element Load and Edit Video)**
Edit videos directly on the node without leaving ComfyUI: automatically detects scene cut points, or you can manually cut, shorten, reorder, and preview while editing. The output is both video and audio after editing.

**🗂 Multi Reference Material Panel (Element Multi REF)**
A material station for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference videos + audio" input. Each material can be cropped, annotated with brushes, and trimmed by time segments, and can also be saved as presets—combined with the queue, it can run multiple sets of materials and prompts at once without switching images.

**🎛 Curve Color Adjustment (HueSat / HueBright / HueHue / ImageCurve)**
Adjust colors like in photo editing software, where the curve is drawn directly on the image. Drag to see the effect instantly, and the same real-time preview works for videos.

**📐 Custom Sampling Curve (Element_SigmaGraph)**
Draw the sigma curve of the sampler by hand, which is especially convenient when you want fewer steps in the beginning and more details in the end.

**🧩 Over 20 Practical Small Nodes**
Image smart merge, mask stroke, image edge blur, frame count calculation, etc.

## Disadvantages to Note

- **Requires some time to get started**: The panel-style nodes have many functions, and the first time you open them, you might wonder "what does this button do?". It is recommended to use it together with the detailed documentation of each node;
- **Some functions depend on external programs**: Video export with audio requires the system to have ffmpeg installed, and automatic scene detection suggests installing scenedetect. It can still be used without installation, but the corresponding functions will be limited;
- **Compatibility depends on a newer version of ComfyUI** (Multi REF uses a new node API), older versions of ComfyUI may not be installable;
- **The nodes are numerous but independent**: If you only need one or two functions, this package might be too large for you.

## 📦 Node Navigation

**🎬 Video and Material Management**

- [Element Multi REF](#element-multi-ref) (includes auxiliary node Element ref convert)
- [Element Load and Edit Video](#element-load-and-edit-video) (includes auxiliary nodes Element Video Clip / Element Video Info)
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler) (includes Advanced version)

**🎛 Curve Color Adjustment**

- [Element ImageCurve](#element-imagecurve) · [Element HueSat](#element-huesat) · [Element HueBright](#element-huebright) · [Element HueHue](#element-huehue)

**🖌 Image Editing and Masking**

- [LoadImage_Preview](#loadimage_preview) · [Smart merge images](#smart-merge-images) · [black_white_color](#black_white_color) · [mask_noise_element](#mask_noise_element) · [mask_stroke](#mask_stroke) · [image_pad_blur](#image_pad_blur)

**📐 Image Generation and Sampling Control**

- [Element_SigmaGraph](#element_sigmagraph) · [chessboard](#chessboard) · [empty_image_rgb](#empty_image_rgb)

**🔧 Number and Text Tools**

- [Frame Calculator](#frame-calculator) · [ImageSize Div](#imagesize-div) · [random_chars](#random_chars) · [text_line_break](#text_line_break)

---
## Bug Fixes and Optimizations

- Now, when the mouse pointer is over a visual interaction node, the ComfyUI canvas can be dragged and scaled normally, except for the thumbnail preview interface of the loadimage_preview node and the timeline window of the Element Load and Edit Video node when selected.

---
<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 New · v1.6.1 Optimized</sub>

Detailed explanation: [Chinese](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

Designed for video/image models like MiniMax-H3, LTXV, Wan, Klein, Qwen, etc., that require multi-reference input, this material and prompt management solution:

- 21 typed slots: reference images ×9, reference videos ×3, as well as start/end frames, various audio, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotation) and audio/video timeline editor (aligned by rules like 17n+5, 8n+1, etc.);
- The bottom bar on the left side of the panel has 4 area switch icons (reference images, start/end frames, audio/video, Prompt), allowing free combination of the panel to meet different needs, and can even be used as a prompt preset node;
- Supports the storage, call, load, and export of multiple presets, as well as the categorization of all references and prompts;
- `run_preset_NUM` parameter corresponds to the index in the preset list, and when receiving input that changes with the prompt queue, combined with sampling inference nodes, it can achieve continuous generation or editing of multiple images/videos;
⚠️ Note: If a preset is loaded, `run_preset_NUM` parameter will automatically become the preset's index. If you modify the reference area content at this time, you must set `run_preset_NUM` parameter to 0 (output the current interface), or save/export the preset, otherwise the output result will be the same as before the modification, which is normal behavior.

The auxiliary node **Element ref convert** is used for the format conversion of reference data.

<img width="1691" height="874" alt="Element Multi REF" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

🎬 Core Scenario: Batch Processing of Storyboards

A script can have dozens or even hundreds of shots. The prompt, reference image, reference video, and start/end frames for each shot are all saved as presets.

Combined with sampling nodes, run all segments with one click. Want to change? Modify, then save the preset—no need to reload workflows or manually switch materials and prompts in individual nodes.

- Before: Change a shot → Switch images → Change prompt → Run → Change the next → Repeat dozens of times. If reference images or audio/videos need minor adjustments, you have to open PS or editing software.
- Now: All presets are arranged → Run with one click → Not satisfied? Change the preset → Run again. Minor adjustments to reference images or audio/videos are done directly on the node, without switching software.

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>v1.5.4 New Addition · v1.6.2 Optimization</sub>

Detailed Description: [Chinese](subMd/Element_scene_detection.zh.md) | [English](subMd/Element_scene_detection.en.md)</sub>

A visual single-track video clipper node:

- PySceneDetect automatically detects scene cut points, or manually split, trim, and rearrange clips on an interactive timeline;
- Synchronize preview of video and audio;
- Directly output clip frame sequences with corresponding audio, supporting exporting audio-enabled mp4 (requires ffmpeg).
- Shortcuts: Space = Play/Pause All Clips; Mouse Wheel = Zoom Timeline; Shift+Mouse Wheel = Pan Timeline View; Segment Selection: Ctrl+Click = Add Selection, Shift+Click = Range Selection; Trim Clips: Hold Alt/Ctrl While Dragging = Linked Trim; delete/Backspace = Delete Selected Segments.

⚠️ The node must be in selection mode to operate icons, buttons, or shortcuts on the node interface.

Auxiliary nodes **Element Video Clip**, **Element Video Info** are used together.

<img width="2147" height="1104" alt="Element Load and Edit Video" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

---

<a id="minimax_h3-latentupscaler"></a>
## Minimax_H3-LatentUpscaler

<sub>v1.5.0 New Addition · Added Simultaneously with Adv Version</sub>

A dedicated node for upsampling video latent space only, does not process audio, output port is Minimax H3 latent.

**Adv Version** includes validation, introduces three conditional upsampling modes:

| Mode | Behavior |
|---|---|
| pass_through | Bypass validation directly |
| NO_refs | Align only, no upsampling |
| refs | Upsample (best quality) |

---

<a id="element-imagecurve"></a>
<a id="element-huesat"></a>
<a id="element-huebright"></a>
<a id="element-huehue"></a>
## Color Curve Series

<sub>v1.2.7 ~ v1.3.1 Added Gradually · v1.6.1 Optimization</sub>

All four nodes use the same interactive method: **draw curves directly on images for real-time preview, single-click to add points, right-click to remove points**, supports single and sequence frame images.

| Node | Curve Type |
|---|---|
| Element ImageCurve | RGB / R / G / B Channel Curves |
| Element HueSat | Hue → Saturation |
| Element HueBright | Hue → Brightness |
| Element HueHue | Hue → Hue |

> ⚠️ Except for Element ImageCurve, do not add points at both ends of the curve simultaneously: the curves at both ends are closed loops, adding points at both ends will make one point invalid, actually one endpoint is sufficient to complete the color adjustment.

<img width="1695" height="891" alt="Element HueSat" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" /> <img width="1767" height="1008" alt="Element ImageCurve" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

---

<a id="loadimage_preview"></a>
## LoadImage_Preview

<sub>v1.3.5 New Addition · v1.6.1 Optimization</sub>

Browse image files under a specified path, enter the editing panel after selection for simple editing: freehand drawing lines, masks, boxes, circles, and crop images.

- `Shift + Left Click`：Draw straight lines, squares, or circles
- `L-alpha`：Load image alpha channel to canvas
- `Return`：Switch between zoom panel and editing panel
- In edit mode, supports `Ctrl+V` to paste images, supports dragging directly from web or file explorer
- ComfyUI's input directory persistent node, folder path specified directory as an additional directory

<img width="1453" height="913" alt="LoadImage_Preview" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>v1.4.3 New Addition · v1.4.8 Optimization · v1.6.3 Fix</sub>

🎬 Core Scenario: Eliminate distortion and color differences caused by block-wise image enlargement using a generative model

When dividing an image into blocks and feeding them to a generative model for enlargement, and then piecing them back together, there are often color differences and distortions at the seams, making direct piecing unsightly.
This node uses common features of two images for intelligent alignment, smoothly piecing the results of block-wise enlargement back into the original image.

How to use (Optimal Input Scheme):
- original_image：Original image
- edited_crop_B：Edited or redrawn block
- original_crop_A：Cropped from the original image without modification or distortion
Three ports work together, the node automatically finds the alignment relationship and stitches the edited part back into the original image.

Supports block merging: When multiple images are input to the edited_crop_B port, the output is a single image of the final merged result.

You need to download the [model files](https://huggingface.co/cglearned/Smart_merge_images/tree/main); by default, they are downloaded automatically.

Manual download: depth-save.pth / disk_lightglue_v0-1_arxiv-pth / loftr_outdoor.ckpt
To: \ComfyUI\models\elementEasy\checkpoints

<img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>v1.1.3 New Addition</sub>

Black and White Zone Style Conversion Node, used to suppress pixel offset issues after style conversion in qwenEdit: first convert the style of the mask area, then convert the invert mask area; try to make the black and white areas roughly equal in size to reduce the problem of inconsistent tones.

The mask on the input port will perform an ADD operation with the mask generated by the node.

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>v0.0.8 new (Image Noise Using Mask)</sub>

Easily add random noise in the mask area of an image.

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 new</sub>

mask stroke: stroke width and blur are controlled separately, support adding overall weight to non-stroke areas (making the output mask have no area with weight 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 new · v1.6.0 refactored · v1.6.1 optimized</sub>

🎬 Core scenario: Expand images for image editing models, visual drag-and-drop, almost meets any expansion requirement

When expanding images with image editing models (klein, QwenImage2.1, Qwen-Edit, Flux-Fill, sdxl, etc.), old nodes need to input a stack of parameters, repeatedly run tests, and some expansion requirements cannot be met.
This node turns expansion into direct operations on the canvas: drag-and-drop, scale, align, what you see is what you get, while also outputting the corresponding mask.

- No need to guess parameters for expansion: directly drag the original image position in the canvas, scale proportionally, one-click align with the 3x3 grid button (center, corners, edges)
- No edge artifacts: the edges of the original image can be specified separately for feathering, making the original image and the expanded area smoothly transition
- Controllable content: background color can be customized, pad mode supports constant / reflect / edge / stretch
- Automatic legal size: retain target_width / target_height, add div parameter to assist alignment to legal resolution
- Directly output mask: automatically generates a mask after expansion, marking which part is the original and which part is added, making it convenient for subsequent editing models to locally redraw

Detailed explanation: [Chinese](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 new · v1.5.3 added P button · v1.6.1 optimized</sub>

Directly draw custom sigma curves on the node: click to add points, right-click to delete points.

**P button**: Rearrange the x coordinates of control points — when the number of points is less than steps+1, the first n-1 points' x are rearranged to 0, 1/steps, ..., (n-2)/steps, y remains unchanged, and the last point is kept as is; when the number of points is at least steps+1, take the first steps+1 points evenly distributed. Simply put: **Without changing the step size of the front steps, add sampling steps to the latter part (increase details)**.

<img width="1176" height="794" alt="Element_SigmaGraph" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

---

<a id="chessboard"></a>
## chessboard

<sub>v0.0.9 new (ChessboardPattern)</sub>

Create a black and white checkerboard image.

<img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />

---

<a id="empty_image_rgb"></a>
## empty_image_rgb

<sub>v0.0.6 new · v1.6.1 optimized</sub>

Create a monochrome image, color is selected from the color wheel, brightness slider controls brightness; the eyedropper can take color from any position on the screen, if the browser is not Chrome / Edge 96+, the eyedropper may be unusable, can switch to the eyedropper in the adjacent color palette button.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 new, v1.5.9 optimized </sub>

Frame count calculation node, provides minimax H3, ltx2, wan legal presets, can be customized through div_by and offset.

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>v1.2.3 new</sub>

Size alignment calculation.

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="random_chars"></a>
## random_chars

<sub>v0.0.6 (Random Chars Append)</sub>

Append invalid special characters to the input text (characters and count can be customized).

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6, v1.5.9 optimized</sub>

Wrap the input text by character count, supports punctuation avoidance at the beginning and end, punctuation squeezing, hanging. The final effect depends on the output carrier.

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---
## Installation

### Manager Installation

Search for **ComfyUI_Element_easy** in ComfyUI Manager and then Install.

### Manual Installation

Enter `./ComfyUI/custom_nodes` directory and run:

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt

### Optional Dependency: ffmpeg

The **video export (with audio)** feature of the node requires the system to have ffmpeg installed. Windows users download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the bin directory to PATH.

When ffmpeg is not installed, all other features work normally, only video export becomes silent video.
