# Element Load and Edit Video User Guide

## 📦 Node Group Overview

This node group provides **video scene detection + visual timeline editing** capabilities, consisting of 3 nodes:

| Node | Purpose |
|---|---|
| **Element Load and Edit Video** | Main node: import video, timeline editing (auto/manual scene splitting, trim, reorder), export |
| **Element Video Clip** | Downstream node: outputs images/audio/frame count/duration of selected clips, plus an info bundle describing the actual output |
| **Element Video Info** | Downstream node: outputs FPS, width, height (accepts info from either upstream node) |

---

## 🚀 Quick Start

1. Add the **Element Load and Edit Video** node, click **Import** in the top-left corner to load a local video
2. Click **Auto Split** to detect scene cuts automatically (or edit manually as described in "Timeline Operations" below)
3. Connect the main node's **info** output to the info input of **Element Video Clip**
4. Run the workflow — Element Video Clip will output the clip frames and audio
5. (Optional) To get FPS/size info: connect **Element Video Clip's info output** to **Element Video Info** — it then reports the *actual output* size after scaling

---

## 🎛 Main Node Toolbar

| Control | Description |
|---|---|
| **Import** | Upload a local video file |
| **Auto Split** | Run PySceneDetect scene detection immediately using the Threshold value |
| **Threshold** | Detection sensitivity (5–50); lower values produce finer cuts |
| **Manual** | Manual marking mode: when enabled, click/drag on the track to add cuts |
| **Force 2** | Force-split the video into two parts when no cuts exist |
| **Auto Run** | ★ When checked, **scene splitting runs automatically on workflow execution** if the timeline has no manual edits |
| **Sync Cuts** | Fetch auto cuts cached on the backend (use together with Auto Run) |
| **Clear** | Clear all cuts and restore the full video as a single clip |

Main node parameters:

- **force_rate**: Force output FPS; 0 = keep the source frame rate
- **subsampling**: Keep every Nth frame (e.g. 2 = half the frames); downstream frame_count/seconds will change accordingly

---

## ✂️ Timeline Operations

| Action | Effect |
|---|---|
| **Click a clip** | Select it (Ctrl+click to add, Shift+click for range selection) |
| **Drag a clip** | Change playback order |
| **Drag a clip edge** | Trim the clip; hold **Alt/Ctrl** while dragging = roll trim (the split point moves as one unit) |
| **Drag the ruler / red playhead** | Scrub the preview |
| **Right-click a boundary** | Merge two adjacent clips |
| **Fit / arrows / Select All** | Fit to width, move selected clips, select all |

Transport bar below the preview: jump to timeline start/end, jump to current clip start/end, **play current clip**, **play all clips in sequence** (with audio sync).

**Export** at the bottom: export selected clips (or all clips when Export All is checked) as mp4 files with audio to the **Out Dir** directory.

---

## 🔗 Downstream Nodes

### Element Video Clip

**clip_select** modes:

- `select clip`: outputs the clip currently **selected** on the timeline
- `segnum`: select by **SegNum** index (1-based, timeline order)
- `first clip` / `last clip` / `all`: first / last / all segments (`all` concatenates them in timeline order)

**Parameters**:

| Parameter | Description |
|---|---|
| **target_long_edge** | ★ Scale frames so the **long edge** equals this value (aspect ratio kept). Smaller than source = downscale; larger = upscale; **0 = keep source resolution**. Default 1366 (≈ 768P for 16:9). Affects `images` (and first/last images when `scale_first_last` is ON) |
| **scale_first_last** | ★ Switch: **ON** — `first_image`/`last_image` follow `target_long_edge` (same size as images). **OFF** (default) — first/last images always stay at **source resolution**, regardless of scaling |

**Outputs**:

| Output | Description |
|---|---|
| `images` | Frame sequence of the selected clip(s) (size affected by `target_long_edge`) |
| `audio` | Audio of exactly the selected segment range(s) (decoded per segment, no bleed from adjacent clips) |
| `frame_count` / `seconds` | Frame count / duration (follow force_rate/subsampling) |
| `first_image` / `last_image` | First / last frame (source resolution by default, see `scale_first_last`) |
| `info` | ★ Info bundle describing what was **actually output** (real FPS, size after scaling, segment ranges, etc.) — **can feed Element Video Info directly** |

### Element Video Info

Accepts **two kinds of info sources** and detects them automatically:

| Wired from | FPS | Width / Height |
|---|---|---|
| **Element Load and Edit Video** | Effective FPS after force_rate/subsampling | **Source** resolution |
| **Element Video Clip** | Real playback FPS of the output images | **Actual output** size after `target_long_edge` scaling (read from the output tensor itself) |

> Recommended: wire Video Clip → Video Info when you need the output size — no need to keep `target_long_edge` settings in sync manually.

---

## 💡 Memory Tips for Long Videos

`images` is materialized at once as a float32 tensor; memory ≈ `frames × width × height × 12 bytes`. For long videos:

1. **Output one segment per run** (`clip_select` = select clip / segnum); run multiple times instead of one `all`
2. **Control resolution with `target_long_edge`** (e.g. a 768P reference-video API doesn't need 4K frames)
3. Use **subsampling / force_rate** to bring the frame rate down to what you actually need (e.g. 24 fps)
4. Consider the ComfyUI launch flag `--cache-lru` to reduce post-run cache retention (images outputs are held by the node cache after execution)

---

## ⚠️ Notes

1. **Dependencies**:
   - Required: `av` (PyAV)
   - For scene detection: `pip install scenedetect`
   - For audio playback / export with audio: **ffmpeg** must be installed on the system (without it, clips export without audio)
2. **Temporary files**: Uploaded videos are saved to ComfyUI/input/element_scene_detection/ and persist with the workflow; re-import only if the file was manually moved or deleted
3. **Manual edits take priority**: Once you have trimmed/reordered the timeline, Auto Run will not overwrite your manual decisions
4. **info outputs**: Both info bundles are JSON (video path, segment ranges, FPS, etc.). The main node’s info describes the *source*; Video Clip's info describes the *actual output* and can be parsed by Element Video Info (or fed back into Element Video Clip)
5. **First/last image size**: By default they stay at source resolution so you always have full-quality reference frames; turn on `scale_first_last` if you need them to match `images`
