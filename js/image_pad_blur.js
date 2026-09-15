import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";
import { $el } from "../../scripts/ui.js";

const NODE_NAMES = ["ImagePadBlur_Element", "ImagePadBlur"];
const NODE_TITLE = "Image Pad & Blur";
const isTargetNode = (name, title) => NODE_NAMES.includes(name) || (title === NODE_TITLE);

const ALWAYS_HIDDEN = [
  "advanced_mode", "alignment", "x_offset", "y_offset",
  "left", "top", "right", "bottom",
  "feathering", "content_blur", "pad_mode", "background_color",
  "scale_width", "scale_height", "feather_edges", "mask_replace",
];

// ====================================================================
// 状态模型：
//   - zoom_w / zoom_h       : 宽/高缩放倍数（相对基准尺寸，按比例记录）
//   - x_offset / y_offset   : target模式位移（绝对像素）
//   - left/top/right/bottom : manual模式四边边距（绝对像素）
//   绝对宽高由 基准×zoom 派生，仅用于显示；Python端用 ui_data 里的 zoom
//   与执行时的真实输入尺寸派生 scale（无任何回退）。
//   播放按钮 = 只跑本节点+上游，
//   Python缓存源图 → executed消息 → 画布刷新。
// ====================================================================
const DEFAULT_STATE = {
  alignment: "center",
  zoom_w: 1.0, zoom_h: 1.0,
  x_offset: 0, y_offset: 0,
  left: 0, top: 0, right: 0, bottom: 0,
  feathering: 50,
  content_blur: 0,
  pad_mode: "constant",
  background_color: "#000000",
  lock: true,
  feather_edges: { left: true, top: true, right: true, bottom: true },
  mask_replace: false,
  src_w: 0, src_h: 0,
};

const ALIGN_GRID = [
  ["top-left", "top", "top-right"],
  ["left", "center", "right"],
  ["bottom-left", "bottom", "bottom-right"],
];

const S = `fill="none" stroke="#fff" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"`;
const ICON = {
  play: `<svg viewBox="0 0 24 24"><polygon points="7 4 20 12 7 20" fill="#fff"/></svg>`,
  fit: `<svg viewBox="0 0 24 24" ${S}><path d="M8 3H5a2 2 0 0 0-2 2v3"/><path d="M21 8V5a2 2 0 0 0-2-2h-3"/><path d="M3 16v3a2 2 0 0 0 2 2h3"/><path d="M16 21h3a2 2 0 0 0 2-2v-3"/></svg>`,
  lock: `<svg viewBox="0 0 24 24" ${S}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 8 0v4"/></svg>`,
  unlock: `<svg viewBox="0 0 24 24" ${S}><rect x="5" y="11" width="14" height="10" rx="2"/><path d="M8 11V7a4 4 0 0 1 7.9-.9"/></svg>`,
  constant: `<svg viewBox="0 0 24 24" ${S}><rect x="6" y="6" width="12" height="12" rx="1.5" fill="#fff" fill-opacity="0.25"/><rect x="6" y="6" width="12" height="12" rx="1.5"/></svg>`,
  edge: `<svg viewBox="0 0 24 24" ${S}><rect x="6" y="6" width="12" height="12" rx="1"/><line x1="1" y1="12" x2="6" y2="12"/><line x1="18" y1="12" x2="23" y2="12"/><line x1="12" y1="1" x2="12" y2="6"/><line x1="12" y1="18" x2="12" y2="23"/></svg>`,
  reflect: `<svg viewBox="0 0 24 24" ${S}><path d="M12 2v20" stroke-dasharray="2 3"/><path d="M9 7L3 12l6 5V7z" fill="#fff" fill-opacity="0.25"/><path d="M15 7l6 5-6 5V7z"/></svg>`,
  stretch: `<svg viewBox="0 0 24 24" ${S}><path d="M15 3h6v6"/><path d="M9 21H3v-6"/><path d="M3 21l7-7"/></svg>`,
  reset: `<svg viewBox="0 0 24 24" ${S}><path d="M3 12a9 9 0 1 0 9-9 9.75 9.75 0 0 0-6.74 2.74L3 8"/><path d="M3 3v5h5"/></svg>`,
  maskoff: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="8.5" fill="none" stroke="currentColor" stroke-width="2.2"/></svg>`,
  maskon: `<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="9" fill="currentColor"/><path d="M12 3a9 9 0 0 1 0 18Z" fill="#1b1b1b" fill-opacity="0.35"/></svg>`,
};

const CSS = `
.eipb-container { display:flex; flex-direction:column; width:100%; height:100%; min-height:230px; background:#1b1b1b; font-family:sans-serif; user-select:none; -webkit-user-select:none; overflow:hidden; pointer-events:none; }
.eipb-row { display:flex; flex-direction:row; align-items:center; gap:6px; padding:5px 8px; background:#242424; flex-wrap:nowrap; white-space:nowrap; overflow:hidden; flex:0 0 auto; pointer-events:none; }
.eipb-spacer { flex:1 1 auto; min-width:4px; }
.eipb-container button, .eipb-container input { pointer-events:auto; }
.eipb-btn { background:transparent; border:1px solid transparent; padding:3px; cursor:pointer; border-radius:4px; width:26px; height:26px; display:flex; align-items:center; justify-content:center; flex:0 0 auto; outline:none; }
.eipb-btn:focus, .eipb-btn:focus-visible { outline:none; box-shadow:none; }
.eipb-btn:hover { background:#333; }
.eipb-btn svg { width:16px; height:16px; }
.eipb-btn.active { background:#007acc33; border-color:#007acc; }
.eipb-maskrep { color:#888; }
.eipb-maskrep:hover { background:#333; color:#aaa; }
.eipb-maskrep.active, .eipb-maskrep.active:focus, .eipb-maskrep.active:focus-visible { background:#0a66c2 !important; border-color:#3b96ff !important; box-shadow:none !important; color:#3b96ff; }
.eipb-maskrep.active:hover { background:#1a75d4 !important; }
.eipb-sep { width:1px; height:18px; background:#3a3a3a; flex:0 0 auto; }
.eipb-color { width:22px; height:22px; padding:0; border:1px solid #555; border-radius:4px; background:none; cursor:pointer; flex:0 0 auto; }
.eipb-num { width:48px; height:22px; background:#1a1a1a; color:#ddd; border:1px solid #444; border-radius:4px; padding:0 3px; font-size:11px; text-align:center; flex:0 0 auto; }
.eipb-x { color:#666; font-size:11px; flex:0 0 auto; }
.eipb-range { width:64px; height:4px; -webkit-appearance:none; appearance:none; background:transparent; cursor:pointer; flex:0 0 auto; }
.eipb-range::-webkit-slider-runnable-track { height:3px; background:#444; border-radius:2px; }
.eipb-range::-webkit-slider-thumb { -webkit-appearance:none; width:12px; height:12px; background:#007acc; border-radius:50%; margin-top:-4.5px; }
.eipb-lbl { color:#888; font-size:10px; flex:0 0 auto; }
.eipb-canvas-wrap { position:relative; flex:1 1 auto; overflow:hidden; background:#121212; min-height:80px; pointer-events:none; }
.eipb-canvas { position:absolute; inset:0; width:100%; height:100%; cursor:default; touch-action:none; pointer-events:auto; }
.eipb-hint { color:#666; font-size:10px; padding:3px 8px; background:#1f1f1f; white-space:nowrap; overflow:hidden; text-overflow:ellipsis; flex:0 0 auto; pointer-events:none; }
.eipb-align { display:grid; grid-template-columns:repeat(3, 10px); grid-template-rows:repeat(3, 10px); gap:3px; padding:4px; border:1px solid #3a3a3a; border-radius:5px; background:#1a1a1a; flex:0 0 auto; pointer-events:none; }
.eipb-align-dot { width:10px; height:10px; border-radius:50%; background:#555; cursor:pointer; padding:0; border:none; display:block; }
.eipb-align-dot:hover { background:#888; }
.eipb-align-dot.active { background:#007acc; box-shadow:0 0 4px #007acc; }
.eipb-edgegrp { display:grid; grid-template-columns:8px 1fr 8px; grid-template-rows:8px 1fr 8px; gap:3px; width:46px; height:46px; box-sizing:border-box; border:1px solid #3a3a3a; border-radius:5px; background:#1a1a1a; flex:0 0 auto; padding:0; pointer-events:none; }
.eipb-edge { background:transparent; border:1.5px solid #666; border-radius:999px; padding:0; cursor:pointer; min-width:0; min-height:0; }
.eipb-edge-t { grid-area:1/2; }
.eipb-edge-b { grid-area:3/2; }
.eipb-edge-l { grid-area:2/1; }
.eipb-edge-r { grid-area:2/3; }
.eipb-edge:hover { border-color:#999; }
.eipb-edge.active { border-color:#007acc; background:#007acc33; box-shadow:0 0 4px #007acc66; }
.eipb-play { background:#1D4483 !important; border:1px solid #3b96ff !important; box-shadow:0 1px 4px rgba(10,102,194,.45); }
.eipb-play:hover { background:#1a75d4 !important; border-color:#5aa9ff !important; box-shadow:0 1px 6px rgba(26,117,212,.6); }
.eipb-play:active { background:#084e99 !important; border-color:#3b96ff !important; box-shadow:0 0 0 3px rgba(59,150,255,.25); }
.eipb-play.running { background:#084e99 !important; border-color:#5aa9ff !important; cursor:progress; animation:eipb-pulse 1s ease-in-out infinite; }
.eipb-play.running:hover { background:#0a5cb0 !important; }
@keyframes eipb-pulse {
  0%,100% { box-shadow:0 0 0 0 rgba(59,150,255,.55); }
  50%     { box-shadow:0 0 0 6px rgba(59,150,255,0); }
}
.eipb-spin { width:16px; height:16px; border:2px solid rgba(255,255,255,.35); border-top-color:#fff; border-radius:50%; animation:eipb-rot .7s linear infinite; flex:0 0 auto; }
@keyframes eipb-rot { to { transform:rotate(360deg); } }

`;

app.registerExtension({
  name: "element_easy.ImagePadBlur",
  async beforeRegisterNodeDef(nodeType, nodeData) {
    if (!isTargetNode(nodeData.name, nodeData.display_name)) return;
    const prevOnExecuted = nodeType.prototype.onExecuted;
    nodeType.prototype.onExecuted = function (message) {
      if (prevOnExecuted) prevOnExecuted.apply(this, arguments);
      try { this.__eipbOnExecuted?.(message); } catch (e) {}
    };
    $el("style", { textContent: CSS, parent: document.head });
  },
  async nodeCreated(node) {
    if (!isTargetNode(node.comfyClass, node.title)) return;
    if (node.__eipb_setup) return;
    node.__eipb_setup = true;
    try { setupPadBlurUI(node); } catch (e) { console.error("[ImagePadBlur] setup failed:", e); }
  },
});

function setupPadBlurUI(node) {
  const W = (n) => node.widgets?.find(w => w.name === n);

  // ========== ui_data：隐藏原生widget但保留value提交 ==========
  // Python optional STRING → ComfyUI 自动生成原生 STRING widget。
  // 隐藏UI（type=hidden + draw空 + inputEl隐藏），value 由状态接管；
  // serializeValue 保证提交瞬间写入最新JSON（zoom 随 prompt 提交）。
  let uiDataW = node.widgets?.find(w => w.name === "ui_data");
  if (!uiDataW) {
    uiDataW = {
      name: "ui_data", type: "hidden", value: "",
      hidden: true, options: { hidden: true },
      computeSize: () => [0, -4], draw: () => {},
    };
    node.widgets.push(uiDataW);
  } else {
    uiDataW.type = "hidden";
    uiDataW.hidden = true;
    if (!uiDataW.options) uiDataW.options = {};
    uiDataW.options.hidden = true;
    uiDataW.computeSize = () => [0, -4];
    uiDataW.draw = () => {};
    if (uiDataW.inputEl) {
      uiDataW.inputEl.style.display = "none";
      if (uiDataW.inputEl.parentElement) uiDataW.inputEl.parentElement.style.display = "none";
    }
    const inIdx = node.inputs?.findIndex(i => i.name === "ui_data");
    if (inIdx !== -1) {
      try { node.removeInput(inIdx); } catch (e) { node.inputs?.splice(inIdx, 1); }
    }
  }

  const hideForever = (w) => {
    if (!w) return;
    w.hidden = true;
    if (!w.options) w.options = {};
    w.options.hidden = true;
    if (w.computeSize) w.computeSize = () => [0, -4];
    w.draw = function () {};
    const el = w.element || w.inputEl;
    if (el) {
      el.style.display = "none";
      if (el.parentElement) el.parentElement.style.display = "none";
    }
  };
  ALWAYS_HIDDEN.forEach(n => hideForever(W(n)));

  const removeGhostInputs = () => {
    if (!Array.isArray(node.inputs)) return;
    for (let i = node.inputs.length - 1; i >= 0; i--) {
      const inp = node.inputs[i];
      if (inp && ALWAYS_HIDDEN.includes(inp.name)) {
        try { if (inp.link != null) node.disconnectInput(i); } catch (e) {}
        try { node.removeInput(i); } catch (e) { node.inputs.splice(i, 1); }
      }
    }
  };
  removeGhostInputs();

  // ========== 状态（白名单解析）==========
  const parseEdges = (v) => {
    const e = { left: true, top: true, right: true, bottom: true };
    if (typeof v === "string" && v) {
      const s = v.toLowerCase();
      if (s.includes("none")) { e.left = e.top = e.right = e.bottom = false; }
      else {
        e.left = s.includes("left"); e.right = s.includes("right");
        e.top = s.includes("top"); e.bottom = s.includes("bottom");
      }
    } else if (v && typeof v === "object") {
      ["left", "top", "right", "bottom"].forEach(k => { if (k in v) e[k] = !!v[k]; });
    }
    return e;
  };

  let state = { ...DEFAULT_STATE };

  const loadState = () => {
    let parsed = null;
    try {
      const raw = uiDataW.value;
      if (raw && typeof raw === "string" && raw.startsWith("{")) parsed = JSON.parse(raw);
    } catch (e) {}
    const pickNum = (v, d) => { const n = Number(v); return Number.isFinite(n) ? n : d; };
    state = {
      alignment: (parsed && typeof parsed.alignment === "string") ? parsed.alignment : "center",
      zoom_w: parsed ? Math.max(0.001, pickNum(parsed.zoom_w, 1)) : 1,
      zoom_h: parsed ? Math.max(0.001, pickNum(parsed.zoom_h, 1)) : 1,
      x_offset: parsed ? Math.round(pickNum(parsed.x_offset, 0)) : 0,
      y_offset: parsed ? Math.round(pickNum(parsed.y_offset, 0)) : 0,
      left: parsed ? Math.max(0, Math.round(pickNum(parsed.left, 0))) : 0,
      top: parsed ? Math.max(0, Math.round(pickNum(parsed.top, 0))) : 0,
      right: parsed ? Math.max(0, Math.round(pickNum(parsed.right, 0))) : 0,
      bottom: parsed ? Math.max(0, Math.round(pickNum(parsed.bottom, 0))) : 0,
      feathering: parsed ? Math.max(0, Math.min(500, Math.round(pickNum(parsed.feathering, 50)))) : 50,
      content_blur: parsed ? Math.max(0, Math.min(500, Math.round(pickNum(parsed.content_blur, 0)))) : 0,
      pad_mode: (parsed && typeof parsed.pad_mode === "string") ? parsed.pad_mode : "constant",
      background_color: (parsed && typeof parsed.background_color === "string") ? parsed.background_color : "#000000",
      lock: parsed ? !!parsed.lock : true,
      feather_edges: parseEdges(parsed ? parsed.feather_edges : undefined),
      mask_replace: parsed ? !!parsed.mask_replace : false,
      src_w: parsed ? Math.max(0, Math.round(pickNum(parsed.src_w, 0))) : 0,
      src_h: parsed ? Math.max(0, Math.round(pickNum(parsed.src_h, 0))) : 0,
    };
  };

  // ========== 运行时变量 ==========
  let srcW = 1024, srcH = 1024, srcImg = null;
  let drag = null;
  let view = null;
  let srcSeq = 0;
  let srcLoadSeq = 0;
  let serverImg = null;
  let serverStamp = 0, localStamp = 0;
  let dirtyLocal = false;

  let lastSrcFp = null, lastMaskFp = null;
  let pollTimer = null;
  const POLL_MS = 700;

  // ========== 布局核心：基准 / 派生 ==========
  function numW(n) {
    const v = parseInt(W(n)?.value);
    return Number.isFinite(v) ? v : 0;
  }

  function baseDims() {
    const tw = numW("target_width"), th = numW("target_height");
    if (tw > 0 && th > 0 && (srcW > tw || srcH > th)) {
      const k = Math.min(tw / srcW, th / srcH);
      return { bw: Math.max(16, Math.round(srcW * k)), bh: Math.max(16, Math.round(srcH * k)) };
    }
    return { bw: Math.max(16, srcW), bh: Math.max(16, srcH) };
  }

  function deriveDims() {
    const { bw, bh } = baseDims();
    const zw = Number(state.zoom_w) || 1, zh = Number(state.zoom_h) || 1;
    let sw = Math.round(bw * zw);
    let sh = Math.round(bh * zh);
    if (Math.abs(zw - 1) < 0.004 && Math.abs(sw - srcW) <= 1) sw = srcW;
    if (Math.abs(zh - 1) < 0.004 && Math.abs(sh - srcH) <= 1) sh = srcH;
    sw = Math.max(16, Math.min(8192, sw));
    sh = Math.max(16, Math.min(8192, sh));
    return { bw, bh, sw, sh };
  }

  function axisModes() {
    return {
      x: numW("target_width") > 0 ? "target" : "manual",
      y: numW("target_height") > 0 ? "target" : "manual",
    };
  }

  const baseFor = (diff, axis) => {
    const a = state.alignment;
    if (axis === "h") {
      if (["left", "top-left", "bottom-left"].includes(a)) return 0;
      if (["right", "top-right", "bottom-right"].includes(a)) return diff;
      return Math.floor(diff / 2);
    }
    if (["top", "top-left", "top-right"].includes(a)) return 0;
    if (["bottom", "bottom-left", "bottom-right"].includes(a)) return diff;
    return Math.floor(diff / 2);
  };

  function sanitizeOffsets() {
    const d = deriveDims();
    const tw = numW("target_width"), th = numW("target_height");
    const V = 16;
    if (tw > 0) {
      const baseL = baseFor(tw - d.sw, "h");
      const lo = -(d.sw - V) - baseL;
      const hi = (tw - V) - baseL;
      if (state.x_offset < lo) state.x_offset = Math.round(lo);
      if (state.x_offset > hi) state.x_offset = Math.round(hi);
    }
    if (th > 0) {
      const baseT = baseFor(th - d.sh, "v");
      const lo = -(d.sh - V) - baseT;
      const hi = (th - V) - baseT;
      if (state.y_offset < lo) state.y_offset = Math.round(lo);
      if (state.y_offset > hi) state.y_offset = Math.round(hi);
    }
  }

  function layout() {
    const d = deriveDims();
    const am = axisModes();
    const tw = numW("target_width"), th = numW("target_height");
    let frameW, imgX;
    if (am.x === "target") {
      frameW = tw;
      imgX = baseFor(tw - d.sw, "h") + Math.round(state.x_offset);
    } else {
      frameW = d.sw + Math.round(state.left) + Math.round(state.right);
      imgX = Math.round(state.left);
    }
    let frameH, imgY;
    if (am.y === "target") {
      frameH = th;
      imgY = baseFor(th - d.sh, "v") + Math.round(state.y_offset);
    } else {
      frameH = d.sh + Math.round(state.top) + Math.round(state.bottom);
      imgY = Math.round(state.top);
    }
    return {
      mode: (am.x === "target" && am.y === "target") ? "target" : "manual",
      am, frameW, frameH, imgX, imgY,
      sw: d.sw, sh: d.sh, bw: d.bw, bh: d.bh,
    };
  }

  const edgesKey = () => {
    const e = state.feather_edges;
    return `${e.left ? 1 : 0}${e.top ? 1 : 0}${e.right ? 1 : 0}${e.bottom ? 1 : 0}`;
  };
  const hasAnyEdge = () => Object.values(state.feather_edges).some(Boolean);
  const edgesToString = () => {
    const parts = hasAnyEdge()
      ? ["left", "top", "right", "bottom"].filter(k => state.feather_edges[k])
      : ["none"];
    if (state.mask_replace) parts.push("replace");
    return parts.join(",");
  };

  const pushStateToWidgets = () => {
    const setW = (n, v) => { const w = W(n); if (w) w.value = v; };
    const am = axisModes();
    setW("alignment", state.alignment);
    setW("pad_mode", state.pad_mode);
    if (am.x === "target") {
      setW("x_offset", Math.round(state.x_offset));
      setW("left", 0); setW("right", 0);
    } else {
      setW("x_offset", 0);
      setW("left", Math.max(0, Math.round(state.left)));
      setW("right", Math.max(0, Math.round(state.right)));
    }
    if (am.y === "target") {
      setW("y_offset", Math.round(state.y_offset));
      setW("top", 0); setW("bottom", 0);
    } else {
      setW("y_offset", 0);
      setW("top", Math.max(0, Math.round(state.top)));
      setW("bottom", Math.max(0, Math.round(state.bottom)));
    }
    setW("feathering", state.feathering);
    setW("content_blur", state.content_blur);
    setW("background_color", state.background_color);
    setW("feather_edges", edgesToString());
    setW("mask_replace", !!state.mask_replace);
  };

  const serialize = () => {
    pushStateToWidgets();
    uiDataW.value = JSON.stringify(state);
    try { if (node.graph && node.graph.change) node.graph.change(); } catch (e) {}
  };
  const markInteractive = () => { dirtyLocal = true; };

  function syncSizeInputs() {
    const d = deriveDims();
    imgWInp.value = Math.round(d.sw);
    imgHInp.value = Math.round(d.sh);
  }

  // ========== DOM：顶栏 ==========
  const playBtn = $el("button.eipb-btn.eipb-play", { title: "Preview: run only this node + upstream chain to refresh source", innerHTML: ICON.play });
  const SPINNER_HTML = `<span class="eipb-spin"></span>`;
  const setPlayRunning = (on) => {
    playBtn.classList.toggle("running", on);
    playBtn.innerHTML = on ? SPINNER_HTML : ICON.play;
  };

  const colorInp = $el("input.eipb-color", { type: "color", value: "#000000", title: "Background color (constant mode)" });
  const imgWInp = $el("input.eipb-num", { type: "number", min: 16, max: 8192, title: "Image width in canvas (derived display; edits convert back to relative scale)" });
  const imgHInp = $el("input.eipb-num", { type: "number", min: 16, max: 8192, title: "Image height in canvas (derived display; edits convert back to relative scale)" });

  const fitBtn = $el("button.eipb-btn", { title: "Fit image to canvas (reset relative scale & offsets)", innerHTML: ICON.fit });
  fitBtn.onclick = () => {
    state.zoom_w = 1; state.zoom_h = 1;
    state.x_offset = 0; state.y_offset = 0;
    state.left = state.top = state.right = state.bottom = 0;
    syncSizeInputs(); serialize(); markInteractive(); redraw();
  };

  const lockBtn = $el("button.eipb-btn", { title: "Lock aspect ratio (Shift inverts while dragging)", innerHTML: ICON.lock });
  const syncLock = () => {
    lockBtn.classList.toggle("active", !!state.lock);
    lockBtn.innerHTML = state.lock ? ICON.lock : ICON.unlock;
  };
  lockBtn.onclick = () => {
    state.lock = !state.lock;
    if (state.lock) state.zoom_h = state.zoom_w;
    serialize(); syncLock(); markInteractive(); redraw();
  };

  const resetBtn = $el("button.eipb-btn", { title: "Reset", innerHTML: ICON.reset });

  const alignBtns = [];
  const alignGrid = $el("div.eipb-align", { title: "Alignment" });
  for (let r = 0; r < 3; r++) for (let c = 0; c < 3; c++) {
    const val = ALIGN_GRID[r][c];
    const b = $el("button.eipb-align-dot", { title: val });
    b.onclick = () => {
      state.alignment = val;
      state.x_offset = 0;
      state.y_offset = 0;
      serialize(); syncAlign(); markInteractive(); redraw();
    };
    alignBtns.push({ b, val });
    alignGrid.appendChild(b);
  }
  const syncAlign = () => alignBtns.forEach(({ b, val }) => b.classList.toggle("active", val === state.alignment));

  const edgeBtns = {};
  const edgeGroup = $el("div.eipb-edgegrp", { title: "Feather edges" });
  const EDGE_CLS = { top: "eipb-edge-t", bottom: "eipb-edge-b", left: "eipb-edge-l", right: "eipb-edge-r" };
  for (const edge of ["top", "left", "right", "bottom"]) {
    const b = $el(`button.eipb-edge.${EDGE_CLS[edge]}`, { title: `Feather ${edge} edge` });
    b.onclick = () => {
      state.feather_edges[edge] = !state.feather_edges[edge];
      serialize(); syncEdges(); markInteractive(); redraw();
    };
    edgeBtns[edge] = b;
    edgeGroup.appendChild(b);
  }
  const syncEdges = () => {
    for (const edge of ["top", "left", "right", "bottom"]) {
      edgeBtns[edge]?.classList.toggle("active", !!state.feather_edges[edge]);
    }
  };

  const topbar = $el("div.eipb-row", {}, [
    playBtn, $el("div.eipb-sep"), colorInp,
    imgWInp, $el("span.eipb-x", { textContent: "×" }), imgHInp,
    fitBtn, lockBtn, $el("div.eipb-sep"), resetBtn,
    $el("div.eipb-spacer"), edgeGroup, alignGrid,
  ]);

  // ========== DOM：底栏 ==========
  const MODES = ["constant", "edge", "reflect", "stretch"];
  const modeBtns = {};
  const mkModeBtn = (mode) => {
    const b = $el("button.eipb-btn", { title: mode, innerHTML: ICON[mode] });
    b.onclick = () => { state.pad_mode = mode; serialize(); syncModes(); markInteractive(); redraw(); };
    modeBtns[mode] = b;
    return b;
  };
  const syncModes = () => MODES.forEach(m => modeBtns[m]?.classList.toggle("active", state.pad_mode === m));

  const mkRange = (min, max, val, title) => $el("input.eipb-range", { type: "range", min, max, step: 1, value: val, title });
  const featherInp = mkRange(0, 500, state.feathering, "Feathering (per-edge, use edge toggles)");
  const blurInp = mkRange(0, 500, state.content_blur, "Background blur (applied to collage)");
  featherInp.oninput = (e) => { state.feathering = parseInt(e.target.value) || 0; serialize(); markInteractive(); redraw(); };
  blurInp.oninput = (e) => { state.content_blur = parseInt(e.target.value) || 0; serialize(); markInteractive(); redraw(); };

  const maskRepBtn = $el("button.eipb-btn.eipb-maskrep", {
    title: "Replace masked area with background in output image",
    innerHTML: state.mask_replace ? ICON.maskon : ICON.maskoff,
  });
  const syncMaskRep = () => {
    maskRepBtn.classList.toggle("active", !!state.mask_replace);
    maskRepBtn.innerHTML = state.mask_replace ? ICON.maskon : ICON.maskoff;
  };
  maskRepBtn.onclick = () => {
    state.mask_replace = !state.mask_replace;
    serialize(); syncMaskRep(); markInteractive(); redraw();
  };

  const bottombar = $el("div.eipb-row", {}, [
    mkModeBtn("constant"), mkModeBtn("edge"), mkModeBtn("reflect"), mkModeBtn("stretch"),
    $el("div.eipb-sep"),
    $el("span.eipb-lbl", { textContent: "Feather" }), featherInp,
    $el("span.eipb-lbl", { textContent: "Blur" }), blurInp,
    $el("div.eipb-spacer"), maskRepBtn,
  ]);

  const canvas = $el("canvas.eipb-canvas");
  const canvasWrap = $el("div.eipb-canvas-wrap", {}, [canvas]);
  const hint = $el("div.eipb-hint", { textContent: "Drag to move (px) · edges/corners to scale · Play = isolated preview run (refreshes source) · Scale stored as ratio, offsets as pixels" });
  const container = $el("div.eipb-container", {}, [topbar, canvasWrap, bottombar, hint]);
  container.style.position = "absolute";
  container.style.inset = "0";

  const wrapper = document.createElement("div");
  wrapper.style.position = "relative";
  wrapper.style.width = "100%";
  wrapper.style.height = "100%";
  wrapper.style.pointerEvents = "none";
  wrapper.appendChild(container);
  wrapper.addEventListener("wheel", (e) => {
    const t = e.target;
    if (t && /^(TEXTAREA|INPUT|SELECT)$/.test(t.tagName)) return;
    if (!app.canvasEl) return;
    const fwd = new WheelEvent("wheel", {
      clientX: e.clientX, clientY: e.clientY,
      deltaX: e.deltaX, deltaY: e.deltaY, deltaMode: e.deltaMode,
      ctrlKey: e.ctrlKey, shiftKey: e.shiftKey, altKey: e.altKey, metaKey: e.metaKey,
    });
    app.canvasEl.dispatchEvent(fwd);
    e.preventDefault();
    e.stopPropagation();
  }, { passive: false });

  const domWidget = node.addDOMWidget("eipb_ui", "div", wrapper, { serialize: false, hideOnZoom: false });
  if (domWidget?.element) {
    domWidget.element.style.width = "100%";
    domWidget.element.style.height = "100%";
    domWidget.element.style.display = "flex";
    setTimeout(() => {
      const p = domWidget.element.parentElement;
      if (p) {
        p.style.flex = "1";
        p.style.display = "flex";
        p.style.flexDirection = "column";
        p.style.overflow = "hidden";
      }
    }, 50);
  }

  // ========== 节点尺寸 ==========
  if (typeof node.id !== "number" || node.id < 0) node.size = [400, 420];
  const MIN_W = 380, MIN_H = 320;
  const origComputeSize = node.computeSize;
  node.computeSize = function () {
    let s = origComputeSize ? origComputeSize.apply(this, arguments) : [MIN_W, MIN_H];
    if (s[0] < MIN_W) s[0] = MIN_W;
    if (s[1] < MIN_H) s[1] = MIN_H;
    return s;
  };
  const origOnResize = node.onResize;
  node.onResize = function () {
    if (origOnResize) origOnResize.apply(this, arguments);
    requestAnimationFrame(resizeCanvas);
  };
  const ro = new ResizeObserver(() => requestAnimationFrame(resizeCanvas));
  ro.observe(container);

  function resizeCanvas() {
    const w = canvasWrap.clientWidth, h = canvasWrap.clientHeight;
    if (w < 2 || h < 2) return;
    canvas.width = w;
    canvas.height = h;
    redraw();
  }

  const toCanvas = (e) => {
    const r = canvas.getBoundingClientRect();
    const kx = r.width > 0 ? canvas.width / r.width : 1;
    const ky = r.height > 0 ? canvas.height / r.height : 1;
    return { x: (e.clientX - r.left) * kx, y: (e.clientY - r.top) * ky };
  };

  // ========== 离屏画布（本地快速管线）==========
  const bgCv = document.createElement("canvas");
  const fgCv = document.createElement("canvas");
  const mskCv = document.createElement("canvas");
  let fgCacheKey = "";

  function buildCollageReal(fw, fh, ox, oy, ix, iy, iw, ih) {
    const w = Math.max(1, Math.round(fw)), h = Math.max(1, Math.round(fh));
    bgCv.width = w; bgCv.height = h;
    const c = bgCv.getContext("2d");
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.filter = "none";
    c.clearRect(0, 0, w, h);
    if (state.pad_mode === "constant") {
      c.fillStyle = state.background_color || "#000";
      c.fillRect(0, 0, w, h);
      return;
    }
    if (state.pad_mode === "stretch") {
      if (srcImg) c.drawImage(srcImg, 0, 0, w, h);
      else { c.fillStyle = "#2c2c2c"; c.fillRect(0, 0, w, h); }
      return;
    }
    if (!srcImg) { c.fillStyle = "#2c2c2c"; c.fillRect(0, 0, w, h); return; }
    const pw = srcImg.naturalWidth || srcImg.width || srcW;
    const ph = srcImg.naturalHeight || srcImg.height || srcH;
    const X = ix - ox, Y = iy - oy;
    if (state.pad_mode === "edge") {
      const O = 1;
      const lw = X, rw = w - (X + iw);
      const th = Y, bh = h - (Y + ih);
      if (lw > 0) c.drawImage(srcImg, 0, 0, 1, ph, 0, Y, lw + O, ih);
      if (rw > 0) c.drawImage(srcImg, pw - 1, 0, 1, ph, X + iw - O, Y, rw + O, ih);
      if (th > 0) c.drawImage(srcImg, 0, 0, pw, 1, X, 0, iw, th + O);
      if (bh > 0) c.drawImage(srcImg, 0, ph - 1, pw, 1, X, Y + ih - O, iw, bh + O);
      if (lw > 0 && th > 0) c.drawImage(srcImg, 0, 0, 1, 1, 0, 0, lw + O, th + O);
      if (rw > 0 && th > 0) c.drawImage(srcImg, pw - 1, 0, 1, 1, X + iw - O, 0, rw + O, th + O);
      if (lw > 0 && bh > 0) c.drawImage(srcImg, 0, ph - 1, 1, 1, 0, Y + ih - O, lw + O, bh + O);
      if (rw > 0 && bh > 0) c.drawImage(srcImg, pw - 1, ph - 1, 1, 1, X + iw - O, Y + ih - O, rw + O, bh + O);
      c.drawImage(srcImg, X, Y, iw, ih);
      return;
    }
    const iMin = Math.floor((0 - X) / iw) - 1;
    const iMax = Math.floor((w - X) / iw) + 1;
    const jMin = Math.floor((0 - Y) / ih) - 1;
    const jMax = Math.floor((h - Y) / ih) + 1;
    for (let j = jMin; j <= jMax; j++) {
      for (let i = iMin; i <= iMax; i++) {
        if (i === 0 && j === 0) continue;
        const flipH = (((i % 2) + 2) % 2) === 1;
        const flipV = (((j % 2) + 2) % 2) === 1;
        c.save();
        if (flipH && flipV) {
          c.translate(X + (i + 1) * iw, Y + (j + 1) * ih);
          c.scale(-1, -1);
          c.drawImage(srcImg, 0, 0, iw, ih);
        } else if (flipH) {
          c.translate(X + (i + 1) * iw, Y + j * ih);
          c.scale(-1, 1);
          c.drawImage(srcImg, 0, 0, iw, ih);
        } else if (flipV) {
          c.translate(X + i * iw, Y + (j + 1) * ih);
          c.scale(1, -1);
          c.drawImage(srcImg, 0, 0, iw, ih);
        } else {
          c.drawImage(srcImg, X + i * iw, Y + j * ih, iw, ih);
        }
        c.restore();
      }
    }
    c.drawImage(srcImg, X, Y, iw, ih);
  }

  function buildFeathered(s, iw, ih) {
    const w = Math.max(1, Math.round(iw)), h = Math.max(1, Math.round(ih));
    const f = Math.max(1, state.feathering * s);
    const maskActive = isMaskConnected() && !!maskImg && !!state.mask_replace;
    const key = `${w}x${h}|f${f.toFixed(2)}|e${edgesKey()}|s${srcSeq}|k${maskActive ? maskSeq : -1}|r${state.mask_replace ? 1 : 0}`;
    if (key === fgCacheKey) return fgCv;
    fgCacheKey = key;
    fgCv.width = w; fgCv.height = h;
    const c = fgCv.getContext("2d", { willReadFrequently: true });
    c.setTransform(1, 0, 0, 1, 0, 0);
    c.clearRect(0, 0, w, h);
    if (srcImg) c.drawImage(srcImg, 0, 0, w, h);
    else { c.fillStyle = "#3a3a3a"; c.fillRect(0, 0, w, h); }
    const img = c.getImageData(0, 0, w, h);
    const d = img.data;
    if (state.feathering > 0 && hasAnyEdge()) {
      const e = state.feather_edges;
      const colR = new Float32Array(w), rowR = new Float32Array(h);
      for (let x = 0; x < w; x++) {
        let a = 1;
        if (e.left) a = Math.min(a, x / f);
        if (e.right) a = Math.min(a, (w - 1 - x) / f);
        colR[x] = a < 0 ? 0 : (a > 1 ? 1 : a);
      }
      for (let y = 0; y < h; y++) {
        let a = 1;
        if (e.top) a = Math.min(a, y / f);
        if (e.bottom) a = Math.min(a, (h - 1 - y) / f);
        rowR[y] = a < 0 ? 0 : (a > 1 ? 1 : a);
      }
      for (let y = 0, i = 0; y < h; y++) {
        const ry = rowR[y];
        for (let x = 0; x < w; x++, i += 4) {
          const rx = colR[x];
          const a = ry < rx ? ry : rx;
          if (a < 1) d[i + 3] = (d[i + 3] * a) | 0;
        }
      }
    }
    if (maskActive) {
      mskCv.width = w; mskCv.height = h;
      const mc = mskCv.getContext("2d", { willReadFrequently: true });
      mc.setTransform(1, 0, 0, 1, 0, 0);
      mc.clearRect(0, 0, w, h);
      mc.drawImage(maskImg, 0, 0, w, h);
      const md = mc.getImageData(0, 0, w, h).data;
      for (let px = 0, di = 3, mi = 0; px < w * h; px++, di += 4, mi += 4) {
        const m = md[mi] / 255;
        if (m > 0) d[di] = (d[di] * (1 - m)) | 0;
      }
    }
    c.putImageData(img, 0, 0);
    return fgCv;
  }

  function redraw() {
    const ctx = canvas.getContext("2d");
    const cw = canvas.width, ch = canvas.height;
    if (cw < 2 || ch < 2) return;
    ctx.setTransform(1, 0, 0, 1, 0, 0);
    ctx.filter = "none";
    ctx.fillStyle = "#121212";
    ctx.fillRect(0, 0, cw, ch);
    const L = layout();
    const pad = 14;
    const s = Math.min((cw - 2 * pad) / L.frameW, (ch - 2 * pad) / L.frameH, 4) || 0.01;
    const fw = L.frameW * s, fh = L.frameH * s;
    const ox = (cw - fw) / 2, oy = (ch - fh) / 2;
    if (!drag) view = { s, ox, oy, layout: L };
    const ix = ox + L.imgX * s, iy = oy + L.imgY * s;
    const iw = L.sw * s, ih = L.sh * s;
    const useServer = serverImg && !dirtyLocal && serverStamp >= localStamp;
    if (useServer) {
      ctx.save();
      ctx.beginPath();
      ctx.rect(ox, oy, fw, fh);
      ctx.clip();
      ctx.drawImage(serverImg, ox, oy, fw, fh);
      ctx.restore();
    } else {
      buildCollageReal(fw, fh, ox, oy, ix, iy, iw, ih);
      ctx.save();
      ctx.beginPath();
      ctx.rect(ox, oy, fw, fh);
      ctx.clip();
      if (state.content_blur > 0) ctx.filter = `blur(${Math.max(0.5, state.content_blur * s / 2)}px)`;
      ctx.drawImage(bgCv, ox, oy, fw, fh);
      ctx.filter = "none";
      const fg = buildFeathered(s, iw, ih);
      ctx.drawImage(fg, ix, iy, iw, ih);
      ctx.restore();
    }
    ctx.strokeStyle = "rgba(255,255,255,0.4)";
    ctx.lineWidth = 1;
    ctx.strokeRect(Math.round(ix) + 0.5, Math.round(iy) + 0.5, Math.max(1, Math.round(iw) - 1), Math.max(1, Math.round(ih) - 1));
    ctx.strokeStyle = "#57a8ff";
    ctx.setLineDash([5, 4]);
    ctx.strokeRect(ox + 0.5, oy + 0.5, fw, fh);
    ctx.setLineDash([]);
    const effL = Math.round(L.imgX), effT = Math.round(L.imgY);
    const effR = Math.round(L.frameW - L.sw - L.imgX), effB = Math.round(L.frameH - L.sh - L.imgY);
    ctx.fillStyle = "#8fd0ff";
    ctx.font = "11px monospace";
    ctx.textAlign = "left";
    ctx.textBaseline = "alphabetic";
    ctx.fillText(`L:${effL} T:${effT} R:${effR} B:${effB}`, ox + 6, oy + fh - 8);
    if (!srcImg && !useServer) {
      ctx.fillStyle = "#bbb";
      ctx.font = "12px sans-serif";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(`${Math.round(L.sw)} × ${Math.round(L.sh)}`, ix + iw / 2, iy + ih / 2);
    }
  }

  // ========== 命中检测 ==========
  function hitHandle(c) {
    if (!view) return null;
    const { s, ox, oy } = view;
    const L = view.layout;
    const ix = ox + L.imgX * s, iy = oy + L.imgY * s;
    const iw = L.sw * s, ih = L.sh * s;
    const t = Math.min(8, Math.max(4, Math.min(iw, ih) / 4));
    if (c.x < ix - t || c.x > ix + iw + t || c.y < iy - t || c.y > iy + ih + t) return null;
    const nearL = c.x <= ix + t, nearR = c.x >= ix + iw - t;
    const nearT = c.y <= iy + t, nearB = c.y >= iy + ih - t;
    if (nearL && nearT) return "nw";
    if (nearR && nearT) return "ne";
    if (nearL && nearB) return "sw";
    if (nearR && nearB) return "se";
    if (nearL) return "w";
    if (nearR) return "e";
    if (nearT) return "n";
    if (nearB) return "s";
    return "move";
  }
  const HANDLE_CURSOR = {
    w: "ew-resize", e: "ew-resize", n: "ns-resize", s: "ns-resize",
    nw: "nwse-resize", se: "nwse-resize", ne: "nesw-resize", sw: "nesw-resize", move: "move"
  };

  // ========== 手势（拖拽=像素位移；缩放=反推相对zoom）==========
  canvas.addEventListener("pointerdown", (e) => {
    if (!view) return;
    const c = toCanvas(e);
    const h = hitHandle(c);
    if (!h) return;
    const L = view.layout;
    drag = {
      v: view, handle: h, c0: c,
      x0: L.imgX, y0: L.imgY, w0: L.sw, h0: L.sh,
      fw: L.frameW, fh: L.frameH,
      am: L.am, bw: L.bw, bh: L.bh,
      baseL: baseFor(L.frameW - L.sw, "h"),
      baseT: baseFor(L.frameH - L.sh, "v"),
      pl0: state.left, pt0: state.top, pr0: state.right, pb0: state.bottom,
    };
    markInteractive();
    try { canvas.setPointerCapture(e.pointerId); } catch (err) {}
    e.preventDefault();
  });

  canvas.addEventListener("pointermove", (e) => {
    const c = toCanvas(e);
    if (!drag) {
      canvas.style.cursor = HANDLE_CURSOR[hitHandle(c)] || "default";
      return;
    }
    const g = drag;
    const dx = (c.x - g.c0.x) / g.v.s;
    const dy = (c.y - g.c0.y) / g.v.s;
    const hs = g.handle;

    if (hs === "move") {
      let nx = g.x0 + dx, ny = g.y0 + dy;
      if (g.am.x === "target") {
        nx = Math.max(-(g.w0 - 16), Math.min(nx, g.fw - 16));
        state.x_offset = Math.round(nx - g.baseL);
      } else {
        nx = Math.max(0, Math.min(nx, g.fw - g.w0));
        state.left = Math.round(nx);
        state.right = Math.round(g.fw - nx - g.w0);
      }
      if (g.am.y === "target") {
        ny = Math.max(-(g.h0 - 16), Math.min(ny, g.fh - 16));
        state.y_offset = Math.round(ny - g.baseT);
      } else {
        ny = Math.max(0, Math.min(ny, g.fh - g.h0));
        state.top = Math.round(ny);
        state.bottom = Math.round(g.fh - ny - g.h0);
      }
      redraw();
      return;
    }

    const prop = state.lock ? !e.shiftKey : e.shiftKey;
    const cx0 = g.x0 + g.w0 / 2;
    const cy0 = g.y0 + g.h0 / 2;
    let nw, nh;
    if (prop) {
      let sc;
      if (hs.length === 2) {
        const ccx = g.v.ox + cx0 * g.v.s, ccy = g.v.oy + cy0 * g.v.s;
        const r0 = Math.max(2, Math.hypot(g.c0.x - ccx, g.c0.y - ccy));
        sc = Math.hypot(c.x - ccx, c.y - ccy) / r0;
      } else if (hs === "e") sc = (g.w0 / 2 + dx) / (g.w0 / 2);
      else if (hs === "w") sc = (g.w0 / 2 - dx) / (g.w0 / 2);
      else if (hs === "s") sc = (g.h0 / 2 + dy) / (g.h0 / 2);
      else sc = (g.h0 / 2 - dy) / (g.h0 / 2);
      sc = Math.max(sc, 16 / g.w0, 16 / g.h0, 0.01);
      nw = Math.round(g.w0 * sc);
      nh = Math.round(g.h0 * sc);
    } else {
      nw = g.w0; nh = g.h0;
      if (hs.includes("e")) nw = g.w0 + 2 * dx;
      if (hs.includes("w")) nw = g.w0 - 2 * dx;
      if (hs.includes("s")) nh = g.h0 + 2 * dy;
      if (hs.includes("n")) nh = g.h0 - 2 * dy;
    }
    nw = Math.max(16, Math.min(8192, Math.round(nw)));
    nh = Math.max(16, Math.min(8192, Math.round(nh)));

    state.zoom_w = nw / g.bw;
    state.zoom_h = nh / g.bh;
    if (g.am.x === "target") {
      const baseL2 = baseFor(g.fw - nw, "h");
      let nx = cx0 - nw / 2;
      nx = Math.max(-(nw - 16), Math.min(nx, g.fw - 16));
      state.x_offset = Math.round(nx - baseL2);
    } else {
      const shiftX = (g.w0 - nw) / 2;
      state.left = Math.max(0, Math.round(g.pl0 + shiftX));
      state.right = Math.max(0, Math.round(g.pr0 + shiftX));
    }
    if (g.am.y === "target") {
      const baseT2 = baseFor(g.fh - nh, "v");
      let ny = cy0 - nh / 2;
      ny = Math.max(-(nh - 16), Math.min(ny, g.fh - 16));
      state.y_offset = Math.round(ny - baseT2);
    } else {
      const shiftY = (g.h0 - nh) / 2;
      state.top = Math.max(0, Math.round(g.pt0 + shiftY));
      state.bottom = Math.max(0, Math.round(g.pb0 + shiftY));
    }
    syncSizeInputs();
    redraw();
  });

  const endDrag = () => {
    if (drag) { drag = null; serialize(); redraw(); }
  };
  canvas.addEventListener("pointerup", endDrag);
  canvas.addEventListener("pointercancel", endDrag);

  // ========== 顶栏输入 ==========
  colorInp.oninput = () => { state.background_color = colorInp.value; serialize(); markInteractive(); redraw(); };

  function applySizeInput(which) {
    const v = Math.max(16, Math.min(8192, parseInt(which === "w" ? imgWInp.value : imgHInp.value) || 16));
    const d = deriveDims();
    if (which === "w") {
      state.zoom_w = v / d.bw;
      if (state.lock) state.zoom_h = state.zoom_w;
    } else {
      state.zoom_h = v / d.bh;
      if (state.lock) state.zoom_w = state.zoom_h;
    }
    sanitizeOffsets();
    syncSizeInputs(); serialize(); markInteractive(); redraw();
  }
  imgWInp.onchange = () => applySizeInput("w");
  imgHInp.onchange = () => applySizeInput("h");

  resetBtn.onclick = () => {
    state = { ...DEFAULT_STATE };
    syncSizeInputs(); serialize();
    syncAlign(); syncModes(); syncLock(); syncEdges(); syncMaskRep();
    colorInp.value = state.background_color;
    featherInp.value = state.feathering;
    blurInp.value = state.content_blur;
    markInteractive(); redraw();
  };

  ["target_width", "target_height"].forEach(n => {
    const w = W(n);
    if (!w) return;
    const cb = w.callback;
    let snapTimer = null;
    w.callback = function (v) {
      if (cb) cb.call(this, v);
      markInteractive();
      requestAnimationFrame(() => { syncSizeInputs(); redraw(); });
      clearTimeout(snapTimer);
      snapTimer = setTimeout(() => {
        const d = Math.max(1, parseInt(W("div")?.value) || 1);
        const num = parseFloat(w.value);
        if (d > 1 && Number.isFinite(num) && num > 0) {
          const snapped = Math.max(d, Math.round(num / d) * d);
          if (snapped !== num) {
            w.value = snapped;
            node.setDirtyCanvas?.(true, true);
          }
        }
        sanitizeOffsets();
        syncSizeInputs();
        serialize();
        redraw();
      }, 350);
    };
  });

  // ========== 本地源图像载入 ==========
  const opaqueCv = document.createElement("canvas");

  function applySourceImage(img, logicalW, logicalH, seq) {
    if (seq !== undefined && seq !== srcLoadSeq) return; // 竞态令牌
    const pw = img.naturalWidth || img.width;
    const ph = img.naturalHeight || img.height;
    const lw = logicalW > 0 ? logicalW : pw;
    const lh = logicalH > 0 ? logicalH : ph;
    try {
      opaqueCv.width = pw; opaqueCv.height = ph;
      const c = opaqueCv.getContext("2d", { willReadFrequently: true });
      c.setTransform(1, 0, 0, 1, 0, 0);
      c.clearRect(0, 0, pw, ph);
      c.drawImage(img, 0, 0, pw, ph);
      const id = c.getImageData(0, 0, pw, ph);
      const d = id.data;
      for (let i = 3; i < d.length; i += 4) d[i] = 255;
      c.putImageData(id, 0, 0);
      srcImg = opaqueCv;
    } catch (err) {
      srcImg = img;
    }
    srcW = lw || pw || 16;
    srcH = lh || ph || 16;
    srcSeq++;
    localStamp = Date.now();
    state.src_w = srcW; state.src_h = srcH;
    sanitizeOffsets();
    syncSizeInputs();
    serialize();
    try { lastSrcFp = srcFingerprint(); } catch (e) {}
    redraw();
  }

  function upstreamFilename() {
    try {
      const inp = node.inputs?.find(i => i.name === "image");
      const link = inp && inp.link != null ? app.graph.links[inp.link] : null;
      const up = link ? app.graph.getNodeById(link.origin_id) : null;
      if (!up) return null;
      const w = up.widgets?.find(x => x.name === "image");
      const v = w?.value;
      if (Array.isArray(v) && v[0]) return { filename: v[0], subfolder: v[1] || "", type: v[2] || "input", up };
      if (typeof v === "string" && v) return { filename: v, subfolder: "", type: "input", up };
      return null;
    } catch (e) { return null; }
  }

  function detectSource() {
    const f = upstreamFilename();
    if (f) {
      const mySeq = ++srcLoadSeq;
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.onload = () => applySourceImage(img, 0, 0, mySeq);
      img.onerror = () => { fetchSource(); };
      img.src = `/view?filename=${encodeURIComponent(f.filename)}&subfolder=${encodeURIComponent(f.subfolder || "")}&type=${encodeURIComponent(f.type || "input")}&t=${Date.now()}`;
      return true;
    }
    try {
      const inp = node.inputs?.find(i => i.name === "image");
      const link = inp && inp.link != null ? app.graph.links[inp.link] : null;
      const up = link ? app.graph.getNodeById(link.origin_id) : null;
      const pv = up?.imgs?.[0];
      const pw = pv?.naturalWidth || pv?.width || 0;
      const ph = pv?.naturalHeight || pv?.height || 0;
      if (pv && pw > 0 && ph > 0) {
        applySourceImage(pv, 0, 0, srcLoadSeq);
        return true;
      }
    } catch (e) {}
    return false;
  }

  async function fetchSource() {
    const mySeq = ++srcLoadSeq;
    try {
      const r = await api.fetchApi("/element_image_pad_blur/get_source", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ node_id: String(node.id) }),
      });
      if (!r.ok) return false;
      const d = await r.json();
      if (!d || !d.image?.filename) return false;
      const lw = d.width > 0 ? d.width : 0;
      const lh = d.height > 0 ? d.height : 0;
      const ok = await new Promise((res) => {
        const img = new Image();
        img.crossOrigin = "anonymous";
        img.onload = () => { applySourceImage(img, lw, lh, mySeq); res(true); };
        img.onerror = () => res(false);
        img.src = api.apiURL(`/view?filename=${encodeURIComponent(d.image.filename)}&subfolder=${encodeURIComponent(d.image.subfolder || "")}&type=${encodeURIComponent(d.image.type || "temp")}&t=${Date.now()}`);
      });
      if (!ok) return false;
      if (d.mask?.filename) loadServerMask(d.mask);
      else if (maskImg) { maskImg = null; maskSeq++; fgCacheKey = ""; redraw(); }
      return true;
    } catch (e) {
      return false;
    }
  }

  async function refreshBestSource() {
    try { lastSrcFp = srcFingerprint(); } catch (e) {}
    if (detectSource()) return true;
    return await fetchSource();
  }

  function loadCompositeFromServer(im) {
    if (!im?.filename) return;
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      serverImg = img;
      serverStamp = Date.now();
      dirtyLocal = false;
      requestAnimationFrame(redraw);
    };
    img.src = api.apiURL(`/view?filename=${encodeURIComponent(im.filename)}&subfolder=${encodeURIComponent(im.subfolder || "")}&type=${encodeURIComponent(im.type || "temp")}&t=${Date.now()}`);
  }

  // ========== mask端口 ==========
  let maskImg = null;
  let maskSeq = 0;

  function isMaskConnected() {
    try {
      const inp = node.inputs?.find(i => i.name === "mask");
      return !!(inp && inp.link != null && app.graph.links[inp.link]);
    } catch (e) { return false; }
  }
  function setMaskFromCanvas(cv) {
    maskImg = cv;
    maskSeq++;
    fgCacheKey = "";
    requestAnimationFrame(redraw);
  }
  function processMaskImage(img) {
    try {
      const cv = document.createElement("canvas");
      cv.width = img.naturalWidth || img.width;
      cv.height = img.naturalHeight || img.height;
      const c = cv.getContext("2d", { willReadFrequently: true });
      c.drawImage(img, 0, 0);
      const id = c.getImageData(0, 0, cv.width, cv.height);
      const d = id.data;
      for (let i = 0; i < d.length; i += 4) {
        const m = 255 - d[i + 3];
        d[i] = d[i + 1] = d[i + 2] = m;
        d[i + 3] = 255;
      }
      c.putImageData(id, 0, 0);
      setMaskFromCanvas(cv);
      return true;
    } catch (e) { return false; }
  }
  function loadServerMask(im) {
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => {
      try {
        const cv = document.createElement("canvas");
        cv.width = img.naturalWidth || img.width;
        cv.height = img.naturalHeight || img.height;
        const c = cv.getContext("2d", { willReadFrequently: true });
        c.drawImage(img, 0, 0);
        const id = c.getImageData(0, 0, cv.width, cv.height);
        const d = id.data;
        for (let i = 0; i < d.length; i += 4) {
          d[i + 1] = d[i];
          d[i + 2] = d[i];
          d[i + 3] = 255;
        }
        c.putImageData(id, 0, 0);
        setMaskFromCanvas(cv);
      } catch (e) {}
    };
    img.src = api.apiURL(`/view?filename=${encodeURIComponent(im.filename)}&subfolder=${encodeURIComponent(im.subfolder || "")}&type=${encodeURIComponent(im.type || "temp")}&t=${Date.now()}`);
  }
  function maskSourceInfo() {
    try {
      const inp = node.inputs?.find(i => i.name === "mask");
      if (!inp || inp.link == null) return null;
      const link = app.graph.links[inp.link];
      if (!link) return null;
      const up = app.graph.getNodeById(link.origin_id);
      if (!up) return null;
      const w2 = up.widgets?.find(x => x.name === "image");
      const v = w2?.value;
      let filename = null, subfolder = "", type = "input";
      if (Array.isArray(v)) [filename, subfolder, type] = v;
      else if (typeof v === "string" && v) filename = v;
      return filename ? { filename, subfolder, type } : null;
    } catch (e) { return null; }
  }
  function refreshMaskPreview() {
    try { lastMaskFp = maskFingerprint(); } catch (e) {}
    const info = maskSourceInfo();
    if (!info) {
      if (maskImg) { maskImg = null; maskSeq++; fgCacheKey = ""; requestAnimationFrame(redraw); }
      return;
    }
    const img = new Image();
    img.crossOrigin = "anonymous";
    img.onload = () => processMaskImage(img);
    img.src = `/view?filename=${encodeURIComponent(info.filename)}&subfolder=${encodeURIComponent(info.subfolder || "")}&type=${encodeURIComponent(info.type || "input")}&t=${Date.now()}`;
  }

  // ========== 输入指纹 + 轮询兜底 ==========
  function srcFingerprint() {
    try {
      const inp = node.inputs?.find(i => i.name === "image");
      if (!inp) return "noinput";
      const link = inp.link != null ? app.graph.links[inp.link] : null;
      if (!link) return "unconnected";
      const up = app.graph.getNodeById(link.origin_id);
      if (!up) return "deadlink";
      const w = up.widgets?.find(x => x.name === "image");
      const v = w?.value;
      const fstr = Array.isArray(v) ? v.join("|") : (typeof v === "string" ? v : "");
      const pv = up.imgs?.[0];
      const pvKey = pv ? `${pv.naturalWidth || 0}x${pv.naturalHeight || 0}:${pv.src || ""}` : "";
      return `${up.id}:${link.id}:${fstr}:${pvKey}`;
    } catch (e) { return "err"; }
  }
  function maskFingerprint() {
    try {
      const inp = node.inputs?.find(i => i.name === "mask");
      if (!inp || inp.link == null) return "nomask";
      const link = app.graph.links[inp.link];
      if (!link) return "nomask";
      const up = app.graph.getNodeById(link.origin_id);
      if (!up) return "deadlink";
      const w = up.widgets?.find(x => x.name === "image");
      const v = w?.value;
      const fstr = Array.isArray(v) ? v.join("|") : (typeof v === "string" ? v : "");
      const pv = up.imgs?.[0];
      const pvKey = pv ? `${pv.naturalWidth || 0}x${pv.naturalHeight || 0}:${pv.src || ""}` : "";
      return `${up.id}:${link.id}:${fstr}:${pvKey}`;
    } catch (e) { return "err"; }
  }
  function pollTick() {
    try {
      const fp = srcFingerprint();
      if (lastSrcFp !== null && fp !== lastSrcFp) refreshBestSource();
      lastSrcFp = fp;
    } catch (e) {}
    try {
      const fp = maskFingerprint();
      if (lastMaskFp !== null && fp !== lastMaskFp) refreshMaskPreview();
      lastMaskFp = fp;
    } catch (e) {}
  }

  node.__eipbOnExecuted = (message) => {
    const imgs = message?.preview_image;
    if (Array.isArray(imgs) && imgs.length && imgs[0]?.filename) {
      loadCompositeFromServer(imgs[0]);
      fetchSource();
    }
  };

  // ========== ★ 播放按钮：隔离执行（直提子图，不再劫持graphToPrompt）==========
  // 新实现：①graphToPrompt拿一次完整API prompt（与正常排队同一路径，Set/Get、
  //   bypass等钩子均生效）②本地递归抽出子图 ③直接POST /prompt 提交子图。
  //   一次调用、零补丁、零mode改动；带client_id → executed消息照常回到画布。
  let previewRunning = false;
  playBtn.onclick = async () => {
    if (previewRunning) return;
    const isConnected = !!node.inputs?.some(i => i.name === "image" && i.link !== null);
    if (!isConnected) { refreshBestSource(); refreshMaskPreview(); return; }
    previewRunning = true;
    setPlayRunning(true);
    try {
      // ① 完整API prompt
      const p = await app.graphToPrompt();
      const prompt = p.output;
      const selectedNodeId = String(node.id);

      // ② 递归追踪依赖 → 子图
      const isolatedPrompt = {};
      const traceDependencies = (nodeId) => {
        if (!prompt[nodeId] || isolatedPrompt[nodeId]) return;
        isolatedPrompt[nodeId] = prompt[nodeId];
        const inputs = prompt[nodeId].inputs;
        for (let key in inputs) {
          const val = inputs[key];
          if (Array.isArray(val) && val.length === 2) {
            traceDependencies(String(val[0]));
          }
        }
      };
      traceDependencies(selectedNodeId);
      if (!isolatedPrompt[selectedNodeId]) {
        console.warn("[ImagePadBlur] node not found in prompt; pulling cache only");
        refreshBestSource(); refreshMaskPreview();
        return;
      }

      // ③ 直提子图到 /prompt（公开队列API；front:true 插队，预览不必等长队列）
      const res = await api.fetchApi("/prompt", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          prompt: isolatedPrompt,
          client_id: api.clientId ?? undefined,
          extra_data: { front: true },
        }),
      });
      if (res.ok) {
        try {
          const j = await res.json();
          console.log("[ImagePadBlur] preview queued:", j?.prompt_id);
        } catch (e) {}
      } else {
        const errText = await res.text().catch(() => "");
        throw new Error(`/prompt ${res.status}: ${errText.slice(0, 300)}`);
      }
    } catch (err) {
      console.error("[ImagePadBlur] direct isolated run failed, trying legacy mute path:", err);
      try { await legacyIsolatedRun(); }
      catch (e2) { console.error("[ImagePadBlur] legacy path failed:", e2); }
    } finally {
      // 主路径：executed消息自动刷新画布；补两次延迟拉取防消息丢失
      setTimeout(() => { refreshBestSource(); refreshMaskPreview(); }, 800);
      setTimeout(() => { refreshBestSource(); refreshMaskPreview(); }, 2500);
      previewRunning = false;
      setPlayRunning(false);
    }
  };

  // 遗留兜底（仅当直提失败时启用，控制台会记录）
  async function legacyIsolatedRun() {
    const p = await app.graphToPrompt();
    const prompt = p.output;
    const isolatedPrompt = {};
    const traceDependencies = (nodeId) => {
      if (!prompt[nodeId] || isolatedPrompt[nodeId]) return;
      isolatedPrompt[nodeId] = prompt[nodeId];
      const inputs = prompt[nodeId].inputs;
      for (let key in inputs) {
        const val = inputs[key];
        if (Array.isArray(val) && val.length === 2) traceDependencies(String(val[0]));
      }
    };
    traceDependencies(String(node.id));
    const originalGraphToPrompt = app.graphToPrompt;
    const virtualNodeTypes = [
      "SetNode", "GetNode", "SetNodeAny", "GetNodeAny",
      "SetImage", "GetImage", "SetLatent", "GetLatent"
    ];
    app.graphToPrompt = async function (...args) {
      const originalModes = new Map();
      for (const n of app.graph._nodes) {
        originalModes.set(n.id, n.mode);
        const isVirtual = virtualNodeTypes.some(t => n.type?.includes(t));
        if (!isolatedPrompt[String(n.id)] && !isVirtual) n.mode = 2;
        else n.mode = 0;
      }
      try { return await originalGraphToPrompt.apply(this, args); }
      finally {
        for (const n of app.graph._nodes) {
          const m = originalModes.get(n.id);
          if (m !== undefined) n.mode = m;
        }
      }
    };
    try { await app.queuePrompt(0, 1); }
    finally {
      if (app.graphToPrompt !== originalGraphToPrompt) {
        app.graphToPrompt = originalGraphToPrompt;
      }
    }
  }



  // ========== 上游widget钩子 / 连接回调 ==========
  let detectTimer = null;
  const debounceDetect = () => {
    clearTimeout(detectTimer);
    detectTimer = setTimeout(() => {
      refreshBestSource();
      refreshMaskPreview();
    }, 200);
  };
  function hookUpstreamWidget() {
    try {
      const inp = node.inputs?.find(i => i.name === "image");
      const link = inp && inp.link != null ? app.graph.links[inp.link] : null;
      const up = link ? app.graph.getNodeById(link.origin_id) : null;
      const w = up?.widgets?.find(x => x.name === "image");
      if (!w || w.__eipb_hooked) return;
      w.__eipb_hooked = true;
      const cb = w.callback;
      w.callback = function (v) {
        if (cb) cb.call(this, v);
        debounceDetect();
      };
    } catch (e) {}
  }

  let connTimer = null;
  const origOnConn = node.onConnectionsChange;
  node.onConnectionsChange = function () {
    if (origOnConn) origOnConn.apply(this, arguments);
    clearTimeout(connTimer);
    connTimer = setTimeout(() => {
      hookUpstreamWidget();
      refreshBestSource();
      refreshMaskPreview();
    }, 250);
  };

  // ========== 工作流事件 → 画布刷新 ==========
  const onExecuted = ({ detail }) => {
    if (!detail) return;
    const nid = String(detail.node ?? "");
    if (nid === String(node.id)) {
      const pv = detail.output?.preview_image;
      if (Array.isArray(pv) && pv.length && pv[0]?.filename) {
        loadCompositeFromServer(pv[0]);
        fetchSource();
      } else {
        requestAnimationFrame(redraw);
      }
      return;
    }
    try {
      const inpImage = node.inputs?.find(i => i.name === "image");
      const linkImage = inpImage && inpImage.link != null ? app.graph.links[inpImage.link] : null;
      if (linkImage && nid === String(linkImage.origin_id)) {
        setTimeout(refreshBestSource, 150);
        return;
      }
      const inpMask = node.inputs?.find(i => i.name === "mask");
      const linkMask = inpMask && inpMask.link != null ? app.graph.links[inpMask.link] : null;
      if (linkMask && nid === String(linkMask.origin_id)) setTimeout(refreshMaskPreview, 150);
    } catch (e) {}
  };

  let execRefreshPending = false;
  const refreshAfterExecution = () => {
    if (!execRefreshPending) return;
    execRefreshPending = false;
    setTimeout(() => {
      refreshBestSource();
      refreshMaskPreview();
    }, 250);
  };
  const onExecStartEvt = () => { execRefreshPending = true; requestAnimationFrame(redraw); };

  api.addEventListener("executed", onExecuted);
  api.addEventListener("execution_start", onExecStartEvt);
  api.addEventListener("execution_success", refreshAfterExecution);
  api.addEventListener("status", ({ detail }) => {
    try { if (detail?.exec_info?.queue_remaining === 0) refreshAfterExecution(); } catch (e) {}
  });

  const origOnRemoved = node.onRemoved;
  node.onRemoved = function () {
    ro.disconnect();
    clearTimeout(connTimer);
    if (pollTimer != null) { clearInterval(pollTimer); pollTimer = null; }
    try {
      api.removeEventListener("executed", onExecuted);
      api.removeEventListener("execution_start", onExecStartEvt);
      api.removeEventListener("execution_success", refreshAfterExecution);
    } catch (e) {}
    if (origOnRemoved) origOnRemoved.apply(this, arguments);
  };

  // ========== 初始化 ==========
  const init = () => {
    loadState();
    removeGhostInputs();
    ["target_width", "target_height"].forEach(n => {
      const w = W(n);
      if (w && !(parseInt(w.value) > 0)) w.value = 1024;
    });
    syncSizeInputs();
    syncAlign(); syncModes(); syncLock(); syncEdges(); syncMaskRep();
    colorInp.value = /^#[0-9a-fA-F]{6}$/.test(state.background_color) ? state.background_color : "#000000";
    featherInp.value = state.feathering;
    blurInp.value = state.content_blur;
    serialize();
    hookUpstreamWidget();
    lastSrcFp = srcFingerprint();
    lastMaskFp = maskFingerprint();
    refreshBestSource();
    refreshMaskPreview();
    if (pollTimer == null) pollTimer = setInterval(pollTick, POLL_MS);
    requestAnimationFrame(resizeCanvas);
  };

  const origOnConfigure = node.onConfigure;
  node.onConfigure = function () {
    if (origOnConfigure) origOnConfigure.apply(this, arguments);
    removeGhostInputs();
    setTimeout(init, 0);
  };
  setTimeout(init, 100);

  // 提交瞬间强制写入最新状态JSON（zoom 随 prompt 提交的最终保障）
  //   serializeValue 的情形，旧写法在 this===undefined 时执行 this.value=...，报错
  //   "Cannot set properties of undefined (setting 'value')" 。
  uiDataW.serializeValue = () => {
    const v = JSON.stringify(state);
    uiDataW.value = v;
    return v;
  };
}
