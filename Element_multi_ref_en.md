# Element Multi REF — Usage Guide

A multi-reference material panel for ComfyUI, designed for video generation models
(MiniMax-H3 / LTXV style) that need first/last frames, reference images, reference
videos and driving audio — with built-in visual editing.

## 1. Dependencies

    pip install av opencv-python numpy    # required
    pip install scenedetect               # optional: better Auto Split

- Requires a recent ComfyUI build (new comfy_api.latest node API).
- ffmpeg/ffprobe on PATH enables a fallback decoder for exotic audio codecs.

## 2. Node Overview

| Node | Purpose |
|---|---|
| Element Multi REF | Visual material panel: import → edit → outputs a REF_ALL_IN_ONE info bundle |
| Element ref convert | Converts the bundle into 21 typed output ports + an info manifest |

## 3. Element Multi REF (Material Panel)

### 3.1 Slots (21 total)

| Group | Slot IDs | Kind |
|---|---|---|
| First/Last frame | first_frame / last_frame | image |
| Reference images | ref_image_0 ~ ref_image_8 | image ×9 |
| Reference videos | ref_video_0 ~ ref_video_2 | video ×3 |
| Video audio | ref_video_audio_0 ~ _2 | audio (pairs with videos) ×3 |
| Reference audio | ref_audio_0 ~ ref_audio_2 | audio ×3 |
| Driving audio | drive_audio | audio ×1 |

Accepted formats:

- Image: .png .jpg .jpeg .webp .bmp
- Video: .mp4 .mov .avi .mkv .webm .m4v
- Audio: .mp3 .wav .flac .ogg .oga .m4a .m4b .aac .opus .wma .aif .aiff .aifc .mka .weba .caf

### 3.2 Importing Files

- **Drag & drop** onto any slot (or empty panel area → auto-assigned to the next
  free slot of the matching kind).
- **Click** an empty slot to open a file browser (filtered by slot kind).
- Multi-file drops are distributed across slots in order.
- Uploads are deduplicated by SHA-256; stored in ComfyUI/input/element_multi_ref/.

### 3.3 Slot Operations

- Hover for ✎ Edit / ✕ Remove buttons.
- **Drag to swap** a filled slot onto another slot of the same kind.
- **Right-click menu**: clear slot / reset edits.
- **×N badge**: material referenced by multiple slots.
- **Clear All** (top bar): wipe everything.

### 3.4 Image Editor

Open via ✎ on an image slot:

**Crop**:
- Drag to draw, drag inside to move;
- **Edge/corner resize**: hover an edge for a ↔/↕ cursor or a corner for a diagonal cursor, then drag to resize (snapping follows div by);
- **div by** (default 32): snaps size to a multiple (model-friendly);
- **W × H** readout at the right of the top bar shows the current crop size (source size when no crop);
- Clear crop removes the box.

**Out W / Out H (output resolution)**:
- Auto-follows the crop box once drawn; you can also type custom values to set the cropped area's output resolution;
- **Lock ratio**: couples W/H by the crop box's aspect ratio (source ratio when no crop); Out updates automatically only when the crop aspect ratio changes — moving or uniformly scaling the box keeps your manual values;
- **⟳ reset**: back to the crop box size (or source size when no crop).

**Paint** (mask/hint strokes; toolbar fixed on the second row):
- Color, brush size 2–80; the cursor is a **ring** matching the brush size (dashed for eraser);
- **Box / Circle**: drag to draw a rectangle/ellipse; **Outline** checked = stroked (Box corners are square), unchecked = filled; cursor becomes a crosshair while a shape tool is active;
- **Shift shortcuts**: in Box/Circle mode hold Shift = square/circle; in free brush mode hold Shift = draw a straight line from the stroke start, release Shift to set the endpoint;
- **Eraser** (combined with a shape tool it erases that shape's area), **Undo** (15 steps), **Clear paint**;
- Strokes are saved as a transparent PNG overlay; the crop box and dimming stay visible in paint mode.

### 3.5 Audio/Video Editor (Timeline)

**Blue selection area or selected segment = final output range**:

- Use selection checked → the blue box defines the output;
- Unchecked → the highlighted segments define the output (click to select,
  Shift = range select, Ctrl = toggle);
- Drag selection edges to trim; drag its body to move (video: Snap to nearest cut).

**Segments**:

- **Auto Split**: automatic scene detection (threshold Thr; PySceneDetect first,
  built-in HSV histogram fallback);
- **Manual (key M)**: click anywhere on the track to slice;
- **Right-click a boundary**: merge adjacent segments;
- **Drag a boundary**: default = roll trim (both sides move); hold Alt/Ctrl =
  one-sided trim/extend;
- **Drag a segment body**: reorder (a cyan insert line shows the drop point).

**Playback**:

- Transport: |◀ (start), ◀| (segment start), ▶ (play current segment),
  ▶▶ (play all segments in order), |▶ (segment end), ▶| (end);
- Click ruler / audio track / selection body to scrub the playhead (frame preview
  + synced audio);
- Fit zoom-to-fit, Full select everything, Zoom manual scale.

**Quantization (output length = a + n × div)**:

| Preset | div | a |
|---|---|---|
| MiniMax H3 (17n+5) | 17 | 5 |
| LTXV (8n+1) | 8 | 1 |
| 4n | 4 | 0 |
| Custom | any | any |

- Live info, e.g. [seg 1] Out: 107 = 17×6+5;
- Audio: enable Quantize to align seconds to frames via Ref FPS (default 24).

**Video extras**: FPS (0 = source) output resampling, Out W/H with lock & ⟳ reset.
**Audio extras**: Quantize / Ref FPS.

**Keyboard shortcuts**:

| Key | Action |
|---|---|
| Space | Play/stop all segments |
| ← / → | Step 1 frame (audio: 0.05s); Shift = 1 second |
| I / O | Set in / out point at playhead |
| Home / End | Selection to start / end |
| M | Toggle manual split mode |

### 3.6 Video–Audio Pairing (ref_video_audio_N)

- Importing a video with audio into ref_video_N automatically fills the matching
  empty ref_video_audio_N slot with that video's waveform (tagged from ref_video_N);
- At execution it outputs the audio of the video's current edit range;
- Right-click the paired slot: open the paired video editor, or replace with an
  independent audio file.

### 3.7 State Persistence

- All materials and edits are serialized into the hidden refs_data widget and saved
  with the workflow;
- Materials are referenced by absolute path — moving/deleting source files or
  switching machines requires re-import (panel shows Material missing).

## 4. Element ref convert (Port Conversion)

Connect REF_ALL_IN_ONE → info input.

### 4.1 Outputs (21 + 1)

| Port | Type | Content |
|---|---|---|
| first_frame / last_frame | IMAGE | Edited first/last frame |
| ref_image_0 ~ _8 | IMAGE | Reference images ×9 |
| ref_video_0 ~ _2 | IMAGE | Frame sequence [T,H,W,3], float 0–1, resampled to output FPS (gaps forward-filled) |
| ref_video_audio_0 ~ _2 | AUDIO | Paired video audio or standalone audio |
| ref_audio_0 ~ _2 | AUDIO | Reference audio |
| drive_audio | AUDIO | Driving audio |
| info | STRING | Per-slot manifest JSON |

### 4.2 Empty-Slot Placeholders

- Image ports → 64×64 black image;
- Audio ports → 1 second of 44100 Hz silence;
- Failed slots also return placeholders and log
  [ElementRefConvert] slot ... → placeholder.

### 4.3 info Manifest Format

    {
      "version": 1,
      "producer": "ElementRefConvert",
      "slots": {
        "first_frame": {"has": true, "kind": "image", "w": 512, "h": 512},
        "ref_video_0": {"has": true, "kind": "video", "frames": 107, "w": 832, "h": 480},
        "drive_audio": {"has": true, "kind": "audio", "seconds": 5.0}
      },
      "missing": ["ref_image_0", "ref_audio_2"]
    }

## 5. Typical Workflow

    [Element Multi REF]
       ├─ first_frame  ← first frame (crop / paint)
       ├─ ref_image_*  ← character / scene references
       ├─ ref_video_0  ← reference video (Auto Split → select segments → 17n+5)
       └─ drive_audio  ← driving audio (optional Quantize)
              │ REF_ALL_IN_ONE
              ▼
       [Element ref convert]
              ├── first/last frame ──▶ video model conditioning
              ├── ref_image_*      ──▶ reference encoders
              ├── ref_video_0      ──▶ VAE Encode / video reference
              ├── ref_video_audio  ──▶ audio conditioning
              └── drive_audio      ──▶ audio-driven models (S2V / lip-sync)

## 6. FAQ

**Q: No waveform on audio slots?** Waveforms come from /element_multi_ref/media_info;
for formats PyAV cannot decode it falls back to the ffmpeg CLI — make sure ffmpeg
is installed.

**Q: fps mismatch log in console?** If the container's nominal fps deviates >2% from
frames/duration, the node switches to the real fps — an automatic correction that
prevents drift over time.

**Q: Auto Split shows "fallback"?** scenedetect isn't installed; a built-in HSV
histogram diff is used. Run pip install scenedetect for better results.

**Q: Timeline laggy with big videos?** Frame previews (LRU, 400 entries) and decoded-
frame cache (~600 MB) are built in; use Fit/Zoom to keep the visible range small.

**Q: Workflow reports Material missing?** Source files were moved/deleted. Re-drop
them into the slots — dedup prevents duplicate storage.

**Q: Where are files stored?** Inputs: ComfyUI/input/element_multi_ref/ (with an
_index.json dedup index); paint overlays: ComfyUI/output/element_multi_ref/paint/.
