<div align="center">

[![Chinese](https://img.shields.io/badge/语言-简体中文-red?style=for-the-badge)](./README.md)
[![English](https://img.shields.io/badge/Language-English-blue?style=for-the-badge)](./README.en.md)

</div>

# ComfyUI_Element_easy

A ComfyUI extension primarily focused on **visual interface and convenient interaction**. The nodes in this package are different: instead of a slider paired with a number, the entire tool is moved directly into the node.

## What You Can Get

**🎬 Video Editing (Element Load and Edit Video)**
Edit videos directly on the node without leaving ComfyUI: automatically detects scene cut points, or you can manually cut, trim, reorder segments, preview while editing, and output both video and audio directly after editing.

**🗂 Multi Reference Material Panel (Element Multi REF)**
A material station for video models (MiniMax-H3, LTXV, Wan, etc.) that require "reference images + start/end frames + reference video + audio" input. Each material can be cropped, annotated with brushes, and trimmed, and can be saved as presets—paired with a queue, it can run multiple sets of materials and prompts at once without switching images back and forth.

**🎛 Curve Color Grading (HueSat / HueBright / HueHue / ImageCurve)**
Like adjusting colors in photo editing software with curves, the curve is drawn directly on the image, and dragging immediately shows the effect, the same real-time preview for videos.

**📐 Custom Sampling Curves (Element_SigmaGraph)**
Manually draw the sigma curve of the sampler, especially convenient when you want fewer steps in the beginning and more details in the end.

**🧩 There are also more than 20 practical small nodes**
Image smart merge, mask stroke, image edge blur, frame count calculation, etc.

## Disadvantages to Note

- **It takes some time to get started**: The panel-style nodes have many functions, and the first time you open them, you might have moments of "what does this button do," it is recommended to use it together with the detailed documentation of each node;
- **Some functions depend on external programs**: Video export with audio requires the system to have ffmpeg installed, automatic scene detection suggests installing scenedetect, you can still use it without installation, but the corresponding functions will be limited;
- **Compatibility depends on a newer version of ComfyUI** (Multi REF uses a new node API), older versions of ComfyUI may not be installable;
- **The nodes are numerous but independent**: If you only need one or two functions, this package might be too large for you.

## 📦 Node Navigation

**🎬 Video and Material Management**

- [Element Multi REF](#element-multi-ref) (includes auxiliary node Element ref convert)
- [Element Load and Edit Video](#element-load-and-edit-video) (includes auxiliary nodes Element Video Clip / Element Video Info)
- [Minimax_H3-LatentUpscaler](#minimax_h3-latentupscaler) (includes Advanced version)

**🎛 Curve Color Grading**

- [Element ImageCurve](#element-imagecurve) · [Element HueSat](#element-huesat) · [Element HueBright](#element-huebright) · [Element HueHue](#element-huehue)

**🖌 Image Editing and Masking**

- [LoadImage_Preview](#loadimage_preview) · [Smart merge images](#smart-merge-images) · [black_white_color](#black_white_color) · [mask_noise_element](#mask_noise_element) · [mask_stroke](#mask_stroke) · [image_pad_blur](#image_pad_blur)

**📐 Image Generation and Sampling Control**

- [Element_SigmaGraph](#element_sigmagraph) · [chessboard](#chessboard) · [empty_image_rgb](#empty_image_rgb)

**🔧 Number and Text Tools**

- [Frame Calculator](#frame-calculator) · [ImageSize Div](#imagesize-div) · [random_chars](#random_chars) · [text_line_break](#text_line_break)

---
## Bug Fixes and Optimizations

- Now the mouse pointer can be dragged and scaled normally on the ComfyUI canvas when interacting with visual nodes, except for the thumbnail preview interface of the loadimage_preview node.

---
<a id="element-multi-ref"></a>
## Element Multi REF

<sub>v1.5.7 New Addition </sub>

Detailed instructions: [Chinese](subMd/Element_multi_ref_zh.md) | [English](subMd/Element_multi_ref_en.md)</sub>

A material and prompt management solution designed for video/image models like MiniMax-H3, LTXV, Wan, Klein, Qwen, etc., that require multi-path reference input:

- 21 typed slots: reference images ×9, reference videos ×3, as well as start/end frames, various audio, and Prompt cards;
- Each card has an independent simple image editor (crop, brush annotation) and audio/video timeline editor (quantized alignment according to rules like 17n+5, 8n+1, etc.);
- Supports the storage, recall, loading, and exporting of multiple presets, as well as organizing all references and prompts;
- The `run_preset_NUM` parameter corresponds to the index in the preset list, and when receiving inputs that change with the prompt queue, paired with sampling inference nodes, it can achieve continuous generation or editing of multiple images/videos;
- The bottom bar on the panel has four area switch icons (reference images, start/end frames, audio/video, Prompt), allowing free combination of the panel to meet different needs, and can even be used as a prompt preset node.

The auxiliary node **Element ref convert** is used for the format conversion of reference data.

<img width="1691" height="874" alt="Element Multi REF" src="https://github.com/user-attachments/assets/e8c32036-3a21-4864-93eb-228ffce3c82b" />

---

<a id="element-load-and-edit-video"></a>
## Element Load and Edit Video

<sub>v1.5.4 New Addition </sub>

Detailed instructions: [Chinese](subMd/Element_scene_detection.zh.md) | [English](subMd/Element_scene_detection.en.md)</sub>

A visual single-track video editor node:

- PySceneDetect automatically detects scene cut points, or you can manually split, trim, and reorder segments on the interactive timeline;
- Synchronized preview of video and audio;
- Directly outputs the sequence of frames of the segment and the corresponding audio, supports exporting mp4 with audio (requires ffmpeg).

The auxiliary nodes **Element Video Clip**, **Element Video Info** are used together.

<img width="2147" height="1104" alt="Element Load and Edit Video" src="https://github.com/user-attachments/assets/5ba547a7-31c8-4323-bf40-7ec58f1b548e" />

---

<a id="minimax_h3-latentupscaler"></a>
## Minimax_H3-LatentUpscaler

<sub>v1.5.0 added · Added simultaneously with Adv version</sub>

A dedicated node for upscaling video latent space only, does not process audio, output port is Minimax H3 latent.

**Adv version** with validation, introduces three conditional upscaling modes:

| Mode | Behavior |
|---|---|
| pass_through | Bypass validation directly |
| NO_refs | Align only, do not upscale |
| refs | Upscale (best quality) |

---

<a id="element-imagecurve"></a>
<a id="element-huesat"></a>
<a id="element-huebright"></a>
<a id="element-huehue"></a>
## Curve Color Series

<sub>v1.2.7 ~ v1.3.1 added gradually · v1.6.0 optimized</sub>

All four nodes have the same interaction method: **curves are drawn directly on the image for real-time preview, click to add points, right-click to remove points**, supports single and sequence frame images.

| Node | Curve Type |
|---|---|
| Element ImageCurve | RGB / R / G / B channel curves |
| Element HueSat | Hue → Saturation |
| Element HueBright | Hue → Brightness |
| Element HueHue | Hue → Hue |

> ⚠️ Except for Element ImageCurve, do not add points at both ends of the curve simultaneously: the curves at both ends are closed loops, adding points at both ends will make one point invalid, actually one endpoint is enough to complete the color adjustment.

<img width="1695" height="891" alt="Element HueSat" src="https://github.com/user-attachments/assets/627e1951-244b-4b13-937c-23c8d98748e8" />
<img width="1767" height="1008" alt="Element ImageCurve" src="https://github.com/user-attachments/assets/f3bcfd71-eaba-4933-aa97-01ee6eefad62" />

---

<a id="loadimage_preview"></a>
## LoadImage_Preview

<sub>v1.3.5 added · v1.6.0 optimized</sub>

Browse image files under the specified path, after selection, enter the editing panel for simple editing: free drawing lines, mask, boxes, circles, and crop images.

- `Shift + Left click`: Draw straight lines, squares, or perfect circles
- `L-alpha`: Load image alpha channel to canvas
- `Return`: Switch between zoom panel and editing panel
- In editing mode, supports `Ctrl+V` to paste images, supports dragging directly from web or file explorer
- ComfyUI's input directory is a permanent node, folder path specified directory as an additional directory

<img width="1453" height="913" alt="LoadImage_Preview" src="https://github.com/user-attachments/assets/ed8d3d43-b18d-482b-84f1-6c0f6b87add5" />

---

<a id="smart-merge-images"></a>
## Smart merge images

<sub>v1.4.3 added · v1.4.8 optimized</sub>

When two images have enough common features, intelligently merge images, suitable for splicing the results of local redraw back into the original image:

- **Optimal input scheme**: original_image + edited_crop_B + original_crop_A. Among them, original_crop_A is an image cut from the original image without modification or deformation, and edited_crop_B is an edited or redrawn image;
- Supports block merging: when multiple images are input to the edited_crop_B port, the output is a single image after final merging. Note that the input must be **Batch and not list**, if it is a list, it needs to be converted through the Image List To Batch node.

<img width="2121" height="963" alt="image" src="https://github.com/user-attachments/assets/0e341594-8b59-45af-8ece-59382ace50e4" />

---

<a id="black_white_color"></a>
## black_white_color

<sub>v1.1.3 added</sub>

Black and white partition style conversion node, used to suppress pixel offset issues after style conversion in qwenEdit: first convert the style of the mask area, then convert the invert mask area; try to make the black and white area sizes average to reduce the problem of inconsistent tones.

The mask at the input port will perform an ADD operation with the mask generated by the node.

<img width="1596" height="1084" alt="black_white_color" src="https://github.com/user-attachments/assets/c715e5e6-1ff3-46ff-9d48-a0a87d2506df" />

---

<a id="mask_noise_element"></a>
## mask_noise_element

<sub>v0.0.8 added (Image Noise Using Mask)</sub>

Conveniently add random noise to the mask area of the image.

<img width="1724" height="878" alt="Screenshot 2026-01-17 134457" src="https://github.com/user-attachments/assets/17b9af6d-e8d2-4c35-9e13-6822e6bfa266" />

---

<a id="mask_stroke"></a>
## mask_stroke

<sub>v0.0.7 added</sub>

Mask stroke: inner and outer stroke widths and blur degrees are controlled separately, supports adding overall weight to non-stroke areas (making the output mask have no area with weight 0).

<img width="1295" height="731" alt="mask_stroke" src="https://github.com/user-attachments/assets/56b86fb6-758a-4d6c-8fa1-997b6bc9ee9d" />

---

<a id="image_pad_blur"></a>
## image_pad_blur

<sub>v0.0.8 added · v1.6.0 refactored</sub>

A visual interactive image edge extension node (drag the image directly with the mouse inside the canvas). The edges of the original image can be specified individually whether to feather (using the same feather value), customize the background, freely or proportionally scale the image inside the canvas, and specify the background color.

- The node attribute parameters retain target width / target height parameters, add div parameter to assist in setting legal resolutions.
- The 3x3 button group corresponds to 9 alignment modes respectively (center, left, right, top, bottom, top-left, top-right, bottom-left, bottom-right)
- pad mode: constant / reflect / edge / stretch

Detailed explanation: [Chinese](subMd/image_pad_blur_zh.md) | [English](subMd/image_pad_blur_en.md)</sub>

<img width="1510" height="855" alt="image" src="https://github.com/user-attachments/assets/e436ca37-d37e-4947-8b13-7a00c9721e7a" />

---

<a id="element_sigmagraph"></a>
## Element_SigmaGraph

<sub>v1.2.4 added · v1.5.3 added P button</sub>

Draw custom sigma curves directly on nodes: click to add points, right-click to delete points.

**P button**: Rearrange the x coordinates of control points—when the number of points is less than steps+1, the first n-1 points' x coordinates are rearranged to 0, 1/steps, ..., (n-2)/steps, y remains unchanged, and the last point is kept as is; when the number of points is at least steps+1, the first steps+1 points are evenly distributed. Simply put: **without changing the step size of the front part, add sampling steps to the latter part (increase details)**.

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

<sub>v0.0.6 added, v1.5.9 optimized</sub>

Create a monochrome image, with color selected from the color wheel, brightness controlled by the slider; the eyedropper can pick color from any position on the screen, if the browser is not Chrome / Edge 96+, the eyedropper may not be available, and can be replaced with the eyedropper in the adjacent color palette button.

<img width="1329" height="904" alt="image" src="https://github.com/user-attachments/assets/9dd2957b-e261-40ce-8041-87a83df33880" />

---

<a id="frame-calculator"></a>
## Frame Calculator

<sub>v1.2.2 added, v1.5.9 optimized</sub>

Frame count calculation node, provides minimax H3, ltx2, wan legal presets, can be customized by div_by and offset.

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

<sub>v0.0.6 (Random Chars Append)</sub>

Append invalid special characters to the input text (characters and count can be customized).

---

<a id="text_line_break"></a>
## text_line_break

<sub>v0.0.6, v1.5.9 optimized</sub>

Wrap the input text by character count, supports punctuation avoidance at the beginning and end, punctuation squashing, and hanging. The final effect depends on the output carrier.

<img width="1693" height="981" alt="image" src="https://github.com/user-attachments/assets/62b3f66a-6cec-4d10-904a-5a33a102ba92" />

---

## Installation

### Manager installation

Search for **ComfyUI_Element_easy** in ComfyUI Manager, then Install.

### Manual installation

Enter `./ComfyUI/custom_nodes` directory, run:

    git clone https://github.com/supElement/ComfyUI_Element_easy.git
    cd ComfyUI_Element_easy
    pip install -r requirements.txt
### Optional dependency: ffmpeg

The node's **video export (with audio)** feature requires the system to have ffmpeg installed. Windows users download from [ffmpeg](https://www.gyan.dev/ffmpeg/builds/), extract, and add the bin directory to PATH.

When ffmpeg is not installed, other features work normally, only video export is silent video.