import { app } from "../../../scripts/app.js";

/* ================= 槽位定义 ================= */
const SLOT_DEFS = [
  { id: "first_frame", kind: "image", group: "frame" },
  { id: "last_frame",  kind: "image", group: "frame" },
  ...Array.from({ length: 9 }, (_, i) => ({ id: `ref_image_${i}`, kind: "image", group: "img" })),
  ...Array.from({ length: 3 }, (_, i) => ({ id: `ref_video_${i}`, kind: "video", group: "video" })),
  ...Array.from({ length: 3 }, (_, i) => ({ id: `ref_video_audio_${i}`, kind: "audio", group: "vau" })),
  ...Array.from({ length: 3 }, (_, i) => ({ id: `ref_audio_${i}`, kind: "audio", group: "aud" })),
  { id: "drive_audio", kind: "audio", group: "drive" },
];
const SLOT_MAP = Object.fromEntries(SLOT_DEFS.map(d => [d.id, d]));
const SLOT_ORDER = SLOT_DEFS.map(d => d.id);
const KIND_ACCEPT = {
  image: "image/*,.png,.jpg,.jpeg,.webp,.bmp",
  video: "video/*,.mp4,.mov,.avi,.mkv,.webm,.m4v",
  audio: "audio/*,.mp3,.wav,.flac,.ogg,.oga,.m4a,.m4b,.aac,.opus,.wma,.aif,.aiff,.aifc,.mka,.weba,.caf",
};
const IMG_EXTS = [".png",".jpg",".jpeg",".webp",".bmp"];
const VID_EXTS = [".mp4",".mov",".avi",".mkv",".webm",".m4v"];
const AUD_EXTS = [".mp3",".wav",".flac",".ogg",".oga",".m4a",".m4b",".aac",".opus",
                  ".wma",".aif",".aiff",".aifc",".mka",".weba",".caf"];
const PRESETS = [
  { name: "MiniMax H3 (17n+5)", div: 17, a: 5 },
  { name: "LTXV (8n+1)",        div: 8,  a: 1 },
  { name: "4n",                 div: 4,  a: 0 },
  { name: "Custom",             div: 17, a: 5 },
];

function guessKind(f) {
  const e = (f?.name?.match(/\.[^.]+$/) || [""])[0].toLowerCase();
  const t = f?.type || "";
  if (IMG_EXTS.includes(e) || t.startsWith("image/")) return "image";
  if (VID_EXTS.includes(e) || t.startsWith("video/")) return "video";
  if (AUD_EXTS.includes(e) || t.startsWith("audio/")) return "audio";
  return null;
}


function filesFromDataTransfer(dt) {
  let files = [...(dt?.files || [])];
  if (files.length || !dt?.items?.length) return files;
  const out = [];                      
  for (const it of dt.items) {
    if (it.kind !== "file") continue;
    const f = it.getAsFile();
    if (f) out.push(f);
  }
  return out;
}

const svgIcon = (p, s = 13) =>
  `<svg width="${s}" height="${s}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">${p}</svg>`;
const ICONS = {
  edit: '<path d="M12 20h9"/><path d="M16.5 3.5a2.1 2.1 0 0 1 3 3L7 19l-4 1 1-4z"/>',
  x:    '<path d="M18 6 6 18"/><path d="m6 6 12 12"/>',
  play: '<path d="M7 4.5v15l13-7.5z" fill="currentColor" stroke="none"/>',
  stop: '<rect x="6" y="6" width="12" height="12" rx="1.5" fill="currentColor" stroke="none"/>',
};

function installStyles() {
  if (document.getElementById("emr-style")) return;
  const st = document.createElement("style"); st.id = "emr-style";
  st.textContent = `
  .emr{box-sizing:border-box;display:flex;flex-direction:column;width:100%;height:100%;min-height:600px;
    background:#14171e;color:#dfe6f2;border-radius:9px;overflow:hidden;font:12px/1.4 Inter,Segoe UI,sans-serif;user-select:none}
  .emr *{box-sizing:border-box}
  .emr-head{display:flex;align-items:center;gap:8px;padding:7px 10px;background:#1b2029;border-bottom:1px solid #2b3342;flex-shrink:0}
  .emr-title{font-weight:700;color:#eaf0fa}
  .emr-status{margin-left:auto;color:#8d97a8;max-width:260px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
  .emr-btn{height:24px;padding:0 9px;border:1px solid #3b4558;border-radius:5px;background:#252d3a;color:#dce5f5;cursor:pointer;display:inline-flex;align-items:center;gap:4px}
  .emr-btn:hover{background:#303a4b}
  .emr-grid{flex:1;display:grid;grid-template-columns:minmax(320px,1fr) minmax(340px,1.1fr);gap:10px;padding:10px;min-height:0}
  .emr-col{display:flex;flex-direction:column;gap:8px;min-height:0}
  .emr-col-img{display:grid;grid-template-columns:repeat(3,1fr);grid-template-rows:repeat(3,1fr);gap:8px;min-height:0}
  .emr-row{display:grid;gap:8px;min-height:0}
  /* 首尾帧行高 = 左列 1/3 行高（(100%-2×8px gap)/3），其余行按比例吃满剩余高度 → 上下边缘对齐 */
  .emr-row-frames{grid-template-columns:1fr 1fr;flex:0 0 calc((100% - 16px)/3)}
  .emr-row-video{grid-template-columns:repeat(3,1fr);flex:36 1 0%}
  .emr-row-vau{grid-template-columns:repeat(3,1fr);flex:18 1 0%}
  .emr-row-aud{grid-template-columns:repeat(3,1fr);flex:18 1 0%}
  .emr-row-drive{grid-template-columns:1fr;flex:28 1 0%}
  .emr-slot{position:relative;border:1.5px solid #3a4356;border-radius:7px;overflow:hidden;cursor:pointer;
    display:flex;align-items:center;justify-content:center;background:#20262f}
  .emr-slot.g-img{background:#232833;border-color:#404a5c}
  .emr-slot.g-frame{background:#251f36;border-color:#4b4166}
  .emr-slot.g-video{background:#1b2a3d;border-color:#35557c}
  .emr-slot.g-vau{background:#172b28;border-color:#2f5c54}
  .emr-slot.g-aud{background:#1c2b1c;border-color:#3a613a}
  .emr-slot.g-drive{background:#16263b;border-color:#2f527c}
  .emr-slot.drop-ok{outline:2px solid #43d9d1;outline-offset:-2px}
  .emr-slot.drag-src{opacity:.4}
  .emr-slot .emr-media{position:absolute;inset:0;display:flex;align-items:center;justify-content:center}
  .emr-slot img.emr-thumb{width:100%;height:100%;object-fit:contain;background:transparent;pointer-events:none}
  .emr-slot canvas.emr-wave{width:100%;height:100%;display:block;pointer-events:none}
  .emr-slot .emr-empty{color:#6f7c92;font-size:11px;pointer-events:none}
  .emr-tag{position:absolute;left:5px;bottom:4px;font-size:10px;font-weight:600;color:#cdd7e5;
    background:rgba(8,12,18,.72);padding:1px 5px;border-radius:4px;pointer-events:none;z-index:2}
  .emr-badge{position:absolute;left:5px;top:4px;font-size:10px;font-weight:700;color:#1a1508;
    background:#e2b04a;padding:0 5px;border-radius:4px;z-index:2;pointer-events:none}
  .emr-pairtag{position:absolute;left:5px;top:4px;font-size:10px;color:#8fd3c8;
    background:rgba(8,14,18,.7);padding:1px 6px;border-radius:4px;pointer-events:none;z-index:2}
  .emr-iconbtn{position:absolute;width:22px;height:22px;border:1px solid rgba(125,145,175,.45);border-radius:5px;
    background:rgba(14,19,27,.88);color:#dfe6f2;cursor:pointer;display:none;align-items:center;justify-content:center;padding:0;z-index:3}
  .emr-iconbtn:hover{background:rgba(40,52,70,.95)}
  .emr-slot:hover .emr-iconbtn{display:flex}
  .emr-edit{right:4px;bottom:4px}
  .emr-del{right:30px;bottom:4px}
  .emr-modal{position:fixed;inset:0;background:rgba(5,8,14,.72);z-index:99999;display:flex;align-items:center;justify-content:center;user-select:none}
  .emr-box{background:#161b24;border:1px solid #34405a;border-radius:10px;color:#dfe6f2;padding:12px;
    display:flex;flex-direction:column;gap:8px;width:min(1080px,92vw);aspect-ratio:4/3;max-height:90vh;
    min-width:0;overflow:auto}
  .emr-box h3{margin:0;font-size:13px;color:#eaf0fa;display:flex;align-items:center;gap:8px}
  .emr-box h3 .emr-x{margin-left:auto}
  .emr-modal img{pointer-events:none;-webkit-user-drag:none}
  .emr-tbar{display:flex;align-items:center;gap:6px;flex-wrap:wrap}
  .emr-tbar label{display:flex;align-items:center;gap:4px;color:#9aa6ba;white-space:nowrap}
  .emr-tbar input[type=number]{width:58px;height:22px;background:#0d1118;border:1px solid #333d50;border-radius:4px;color:#e5ecf8;padding:1px 4px}
  .emr-tbar input[type=text]{width:70px;height:22px;background:#0d1118;border:1px solid #333d50;border-radius:4px;color:#e5ecf8;padding:1px 4px}
  .emr-tbar select{height:24px;background:#0d1118;border:1px solid #333d50;border-radius:4px;color:#e5ecf8}
  .emr-tbar input[type=checkbox]{accent-color:#43d9d1}
  .emr-canvaswrap{background:#0b0e14;border:1px solid #2a3242;border-radius:6px;display:flex;align-items:center;justify-content:center;min-height:300px;position:relative;overflow:hidden}
  .emr-canvaswrap canvas{max-width:100%;cursor:crosshair}
  .emr-foot{display:flex;gap:8px;justify-content:flex-end}
  .emr-pbtn{background:#2a4b7a;border-color:#4e7fc0}
  .emr-tl{position:relative;border:1px solid #2a3242;border-radius:6px;overflow-x:auto;overflow-y:hidden;background:#0b0e14}
  .emr-tl-inner{position:relative;height:150px}
  .emr-ruler{position:relative;height:18px;border-bottom:1px solid #2c3443;background:#10151d}
  .emr-tick{position:absolute;bottom:0;width:1px;height:6px;background:#4d5870}
  .emr-tick.major{height:11px;background:#77839b}
  .emr-tick span{position:absolute;left:3px;top:-10px;font-size:9px;color:#8490a4;white-space:nowrap}
  .emr-thumbs{position:relative;height:56px;display:flex;background:#0d1119}
  .emr-thumbs img{height:100%;object-fit:contain;background:#000;flex-shrink:0}
  .emr-wavecv{position:relative;height:52px}
  .emr-wavecv canvas{position:absolute;inset:0;width:100%;height:100%}
  .emr-sel{position:absolute;top:0;height:100%;background:rgba(80,170,255,.28);border-left:2px solid #57a8ff;border-right:2px solid #57a8ff;cursor:grab;z-index:6}
  .emr-sel .h{position:absolute;top:0;width:9px;height:100%;cursor:ew-resize;background:transparent}
  .emr-sel .h.l{left:-5px}.emr-sel .h.r{right:-5px}
  .emr-shade{position:absolute;top:0;height:100%;background:rgba(0,0,0,.5);z-index:5;pointer-events:none}
  .emr-playhead{position:absolute;top:0;bottom:0;width:2px;background:#ff737d;z-index:9;pointer-events:none}
  .emr-cutmark{position:absolute;top:0;width:1px;height:100%;background:#ffb340;opacity:.8;z-index:4;pointer-events:none}
  .emr-menu{position:fixed;background:#1d2430;border:1px solid #3a4558;border-radius:6px;z-index:100000;
    padding:4px;min-width:130px;box-shadow:0 6px 18px rgba(0,0,0,.5)}
  .emr-menu div{padding:5px 10px;border-radius:4px;cursor:pointer;color:#dce5f5}
  .emr-menu div:hover{background:#2b3648}
  .emr-segbar{position:relative;height:14px;background:#0d1119;border-top:1px solid #2c3443}
  .emr-segbar .seg{position:absolute;top:1px;height:12px;background:#1c2736;
    border-right:1px solid #46566e;cursor:pointer}
  .emr-segbar .seg:hover{background:#27354a}
  .emr-segbar .seg.on{background:#2a4b7a;outline:1px solid #57a8ff}
  .emr-sel,.emr-shade{transition:opacity .15s}
  /* --- AVEditor v3：布局 / 播放组 / 分段轨道 --- */
  .emr-tbar{flex-wrap:nowrap;overflow-x:auto;scrollbar-width:thin}
  .emr-tbar .emr-btn{height:34px;padding:0 12px}
  .emr-tbar input[type=number]{height:30px}
  .emr-tbar select{height:30px}
  .emr-tbar label{gap:6px}
  .emr-transport{display:flex;align-items:center;justify-content:center;gap:10px;flex-shrink:0}
  .emr-transport .emr-btn{height:48px;width:52px;padding:0;justify-content:center}
  .emr-transport .emr-btn svg{width:22px;height:22px}
  .emr-pvcol{flex:1;min-height:0;display:flex;flex-direction:column;align-items:center;gap:4px;max-width:100%}
  .emr-pvimg{flex:1;min-height:0;display:flex;align-items:center;justify-content:center;width:100%}
  .emr-pvimg img{max-width:100%;max-height:100%;object-fit:contain;border-radius:4px}
  .emr-pvinfo{display:flex;justify-content:space-between;gap:12px;color:#9aa6ba;font-size:12px;white-space:nowrap;max-width:100%}
  .emr-track{position:relative;height:64px;background:#0d1119;border-top:1px solid #2c3443;border-bottom:1px solid #262d3a;overflow:hidden}
  .emr-segblk{position:absolute;top:4px;bottom:4px;border:1px solid #35557c;border-radius:4px;background:#1b2a3d;overflow:hidden;cursor:pointer}
  .emr-segblk.selected{border-color:#b9ddff;box-shadow:0 0 0 1px rgba(87,168,255,.55);background:#22406b}
  .emr-segblk .lbl{position:absolute;left:5px;top:2px;z-index:2;color:#fff;font-weight:700;font-size:10px;text-shadow:0 1px 2px #000;pointer-events:none}
  .emr-segblk .ths{display:flex;height:100%}
  .emr-segblk .ths img{flex:1 1 0;min-width:0;height:100%;object-fit:cover;opacity:0;transition:opacity .2s}
  .emr-segblk .ths img.ld{opacity:1}
  .emr-tl-inner.trimhov .emr-segblk{cursor:ew-resize}
  .emr-tl-inner.marking .emr-track,.emr-tl-inner.marking .emr-segblk{cursor:crosshair}
  // .emr-tl-inner{height:140px}
  .emr-tl-inner{height:auto}
  .emr-track.audio{height:48px;background:#111720;border-bottom:none}
  .emr-waveblk{position:absolute;top:3px;bottom:3px;border:1px solid rgba(86,136,236,.35);border-radius:3px;overflow:hidden;pointer-events:none}
  .emr-waveblk.selected{border-color:#43d9d1;box-shadow:0 0 0 1px rgba(67,217,209,.4)}
  .emr-waveblk canvas{position:absolute;inset:0;width:100%;height:100%}
  .emr-waveblk .lbl{position:absolute;left:5px;top:2px;z-index:2;color:#9fd48f;font-weight:700;font-size:10px;text-shadow:0 1px 2px #000}
  .emr-insert{position:absolute;top:0;width:2px;height:100%;background:#43d9d1;box-shadow:0 0 6px #43d9d1;z-index:12;pointer-events:none}
  .emr-tl-inner.reordering,.emr-tl-inner.reordering .emr-segblk{cursor:grabbing !important}
  .emr-pvimg{align-items:flex-end}          
  .emr-pvcol{gap:6px}                       
  .emr-pvright{display:inline-flex;gap:14px;align-items:baseline}
  .emr-transport + .emr-tbar{margin-top:16px} 
  .emr-tl + .emr-transport{margin-top:8px}    
  .emr-playhead{z-index:35;cursor:ew-resize}
  .emr-playhead::after{content:"";position:absolute;left:-6px;right:-6px;top:0;bottom:0}  /* 14px 热区 */

  `;
  document.head.appendChild(st);
}


function drawWaveCanvas(cv, pts) {
  const dpr = window.devicePixelRatio || 1;
  const w = cv.clientWidth || cv.parentElement?.clientWidth || 100;
  const h = cv.clientHeight || 34;
  cv.width = Math.max(1, Math.round(w * dpr));
  cv.height = Math.max(1, Math.round(h * dpr));
  const ctx = cv.getContext("2d");
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, w, h);
  if (!pts || !pts.length) return;
  const n = pts.length, mid = h / 2, amp = h / 2 - 1;
  ctx.beginPath();
  for (let i = 0; i < n; i++) { const x = (i / (n - 1)) * w, y = mid - pts[i] * amp; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
  for (let i = n - 1; i >= 0; i--) { const x = (i / (n - 1)) * w, y = mid + pts[i] * amp; ctx.lineTo(x, y); }
  ctx.closePath();
  ctx.fillStyle = "rgba(90,173,90,.45)";
  ctx.fill();
  ctx.strokeStyle = "#5aad5a";
  ctx.lineWidth = 1;
  ctx.stroke();
}

const previewUrl = (p, f, s) => `/emr/preview?p=${encodeURIComponent(p)}&f=${f}&s=${s}`;
const audioUrl   = (p) => `/emr/audio?p=${encodeURIComponent(p)}`;

/* ================= 图像编辑器 ================= */
class ImageEditor {
  static open(mat, slot, onApply) {
    const edit = slot.edit;
    const ov = document.createElement("div");
    ov.className = "emr-modal";
    ov.innerHTML = `
      <div class="emr-box">
        <h3>Edit Image · ${mat.path.split(/[\\/]/).pop()} <button class="emr-btn emr-x">✕</button></h3>
        <div class="emr-tbar">
          <button class="emr-btn" data-m="crop">Crop</button>
          <label title="crop step (px multiple)">div by<input type="number" data-f="div" value="${edit.div_by}" min="1" step="1"></label>
          <button class="emr-btn" data-a="clearcrop" title="Remove crop box entirely">Clear crop</button>
          <span style="width:14px"></span>
          <label>Out W<input type="number" data-f="ow" min="0" step="2" value="${edit.out_w || 0}"></label>
          <label>Out H<input type="number" data-f="oh" min="0" step="2" value="${edit.out_h || 0}"></label>
          <label><input type="checkbox" data-f="olock" checked>Lock ratio</label>
          <button class="emr-btn" data-a="resetsize" title="Reset out size">⟳</button>
          <span data-whtxt title="Crop size (source size when no crop)" style="margin-left:auto;color:#9aa6ba;white-space:nowrap;font-size:11px"></span>
        </div>
        <div class="emr-tbar" data-paintbar>
          <button class="emr-btn" data-m="paint">Paint</button>
          <span data-paintctl style="display:inline-flex;align-items:center;gap:6px;transition:opacity .15s">
            <label>Color<input type="color" data-f="color" value="#ff3355" style="width:34px;height:24px;padding:0"></label>
            <label>Size<input type="range" data-f="size" min="2" max="80" value="18" style="width:90px"></label>
            <button class="emr-btn" data-a="box" title="Draw rectangle (Shift = square)">Box</button>
            <button class="emr-btn" data-a="circle" title="Draw ellipse (Shift = circle)">Circle</button>
            <label title="Outline (stroke) instead of filled"><input type="checkbox" data-f="outline">Outline</label>
            <button class="emr-btn" data-a="erase">Eraser</button>
            <button class="emr-btn" data-a="undo">Undo</button>
            <button class="emr-btn" data-a="clearpaint">Clear paint</button>
          </span>
        </div>
        <div class="emr-canvaswrap" style="flex:1;min-height:240px"><canvas></canvas></div>
        <div class="emr-foot">
          <button class="emr-btn" data-a="cancel">Cancel</button>
          <button class="emr-btn emr-pbtn" data-a="apply">Apply</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    const q = (s) => ov.querySelector(s);
    const canvas = q("canvas"), wrap = q(".emr-canvaswrap");
    const whEl = q("[data-whtxt]"), paintCtl = q("[data-paintctl]");
    // ---- paint 模式圆环光标 ----
    const ring = document.createElement("div");
    ring.style.cssText = "position:absolute;border:1px solid #fff;border-radius:50%;pointer-events:none;display:none;transform:translate(-50%,-50%);box-shadow:0 0 0 1px rgba(0,0,0,.6);z-index:5";
    wrap.appendChild(ring);
    let lastMouseEv = null;
    function updateRing(e) {
      lastMouseEv = e;
      if (mode !== "paint" || shapeMode) { ring.style.display = "none"; return; }
      const s = Math.max(2, +q('[data-f="size"]').value * scale);
      ring.style.width = ring.style.height = s + "px";
      const wr = wrap.getBoundingClientRect();
      ring.style.left = (e.clientX - wr.left) + "px";
      ring.style.top = (e.clientY - wr.top) + "px";
      ring.style.borderStyle = eraseMode ? "dashed" : "solid";
      ring.style.display = "block";
    }
    function hideRing() { ring.style.display = "none"; }
	
    function applyCursor() { 
      canvas.style.cursor = (mode !== "paint") ? "" : (shapeMode ? "crosshair" : "none");
    }
	
    wrap.addEventListener("pointermove", (e) => { if (!painting) updateRing(e); });
    wrap.addEventListener("pointerleave", hideRing);
    q('[data-f="size"]').addEventListener("input", () => { if (lastMouseEv) updateRing(lastMouseEv); });
    const img = new Image();
    let W = 0, H = 0, scale = 1, mode = "crop";
    let rect = edit.crop ? { x: edit.crop[0], y: edit.crop[1], w: edit.crop[2], h: edit.crop[3] } : null;
    let drag = null, painting = false, eraseMode = false, lastPt = null;
    let shapeMode = null, lineStroke = false, strokeStart = null, strokeSnap = null; 
    let strokesState = edit.strokes_file ? "clean" : "empty";
    let syncedW = 0, syncedH = 0;
    const strokes = document.createElement("canvas");
    const undoStack = [];
    const snapV = (v, d) => Math.max(0, Math.round(v / d) * d);
    const snapQ = (v, d) => Math.round(v / d) * d;
    const divNow = () => Math.max(1, parseInt(q('[data-f="div"]').value) || 32);
    img.onload = () => {
      W = img.naturalWidth; H = img.naturalHeight;
      strokes.width = W; strokes.height = H;
      if (rect) {
        const d0 = divNow();
        rect.w = Math.max(d0, Math.round(rect.w / d0) * d0);
        rect.h = Math.max(d0, Math.round(rect.h / d0) * d0);
        rect.x = Math.max(0, Math.min(rect.x, W - rect.w));
        rect.y = Math.max(0, Math.min(rect.y, H - rect.h));
      }
      syncedW = rect ? rect.w : W;
      syncedH = rect ? rect.h : H;
      if (edit.strokes_file) {
        const p2 = new Image();
        p2.onload = () => { strokes.getContext("2d").drawImage(p2, 0, 0, W, H); redrawPaint(); };
        p2.src = `${previewUrl(edit.strokes_file, -1, 4096)}&alpha=1`;
      }
      fitCanvas();
      syncInputs();
      outFromRectIfUnset();
      redraw();
    };
    img.src = previewUrl(mat.path, -1, 4096);
    function fitCanvas() {
      const mw = Math.max(200, wrap.clientWidth - 8), mh = Math.max(200, wrap.clientHeight - 8);
      scale = Math.min(mw / W, mh / H, 1);
      canvas.width = Math.round(W * scale);
      canvas.height = Math.round(H * scale);
    }
    function redraw() {
      const ctx = canvas.getContext("2d");
      ctx.setTransform(1, 0, 0, 1, 0, 0);
      ctx.clearRect(0, 0, canvas.width, canvas.height);
      ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
      ctx.drawImage(strokes, 0, 0, canvas.width, canvas.height);
      if (rect) {
        const d = divNow();
        const sx = rect.x * scale, sy = rect.y * scale;
        const sw = Math.max(d, Math.round(rect.w / d) * d) * scale;
        const sh = Math.max(d, Math.round(rect.h / d) * d) * scale;
        ctx.fillStyle = "rgba(0,0,0,.45)";
        ctx.fillRect(0, 0, canvas.width, sy);
        ctx.fillRect(0, sy + sh, canvas.width, Math.max(0, canvas.height - sy - sh));
        ctx.fillRect(0, sy, Math.max(0, sx), sh);
        ctx.fillRect(sx + sw, sy, Math.max(0, canvas.width - sx - sw), sh);
        ctx.strokeStyle = "#57a8ff";
        ctx.lineWidth = 1.5;
        ctx.strokeRect(sx, sy, sw, sh);
      }
    }
    function redrawPaint() { redraw(); }
    function syncInputs() {
      const d = divNow();
      const r = rect || { w: W, h: H };
      whEl.textContent = `W ${Math.max(d, Math.round(r.w / d) * d)} × H ${Math.max(d, Math.round(r.h / d) * d)}`;
    }
    function outFromRect() {
      if (!q('[data-f="olock"]').checked) return;
      const d = divNow();
      if (rect) {
        q('[data-f="ow"]').value = Math.max(d, Math.round(rect.w / d) * d);
        q('[data-f="oh"]').value = Math.max(d, Math.round(rect.h / d) * d);
      } else {
        q('[data-f="ow"]').value = W;
        q('[data-f="oh"]').value = H;
      }
    }
    function outFromRectIfUnset() {
      if (!q('[data-f="olock"]').checked) return;
      const ow = Math.round(+q('[data-f="ow"]').value || 0), oh = Math.round(+q('[data-f="oh"]').value || 0);
      if (ow > 0 && oh > 0) return;
      outFromRect();
    }
    function maybeSyncOut() {
      const cw = rect ? rect.w : W, ch = rect ? rect.h : H;
      if (!cw || !ch) return;
      if (!syncedW || !syncedH || Math.abs(cw * syncedH - syncedW * ch) > 1e-6) {
        outFromRect();
        syncedW = cw; syncedH = ch;
      }
    }
    function syncPaintbar() {
      const on = mode === "paint";
      paintCtl.style.opacity = on ? "1" : ".45";
      paintCtl.style.pointerEvents = on ? "auto" : "none";
    }
    /* ---- crop 边缘/角落手柄 ---- */
    function edgeAt(p) {
      if (!rect) return null;
      const tol = Math.max(2, 8 / scale);
      if (p.x < rect.x - tol || p.x > rect.x + rect.w + tol || p.y < rect.y - tol || p.y > rect.y + rect.h + tol) return null;
      const nearL = Math.abs(p.x - rect.x) <= tol;
      const nearR = Math.abs(p.x - (rect.x + rect.w)) <= tol;
      const nearT = Math.abs(p.y - rect.y) <= tol;
      const nearB = Math.abs(p.y - (rect.y + rect.h)) <= tol;
      const h = nearL ? "l" : nearR ? "r" : "";
      const v = nearT ? "t" : nearB ? "b" : "";
      return (h || v) ? { h, v } : null;
    }
    function cursorFor(ed) {
      if (ed.h === "l" && ed.v === "t" || ed.h === "r" && ed.v === "b") return "nwse-resize";
      if (ed.h === "r" && ed.v === "t" || ed.h === "l" && ed.v === "b") return "nesw-resize";
      if (ed.h) return "ew-resize";
      return "ns-resize";
    }
    function applyResize(p, dg) {
      const d = divNow(), o = dg.orig;
      let x0 = o.x, y0 = o.y, x1 = o.x + o.w, y1 = o.y + o.h;
      if (dg.ed.h === "l") x0 = Math.min(Math.max(0, snapQ(p.x, d)), x1 - d);
      else if (dg.ed.h === "r") x1 = Math.max(Math.min(W, snapQ(p.x, d)), x0 + d);
      if (dg.ed.v === "t") y0 = Math.min(Math.max(0, snapQ(p.y, d)), y1 - d);
      else if (dg.ed.v === "b") y1 = Math.max(Math.min(H, snapQ(p.y, d)), y0 + d);
      rect = { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
    }
    /* ---- 参数 ---- */
    q('[data-f="div"]').onchange = () => syncInputs();
    q('[data-f="ow"]').onchange = () => {
      const ow = Math.max(0, Math.round(+q('[data-f="ow"]').value || 0));
      q('[data-f="ow"]').value = ow;
      if (q('[data-f="olock"]').checked && ow > 0) {
        const rw = rect ? rect.w : W, rh = rect ? rect.h : H;
        if (rw > 0) q('[data-f="oh"]').value = Math.max(2, Math.round(ow * rh / rw / 2) * 2);
      }
    };
    q('[data-f="oh"]').onchange = () => {
      const oh = Math.max(0, Math.round(+q('[data-f="oh"]').value || 0));
      q('[data-f="oh"]').value = oh;
      if (q('[data-f="olock"]').checked && oh > 0) {
        const rw = rect ? rect.w : W, rh = rect ? rect.h : H;
        if (rh > 0) q('[data-f="ow"]').value = Math.max(2, Math.round(oh * rw / rh / 2) * 2);
      }
    };
    q('[data-f="olock"]').onchange = () => { if (q('[data-f="olock"]').checked) outFromRect(); };
    q('[data-a="resetsize"]').onclick = () => {
      const d = divNow();
      if (rect) {
        q('[data-f="ow"]').value = Math.max(d, Math.round(rect.w / d) * d);
        q('[data-f="oh"]').value = Math.max(d, Math.round(rect.h / d) * d);
        syncedW = rect.w; syncedH = rect.h;
      } else {
        q('[data-f="ow"]').value = W;
        q('[data-f="oh"]').value = H;
        syncedW = W; syncedH = H;
      }
    };
    q('[data-a="clearcrop"]').onclick = () => { rect = null; syncInputs(); maybeSyncOut(); redraw(); };
    ov.querySelectorAll("[data-m]").forEach(b => b.onclick = () => {
      mode = b.dataset.m;
      ov.querySelectorAll("[data-m]").forEach(x => x.classList.toggle("emr-pbtn", x === b));
      syncPaintbar();
      applyCursor();
      hideRing();
      redraw();
      if (mode === "paint") redrawPaint();
    });
    q('[data-m="crop"]').classList.add("emr-pbtn");
    syncPaintbar();
    q('[data-a="erase"]').onclick = (e) => { eraseMode = !eraseMode; e.currentTarget.classList.toggle("emr-pbtn", eraseMode); };
    // ---- 形状工具（box / circle ----
    const setShape = (s) => {
      shapeMode = (shapeMode === s) ? null : s;
      ov.querySelectorAll("[data-a='box'],[data-a='circle']").forEach(b => b.classList.toggle("emr-pbtn", b.dataset.a === shapeMode));
	  applyCursor();
	  hideRing();
    };
    q('[data-a="box"]').onclick = () => setShape("box");
    q('[data-a="circle"]').onclick = () => setShape("circle");
    q('[data-a="undo"]').onclick = () => { const last = undoStack.pop(); if (last) strokes.getContext("2d").putImageData(last, 0, 0); strokesState = "dirty"; redrawPaint(); };
    q('[data-a="clearpaint"]').onclick = () => { strokes.getContext("2d").clearRect(0, 0, W, H); strokesState = "cleared"; undoStack.length = 0; redraw(); };
    const pos = (e) => { const r = canvas.getBoundingClientRect(); return { x: (e.clientX - r.left) / scale, y: (e.clientY - r.top) / scale }; };
    const inRect = (p) => rect && p.x >= rect.x && p.x <= rect.x + rect.w && p.y >= rect.y && p.y <= rect.y + rect.h;
    function seg(a, b) {
      const ctx = strokes.getContext("2d");
      ctx.save();
      if (eraseMode) ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = q('[data-f="color"]').value;
      ctx.lineWidth = +q('[data-f="size"]').value;
      ctx.lineCap = "round";
      ctx.lineJoin = "round";
      ctx.beginPath();
      ctx.moveTo(a.x, a.y);
      ctx.lineTo(b.x + 0.01, b.y + 0.01);
      ctx.stroke();
      ctx.restore();
      strokesState = "dirty";
      redrawPaint();
    }
    // ---- ★ 形状 / 直线绘制（落笔时拍底片，move 中恢复底片 + 画预览）----
    const shapeOpts = (ctx) => {
      if (eraseMode) ctx.globalCompositeOperation = "destination-out";
      ctx.strokeStyle = ctx.fillStyle = q('[data-f="color"]').value;
      ctx.lineWidth = Math.max(1, +q('[data-f="size"]').value);
    };
    const sqConstraint = (a, b) => {  
      const dx = b.x - a.x, dy = b.y - a.y;
      const m = Math.max(Math.abs(dx), Math.abs(dy));
      return { x: a.x + Math.sign(dx) * m, y: a.y + Math.sign(dy) * m };
    };
    function drawBox(a, b, fill) {
      const ctx = strokes.getContext("2d");
      ctx.save(); shapeOpts(ctx);
      ctx.lineJoin = "miter";                    
      const x = Math.min(a.x, b.x), y = Math.min(a.y, b.y), w = Math.abs(b.x - a.x), h = Math.abs(b.y - a.y);
      fill ? ctx.fillRect(x, y, w, h) : ctx.strokeRect(x, y, w, h);
      ctx.restore(); strokesState = "dirty";
    }
    function drawCircle(a, b, fill) {
      const ctx = strokes.getContext("2d");
      ctx.save(); shapeOpts(ctx);
      ctx.beginPath();
      ctx.ellipse((a.x + b.x) / 2, (a.y + b.y) / 2, Math.abs(b.x - a.x) / 2, Math.abs(b.y - a.y) / 2, 0, 0, Math.PI * 2);
      fill ? ctx.fill() : ctx.stroke();
      ctx.restore(); strokesState = "dirty";
    }
    function drawLineSeg(a, b) {
      const ctx = strokes.getContext("2d");
      ctx.save(); shapeOpts(ctx);
      ctx.lineCap = "round";
      ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x + 0.01, b.y + 0.01); ctx.stroke();
      ctx.restore(); strokesState = "dirty";
    }
    canvas.onpointerdown = (e) => {
      if (mode === "crop") {
        const d = divNow(), p = pos(e);
        const ed = rect && edgeAt(p);
        if (ed) drag = { kind: "resize", ed, orig: { ...rect } };
        else if (rect && inRect(p)) drag = { kind: "move", dx: p.x - rect.x, dy: p.y - rect.y };
        else drag = { kind: "new", sx: snapV(p.x, d), sy: snapV(p.y, d), d };
        canvas.setPointerCapture(e.pointerId);
      } else {
        painting = true;
        lineStroke = false;
        strokeStart = pos(e);                    
        lastPt = strokeStart;
        canvas.setPointerCapture(e.pointerId);
        if (undoStack.length >= 15) undoStack.shift();
        undoStack.push(strokes.getContext("2d").getImageData(0, 0, W, H));
        strokeSnap = strokes.getContext("2d").getImageData(0, 0, W, H); // 
        if (shapeMode) {
        } else if (e.shiftKey) {
          lineStroke = true;                    
        } else {
          seg(lastPt, lastPt);
        }
        updateRing(e);
      }
    };
    canvas.onpointermove = (e) => {
      if (mode === "crop") {
        const p = pos(e);
        if (drag) {
          if (drag.kind === "move") {
            rect.x = Math.round(Math.max(0, Math.min(W - rect.w, p.x - drag.dx)));
            rect.y = Math.round(Math.max(0, Math.min(H - rect.h, p.y - drag.dy)));
            syncInputs(); redraw();
          } else if (drag.kind === "resize") {
            applyResize(p, drag);
            syncInputs(); maybeSyncOut(); redraw();
          } else {
            const d = drag.d;
            const x = snapV(Math.min(drag.sx, p.x), d), y = snapV(Math.min(drag.sy, p.y), d);
            const w = Math.max(d, Math.round(Math.abs(p.x - drag.sx) / d) * d);
            const h = Math.max(d, Math.round(Math.abs(p.y - drag.sy) / d) * d);
            rect = { x, y, w: Math.min(w, W - x), h: Math.min(h, H - y) };
            syncInputs(); maybeSyncOut(); redraw();
          }
        } else {
          const ed = rect && edgeAt(p);
          canvas.style.cursor = ed ? cursorFor(ed) : (inRect(p) ? "move" : "crosshair");
        }
      } else if (painting) {
        const p = pos(e);
        const sctx = strokes.getContext("2d");
        if (shapeMode) {                         
          const b = e.shiftKey ? sqConstraint(strokeStart, p) : p;
          sctx.putImageData(strokeSnap, 0, 0);
          if (shapeMode === "box") drawBox(strokeStart, b, !q('[data-f="outline"]').checked);
          else drawCircle(strokeStart, b, !q('[data-f="outline"]').checked);
          redrawPaint();
        } else if (lineStroke || e.shiftKey) {   
          if (!e.shiftKey) {                     
            lineStroke = false; painting = false; strokeSnap = null;
          } else {
            lineStroke = true;
            sctx.putImageData(strokeSnap, 0, 0);
            drawLineSeg(strokeStart, p);
            redrawPaint();
          }
        } else {
          seg(lastPt, p);
          lastPt = p;
        }
        updateRing(e);
      }
    };
    canvas.onpointerup = () => {
      drag = null; painting = false; lineStroke = false; strokeSnap = null; strokeStart = null; lastPt = null;
    };
    const close = () => ov.remove();
    q(".emr-x").onclick = close;
    q('[data-a="cancel"]').onclick = close;
    q('[data-a="apply"]').onclick = async () => {
      const d = divNow();
      const out = { ...edit, div_by: d,
        out_w: Math.max(0, Math.round(+q('[data-f="ow"]').value || 0)),
        out_h: Math.max(0, Math.round(+q('[data-f="oh"]').value || 0)),
        paint_file: null };
      delete out.lock_ratio;
      out.crop = rect ? [rect.x, rect.y, rect.w, rect.h] : null;
      if (strokesState === "dirty") {
        const blob = await new Promise(res => strokes.toBlob(res, "image/png"));
        const fd = new FormData();
        fd.append("paint_file", blob, "strokes.png");
        const pj = await (await fetch("/element_multi_ref/save_paint", { method: "POST", body: fd })).json();
        out.strokes_file = pj.path || null;
      } else if (strokesState === "cleared" || strokesState === "empty") out.strokes_file = null;
      else out.strokes_file = edit.strokes_file || null;
      onApply(out);
      close();
    };
  }
}



/* ================= 音视频编辑器 v3 ================= */
const PB = {
  start:   '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="5" width="2.4" height="14"/><polygon points="21,5 21,19 13,12"/><polygon points="13,5 13,19 5,12"/></svg>',
  segstart:'<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="5" y="5" width="2.4" height="14"/><polygon points="20,5 20,19 9.5,12"/></svg>',
  play:    '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><polygon points="7,4.5 7,19.5 20,12"/></svg>',
  stop:    '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="6.5" y="6.5" width="11" height="11"/></svg>',
  playall: '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><rect x="3" y="6" width="8" height="12" opacity=".35"/><polygon points="13,5 13,19 22,12"/></svg>',
  segend:  '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><polygon points="4,5 4,19 14.5,12"/><rect x="16.6" y="5" width="2.4" height="14"/></svg>',
  end:     '<svg width="15" height="15" viewBox="0 0 24 24" fill="currentColor"><polygon points="3,5 3,19 11,12"/><polygon points="11,5 11,19 18,12"/><rect x="18.6" y="5" width="2.4" height="14"/></svg>',
};
class AVEditor {
  static open(mat, slot, onApply) {
    const edit = slot.edit, media = mat.media;
    const isVideo = mat.kind === "video";
    const srcFps = isVideo ? (media.fps || 24) : 1;
    const total = isVideo ? Math.max(1, media.total_frames || 1) : Math.max(0.01, media.duration || 1);
    const toSec = (f) => isVideo ? f / srcFps : f;
    const fromSec = (s) => isVideo ? s * srcFps : s;
    const MIN = isVideo ? 2 : 0.05;            // 分段最小长度（帧/秒），同 ESD MIN_SEG_FRAMES
    const minLen = () => isVideo ? 1 : 0.01;
    const ov = document.createElement("div"); ov.className = "emr-modal";
    ov.innerHTML = `
      <div class="emr-box" ${isVideo ? "" : 'style="aspect-ratio:auto;height:auto;max-height:88vh"'}>
        <h3>Edit ${isVideo ? "Video" : "Audio"} · ${mat.path.split(/[\\/]/).pop()} <button class="emr-btn emr-x">✕</button></h3>
        ${isVideo ? `
        <div class="emr-pvcol">
          <div class="emr-pvimg"><img draggable="false"></div>
          <div class="emr-pvinfo"><span data-t></span><span class="emr-pvright"><span data-q style="color:#43d9d1"></span><span data-s style="color:#f3af4e"></span></span></div>
        </div>
        <div class="emr-transport">
          <button class="emr-btn" data-a="start" title="Timeline start">${PB.start}</button>
          <button class="emr-btn" data-a="segstart" title="Start of current segment">${PB.segstart}</button>
          <button class="emr-btn" data-a="play" title="Play current segment">${PB.play}</button>
          <button class="emr-btn" data-a="playall" title="Play all segments in order">${PB.playall}</button>
          <button class="emr-btn" data-a="segend" title="End of current segment">${PB.segend}</button>
          <button class="emr-btn" data-a="end" title="Timeline end">${PB.end}</button>
        </div>` : `
        <div class="emr-pvinfo" style="width:100%"><span data-t></span><span class="emr-pvright"><span data-q style="color:#43d9d1"></span><span data-s style="color:#f3af4e"></span></span></div>`}
        <div class="emr-tbar">
          <button class="emr-btn" data-a="fit">Fit</button>
          <button class="emr-btn" data-a="full">Full</button>
          <label title="Blue box = final trim. Off → selected segment(s) are used"><input type="checkbox" data-f="usesel">Use selection</label>
          <button class="emr-btn" data-a="detect">Auto Split</button>
          <label>Thr<input type="number" data-f="thr" value="40" step="1" style="width:56px"></label>
          <button class="emr-btn" data-a="manual" title="Click track to split (M)">Manual</button>
          ${isVideo ? '<label><input type="checkbox" data-f="snapcut" ' + (edit.snap_cut ? "checked" : "") + '>Snap</label>' : ""}
		  <button class="emr-btn" data-a="clearedit" title="Reset all edits to defaults">Clear</button>
        </div>
        <div class="emr-tbar">
          <label>Preset<select data-f="preset">${PRESETS.map((p, i) => `<option value="${i}">${p.name}</option>`).join("")}</select></label>
          <label>div by<input type="number" data-f="div" value="${edit.div_by}" min="1" step="1"></label>
          <label>a<input type="number" data-f="a" value="${edit.a}" min="0" step="1"></label>
          ${isVideo ? `<label>FPS<input type="number" data-f="fps" value="${edit.fps || 0}" min="0" step="0.5" title="0 = source fps"></label>
          <label>Out W<input type="number" data-f="ow" min="0" step="2"></label>
          <label>Out H<input type="number" data-f="oh" min="0" step="2"></label>
          <label><input type="checkbox" data-f="olock" checked>Lock</label>
          <button class="emr-btn" data-a="resetsize" title="Reset out size">⟳</button>`
          : `<label title="Quantize to a+n·div at Ref FPS"><input type="checkbox" data-f="quant" ${edit.quant ? "checked" : ""}>Quantize</label>
          <label>Ref FPS<input type="number" data-f="rfps" value="${edit.ref_fps || 24}" min="1" step="1"></label>`}
          <label>Zoom<input type="range" data-f="zoom" min="0.05" max="16" step="0.05" value="1" style="width:110px"></label>
        </div>
        <div class="emr-tl"><div class="emr-tl-inner">
          <div class="emr-ruler"></div>
          <div class="emr-track"></div>
          <div class="emr-track audio"></div>
          <div class="emr-shade" data-sh="l"></div><div class="emr-shade" data-sh="r"></div>
          <div class="emr-sel"><div class="h l"></div><div class="h r"></div></div>
          <div class="emr-playhead"></div>
        </div></div>
		
        ${isVideo ? "" : `
        <div class="emr-transport">
          <button class="emr-btn" data-a="start" title="Timeline start">${PB.start}</button>
          <button class="emr-btn" data-a="segstart" title="Start of current segment">${PB.segstart}</button>
          <button class="emr-btn" data-a="play" title="Play current segment">${PB.play}</button>
          <button class="emr-btn" data-a="playall" title="Play all segments in order">${PB.playall}</button>
          <button class="emr-btn" data-a="segend" title="End of current segment">${PB.segend}</button>
          <button class="emr-btn" data-a="end" title="Timeline end">${PB.end}</button>
        </div>`}

		
        <div class="emr-foot">
          <button class="emr-btn" data-a="cancel">Cancel</button>
          <button class="emr-btn emr-pbtn" data-a="apply">Apply</button>
        </div>
      </div>`;
    document.body.appendChild(ov);
    const q = (s) => ov.querySelector(s);
    const inner = q(".emr-tl-inner"), track = q(".emr-track"), atrack = q(".emr-track.audio"),
      selEl = q(".emr-sel"), phEl = q(".emr-playhead"), timeEl = q("[data-t]"), qEl = q("[data-q]"),
      sEl = q("[data-s]"), shL = q('[data-sh="l"]'), shR = q('[data-sh="r"]');
    let div = Math.max(1, +q('[data-f="div"]').value || 17);
    let a = Math.max(0, +q('[data-f="a"]').value || 0);
    let zoom = 1, baseZoom = 60, pxPerSec = 60, innerW = 600;
    // ---- 状态恢复（#4）----
    let cuts = Array.isArray(edit.cuts) ? edit.cuts.map(Number) : [];
    if (isVideo) cuts = cuts.map(c => Math.round(c));
    cuts = [...new Set(cuts)].filter(c => c > 0 && c < total).sort((x, y) => x - y);
    let order = []; let selIdx = Array.isArray(edit.sel_idx) ? edit.sel_idx.filter(i => i >= 0) : [];
    let selAnchor = null;
    let sel = { s: Math.max(0, Math.min(total, (edit.sel?.[0] ?? edit.trim?.[0]) ?? 0)),
                e: Math.min(total, Math.max(0, (edit.sel?.[1] ?? edit.trim?.[1]) ?? total)) };
    if (!(sel.e > sel.s)) sel = { s: 0, e: total };
    if (isVideo) { sel.s = Math.round(sel.s); sel.e = Math.round(sel.e); }
    q('[data-f="usesel"]').checked = edit.usesel !== false;
    let marking = false, trimDrag = null, pendSel = null, reorder = null, insertEl = null;
    let playing = false, playAllMode = false, playQ = [], playFrame = edit.playhead ?? sel.s,
        raf = 0, acc = 0, lastT = 0, seq = 0, probe = null, lastPrevAt = 0;
	let audioMaster = false;
    if (isVideo) playFrame = Math.round(playFrame);
    playFrame = Math.max(0, Math.min(total - minLen(), playFrame));

    const outFps = () => isVideo ? ((+q('[data-f="fps"]').value || 0) || srcFps) : (+q('[data-f="rfps"]').value || 24);
    const lenToOut = (L) => isVideo ? L * outFps() / srcFps : L * outFps();
    const outToLen = (F) => isVideo ? F * srcFps / outFps() : F / outFps();
    const quantOn = () => isVideo || q('[data-f="quant"]').checked;
    const useSelOn = () => q('[data-f="usesel"]').checked;
    const clamp = (v, lo, hi) => Math.max(lo, Math.min(hi, v));
    const status = (t) => { sEl.textContent = t; setTimeout(() => { if (sEl.textContent === t) sEl.textContent = ""; }, 2500); };

    function rebuildOrder() { order = []; let s = 0; for (const c of cuts) { if (c > s) order.push({ start: s, end: c }); s = c; } if (s < total) order.push({ start: s, end: total }); }
    function syncCuts() { cuts = [...new Set(order.slice(1).map(x => x.start))].sort((x, y) => x - y); }
    rebuildOrder();
    if (selIdx.length >= order.length) selIdx = [];

    let layout = [];
    const seqDur = () => order.reduce((s, x) => s + (x.end - x.start), 0) / srcFps;
    function layoutSegs() {
      pxPerSec = Math.max(0.5, baseZoom * zoom);      
      layout = []; let cx = 0;
      for (const s of order) { const w = Math.max(2, toSec(s.end - s.start) * pxPerSec); layout.push({ x: cx, w }); cx += w; }
      const cw = inner.parentElement.clientWidth || 600;
      innerW = Math.max(cw, Math.ceil(cx));
      inner.style.width = innerW + "px";
      [...track.children].forEach((el, i) => { const L = layout[i]; if (L) { el.style.left = L.x + "px"; el.style.width = L.w + "px"; } });
      [...atrack.children].forEach((el, i) => { const L = layout[i]; if (L) { el.style.left = L.x + "px"; el.style.width = L.w + "px"; } });
    }
    const frameAtX = (x) => {
      for (let i = 0; i < layout.length; i++) { const L = layout[i];
        if (x >= L.x && x <= L.x + L.w) return order[i].start + fromSec((x - L.x) / pxPerSec); }
      return fromSec(x / pxPerSec);
    };
    const xAtFrame = (f) => {
      for (let i = 0; i < order.length; i++) { const s = order[i];
        if (f >= s.start && f <= s.end) return layout[i].x + toSec(f - s.start) * pxPerSec; }
      return toSec(f) * pxPerSec;
    };
    function boundaryAt(x) {
      const TH = 6; if (!layout.length) return null;
      if (Math.abs(layout[0].x - x) <= TH) return { l: null, r: 0 };
      for (let i = 1; i < order.length; i++) if (Math.abs(layout[i].x - x) <= TH) return { l: i - 1, r: i };
      const L = layout[layout.length - 1];
      if (Math.abs(L.x + L.w - x) <= TH) return { l: order.length - 1, r: null };
      return null;
    }

    // ---- 渲染 ----
    function renderBlocks() {
      track.innerHTML = order.map((s, i) =>
        `<div class="emr-segblk" data-i="${i}"><div class="ths"></div><span class="lbl">${i + 1}</span></div>`).join("");
      atrack.innerHTML = order.map((s, i) =>
        `<div class="emr-waveblk" data-i="${i}"><canvas></canvas><span class="lbl">${i + 1}</span></div>`).join("");
      layoutSegs(); loadThumbs(); drawWaves(); syncSelHighlight(); updateSel(); updatePlayhead(); updateInfo();
    }
    function loadThumbs() {
      if (!isVideo) return;
      [...track.children].forEach(el => {
        const s = order[+el.dataset.i], L = layout[+el.dataset.i]; if (!s || !L) return;
        const n = Math.max(1, Math.min(8, Math.floor(L.w / 40)));
        if (+el.dataset.n === n) return;
        el.dataset.n = n;
        const th = el.querySelector(".ths"); th.innerHTML = "";
        for (let j = 0; j < n; j++) {
          const f = Math.min(s.end - 1, Math.round(s.start + (s.end - s.start) * (j + 0.5) / n));
          const im = document.createElement("img");
          im.draggable = false; im.onload = () => im.classList.add("ld");
          im.src = previewUrl(mat.path, f, 72);
          th.appendChild(im);
        }
      });
    }
    function drawWaves() {
      const pts = mat._wave || [], len = pts.length;
      [...atrack.children].forEach(el => {
        const s = order[+el.dataset.i], L = layout[+el.dataset.i]; if (!s || !L) return;
        const cv = el.querySelector("canvas"), dpr = window.devicePixelRatio || 1;
        const cw = Math.max(1, Math.round(L.w)), ch = el.clientHeight || 40;
        cv.width = cw * dpr; cv.height = ch * dpr;
        const ctx = cv.getContext("2d"); ctx.setTransform(dpr, 0, 0, dpr, 0, 0); ctx.clearRect(0, 0, cw, ch);
        if (!len) return;
        const audioDur = (mat.media && mat.media.audio_duration) ? mat.media.audio_duration : (total / srcFps);
        const a0 = Math.floor((s.start / srcFps) / audioDur * len), b0 = Math.max(a0 + 1, Math.ceil((s.end / srcFps) / audioDur * len));
        const step = cw / (b0 - a0), mid = ch / 2, amp = ch / 2 - 2;
        ctx.beginPath();
        for (let i = a0; i < b0; i++) { const x = (i - a0) * step, y = mid - (pts[i] || 0) * amp; i === a0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y); }
        for (let i = b0 - 1; i >= a0; i--) { const x = (i - a0) * step, y = mid + (pts[i] || 0) * amp; ctx.lineTo(x, y); }
        ctx.closePath(); ctx.fillStyle = "rgba(90,173,90,.4)"; ctx.fill();
        ctx.strokeStyle = "#5aad5a"; ctx.lineWidth = 1; ctx.stroke();
      });
    }
    function syncSelHighlight() {
      [...track.children].forEach((el, i) => el.classList.toggle("selected", selIdx.includes(i)));
      [...atrack.children].forEach((el, i) => el.classList.toggle("selected", selIdx.includes(i)));
    }
    function drawRuler() {
      let html = "";
      const seqT = seqDur(), stepT = pxPerSec >= 90 ? 0.5 : pxPerSec >= 40 ? 1 : pxPerSec >= 18 ? 2 : pxPerSec >= 8 ? 5 : 10;
      for (let t = 0; t <= seqT + 1e-6; t += stepT) {
        const major = Math.abs(t - Math.round(t)) < 1e-3;
        html += `<i class="emr-tick ${major ? "major" : ""}" style="left:${t * pxPerSec}px">${major ? `<span>${t.toFixed(0)}s</span>` : ""}</i>`;
      }
      q(".emr-ruler").innerHTML = html;
    }
    function layoutAll() { layoutSegs(); drawRuler(); updateSel(); updatePlayhead(); updateInfo(); }
    function fitZoom() {
      const cw = inner.parentElement.clientWidth || 600;
      zoom = clamp(cw / Math.max(1e-6, seqDur() * baseZoom), 0.02, 16);
      q('[data-f="zoom"]').value = zoom;
    }

    // ---- 信息 / 蓝框 ----
    function finalSpan() {
      if (useSelOn()) return { s: sel.s, e: sel.e, tag: "sel" };
      if (selIdx.length) {
        const lo = Math.min(...selIdx), hi = Math.max(...selIdx);
        return { s: order[lo].start, e: order[hi].end, tag: selIdx.length > 1 ? `segs×${selIdx.length}` : `seg ${lo + 1}` };
      }
      const i = Math.max(0, segIdxAt(playFrame));
      return { s: order[i]?.start ?? 0, e: order[i]?.end ?? total, tag: `seg ${i + 1}` };
    }
    function updateInfo() {
      const r = finalSpan();
      const L = lenToOut(r.e - r.s), showQ = div > 0 && quantOn();
      const n = showQ ? Math.max(0, Math.floor((L - a) / div + 1e-6)) : null;
      const of = showQ ? a + n * div : Math.max(0, Math.floor(L));
      qEl.textContent = `[${r.tag}] Out: ${of}` + (showQ ? ` = ${div}×${n}+${a}` : "");
    }
    function applyUseSel() {
      const on = useSelOn();
      selEl.style.opacity = on ? "1" : ".22";
      selEl.style.pointerEvents = on ? "auto" : "none";
      shL.style.opacity = shR.style.opacity = on ? "1" : ".3";
      updateInfo();
    }
    function updateSel() {
      const x = xAtFrame(sel.s), w = Math.max(3, xAtFrame(sel.e) - x);
      selEl.style.left = x + "px"; selEl.style.width = w + "px";
      shL.style.left = "0"; shL.style.width = x + "px";
      shR.style.left = (x + w) + "px"; shR.style.width = Math.max(0, innerW - x - w) + "px";
      updateInfo();
    }
    function snapSelection(side) {
      if (side === "r") {
        if (quantOn() && div > 0 && sel.e < total - minLen() * 0.5) {
          let n = Math.round((lenToOut(sel.e - sel.s) - a) / div);
          n = Math.max(0, Math.min(n, Math.floor((lenToOut(total - sel.s) - a) / div)));
          sel.e = Math.min(total, sel.s + Math.max(minLen(), outToLen(a + n * div)));
        }
        sel.e = Math.min(total, Math.max(sel.s + minLen(), sel.e));
      } else {
        if (quantOn() && div > 0 && sel.s > minLen() * 0.5) {
          let n = Math.round((lenToOut(sel.e - sel.s) - a) / div);
          n = Math.max(0, Math.min(n, Math.floor((lenToOut(sel.e) - a) / div)));
          sel.s = Math.max(0, sel.e - Math.max(minLen(), outToLen(a + n * div)));
        }
        sel.s = Math.max(0, Math.min(sel.e - minLen(), sel.s));
      }
      if (isVideo) { sel.s = Math.round(sel.s); sel.e = Math.round(sel.e); }
      updateSel();
    }
    function nearestCut(f) {
      let best = f, bd = 1e9;
      for (const c of cuts) { const d = Math.abs(c - f); if (d < bd) { bd = d; best = c; } }
      return bd <= srcFps * 0.4 ? best : f;
    }
    function finalizeRange(s0, e0) {
      if (isVideo) { s0 = Math.round(s0); e0 = Math.round(e0); }
      if (quantOn() && div > 0 && e0 < total - minLen() * 0.5) {
        const n = Math.max(0, Math.floor((lenToOut(e0 - s0) - a) / div + 1e-6));
        e0 = Math.min(e0, s0 + Math.max(minLen(), outToLen(a + n * div)));
        if (isVideo) e0 = Math.round(e0);
      }
      return [s0, Math.min(total, Math.max(s0 + minLen(), e0))];
    }

    // ---- 游标 / 预览 / 音频 ----
    function updatePlayhead() {
      const qi = (playing && playQ[0] && Number.isInteger(playQ[0].i)) ? playQ[0].i : -1;
      const L = qi >= 0 ? layout[qi] : null;
      const px = L ? L.x + toSec(clamp(playFrame, order[qi].start, order[qi].end) - order[qi].start) * pxPerSec
                   : xAtFrame(playFrame);
      phEl.style.left = px + "px";
      timeEl.textContent = isVideo
        ? `f ${Math.round(playFrame)}/${total} (${toSec(playFrame).toFixed(2)}s)`
        : `${playFrame.toFixed(2)}s / ${total.toFixed(2)}s`;
    }
    function setPlayhead(f) {
      playFrame = Math.max(0, Math.min(total - minLen(), isVideo ? Math.round(f) : f));
      updatePlayhead(); schedulePreview(playFrame);
    }
    function schedulePreview(f) {
      if (!isVideo) return;
      const now = performance.now();
      if (now - lastPrevAt < 70) return;
      lastPrevAt = now;
      const s = ++seq;
      if (probe) { probe.onload = null; probe.onerror = null; }
      const p = new Image(); probe = p;
      p.onload = () => { if (s === seq) q(".emr-pvimg img").src = previewUrl(mat.path, Math.round(f), 640); };
      p.src = previewUrl(mat.path, Math.round(f), 640);
    }
    const audioEl = new Audio(audioUrl(mat.path)); audioEl.preload = "auto";
    let audioReady = false, audioFailed = false, pendingPlay = null, bufTimer = 0;
    audioEl.addEventListener("canplay", () => { audioReady = true; flushPendingPlay(); });
    audioEl.addEventListener("error", () => { audioFailed = true; audioReady = true; flushPendingPlay(); });
    audioEl.addEventListener("loadedmetadata", () => { if (playing) syncAudio(playFrame, true); });
    audioEl.load();                                  
    function flushPendingPlay() {
      if (bufTimer) { clearTimeout(bufTimer); bufTimer = 0; }
      if (pendingPlay) { const p = pendingPlay; pendingPlay = null; p(); }
    }
    function syncAudio(f, seek) {
      const t = toSec(f);
      try {
        if (!Number.isFinite(audioEl.duration)) return;   
        if (audioEl.readyState >= 1 && (seek || Math.abs(audioEl.currentTime - t) > 0.15))
          audioEl.currentTime = Math.min(Math.max(0, t), Math.max(0, audioEl.duration - 0.01));
      } catch (_) {}
    }
    // ---- 播放----
    function segIdxAt(f) {
      for (let i = 0; i < order.length; i++) if (f >= order[i].start && f < order[i].end) return i;
      return Math.max(0, order.length - 1);
    }
    function startPlayback(all) {
      if (!audioReady) {
        if (!pendingPlay) {
          pendingPlay = () => startPlayback(all);
          status("Buffering audio…");
          bufTimer = setTimeout(() => { audioReady = true; audioFailed = true; flushPendingPlay(); }, 30000);
        }
        return;
      }
      const i = segIdxAt(playFrame), cur = order[i];
      if (!cur) return;
      let from = playFrame;
      if (from >= cur.end - minLen()) from = cur.start;
      from = Math.max(cur.start, Math.min(cur.end - minLen(), from));
      playAllMode = !!all;
      playQ = [{ s: from, e: cur.end, i }];
      if (playAllMode) for (let j = i + 1; j < order.length; j++) playQ.push({ s: order[j].start, e: order[j].end, i: j });
      playing = true; audioMaster = false; acc = 0; lastT = performance.now();
      const arm = () => { if (!playing) return; audioMaster = true; const p = audioEl?.play?.();
	  if (p && p.catch) p.catch(() => { audioMaster = false; });
	  if (raf) cancelAnimationFrame(raf); raf = requestAnimationFrame(playTick); };

      try { audioEl.currentTime = Math.max(0, Math.min(toSec(from), (audioEl.duration || toSec(from)) - 0.01)); } catch (_) {}
      if (audioEl.seeking || audioEl.readyState < 2) {
        const onReady = () => { audioEl.removeEventListener("seeked", onReady); arm(); };
        audioEl.addEventListener("seeked", onReady);
        setTimeout(() => { if (!audioMaster) { audioEl.removeEventListener("seeked", onReady); arm(); } }, 1500);
      } else arm();
      q('[data-a="play"]').innerHTML = PB.stop;
      const pab = q('[data-a="playall"]');
      pab.innerHTML = playAllMode ? PB.stop : PB.playall;      
      pab.title = playAllMode ? "Stop" : "Play all segments in order";
      pab.classList.toggle("emr-pbtn", playAllMode);
    }

    function stopPlayback() {
      playing = false;
	  audioMaster = false;
      if (raf) { cancelAnimationFrame(raf); raf = 0; }
      playQ = [];
	  pendingPlay = null;
      if (bufTimer) { clearTimeout(bufTimer); bufTimer = 0; }
      try { audioEl?.pause?.(); } catch (_) {}
      q('[data-a="play"]').innerHTML = PB.play;
      const pab = q('[data-a="playall"]');
      pab.innerHTML = PB.playall;
      pab.title = "Play all segments in order";
      pab.classList.remove("emr-pbtn");
    }

    function playTick(now) {
      raf = 0; 
	  if (!playing) return;
	  if (audioMaster && audioEl.ended) audioMaster = false;   
      const dt = Math.min(0.25, (now - lastT) / 1000); lastT = now;
      const r = playQ[0];
      if (!r) { stopPlayback(); return; }
      const aPlaying = audioMaster && !audioEl.paused && !audioEl.ended && audioEl.readyState >= 2;
      let f;
      if (audioMaster) {
        f = aPlaying ? (isVideo ? audioEl.currentTime * srcFps : audioEl.currentTime) : playFrame;  // ★ 停等
      } else if (isVideo) {
        acc += dt * srcFps; f = Math.max(playFrame, r.s);
        if (acc >= 1) { const adv = Math.floor(acc); acc -= adv; f += adv; }
      } else f = playFrame + dt;
      if (f >= r.e - minLen() * 0.5) {
        playQ.shift();
        const nx = playQ[0];
        if (!nx) { playFrame = r.e - minLen(); updatePlayhead(); schedulePreview(playFrame); stopPlayback(); return; }
        f = nx.s; acc = 0;
        if (audioMaster) {   
            const tPos = toSec(nx.s);
            if (Math.abs(audioEl.currentTime - tPos) > 0.04) {
                try { audioEl.currentTime = Math.max(0, Math.min(tPos, (audioEl.duration || tPos) - 0.01)); } catch (_) {}
            }
        }
    }
      playFrame = f; updatePlayhead(); schedulePreview(f);
      raf = requestAnimationFrame(playTick);
    }

	
    // ---- 播放组 / 工具 ----
    const stepLen = () => isVideo ? 1 : 0.05;
    q('[data-a="start"]').onclick = () => { setPlayhead(order[0]?.start ?? 0); syncAudio(playFrame, true); };
    q('[data-a="segstart"]').onclick = () => { if (useSelOn() && playFrame >= sel.s && playFrame <= sel.e) { setPlayhead(sel.s); syncAudio(sel.s, true); return; } const s = order[segIdxAt(playFrame)]; setPlayhead(s.start); syncAudio(s.start, true); }; 

    q('[data-a="segend"]').onclick = () => {
        if (useSelOn() && playFrame >= sel.s && playFrame <= sel.e) { setPlayhead(Math.max(sel.s, sel.e - minLen())); syncAudio(playFrame, true); return; }
        const s = order[segIdxAt(playFrame)];
        setPlayhead(Math.max(s.start, s.end - minLen())); syncAudio(playFrame, true);
    };

    q('[data-a="end"]').onclick = () => { const l = order[order.length - 1]; setPlayhead(Math.max(l.start, l.end - minLen())); syncAudio(playFrame, true); };
    q('[data-a="play"]').onclick = () => playing ? stopPlayback() : startPlayback(false);
    q('[data-a="playall"]').onclick = () => playing ? stopPlayback() : startPlayback(true);
    q('[data-a="full"]').onclick = () => { sel = { s: 0, e: total }; q('[data-f="usesel"]').checked = true; applyUseSel(); updateSel(); };
    q('[data-a="fit"]').onclick = () => { fitZoom(); layoutAll(); };
	q('[data-a="clearedit"]').onclick = () => {
      stopPlayback();
      cuts = []; rebuildOrder();          
      selIdx = []; selAnchor = null;      
      if (insertEl) { insertEl.remove(); insertEl = null; }
      renderBlocks(); applyUseSel(); setPlayhead(0);
      status("Timeline cleared — Apply to save");
    };

    q('[data-a="manual"]').onclick = (e) => {
      marking = !marking; e.currentTarget.classList.toggle("emr-pbtn", marking);
      inner.classList.toggle("marking", marking);
    };
    const detectBtn = q('[data-a="detect"]');
    detectBtn.onclick = async () => {
      detectBtn.textContent = "Analyzing…";
      try {
        const thr = +q('[data-f="thr"]').value || 40;
        const r = await fetch(`/element_multi_ref/detect_cuts?p=${encodeURIComponent(mat.path)}&threshold=${thr}`);
        const d = await r.json();
        cuts = (d.cuts || []).map(Number);
        if (isVideo) cuts = cuts.map(c => Math.round(c));
        cuts = [...new Set(cuts)].sort((x, y) => x - y);
        rebuildOrder(); selIdx = []; selAnchor = null;
        renderBlocks(); status(`${cuts.length} cuts`);
        detectBtn.textContent = `${cuts.length} cuts`;
      } catch { detectBtn.textContent = "Auto Split"; }
    };
    // ---- 切 / 选 / 合 / 修 / 排序 ----
    function splitAt(f) {
	  if (isVideo) f = Math.round(f);
      const i = order.findIndex(s => f > s.start && f < s.end);
      if (i < 0) return;
      const s = order[i];
      if (f - s.start < MIN || s.end - f < MIN) { status("Too close to segment edge"); return; }
      order.splice(i, 1, { start: s.start, end: f }, { start: f, end: s.end });
      syncCuts(); selIdx = []; selAnchor = null; renderBlocks();
    }
    function mergeAt(x) {                                     
      const b = boundaryAt(x);
      if (!b || b.l == null || b.r == null) return;
      const l = order[b.l], r = order[b.r];
      if (l.end !== r.start) { status("Clips not adjacent, cannot merge"); return; }
      l.end = r.end;
      order.splice(b.r, 1);
      syncCuts(); selIdx = []; selAnchor = null; renderBlocks(); status("Merged");
    }
    function maxEndFor(i, pre) {
      const si = pre[i].start; let hi = total;
      for (let j = 0; j < pre.length; j++) { if (j === i) continue;
        if (pre[j].end > si && pre[j].start < hi) hi = pre[j].start; }
      return hi;
    }
    function minStartFor(i, pre) {
      const ei = pre[i].end; let lo = 0;
      for (let j = 0; j < pre.length; j++) { if (j === i) continue;
        if (pre[j].start < ei && pre[j].end > lo) lo = pre[j].end; }
      return lo;
    }
    let hinted = false;
    const hint = (m) => { if (!hinted) { hinted = true; status(m); } };
    function relayout() { layoutSegs(); updateSel(); updatePlayhead(); updateInfo(); }
    function applyTrimLive(x) {                               // （side=增减 / roll=切点）
      const d = trimDrag; if (!d) return;
      const df = isVideo ? Math.round((x - d.startX) / pxPerSec * srcFps) : (x - d.startX) / pxPerSec;
      const pre = d.pre, b = d.b;
      if (b.l == null) {
        const p = pre[0], raw = p.start + df, ns = clamp(raw, 0, p.end - MIN);
        if (ns !== order[0].start) { if (raw !== ns) hint(raw > ns ? "Min clip length reached" : "No earlier source frames"); order[0].start = ns; relayout(); }
        return;
      }
      if (b.r == null) {
        const i = order.length - 1, p = pre[i], raw = p.end + df, ne = clamp(raw, p.start + MIN, total);
        if (ne !== order[i].end) { if (raw !== ne) hint(raw < ne ? "Min clip length reached" : "No later source frames"); order[i].end = ne; relayout(); }
        return;
      }
      const li = b.l, ri = b.r;
      if (d.roll) {
        const pl = pre[li], pr = pre[ri];
        let lo, hi;
        if (pl.end === pr.start) { lo = pl.start + MIN; hi = pr.end - MIN; }
        else { lo = Math.max(pl.start, pr.start) + MIN; hi = Math.min(pl.end, pr.end) - MIN; }
        if (lo > hi) { hint("No trim range on this boundary"); return; }
        const f = clamp(pl.end + df, lo, hi);
        if (f !== order[li].end || f !== order[ri].start) { order[li].end = f; order[ri].start = f; relayout(); }
        return;
      }
      if (d.side === "left") {
        const p = pre[li], raw = p.end + df, ne = clamp(raw, p.start + MIN, maxEndFor(li, pre));
        if (ne !== order[li].end) { if (raw !== ne) hint(raw < ne ? "Min clip length reached" : "Blocked by next clip (Alt/Ctrl = extend)"); order[li].end = ne; relayout(); }
        return;
      }
      const p = pre[ri], raw = p.start + df, ns = clamp(raw, minStartFor(ri, pre), p.end - MIN);
      if (ns !== order[ri].start) { if (raw !== ns) hint(raw > ns ? "Min clip length reached" : "Blocked by next clip (Alt/Ctrl = extend)"); order[ri].start = ns; relayout(); }
    }
    function commitTrim() {
      if (!trimDrag) return;
      trimDrag = null; hinted = false;
      syncCuts(); drawWaves(); loadThumbs();
    }
    function applySelect(p) {                                 
      if (p.shift) {
        const anchor = selAnchor ?? (selIdx.length ? selIdx[selIdx.length - 1] : 0);
        const A = Math.min(anchor, p.i), B = Math.max(anchor, p.i);
        selIdx = []; for (let i = A; i <= B; i++) selIdx.push(i);
      } else if (p.ctrl) {
        const pos = selIdx.indexOf(p.i);
        if (pos >= 0) selIdx.splice(pos, 1); else selIdx.push(p.i);
        selAnchor = p.i;
      } else { selIdx = [p.i]; selAnchor = p.i; }
      selIdx.sort((x, y) => x - y);
      if (selIdx.length) { q('[data-f="usesel"]').checked = false; applyUseSel(); }
      syncSelHighlight(); updateInfo();
    }
    // 重排序
    function beginReorder() {
      const idx = pendSel.i;
      if (!selIdx.includes(idx)) { selIdx = [idx]; selAnchor = idx; syncSelHighlight(); }
      reorder = { k: idx };
      if (!insertEl) { insertEl = document.createElement("div"); insertEl.className = "emr-insert"; inner.appendChild(insertEl); }
      insertEl.style.display = "block";
      inner.classList.add("reordering");
    }
    function updateInsertLine(x) {
      if (!insertEl || !layout.length) return;
      let k = layout.length;
      for (let i = 0; i < layout.length; i++) if (x < layout[i].x + layout[i].w / 2) { k = i; break; }
      reorder.k = k;
      const edgeX = k < layout.length ? layout[k].x : layout[layout.length - 1].x + layout[layout.length - 1].w;
      insertEl.style.left = edgeX + "px";
    }
    function commitReorder() {
      const k = reorder.k;
      const selS = [...selIdx].sort((x, y) => x - y);
      const moved = selS.map(i => order[i]);
      const rest = order.filter((_, i) => !selIdx.includes(i));
      const pos = Math.max(0, Math.min(rest.length, k - selS.filter(i => i < k).length));
      rest.splice(pos, 0, ...moved);
      order = rest;
      selIdx = moved.map((_, j) => pos + j).sort((x, y) => x - y);
      selAnchor = null;
      if (insertEl) { insertEl.remove(); insertEl = null; }
      inner.classList.remove("reordering");
      reorder = null; pendSel = null;
      syncCuts(); renderBlocks(); status("Reordered");
    }
    // ---- 轨道指针事件 ----
    const ex = (e) => e.clientX - inner.getBoundingClientRect().left;
    track.addEventListener("pointerdown", (e) => {
      if (e.button === 2 || e.button !== 0) return;
      const x = ex(e);
      if (marking) { track.setPointerCapture(e.pointerId); return; }
      const b = boundaryAt(x);
      if (b) {
        const roll = !(e.altKey || e.ctrlKey || e.metaKey);
        let side = null;
        if (b.l == null) side = "right";
        else if (b.r == null) side = "left";
        else side = (x < layout[b.r].x) ? "left" : "right";
        trimDrag = { b, roll, side, startX: x, pre: order.map(o => ({ start: o.start, end: o.end })) };
        hinted = false;
        track.setPointerCapture(e.pointerId); e.stopPropagation(); return;
      }
      const el = e.target.closest(".emr-segblk");
      if (!el) return;
      pendSel = { i: +el.dataset.i, x, shift: e.shiftKey, ctrl: e.ctrlKey || e.metaKey };
      track.setPointerCapture(e.pointerId);
    });
    track.addEventListener("pointermove", (e) => {
      const x = ex(e);
      if (marking) return;
      if (trimDrag) { applyTrimLive(x); return; }
      if (reorder) { updateInsertLine(x); return; }
      if (pendSel) { if (Math.abs(x - pendSel.x) > 4) { beginReorder(); updateInsertLine(x); } return; }
      inner.classList.toggle("trimhov", !!boundaryAt(x));
    });
    track.addEventListener("pointerup", (e) => {
      const x = ex(e);
      if (marking) { splitAt(frameAtX(x)); return; }
      if (trimDrag) { commitTrim(); return; }
      if (reorder) { commitReorder(); return; }
      if (pendSel) { applySelect(pendSel); pendSel = null; }
    });
    track.addEventListener("contextmenu", (e) => { e.preventDefault(); mergeAt(ex(e)); });
    for (const zone of [q(".emr-ruler"), atrack]) {
      zone.addEventListener("pointerdown", (e) => {
        if (e.button !== 0) return;
        e.stopPropagation();
        zone.setPointerCapture(e.pointerId);
        setPlayhead(frameAtX(ex(e))); syncAudio(playFrame, true);
        const mv = (ev) => setPlayhead(frameAtX(ex(ev)));
        const up = () => { zone.removeEventListener("pointermove", mv); zone.removeEventListener("pointerup", up); syncAudio(playFrame, true); };
        zone.addEventListener("pointermove", mv); zone.addEventListener("pointerup", up);
      });
    }

    phEl.addEventListener("pointerdown", (e) => {
      if (e.button !== 0) return;
      e.stopPropagation();
      phEl.setPointerCapture(e.pointerId);
      setPlayhead(frameAtX(ex(e))); syncAudio(playFrame, true);
      const mv = (ev) => setPlayhead(frameAtX(ex(ev)));
      const up = () => { phEl.removeEventListener("pointermove", mv); phEl.removeEventListener("pointerup", up); syncAudio(playFrame, true); };
      phEl.addEventListener("pointermove", mv); phEl.addEventListener("pointerup", up);
    });
	
    let dragSel = null;
    const scrubPH = (e) => {                 
      selEl.setPointerCapture(e.pointerId);
      setPlayhead(frameAtX(ex(e)));
      syncAudio(playFrame, true);
      const mv = (ev) => setPlayhead(frameAtX(ex(ev)));
      const up = () => { selEl.removeEventListener("pointermove", mv); selEl.removeEventListener("pointerup", up); syncAudio(playFrame, true); };
      selEl.addEventListener("pointermove", mv);
      selEl.addEventListener("pointerup", up);
    };
    selEl.addEventListener("pointerdown", (e) => {
      const isL = e.target.classList.contains("l"), isR = e.target.classList.contains("r");
      if (!isL && !isR && e.button === 0 && Math.abs(ex(e) - xAtFrame(playFrame)) <= 7) {
          e.stopPropagation(); scrubPH(e); return;
      }
      dragSel = { mode: isL ? "l" : isR ? "r" : "body", e0: sel.e, s0: sel.s, grab: frameAtX(ex(e)) - sel.s };
      selEl.setPointerCapture(e.pointerId);
      e.stopPropagation();
    });

    selEl.addEventListener("pointermove", (e) => {
      if (!dragSel) return;
      const cur = frameAtX(ex(e));
      if (dragSel.mode === "body") {
        let s = cur - dragSel.grab;
        s = Math.max(0, Math.min(total - (sel.e - sel.s), s));
        if (isVideo && q('[data-f="snapcut"]')?.checked) s = nearestCut(s);
        sel = { s, e: s + (dragSel.e0 - dragSel.s0) };
      } else if (dragSel.mode === "r") sel.e = Math.max(sel.s + minLen(), Math.min(total, cur));
      else sel.s = Math.max(0, Math.min(sel.e - minLen(), cur));
      updateSel();
    });
    selEl.addEventListener("pointerup", () => { if (dragSel && dragSel.mode !== "body") snapSelection(dragSel.mode); dragSel = null; });
    // ---- 参数 ----
    const resnap = () => { if (useSelOn() && quantOn() && div > 0 && sel.e < total) snapSelection("r"); else updateInfo(); };
    q('[data-f="div"]').onchange = () => { div = Math.max(1, +q('[data-f="div"]').value || 17); resnap(); };
    q('[data-f="a"]').onchange = () => { a = Math.max(0, +q('[data-f="a"]').value || 0); resnap(); };
    q('[data-f="fps"]')?.addEventListener("change", () => updateInfo());
    q('[data-f="quant"]')?.addEventListener("change", () => updateInfo());
    q('[data-f="rfps"]')?.addEventListener("change", () => updateInfo());
    q('[data-f="usesel"]').onchange = applyUseSel;
    q('[data-f="preset"]').onchange = () => {
      const p = PRESETS[+q('[data-f="preset"]').value];
      q('[data-f="div"]').value = p.div; q('[data-f="a"]').value = p.a;
      div = p.div; a = p.a; resnap();
    };
    q('[data-f="zoom"]').oninput = () => { zoom = +q('[data-f="zoom"]').value; layoutAll(); };
    if (isVideo) {
      q('[data-f="ow"]').value = edit.out_w || media.w || 0;   
      q('[data-f="oh"]').value = edit.out_h || media.h || 0;
      q('[data-f="ow"]').onchange = () => {
        const ow = Math.max(0, Math.round(+q('[data-f="ow"]').value || 0)); q('[data-f="ow"]').value = ow;
        if (q('[data-f="olock"]').checked && media.w > 0 && ow > 0)
          q('[data-f="oh"]').value = Math.max(2, Math.round(ow * media.h / media.w / 2) * 2);
      };
      q('[data-f="oh"]').onchange = () => {
        const oh = Math.max(0, Math.round(+q('[data-f="oh"]').value || 0)); q('[data-f="oh"]').value = oh;
        if (q('[data-f="olock"]').checked && media.h > 0 && oh > 0)
          q('[data-f="ow"]').value = Math.max(2, Math.round(oh * media.w / media.h / 2) * 2);
      };
      q('[data-a="resetsize"]').onclick = () => { q('[data-f="ow"]').value = media.w || 0; q('[data-f="oh"]').value = media.h || 0; };
      const pvImg = q(".emr-pvimg img"), pvInfo = q(".emr-pvinfo");
      pvImg.addEventListener("load", () => { const w = pvImg.clientWidth; if (w > 60) pvInfo.style.width = w + "px"; });
    }
    // ---- 快捷键 ----
    const keyHandler = (e) => {
      if (e.target.tagName === "INPUT" || e.target.tagName === "SELECT") return;
      const step = e.shiftKey ? srcFps : stepLen();
      switch (e.key) {
        case " ": e.preventDefault(); playing ? stopPlayback() : startPlayback(true); break;  
        case "ArrowLeft": e.preventDefault(); setPlayhead(playFrame - step); syncAudio(playFrame, true); break;
        case "ArrowRight": e.preventDefault(); setPlayhead(playFrame + step); syncAudio(playFrame, true); break;
        case "i": case "I":
          sel.s = Math.max(0, isVideo ? Math.round(playFrame) : playFrame);
          if (sel.s >= sel.e) sel.e = Math.min(total, sel.s + minLen());
          q('[data-f="usesel"]').checked = true; applyUseSel(); snapSelection("l"); break;
        case "o": case "O":
          sel.e = Math.min(total, isVideo ? Math.round(playFrame) : playFrame);
          if (sel.e <= sel.s) sel.s = Math.max(0, sel.e - minLen());
          q('[data-f="usesel"]').checked = true; applyUseSel(); snapSelection("r"); break;
        case "Home": sel.s = 0; snapSelection("l"); break;
        case "End": sel.e = total; snapSelection("r"); break;
        case "m": case "M": q('[data-a="manual"]').click(); break;
      }
    };
    window.addEventListener("keydown", keyHandler);
    // ---- 收尾 ----
    const close = () => {
      stopPlayback();
      try { audioEl?.pause?.(); } catch (_) {}
      window.removeEventListener("keydown", keyHandler);
      ov.remove();
    };
    q(".emr-x").onclick = close;
    q('[data-a="cancel"]').onclick = close;
    q('[data-a="apply"]').onclick = () => {
      const r = finalSpan();
      const [s0, e0] = finalizeRange(r.s, r.e);
      const out = { ...edit, trim: [s0, e0], div_by: div, a,
        cuts: cuts.slice(), sel_idx: selIdx.slice(), usesel: useSelOn(), sel: [sel.s, sel.e],
        playhead: Math.round(playFrame),
        snap_cut: isVideo ? !!q('[data-f="snapcut"]')?.checked : !!edit.snap_cut };
      if (isVideo) {
        out.fps = +q('[data-f="fps"]').value || 0;
        out.out_w = Math.max(0, Math.round(+q('[data-f="ow"]').value || 0));
        out.out_h = Math.max(0, Math.round(+q('[data-f="oh"]').value || 0));
        out.lock_ratio = true;
      } else {
        out.quant = q('[data-f="quant"]').checked;
        out.ref_fps = Math.max(1, +q('[data-f="rfps"]').value || 24);
      }
      onApply(out); close();
    };
    mat._wave = mat._wave || [];
    if (!mat._wave.length) {
      fetch(`/element_multi_ref/media_info?p=${encodeURIComponent(mat.path)}`)
        .then(r => r.json()).then(d => { mat._wave = d.waveform || []; fitZoom(); renderBlocks(); layoutAll(); }).catch(() => {});
    }
    fitZoom(); renderBlocks(); layoutAll(); applyUseSel(); schedulePreview(playFrame);
    requestAnimationFrame(() => { fitZoom(); layoutAll(); });   
  }
}


/* ================= 主 UI ================= */
class MultiRefUI {
  constructor(node, root, widget) {
    this.node = node; this.root = root; this.widget = widget;
    let saved = {};
    try { saved = JSON.parse(widget?.value || "{}"); } catch (_) {}
    this.mats = saved.materials || {};
    this.slots = saved.slots || {};
    this._waves = {};           
    this._dragSlot = null;
	this._editVer = {};   
    this.build(); this.render();
    this._ro = new ResizeObserver(() => { this.node.onResize?.(); this.node.setDirtyCanvas?.(true, true); });
    setTimeout(() => this._ro.observe(root), 100);
  }
  status(t) { const el = this.root.querySelector(".emr-status"); if (el) el.textContent = t; }
  defaultEdit(kind, mat) {
    if (kind === "image") return { crop: null, out_w: 0, out_h: 0, lock_ratio: true, div_by: 32, paint_file: null };
    if (kind === "video") {
      const total = mat?.media?.total_frames || 0;
      return { trim: [0, total], div_by: 17, a: 5, fps: 0, out_w: 0, out_h: 0, lock_ratio: true, snap_cut: false };
    }
    const dur = mat?.media?.duration || 0;
    return { trim: [0, dur], quant: false, div_by: 17, a: 5, ref_fps: 24 };
  }
  build() {
    this.root.className = "emr";
    const card = (d) => `<div class="emr-slot g-${d.group}" data-slot="${d.id}" draggable="false">
      <div class="emr-media"><span class="emr-empty">Drop or click to add</span></div>
      <span class="emr-tag">${d.id}</span>
      <button class="emr-iconbtn emr-edit" title="Edit">${svgIcon(ICONS.edit, 12)}</button>
      <button class="emr-iconbtn emr-del" title="Remove">${svgIcon(ICONS.x, 11)}</button>
    </div>`;
    const img9 = SLOT_DEFS.filter(d => d.group === "img").map(card).join("");
    const frame = SLOT_DEFS.filter(d => d.group === "frame").map(card).join("");
    const vids = SLOT_DEFS.filter(d => d.group === "video").map(card).join("");
    const vau = SLOT_DEFS.filter(d => d.group === "vau").map(card).join("");
    const aud = SLOT_DEFS.filter(d => d.group === "aud").map(card).join("");
    const drv = SLOT_DEFS.filter(d => d.group === "drive").map(card).join("");
    this.root.innerHTML = `
      <div class="emr-head">
        <span class="emr-title">Element Multi REF</span>
        <span style="color:#66718a;font-size:11px">Drop files · drag to swap · ✎ edit</span>
        <span class="emr-status">Ready</span>
        <button class="emr-btn" data-a="clearall">Clear</button>
      </div>
      <div class="emr-grid">
        <div class="emr-col-img">${img9}</div>
        <div class="emr-col">
          <div class="emr-row emr-row-frames">${frame}</div>
          <div class="emr-row emr-row-video">${vids}</div>
          <div class="emr-row emr-row-vau">${vau}</div>
          <div class="emr-row emr-row-aud">${aud}</div>
          <div class="emr-row emr-row-drive">${drv}</div>
        </div>
      </div>
      <input type="file" hidden accept="image/*,video/*,audio/*">`;
    this.fileInput = this.root.querySelector("input[type=file]");
    this.fileInput.onchange = (e) => {
      const files = [...(e.target.files || [])];
      const slot = this._pendingSlot;
      this._pendingSlot = null; e.target.value = "";
      if (files.length && slot)
        this.handleFiles(files, slot).catch(err => {
          console.error("[EMR] handleFiles error:", err);
          this.status("Import error: " + err.message);
        });
    };

    this.root.querySelector('[data-a="clearall"]').onclick = () => {
      this.mats = {}; this.slots = {}; this._waves = {}; this.updateState(); this.render(); this.status("Cleared");
    };
    const grid = this.root.querySelector(".emr-grid");
    grid.addEventListener("dragenter", (e) => { e.preventDefault(); });
    grid.addEventListener("dragover", (e) => { e.preventDefault(); e.stopPropagation(); });
    grid.addEventListener("drop", (e) => {
      e.preventDefault(); e.stopPropagation();
      const files = filesFromDataTransfer(e.dataTransfer);
      if (files.length)
        this.handleFiles(files, e.target.closest?.(".emr-slot")?.dataset.slot || null).catch(err => {
          console.error("[EMR] handleFiles error:", err);
          this.status("Import error: " + err.message);
        });
    });

    for (const el of this.root.querySelectorAll(".emr-slot")) {
      const id = el.dataset.slot, def = SLOT_MAP[id];
      el.addEventListener("dragenter", (e) => { e.preventDefault(); });
      el.addEventListener("dragstart", (e) => {
        if (!this.slots[id]) { e.preventDefault(); return; }
        this._dragSlot = id;
        e.dataTransfer.setData("text/emr", id); e.dataTransfer.effectAllowed = "move";
        el.classList.add("drag-src");
      });
      el.addEventListener("dragend", () => {
        this._dragSlot = null; el.classList.remove("drag-src");
        this.root.querySelectorAll(".emr-slot.drop-ok").forEach(x => x.classList.remove("drop-ok"));
      });
      el.addEventListener("dragover", (e) => {
        e.preventDefault(); e.stopPropagation();
        const hasFiles = [...(e.dataTransfer?.types || [])].includes("Files");
        el.classList.add("drop-ok");
        e.dataTransfer.dropEffect = hasFiles ? "copy" : "move";
      });
      el.addEventListener("dragleave", () => el.classList.remove("drop-ok"));
      el.addEventListener("drop", (e) => {
        e.preventDefault(); e.stopPropagation(); el.classList.remove("drop-ok");
        const files = filesFromDataTransfer(e.dataTransfer);
        if (files.length) {
          this.handleFiles(files, id).catch(err => {
            console.error("[EMR] handleFiles error:", err);
            this.status("Import error: " + err.message);
          });
          return;  
        }
        else if ([...(e.dataTransfer?.types || [])].includes("Files")) {
          this.status("Drop contained no readable files — drag real files from Explorer");
        }
        if (this._dragSlot && this._dragSlot !== id && SLOT_MAP[this._dragSlot].kind === def.kind) {
          const tmp = this.slots[id]; this.slots[id] = this.slots[this._dragSlot]; this.slots[this._dragSlot] = tmp;
          this._dragSlot = null; this.updateState(); this.render(); this.status("Swapped");
        }
      });

      el.addEventListener("click", (e) => {
        if (e.target.closest(".emr-iconbtn")) return;
        if (this.slots[id]) return;
        const pv = this._pairedVideoSlotId(id);
        if (pv) { this.openEditor(pv); return; }   
        this._pendingSlot = id; this.fileInput.accept = KIND_ACCEPT[def.kind]; this.fileInput.click();
      });
      el.querySelector(".emr-edit").onclick = () => this.openEditor(id);
      el.querySelector(".emr-del").onclick = () => { delete this.slots[id]; this.updateState(); this.render(); };
      el.addEventListener("contextmenu", (e) => {
        e.preventDefault(); e.stopPropagation();
        if (this.slots[id]) {
          this.showMenu(e.clientX, e.clientY, [
            ["Clear this slot", () => { delete this.slots[id]; this.updateState(); this.render(); }],
            ["Reset edits", () => { const m = this.mats[this.slots[id].mat];
              this.slots[id].edit = this.defaultEdit(m.kind, m); this.updateState(); this.render(); }],
          ]);
        } else {
          const pv = this._pairedVideoSlotId(id);
          if (!pv) return;
          this.showMenu(e.clientX, e.clientY, [
            ["Open paired video editor", () => this.openEditor(pv)],
            ["Replace with independent audio…", () => { this._pendingSlot = id;
              this.fileInput.accept = KIND_ACCEPT.audio; this.fileInput.click(); }],
          ]);
        }
      });
    }
  }
  showMenu(x, y, items) {
    document.querySelectorAll(".emr-menu").forEach(m => m.remove());
    const m = document.createElement("div"); m.className = "emr-menu";
    for (const [t, fn] of items) { const d = document.createElement("div"); d.textContent = t; d.onclick = () => { fn(); m.remove(); }; m.appendChild(d); }
    document.body.appendChild(m);
    const r = m.getBoundingClientRect();
    m.style.left = Math.min(x, innerWidth - r.width - 8) + "px";
    m.style.top = Math.min(y, innerHeight - r.height - 8) + "px";
    setTimeout(() => document.addEventListener("click", () => m.remove(), { once: true }), 0);
  }

  async handleFiles(files, targetId) {
    console.log("[EMR] handleFiles:", files.map(f => `${f.name} (${f.type || "?"})`));
    let cursor = targetId ? Math.max(0, SLOT_ORDER.indexOf(targetId)) : 0;
    let placed = 0, skipped = 0, failed = 0, first = true;
    for (const f of files) {
      const kind = guessKind(f);
      if (!kind) { skipped++; console.warn("[EMR] unsupported file:", f.name, f.type); continue; }
      let slotId = null;
      if (first && targetId && SLOT_MAP[targetId]?.kind === kind) slotId = targetId;
      first = false;
      if (!slotId) {
        const len = SLOT_ORDER.length;
        for (let k = 0; k < len; k++) {
          const cand = SLOT_ORDER[(cursor + k) % len];
          if (SLOT_MAP[cand].kind === kind && !this.slots[cand]) { slotId = cand; break; }
        }
      }
      if (!slotId) { skipped++; this.status(`No free ${kind} slot for ${f.name}`); continue; }
      cursor = SLOT_ORDER.indexOf(slotId) + 1;
      const mat = await this.upload(f);
      if (mat && this.assign(slotId, mat)) { placed++; this.render(); }
      else failed++;
    }
    this.updateState(); this.render();
    this.status(`Imported ${placed}${failed ? ` · failed ${failed}` : ""}${skipped ? ` · skipped ${skipped}` : ""}`);
  }
  async upload(file) {
    this.status(`Uploading ${file.name}…`);
    const fd = new FormData(); fd.append("file", file);
    try {
      const r = await fetch("/element_multi_ref/upload", { method: "POST", body: fd });
      let d = null; try { d = await r.json(); } catch (_) {}
      if (!r.ok || !d || d.error) {
        this.status(`Upload failed: ${(d && d.error) || r.status}`);
        console.warn("[EMR] upload failed:", file.name, r.status, d);
        return null;
      }
      const mat = { id: "m_" + Math.random().toString(36).slice(2, 9),
                    kind: d.kind, path: d.path, media: d.media || {}, _wave: d.waveform || [] };
      this.mats[mat.id] = mat;
      return mat;
    } catch (err) { this.status("Upload error: " + err.message); return null; }
  }


  assign(slotId, mat) {
    if (SLOT_MAP[slotId].kind !== mat.kind) return false;
    const slot = { mat: mat.id, edit: this.defaultEdit(mat.kind, mat) };
    if (mat.kind === "video") slot.with_audio = !!mat.media.has_audio;
    this.slots[slotId] = slot;
    return true;
  }
  _pairedVideoSlotId(audioSlotId) {
    if (!audioSlotId?.startsWith("ref_video_audio_")) return null;
    const vid = "ref_video_" + audioSlotId.slice(-1);
    const vs = this.slots[vid];
    if (!vs) return null;
    const vm = this.mats[vs.mat];
    return (vm && vm.kind === "video" && vs.with_audio && vm.media?.has_audio) ? vid : null;
  }
  openEditor(slotId) {
    let slot = this.slots[slotId];
    if (!slot) {                       
      const pv = this._pairedVideoSlotId(slotId);
      if (!pv) return;
      slotId = pv; slot = this.slots[slotId];
    }
    const mat = this.mats[slot.mat]; if (!mat) { this.status("Material missing — re-import"); return; }
    const apply = (edit) => {
      slot.edit = edit;
      this._editVer[slotId] = (this._editVer[slotId] || 0) + 1;
      this.updateState(); this.render(); this.status("Edit applied");
    };

    if (mat.kind === "image") ImageEditor.open(mat, slot, apply);
    else AVEditor.open(mat, slot, apply);
  }

  render() {
    const useCount = {};
    for (const s of Object.values(this.slots)) if (s?.mat) useCount[s.mat] = (useCount[s.mat] || 0) + 1;
    for (const el of this.root.querySelectorAll(".emr-slot")) {
      const id = el.dataset.slot, def = SLOT_MAP[id];
      const slot = this.slots[id];
      el.draggable = !!slot;
      el.querySelector(".emr-badge")?.remove();
	  el.querySelector(".emr-del").style.display = "";
      const media = el.querySelector(".emr-media");
      if (!slot) {
        const pv = this._pairedVideoSlotId(id);
        if (pv) {
          el.querySelector(".emr-del").style.display = "none";
          const vslot = this.slots[pv], vm = this.mats[vslot.mat];
          media.innerHTML = `<canvas class="emr-wave"></canvas><span class="emr-pairtag"> from ${pv}  </span>`;
          const cv = media.querySelector("canvas");

          const draw = () => {
            const pts = vm._wave || [];
            if (!pts.length) return;
            const fps = vm.media?.fps || 24;
            const dur = vm.media?.audio_duration || vm.media?.duration || (vm.media?.total_frames || 0) / fps || 1;
            const tr = (Array.isArray(vslot.edit?.trim) && vslot.edit.trim.length === 2) ? vslot.edit.trim : [0, Math.round(dur * fps)];
            const q0 = Math.max(0, Math.min(1, (tr[0] / fps) / dur));
            const q1 = Math.max(q0 + 1e-4, Math.min(1, (tr[1] / fps) / dur));
            drawWaveCanvas(cv, pts.slice(Math.floor(q0 * (pts.length - 1)), Math.max(2, Math.ceil(q1 * (pts.length - 1)))));
          };
          if (vm._wave?.length) draw();
          else fetch(`/element_multi_ref/media_info?p=${encodeURIComponent(vm.path)}`)
            .then(r => r.json()).then(d => { vm._wave = d.waveform || []; if (!this.slots[id]) draw(); })
            .catch(() => {});
        } else {
            media.innerHTML = '<span class="emr-empty">Drop or click to add</span>';
        }
        continue;
      }

      const mat = this.mats[slot.mat];
      if (!mat) { media.innerHTML = '<span class="emr-empty">Material missing — click ✕ to remove</span>'; continue; }
      if (useCount[mat.id] > 1) {
        const b = document.createElement("span"); b.className = "emr-badge"; b.textContent = "×" + useCount[mat.id];
        el.appendChild(b);
      }
      if (mat.kind === "image") {
        const e = slot.edit || {};
        let u = previewUrl(mat.path, -1, 256);         
        if (e.crop) u += `&crop=${e.crop.map(v => Math.round(v)).join(",")}`;
        if (e.strokes_file) u += `&strokes=${encodeURIComponent(e.strokes_file)}`;
        u += `&v=${this._editVer?.[id] || 0}`;
        media.innerHTML = `<img class="emr-thumb" src="${u}" draggable="false" onerror="this.style.opacity=.2">`;
      } else if (mat.kind === "video") {
        const tot = mat.media.total_frames || 1;
        let f = slot.edit?.trim?.[0];
        if (!Number.isFinite(f)) f = 0;
        f = Math.max(0, Math.min(tot - 1, Math.round(f)));
        const u = `${previewUrl(mat.path, f, 256)}&v=${this._editVer?.[id] || 0}`;
        media.innerHTML = `<img class="emr-thumb" src="${u}" draggable="false" onerror="this.style.opacity=.2">`;
      } else {
        media.innerHTML = `<canvas width="240" height="64" style="width:100%;height:64px;border-radius:6px;background:#0d1119;display:block"></canvas>`;
        const cv = media.querySelector("canvas");
        const drawW = (pts) => {
          const ctx = cv.getContext("2d"), W = cv.width, H = cv.height;
          ctx.clearRect(0, 0, W, H);
          if (!pts?.length) return;
          const total = Math.max(0.01, mat.media.duration || 1);
          const tr = slot.edit?.trim || [0, total];
          const a = Math.max(0, Math.min(1, tr[0] / total)), b = Math.max(a + 0.01, Math.min(1, tr[1] / total));
          const i0 = Math.floor(a * (pts.length - 1)), i1 = Math.ceil(b * (pts.length - 1));
          const n = Math.max(2, i1 - i0), mid = H / 2, amp = H / 2 - 3;
          ctx.beginPath();
          for (let i = 0; i < n; i++) { const x = i / (n - 1) * W, y = mid - (pts[i0 + i] || 0) * amp; i ? ctx.lineTo(x, y) : ctx.moveTo(x, y); }
          for (let i = n - 1; i >= 0; i--) { const x = i / (n - 1) * W, y = mid + (pts[i0 + i] || 0) * amp; ctx.lineTo(x, y); }
          ctx.closePath(); ctx.fillStyle = "rgba(90,173,90,.45)"; ctx.fill();
          ctx.strokeStyle = "#5aad5a"; ctx.stroke();
        };
        if (mat._wave?.length) drawW(mat._wave);
        else fetch(`/element_multi_ref/media_info?p=${encodeURIComponent(mat.path)}`)
          .then(r => r.json()).then(d => { mat._wave = d.waveform || []; drawW(mat._wave); }).catch(() => {});
      }
    }
  }
  updateState() {
    const nodeId = this.node.__nodeId !== undefined ? this.node.__nodeId : this.node.id;
    const payload = { version: 2, _node_id: nodeId, materials: this.mats, slots: this.slots };
    const mats = JSON.parse(JSON.stringify(payload.materials));
    for (const m of Object.values(mats)) delete m._wave;
    payload.materials = mats;
    if (this.widget) {
      this.widget.value = JSON.stringify(payload);
      this.widget.callback?.(this.widget.value);
    }
    this.node.setDirtyCanvas?.(true, true);
  }
  reloadFromWidget() {
    let saved = {};
    try { saved = JSON.parse(this.widget?.value || "{}"); } catch (_) {}
    this.mats = saved.materials || this.mats;
    this.slots = saved.slots || this.slots;
    this.render();
  }
}

/* ================= 注册 ================= */
app.registerExtension({
  name: "Element.MultiRef",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (nodeData.name !== "ElementMultiRef") return;
    installStyles();
    const BODY_PAD = 8, FALLBACK_H = 640;
    const origCreated = nodeType.prototype.onNodeCreated;
    nodeType.prototype.onNodeCreated = function () {
      const result = origCreated?.apply(this, arguments);
      this.__nodeId = this.id;
      const hideWidget = (w) => {
        if (!w) return;
        w.hidden = true; if (!w.options) w.options = {}; w.options.hidden = true;
        if (w.computeSize) w.computeSize = () => [0, -4];
        w.draw = function () {};
        const el = w.element || w.inputEl;
        if (el) { el.style.display = "none"; if (el.parentElement) el.parentElement.style.display = "none"; }
      };
      hideWidget(this.widgets?.find(w => w.name === "refs_data"));
      const root = document.createElement("div");
      const domWidget = this.addDOMWidget("multi_ref_ui", "div", root, { serialize: false, hideOnZoom: false });
      const widget = this.widgets?.find(w => w.name === "refs_data");
      this.__emr = new MultiRefUI(this, root, widget);
      let panelH = FALLBACK_H;
      const measure = () => {
        const p = root.firstElementChild;
        if (!p || !root.isConnected) return 0;
        const prev = p.style.height; p.style.height = "auto";
        const h = Math.ceil(p.offsetHeight); p.style.height = prev;
        return h > 100 ? h : 0;
      };
      panelH = measure() || FALLBACK_H;
      domWidget.computeSize = (w) => [Math.max(100, (this.size?.[0] || w || 900) - 20), panelH];
      this.size = [Math.max(this.size?.[0] || 0, 920), this.computeSize()[1] - BODY_PAD];
      this.onResize = () => { this.size[1] = this.computeSize()[1] - BODY_PAD; };
      requestAnimationFrame(() => {
        const h = measure();
        if (h && Math.abs(h - panelH) > 2) { panelH = h; this.size[1] = this.computeSize()[1] - BODY_PAD; this.setDirtyCanvas?.(true, true); }
      });
      return result;
    };
    const origConfigure = nodeType.prototype.onConfigure;
    nodeType.prototype.onConfigure = function () {
      const r = origConfigure?.apply(this, arguments);
      this.__nodeId = this.id;
      const h = this.computeSize()[1] - BODY_PAD;
      if (Math.abs((this.size?.[1] || 0) - h) > 2) this.size[1] = h;
      if (this.__emr) setTimeout(() => this.__emr.reloadFromWidget(), 50);
      return r;
    };
    const origRemoved = nodeType.prototype.onRemoved;
    nodeType.prototype.onRemoved = function () {
      if (this.__emr) {
        try { this.__emr._ro?.disconnect(); } catch (_) {}
        this.__emr = null;
      }
      return origRemoved?.apply(this, arguments);
    };
  },
});
