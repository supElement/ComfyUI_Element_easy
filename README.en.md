<div align="center">

[![Chinese](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

A ComfyUI extension primarily focused on **visual interface and convenient interaction**. The nodes in this package are different: instead of a slider paired with a number, the entire tool is moved directly into the node.

## What You Can Get

**🎬 Video Editing (Element Load and Edit Video)**
Edit videos directly on the node without leaving ComfyUI: automatically detects scene cut points, or manually cut, shorten, reorder, preview while editing, and output both video and audio directly after editing.

**🗂 Multi Reference Material Panel (Element Multi REF)**
A material station for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference video + audio" input. Each material can be cropped, brushed with annotations, and trimmed by time segment, and can also be saved as presets——combined with the queue, it can run multiple sets of materials and prompts at once without switching images back and forth.

**🎛 Curve Color Adjustment (HueSat / HueBright / HueHue / ImageCurve)**
Adjust colors like in photo editing software, with curves drawn directly on the image, and see the effect immediately by dragging, just like video.

**📐 Custom Sampling Curve (Element_SigmaGraph)**
Draw the sigma curve of the sampler by hand, especially convenient when you want fewer steps in the beginning and more details in the end.

**🧩 There are also more than 20 practical small nodes**
Image smart merge, mask stroke, image edge blur, frame count calculation, etc.

## Points to Note as Disadvantages

- **It takes some time to get started**: The panel-style nodes have many functions, and the first time you open them, you might think "What does this button do?", it is recommended to use the detailed documentation of each node;
- **Some functions depend on external programs**: Video export with audio requires the system to have ffmpeg installed, automatic scene detection suggests installing scenedetect, and without installation, the corresponding functions are limited;
- **Compatibility depends on a newer version of ComfyUI** (Multi REF uses a new node API), older versions of ComfyUI may not be installable;
- **The nodes are many but independent**: If you only need one or two functions, this package might be too large for you.

## 📦 Node Navigation

**🎬 Video and Material Management**

- [Element Multi REF](#element-multi-ref) (including auxiliary node Element ref convert)
- [Element Load and Edit Video](#element-load-and-edit-video) (including auxiliary nodes Element Video Clip / Element Video Info)
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler) (including Adv version)

**🎛 Curve Color Adjustment**

- [Element ImageCurve](#element-imagecurve) · [Element HueSat](#element-huesat) · [Element HueBright](#element-huebright) · [Element HueHue](#element-huehue)

**🖌 Image Editing and Masking**

- [LoadImage_Preview](#loadimage_preview) · [Smart merge images](#smart-merge-images) · [black_white_color](#black_white_color) · [mask_noise_element](#mask_noise_element) · [mask_stroke](#mask_stroke) · [image_pad_blur](#image_pad_blur)

**📐 Image Generation and Sampling Control**

- [Element_SigmaGraph](#element_sigmagraph) · [chessboard](#chessboard) · [empty_image_rgb](#empty_image_rgb)

**🔧 Numerical and Textual Tools**

- [Element_ListGraph](#Element_ListGraph) · [Frame Calculator](#frame-calculator) · [ImageSize Div](#imagesize-div) · [random_chars](#random_chars) · [text_line_break](#text_line_break)

---
## Bug Fixes and Optimizations

- Now, when the mouse pointer is on a visual interaction node, the ComfyUI canvas can be dragged and scaled normally, except for the thumbnail preview interface of the loadimage_preview node and the timeline window of the Element Load and Edit Video node when selected.

---
<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 New · v1.6.1 Optimized · v1.6.9 Enhanced </sub>

Detailed instructions: [Chinese](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

A material and prompt management solution designed for video/image models like MiniMax-H3, LTXV, Wan, Klein, Qwen, etc., that require multiple reference inputs:

- 21 typed slots: reference images ×9, reference videos ×3, as well as start/end frames, various audio, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotations) and audio/video timeline editor (quantized alignment according to rules like 17n+5, 8n+1, etc.);
- The bottom bar of the panel has 4 area switch icons (reference images, start/end frames, audio/video, Prompt), which can be freely combined to meet different needs, and can even be used as a prompt preset node;
- Supports the storage, call, load, and export of multiple presets, as well as the categorization of all references and prompts;
- `run_preset_NUM` parameter corresponds to the index in the preset list, and when receiving input that changes with the prompt queue, combined with sampling inference nodes, it can achieve continuous generation or editing of multiple images/videos;
⚠️ Note: If a preset is loaded, `run_preset_NUM` parameter will automatically become the index of the preset, and if you modify the reference area content without saving/another saving the preset, the output result will be the same as before, which is normal behavior; if you do not want to save the preset and want to output the modified content of the current interface, you can now click once `reset` button (set `run_preset_NUM` parameter to 0).
- If reference materials used in presets are deleted, you can now use the relink button to specify a directory to reconnect (the directory must contain files with the same name).
- The auxiliary node **Element ref convert** is used for the format conversion of reference data.

<img width="1691" height="874" alt="650757311-e8c32036-3a21-4864-93eb-228ffce3c82b" src="https://github.com/user-attachments/assets/85383cea-931e-4da6-a46b-4d373c95ef49" />

🎬 Core Scenario: Batch Processing of Storyboards

A script may have dozens or even hundreds of shots. The prompt, reference image, reference video, start/end frame for each shot are all saved as presets.

Combined with sampling nodes, run all segments with one click. Want to change? Change it, satisfied? Save the preset——no need to load workflows back and forth, or manually switch materials and prompts in individual nodes.

- Before: Change a shot → Switch image → Change prompt → Run → Change the next → Repeat dozens of times. If reference images or audio/video need micro-adjustments, you have to open PS or editing software.
- Now: All presets are arranged → Run with one click → Not satisfied? Change the preset → Run again. Micro-adjustments of reference images or audio/video are completed directly on the node, without switching software.

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>v1.5.4 New Addition · v1.6.2 Optimization</sub>

Detailed Description: [Chinese](subMd/Element_scene_detection.zh.md) | [English](subMd/Element_scene_detection.en.md)</sub>

A visual single-track video clipper node:

- PySceneDetect automatically detects scene cut points, or manually split, trim, and rearrange clips on an interactive timeline;
- Synchronize preview of video and audio;
- Directly output clip frame sequences with corresponding audio, supporting exporting audio-enabled mp4 (requires ffmpeg).
- Shortcuts: Spacebar = Play/Pause All Clips; Mouse Wheel = Zoom Timeline; Shift+Mouse Wheel = Pan Timeline View; Segment Selection: Ctrl+Click = Add Selection, Shift+Click = Range Selection; Trim Clips: Hold Alt/Ctrl While Dragging = Linked Trim; Delete/Backspace = Delete Selected Segments.

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

<sub>v1.3.5 New Addition · v1.6.1 Optimization · v1.6.7 Modified Output Ports</sub>

Browse image files under the specified path, enter the editing panel after selection for simple editing: freehand drawing lines, masks, boxes, circles, and cropping images.

- `Shift + Left Click`: Draw straight lines, squares, or circles
- `L-alpha`: Load image alpha channel to canvas
- `Return`: Switch between zoom panel and editing panel
- In edit mode, supports `Ctrl+V` to paste images, supports dragging directly from web or file explorer
- ComfyUI's input directory persistent node, folder path specified directory as an additional added directory

<img width="1453" height="913" alt="Untitled-1" src="https://github.com/user-attachments/assets/8ea3ad14-90d6-499e-8afe-41b9c84f6792" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>v1.4.3 New Addition · v1.4.8 Optimization · v1.7.0 Optimization</sub>

Detailed Description: [Chinese](subMd/SmartMergeImages_zh.md) | [English](subMd/SmartMergeImages_en.md)</sub>

🎬 Core Scenario: Eliminate distortion and color differences caused by block-wise upscaling of images through a generative model

When splitting an image into multiple blocks, or when a part of the image is given to a generative model for resampling/editing/upscaling and then reassembled, there are often color differences and distortions at the seams, and the direct merge effect may be poor.
This node uses common features of two images for intelligent alignment, smoothly reassembling the block-wise upscaling results back into the original image.

Download [model files](https://huggingface.co/cglearned/Smart_merge_images/tree/main), default auto-download.

Manual download: depth-save.pth / disk_lightglue_v0-1_arxiv-pth / loftr_outdoor.ckpt
To \ComfyUI\models\elementEasy\checkpoints

<img width="1949" height="1171" alt="image" src="https://github.com/user-attachments/assets/702f1d85-2771-451d-ae3b-9111342118ae" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>v1.1.3 New Addition</sub>

Black and white partition style conversion node, used to suppress pixel offset issues after style conversion in qwenEdit style conversion: first convert the style of the mask area, then convert the invert mask area; try to make the black and white area sizes average to reduce the problem of inconsistent tones.

The mask at the input port will perform an ADD operation with the mask generated by the node.

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>v0.0.8 added (Image Noise Using Mask)</sub>

Easily add random noise to the mask area of an image.

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 added</sub>

mask stroke: individual control of inner and outer stroke widths and blur, supports adding overall weight to non-stroke areas (ensuring the output mask has no areas with weight 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 added · v1.6.0 refactored · v1.6.1 optimized</sub>

🎬 Core scenario: Enlarging images for image editing models, visual dragging, almost meets any enlargement requirement

When enlarging images with image editing models (klein, QwenImage2.1, Qwen-Edit, Flux-Fill, sdxl, etc.), old nodes require entering a stack of parameters, repeatedly running tests, and some enlargement requirements cannot be met.
This node turns enlargement into direct operations on the canvas: drag, scale, align, what you see is what you get, while also outputting the corresponding mask.

- No need to guess parameters for enlargement: directly drag the original image position on the canvas, scale proportionally, and use the 3x3 grid buttons for one-click alignment (center, corners, edges)
- No awkward edges: the edges of the original image can be individually specified for feathering, allowing the original image and the extended area to transition smoothly
- Controllable content: the background can be customized with color, pad mode supports constant / reflect / edge / stretch
- Automatic legal dimensions: retains target_width / target_height, adds div parameter to assist alignment to legal resolutions
- Direct mask output: automatically generates a mask after enlargement, marking which part is the original and which part is newly added, facilitating subsequent local redrawing by editing models

Detailed explanation: [Chinese](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 added · v1.5.3 added P button · v1.6.1 optimized</sub>

Directly draw custom sigma curves on the node: click to add points, right-click to delete points.

**P button**: Rearranges the x coordinates of control points — when the number of points is less than steps+1, the first n-1 points' x values are rearranged to 0, 1/steps, ..., (n-2)/steps, y values remain unchanged, and the last point is kept as is; when the number of points is at least steps+1, the first steps+1 points are evenly distributed. Simply put: **without changing the step size of the front part, it adds sampling steps to the latter part (increasing details)**.

<img width="1176" height="794" alt="Element_SigmaGraph" src="https://github.com/user-attachments/assets/a8741609-cbe7-4ec8-a88d-5cae79b031a8" />

---

<a id="chessboard"></a>
## chessboard

<sub>v0.0.9 added (ChessboardPattern)</sub>

Create a black and white checkerboard image.

<img width="1714" height="608" alt="image" src="https://github.com/user-attachments/assets/466bc026-adc5-42cd-abe5-c28f323dd482" />

---

<a id="empty_image_rgb"></a>
## empty_image_rgb

<sub>v0.0.6 added · v1.6.1 optimized</sub>

Create a monochrome image, with color selected from the color wheel, brightness controlled by the brightness slider; the eyedropper can pick color from any position on the screen, but if the browser is not Chrome / Edge 96+, the eyedropper may be unusable, and the eyedropper in the adjacent color palette button can be used instead.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="Element_ListGraph"></a>
## Element_ListGraph

<sub>v1.6.6 added </sub>

Similar to Element_SigmaGraph, the y values of points on the curve are no longer limited to decreasing with x values, output as float and string lists, with the number of elements in the list being the same as steps, not steps + 1. Can be connected to [ComfyUI-Element_TileUpscale](https://github.com/supElement/ComfyUI-Element_TileUpscale)'s reference_strength parameter to control the image reference strength for each step sampling.

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 added, v1.5.9 optimized </sub>

Frame count calculation node, provides minimax H3, ltx2, wan legal presets, can be customized with div_by and offset.

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>v1.2.3 added</sub>

Size alignment calculation.

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="random_chars"></a>
## random_chars

<sub>v0.0.6（Random Chars Append）</sub>

Append invalid special characters to the input text (customizable characters and count).

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6, v1.5.9 optimized</sub>

Wrap the input text by character count, supporting punctuation avoidance at the beginning and end, punctuation squashing, and dangling. The final effect depends on the output carrier.

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---

## Installation

### Manager Installation

Search for **ComfyUI_Element_easy** in the ComfyUI Manager and then Install.

### Manual Installation

Enter the `./ComfyUI/custom_nodes` directory and run:

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt
### Optional Dependency: ffmpeg

The **video export (with audio)** feature of the node requires the system to have ffmpeg installed. Windows users download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/), extract it, and add the bin directory to PATH.

When ffmpeg is not installed, all other features work normally, only video export becomes a silent video.