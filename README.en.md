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
A material panel for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference video + audio" input. Each material can be cropped, annotated with brushes, and trimmed by time segment, and can also be saved as presets——combined with the queue, it can run multiple sets of materials and prompts at once without switching images back and forth.

**🎛 Curves Color Adjustment (HueSat / HueBright / HueHue / ImageCurve)**
Adjust colors like in photo editing software, where curves are drawn directly on the image, and effects are immediately visible with a drag, just like video for real-time preview.

**📐 Custom Sampling Curves (Element_SigmaGraph)**
Draw the sigma curve of the sampler by hand, especially convenient when you want fewer steps in the beginning and more details in the end.

**🧩 There are over 20 practical small nodes**
Image smart merge, mask stroke, image edge blur, frame count calculation, etc.

## Points to Note as Disadvantages

- **Requires some time to get started**: The panel-style nodes have many functions, and the first time you open them, you might have moments of "what does this button do," it is recommended to use the detailed documentation of each node;
- **Some functions depend on external programs**: Video export with audio requires the system to have ffmpeg installed, automatic scene detection suggests installing scenedetect, and they can still be used without installation, but the corresponding functions are limited;
- **Compatibility depends on a newer version of ComfyUI** (Multi REF uses a new node API), older versions of ComfyUI may not be installable;
- **Nodes are numerous but independent**: If you only need one or two functions, this package might be too large for you.

## 📦 Node Navigation

**🎬 Video and Material Management**

- [Element Multi REF](#element-multi-ref) (includes auxiliary node Element ref convert)
- [Element Load and Edit Video](#element-load-and-edit-video) (includes auxiliary nodes Element Video Clip / Element Video Info)
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler) (includes Advanced version)

**🎛 Curves Color Adjustment**

- [Element ImageCurve](#element-imagecurve) · [Element HueSat](#element-huesat) · [Element HueBright](#element-huebright) · [Element HueHue](#element-huehue)

**🖌 Image Editing and Masking**

- [LoadImage_Preview](#loadimage_preview) · [Smart merge images](#smart-merge-images) · [black_white_color](#black_white_color) · [mask_noise_element](#mask_noise_element) · [mask_stroke](#mask_stroke) · [image_pad_blur](#image_pad_blur)

**📐 Image Generation and Sampling Control**

- [Element_SigmaGraph](#element_sigmagraph) · [chessboard](#chessboard) · [empty_image_rgb](#empty_image_rgb)

**Model Merging**

- [Model Merge (Curve)](#element_modelmergecurve) (includes 8 Extras nodes)

**🔧 Numerical and Textual Tools**

- [Element_ListGraph](#Element_ListGraph) · [Frame Calculator](#frame-calculator) · [ImageSize Div](#imagesize-div) · [Element_Prompt_Presets](#Element_Prompt_Presets) · [Element_random_value_remap](#Element_random_value_remap) · [random_chars](#random_chars) · [text_line_break](#text_line_break)

---
## Bug Fixes and Optimizations

- Now, when the mouse pointer is over a visual interaction node, the ComfyUI canvas can be dragged and scaled normally, except for the thumbnail preview interface of the loadimage_preview node and the timeline window of the Element Load and Edit Video node when selected.

---
<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 New · v1.6.1 Optimized · v1.6.9 Enhanced </sub>

Detailed instructions: [Chinese](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

A material and prompt management solution designed for video/image models like MiniMax-H3, LTXV, Wan, Klein, Qwen, etc., that require multiple reference inputs:

- 21 typed slots: reference images ×9, reference videos ×3, as well as start/end frames, various audio, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotation) and audio/video timeline editor (quantized alignment according to rules like 17n+5, 8n+1, etc.);
- The bottom bar of the panel has 4 area switch icons (reference images, start/end frames, audio/video, Prompt), which can freely combine the panel to meet different needs, and can even be used as a prompt preset node;
- Supports the storage, call, load, and export of multiple presets, as well as the categorization of all references and prompts;
- `run_preset_NUM` parameter corresponds to the index in the preset list, and when receiving input that changes with the prompt queue, combined with sampling inference nodes, it can achieve continuous generation or editing of multiple images/videos;
⚠️ Note: If a preset is loaded, `run_preset_NUM` parameter will automatically become the preset's index, and if you modify the reference area's content without saving/renaming the preset, the output result will be the one before the modification, which is normal behavior; if you don't want to save presets and want to output the modified content of the current interface, you can now click once `reset` button (set `run_preset_NUM` parameter to 0).
- If reference materials used in presets are deleted, you can now use the relink button to specify a directory to reconnect (the directory must contain files with the same names).
- The auxiliary node **Element ref convert** is used for the format conversion of reference data.

<img width="1691" height="874" alt="650757311-e8c32036-3a21-4864-93eb-228ffce3c82b" src="https://github.com/user-attachments/assets/85383cea-931e-4da6-a46b-4d373c95ef49" />

🎬 Core Scenario: Batch Processing of Storyboards

A script may have dozens or even hundreds of shots. Each shot's prompt, reference image, reference video, start/end frames, are all saved as presets.

Combined with sampling nodes, run all segments with one click. Change if needed, save presets when satisfied——no need to load workflows back and forth, or manually switch materials and prompts in individual nodes.

- Before: Change a shot → Switch image → Change prompt → Run → Change next → Repeat dozens of times. If reference images or audio/video need fine-tuning, you have to open PS or editing software.
- Now: All presets are arranged → Run with one click → Not satisfied, change preset → Run again. Fine-tuning of reference images or audio/video is completed directly on the node, without switching software.

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

<sub>v1.4.3 New Addition · v1.8.2 Fix: Set torch.hub directory on first run </sub>

Detailed Description: [Chinese](subMd/SmartMergeImages_zh.md) | [English](subMd/SmartMergeImages_en.md)</sub>

🎬 Core Scenario: Eliminate distortion and color differences caused by block-wise scaling of images after passing through a generative model

When splitting an image into multiple blocks, or when a part of the image is given to a generative model for resampling/editing/upscaling and then reassembled, there are often color differences and distortions at the seams, and the direct assembly effect may be poor.
This node uses common features of two images for intelligent alignment, smoothly reassembles the results of block-wise upscaling back into the original image.

Download [model files](https://huggingface.co/cglearned/Smart_merge_images/tree/main), default to automatic download.

Manual download: depth-save.pth / disk_lightglue_v0-1_arxiv-pth / loftr_outdoor.ckpt
To \ComfyUI\models\elementEasy\checkpoints

<img width="1949" height="1171" alt="68700067" src="https://github.com/user-attachments/assets/3682af85-9d8a-4936-9653-429e760907de" />

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

Easily add random noise to the mask areas of an image.

<img width="1724" height="878" alt="屏幕截图 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 added</sub>

mask stroke: individually control the width and blur of inner and outer strokes, support adding overall weight to non-stroke areas (making the output mask have no area with weight 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 added · v1.6.0 refactored · v1.6.1 optimized</sub>

🎬 Core scenario: Expand images for image editing models, visual drag-and-drop, almost meets any expansion requirement

When expanding images with image editing models (klein, QwenImage2.1, Qwen-Edit, Flux-Fill, sdxl, etc.), old nodes require entering a stack of parameters, repeatedly running tests, and some expansion requirements cannot be met.
This node turns expansion into direct operations on the canvas: drag-and-drop, scale, align, what you see is what you get, while also outputting the corresponding mask.

- No need to guess parameters for expansion: directly drag the original image position in the canvas, scale proportionally, one-click align with the 3x3 grid button (center, corners, edges)
- No edge artifacts: the edges of the original image can be individually specified for feathering, allowing the original image and the expanded area to transition smoothly
- Controllable content: background color can be customized, pad mode supports constant / reflect / edge / stretch
- Automatic valid size: retain target_width / target_height, add div parameter to assist alignment to valid resolution
- Directly output mask: automatically generates a mask after expansion, marking which part is the original and which part is newly added, convenient for subsequent editing model local redraw
  
Detailed explanation: [Chinese](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 added · v1.5.3 added P button · v1.6.1 optimized</sub>

Directly draw custom sigma curves on the node: click to add points, right-click to delete points.

**P button**: Rearrange the x coordinates of control points — when the number of points is less than steps+1, the first n-1 points' x are rearranged to 0, 1/steps, ..., (n-2)/steps, y remains unchanged, and the last point is kept as is; when the number of points is at least steps+1, take the first steps+1 points evenly distributed. Simply put: **without changing the step size of the front part, add sampling steps to the latter part (increase details)**.

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

Create a monochrome image, color selected from the color wheel, brightness slider controls brightness; the eyedropper can pick color from any position on the screen, if the browser is not Chrome / Edge 96+, the eyedropper may be unusable, can switch to the palette button next to it.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="Element_ListGraph"></a>
## Element_ListGraph

<sub>v1.6.6 added </sub>

Similar to Element_SigmaGraph, the y values of points on the curve are no longer limited to decreasing with x, output as float and string lists, the number of elements in the list is the same as steps, not steps + 1. Can be connected to [ComfyUI-Element_TileUpscale](https://github.com/supElement/ComfyUI-Element_TileUpscale) reference_strength parameter, to control the image reference strength for each step sampling.

---

<a id="element_modelmergecurve"></a>
## Model Merge (Curve)

<sub>v1.8.8 added </sub>

Detailed explanation: [Chinese](subMd/Element_ModelMerge_zh.md) | [English](subMd/Element_ModelMerge_en.md)

Use a curve to determine the proportion of each block to take model1, mixing model2 in by depth. A general node switches `model_type` between Krea2, MOSS Image, Qwen Image, MiniMax H3, Auraflow, LTXV, SDXL, WAN 2.1; non-block layers are provided with corresponding 8 Extras nodes for proportions, all 1.0 when not connected. Curve y=1 is to take only model1, y=0 is to take only model2, with y=0.5 and x=0.5 reference lines on the canvas.

<img width="1164" height="844" alt="image" src="https://github.com/user-attachments/assets/63b95a61-6b40-45b1-8a70-96e2b5f52632" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 Added, v1.5.9 Optimized</sub>

Frame count calculation node, provides minimax H3, ltx2, wan presets, and can be customized via div_by and offset.

<img width="1154" height="655" alt="image" src="https://github.com/user-attachments/assets/9a99acc7-96b3-43e8-a3c7-1b4fd2ab93f4" />

---

<a id="imagesize-div"></a>
## ImageSize Div

<sub>v1.2.3 Added</sub>

Size alignment calculation.

<img width="1317" height="596" alt="ImageSize Div" src="https://github.com/user-attachments/assets/6f53211f-f695-4db6-9483-9da984d193ef" />

---

<a id="Element_Prompt_Presets"></a>
## Element_Prompt_Presets

<sub>v1.7.9 Added · v1.8.4 Enhanced</sub>

Detailed description: [Chinese](subMd/Element_prompt_presets_zh.md) | [English](subMd/Element_prompt_presets_en.md)</sub>

- Prompt management node: Select prompts by "Category → Entry," edit, create, or delete directly on the node, and export JSON backups, supporting import of json, xlsx, csv format files.
- Supports multi-select entries in the popup: prompt_text outputs a single paragraph of text separated by links, prompt_list outputs a list of entry texts; selection status is saved with the workflow, and entries can be deleted directly in the popup / category.
- Entries can be marked as tags or Natural language: The entry option displays a solid dot after the tags entry name (only displayed, not entered into output); check tags when creating, or use "Modify tags" to mark; multi-select popup can filter by both categories.
- Two types of output: full paragraph / single line; when single_line is enabled, it extracts one line from the full text based on seed, combined with fixed / incremental / decremental / random four seed modes, which can automatically rotate different sentences with the queue. Exception: When all selected entries are natural language (no tags), prompt_text changes to output the full entry selected by seed (prompt_list remains unchanged).
- Preset storage location: ComfyUI\user\element_easy\promptPresets\prompts.json.

<img width="1687" height="575" alt="image" src="https://github.com/user-attachments/assets/473d16e5-006f-43ad-96e5-14b566cb9a96" />

---

<a id="Element_random_value_remap"></a>
## Element_random_value_remap

<sub>v1.8.5 Added</sub>

Stably maps input values (most commonly seed) to [min, max] range, outputs float and int two ports.

- value input port is optional, accepts both int and float, for example, directly connected to Seed node; when no input is connected, it also randomly outputs between min and max each time; min and max are floating-point parameters, can be negative;
- The same input value always gets the same result; different seeds are scattered within the range, combined with the fixed / incremental / decremental / random modes of seed, the queue can change;

<img width="1481" height="409" alt="image" src="https://github.com/user-attachments/assets/7bc360e3-daee-4a3b-911d-17d00fba14e1" />

---
<a id="random_chars"></a>
## random_chars

<sub>v0.0.6（Random Chars Append）</sub>

Appends invalid special characters to the input text (characters and count can be customized).

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6, v1.5.9 Optimized</sub>

Breaks the input text into lines based on character count, supporting punctuation avoidance at the beginning and end, punctuation squeezing, and hanging. The final effect depends on the output carrier.

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

The **video export (with audio)** feature of the node requires the system to install ffmpeg. Windows users download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/), extract, and add the bin directory to PATH.

All other features work normally when ffmpeg is not installed, only video export is silent video.

---

⚠️ Model files for smart_merge node have been permanently removed from this repository's Git history (git pull / reinstalling the plugin will not restore them), and are now downloaded from HuggingFace.

📦 [Model files](https://huggingface.co/cglearned/Smart_merge_images/tree/main)

✅ When running smart_merge node for the first time, if the model is missing, it will be automatically downloaded to:
    ComfyUI/models/elementEasy/checkpoints/

📥 For manual download (when unable to access HuggingFace), please download the following 3 files to the above directory:
    - depth-save.pth
    - disk_lightglue_v0-1_arxiv-pth
    - loftr_outdoor.ckpt

⚠️ Note: disk_lightglue_v0-1_arxiv-pth does not have the .pth suffix, this is kornia's naming convention, not file corruption, do not rename manually.
## About Sponsorship

[![ko-fi](https://ko-fi.com/img/githubbutton_sm.svg)](https://ko-fi.com/supElement)

**⚠️ Note:**  
Whether you choose to sponsor or not, it will have no impact on the features or user experience provided by my plugin. All content will remain free and open-source.  
**Please only consider sponsoring if you genuinely find these tools helpful to you, or if you have gained benefits from using them.**