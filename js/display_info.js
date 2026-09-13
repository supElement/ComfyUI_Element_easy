import { app } from "../../scripts/app.js";

console.log(">>> Element_easy JS (ColorPicker v5) Loaded! <<<"); 

/* ================= 颜色工具 ================= */
const clamp = (v, a, b) => Math.min(b, Math.max(a, v));

function hsv2rgb(h, s, v) {
    h = ((h % 360) + 360) % 360;
    const c = v * s, x = c * (1 - Math.abs(((h / 60) % 2) - 1)), m = v - c;
    let r = 0, g = 0, b = 0;
    if (h < 60) { r = c; g = x; }
    else if (h < 120) { r = x; g = c; }
    else if (h < 180) { g = c; b = x; }
    else if (h < 240) { g = x; b = c; }
    else if (h < 300) { r = x; b = c; }
    else { r = c; b = x; }
    return [Math.round((r + m) * 255), Math.round((g + m) * 255), Math.round((b + m) * 255)];
}

const rgb2hex = (r, g, b) =>
    "#" + [r, g, b].map(v => clamp(v, 0, 255).toString(16).padStart(2, "0")).join("").toUpperCase();

function rgb2hsv(r, g, b) {
    r /= 255; g /= 255; b /= 255;
    const max = Math.max(r, g, b), min = Math.min(r, g, b), d = max - min;
    let h = 0;
    if (d !== 0) {
        if (max === r) h = 60 * (((g - b) / d) % 6);
        else if (max === g) h = 60 * ((b - r) / d + 2);
        else h = 60 * ((r - g) / d + 4);
    }
    if (h < 0) h += 360;
    return { h, s: max === 0 ? 0 : d / max, v: max };
}

function parseColor(str) {
    if (str == null) return null;
    let c = String(str).trim();
    try {
        if (c.startsWith("#")) {
            c = c.slice(1);
            if (c.length === 3) c = c.split("").map(x => x + x).join("");
            if (c.length === 6) return rgb2hsv(...[0, 2, 4].map(i => parseInt(c.slice(i, i + 2), 16)));
        } else if (c.includes(",")) {
            const p = c.split(",").map(v => parseInt(v));
            if (p.length >= 3 && p.every(v => !isNaN(v))) return rgb2hsv(p[0], p[1], p[2]);
        } else if (c !== "" && isFinite(c)) {
            const v = parseInt(c);
            return rgb2hsv(v, v, v);
        }
    } catch (e) {}
    return null;
}

function buildWheelBase(size = 512) {
    const cv = document.createElement("canvas");
    cv.width = cv.height = size;
    const ctx = cv.getContext("2d");
    const img = ctx.createImageData(size, size);
    const R = size / 2;
    for (let y = 0; y < size; y++) {
        for (let x = 0; x < size; x++) {
            const dx = x - R + 0.5, dy = y - R + 0.5;
            const dist = Math.sqrt(dx * dx + dy * dy);
            const i = (y * size + x) * 4;
            if (dist > R + 0.5) continue;
            const hue = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
            const sat = clamp(dist / (R - 2), 0, 1);
            const [r, g, b] = hsv2rgb(hue, sat, 1);
            img.data[i] = r;
            img.data[i + 1] = g;
            img.data[i + 2] = b;
            img.data[i + 3] = clamp(R + 0.5 - dist, 0, 1) * 255; 
        }
    }
    ctx.putImageData(img, 0, 0);
    return cv;
}
const WHEEL_BASE = buildWheelBase(512);
const FIXED_H = 280;    // DOM 取色器区域固定高度（px）
const WHEEL_SIZE = 160; // 色轮固定尺寸（px）

/* ============= Lucide 风格 SVG 图标 =========== */
const ICON_EYEDROPPER = `
<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <path d="m2 22 1-1h3l9-9"/>
  <path d="M3 21v-3l9-9"/>
  <path d="m15 6 3.4-3.4a2.1 2.1 0 1 1 3 3L18 9l.4.4a2.1 2.1 0 1 1-3 3l-3.8-3.8a2.1 2.1 0 1 1 3-3l.4.4Z"/>
</svg>`;

const ICON_PALETTE = `
<svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
  <circle cx="13.5" cy="6.5" r=".5" fill="currentColor"/>
  <circle cx="17.5" cy="10.5" r=".5" fill="currentColor"/>
  <circle cx="8.5" cy="7.5" r=".5" fill="currentColor"/>
  <circle cx="6.5" cy="12.5" r=".5" fill="currentColor"/>
  <path d="M12 2C6.5 2 2 6.5 2 12s4.5 10 10 10c.926 0 1.648-.746 1.648-1.688 0-.437-.18-.835-.437-1.125-.29-.289-.438-.652-.438-1.125a1.64 1.64 0 0 1 1.668-1.668h1.996c3.051 0 5.555-2.503 5.555-5.554C21.965 6.012 17.461 2 12 2z"/>
</svg>`;

/* ================= 取色器初始化 ================= */
function setupColorPicker(node) {
    try {
        if (typeof node.addDOMWidget !== "function") {
            console.warn("[Element_easy] addDOMWidget 不可用，取色器跳过");
            return;
        }

        const origWidget = node.widgets?.find(w => w.name === "color_code");
        if (!origWidget) {
            console.warn("[Element_easy] 未找到 color_code widget，取色器跳过");
            return;
        }

        origWidget.computeSize = () => [0, -4];
        origWidget.draw = function () {};

        const state = { h: 0, s: 0, v: 0.5 };

        const el = document.createElement("div");
        el.innerHTML = `
        <style>
          .ee-cp{
            display:flex; flex-direction:column; gap:6px;
            padding:8px 12px 10px; box-sizing:border-box; overflow:hidden;
          }
          .ee-cp *{ box-sizing:border-box; }
          .ee-cp-wheelbox{
            flex:1 1 auto; min-height:0; min-width:0;
            display:flex; align-items:center; justify-content:center;
          }
          .ee-cp-wheel{
            width:${WHEEL_SIZE}px; height:${WHEEL_SIZE}px;   /* ★ 固定像素，约原来的 80% */
            max-width:100%;
            border-radius:50%;
            cursor:crosshair; touch-action:none;
          }
          .ee-cp-slider{
            width:100%;                 /* ★ 拉满整行，与下方按钮行左右对齐 */
            display:block; margin:0 auto;
            cursor:pointer; flex:0 0 auto;
            -webkit-appearance:none;    /* ★ 去掉浏览器默认外观，才能自定义轨道/圆点 */
            appearance:none;
            background:transparent;     /* 由伪元素绘制轨道 */
            height:16px;                /* 占位高度，给圆点留出空间，不影响视觉粗细 */
          }
          /* ---- 轨道：白色、变细（约原来的一半） ---- */
          .ee-cp-slider::-webkit-slider-runnable-track{
            height:2px;                 /* ★ 默认轨道约 4~6px，这里减半 */
            background:#ffffff;         /* ★ 整条轨道白色 */
            border-radius:1px;
          }
          .ee-cp-slider::-moz-range-track{
            height:2px;
            background:#ffffff;
            border-radius:1px;
          }
          /* ---- 圆点（thumb）：半径变小，白色 ---- */
          .ee-cp-slider::-webkit-slider-thumb{
            -webkit-appearance:none;
            appearance:none;
            width:10px;                 /* ★ 默认约 16~20px，减半左右 */
            height:10px;
            border-radius:50%;
            background:#ffffff;
            border:none;
            margin-top:-4px;            /* 让圆点垂直居中在 2px 轨道上：(2-10)/2 = -4 */
            box-shadow:0 0 3px rgba(0,0,0,.5); /* 深色背景下加一点描影，避免白点看不清边界 */
          }
          .ee-cp-slider::-moz-range-thumb{
            width:10px;
            height:10px;
            border-radius:50%;
            background:#ffffff;
            border:none;
            box-shadow:0 0 3px rgba(0,0,0,.5);
          }
          
          .ee-cp-row{
            display:flex; gap:6px; align-items:center; flex:0 0 auto;
          }
          .ee-cp-swatch{
            width:30px; height:26px; border-radius:5px; flex:0 0 auto;
            border:1px solid rgba(255,255,255,.3);
          }
          .ee-cp-hex{
            flex:1 1 auto; min-width:0;
            background:rgba(0,0,0,.35); color:inherit;
            border:1px solid rgba(255,255,255,.15); border-radius:4px;
            padding:4px 8px; font-size:12px; font-family:monospace;
          }
          .ee-cp-hex:focus{ outline:1px solid rgba(255,255,255,.35); }
          .ee-cp-btn{
            flex:0 0 auto; width:30px; height:26px;
            display:flex; align-items:center; justify-content:center;
            cursor:pointer; border:none; border-radius:4px;
            background:rgba(255,255,255,.1); color:rgba(255,255,255,.8); padding:0;
          }
          .ee-cp-btn:hover{ background:rgba(255,255,255,.22); color:#fff; }
          .ee-cp-info{
            flex:0 0 auto; font-size:11px; line-height:1.5;
            color:rgba(255,255,255,.55); background:rgba(0,0,0,.25);
            border-radius:5px; padding:4px 8px; font-family:monospace; white-space:pre;
          }
        </style>
        <div class="ee-cp">
          <div class="ee-cp-wheelbox"><canvas class="ee-cp-wheel"></canvas></div>
          <input class="ee-cp-slider" type="range" min="0" max="255" step="1" title="明度 Brightness" />
          <div class="ee-cp-row">
            <div class="ee-cp-swatch"></div>
            <input class="ee-cp-hex" type="text" spellcheck="false" title="#RRGGBB / R,G,B / 灰度值" />
            <button class="ee-cp-btn ee-cp-eye" title="屏幕吸管：拾取屏幕任意颜色 (Chrome/Edge)">${ICON_EYEDROPPER}</button>
            <button class="ee-cp-btn ee-cp-native" title="系统取色器">${ICON_PALETTE}</button>
          </div>
          <div class="ee-cp-info">Ready...</div>
        </div>
        `;

        const root = el.querySelector(".ee-cp");

        const canvas    = root.querySelector(".ee-cp-wheel");
        const slider    = root.querySelector(".ee-cp-slider");
        const swatch    = root.querySelector(".ee-cp-swatch");
        const hexInput  = root.querySelector(".ee-cp-hex");
        const infoEl    = root.querySelector(".ee-cp-info");
        const eyeBtn    = root.querySelector(".ee-cp-eye");
        const nativeBtn = root.querySelector(".ee-cp-native");

        function refreshCanvasRes() {
            const rect = canvas.getBoundingClientRect();
            if (rect.width < 2 || rect.height < 2) return;
            const dpr = window.devicePixelRatio || 1;
            const px = clamp(Math.round(rect.width * dpr), 64, 1024);
            if (canvas.width !== px) {
                canvas.width = canvas.height = px;
                render();
            }
        }

        function render() {
            const S = canvas.width;
            if (!S) return;
            const ctx = canvas.getContext("2d");
            ctx.clearRect(0, 0, S, S);
            ctx.drawImage(WHEEL_BASE, 0, 0, S, S);
            if (state.v < 0.999) {
                ctx.globalAlpha = 1 - state.v;
                ctx.fillStyle = "#000";
                ctx.beginPath();
                ctx.arc(S/2, S/2, S/2, 0, Math.PI * 2);
                ctx.fill();
                ctx.globalAlpha = 1;
            }
            const R = S / 2, rad = state.h * Math.PI / 180, k = S / 150;
            const mx = R + Math.cos(rad) * state.s * (R - 2);
            const my = R + Math.sin(rad) * state.s * (R - 2);
            ctx.beginPath();
            ctx.arc(mx, my, 6*k, 0, Math.PI*2);
            ctx.lineWidth = 2*k;
            ctx.strokeStyle = "#fff";
            ctx.stroke();
            ctx.beginPath();
            ctx.arc(mx, my, 7.5*k, 0, Math.PI*2);
            ctx.lineWidth = 1.2*k;
            ctx.strokeStyle = "rgba(0,0,0,.75)";
            ctx.stroke();
        }

        function commit() {
            const [r, g, b] = hsv2rgb(state.h, state.s, state.v);
            const hex = rgb2hex(r, g, b);
            swatch.style.background = hex;
            if (hexInput.value.toUpperCase() !== hex) hexInput.value = hex;
            origWidget.value = hex;
        }

        function applyParsed(p) {
            if (!p) return;
            Object.assign(state, p);
            slider.value = Math.round(state.v * 255);
            render();
            commit();
        }

        node.__eeSetInfo = (t) => {
            if (typeof t === "string") infoEl.textContent = t;
        };

        function syncFromWidget() {
            const p = parseColor(origWidget.value);
            Object.assign(state, p || { h: 0, s: 0, v: 0.5 });
            slider.value = Math.round(state.v * 255);
            commit();
            render();
        }

        node.__eeColorPicker = { syncFromWidget, refreshCanvasRes };

        /* --- 色轮交互 --- */
        let dragging = false;
        function pick(e) {
            const rect = canvas.getBoundingClientRect();
            const dx = e.clientX - rect.left - rect.width/2;
            const dy = e.clientY - rect.top - rect.height/2;
            const R = rect.width/2 - 1;
            state.h = (Math.atan2(dy, dx) * 180 / Math.PI + 360) % 360;
            state.s = clamp(Math.hypot(dx, dy) / R, 0, 1);
            render();
            commit();
        }
        canvas.addEventListener("pointerdown", e => {
            dragging = true;
            try { canvas.setPointerCapture(e.pointerId); } catch (_) {}
            pick(e);
            e.preventDefault();
        });
        canvas.addEventListener("pointermove", e => { if (dragging) pick(e); });
        canvas.addEventListener("pointerup", () => dragging = false);
        canvas.addEventListener("pointercancel", () => dragging = false);

        slider.addEventListener("input", () => {
            state.v = +slider.value / 255;
            render();
            commit();
        });

        hexInput.addEventListener("change", () => {
            const p = parseColor(hexInput.value);
            if (p) applyParsed(p);
            else hexInput.value = rgb2hex(...hsv2rgb(state.h, state.s, state.v));
        });
        hexInput.addEventListener("keydown", e => {
            if (e.key === "Enter") hexInput.blur();
        });

        eyeBtn.addEventListener("click", async () => {
            if (!window.EyeDropper) {
                alert("当前浏览器不支持屏幕取色，请使用 Chrome / Edge 96+，或改用旁边的调色板按钮。");
                return;
            }
            try {
                applyParsed(parseColor((await new EyeDropper().open()).sRGBHex));
            } catch (e) { /* Esc 取消 */ }
        });

        nativeBtn.addEventListener("click", () => {
            const inp = document.createElement("input");
            inp.type = "color";
            inp.value = rgb2hex(...hsv2rgb(state.h, state.s, state.v));
            inp.addEventListener("change", () => applyParsed(parseColor(inp.value)));
            inp.click();
        });

        /* --- DOM 挂载：高度固定，不随节点拖拽变化 --- */
        const domWidget = node.addDOMWidget("color_picker", "custom", el, { hideOnZoom: false });

        function applyLayout() {
            root.style.height = FIXED_H + "px";   
            return [node.size[0], FIXED_H];
        }
        domWidget.computeSize = () => applyLayout();

        const prevResize = node.onResize;
        node.onResize = function () {
            prevResize?.apply(this, arguments);
            refreshCanvasRes();
        };

        if (typeof ResizeObserver === "function") {
            new ResizeObserver(() => { refreshCanvasRes(); }).observe(canvas);
        }

        requestAnimationFrame(() => {
            let above = 0;
            for (const wd of node.widgets || []) {
                if (wd === domWidget) break;
                const h = wd.computeSize ? wd.computeSize(node.size[0])[1] : (wd.height ?? 20);
                above += Math.max(0, h);
            }
            node.size[1] = Math.round(above + FIXED_H + 6);

            applyLayout();
            refreshCanvasRes();
            syncFromWidget();
            console.log("[Element_easy] ColorPicker mounted on node", node.id);
        });

    } catch (err) {
        console.error("[Element_easy] ColorPicker init failed (node still usable):", err);
    }
}

/* ================= 注册扩展 ================= */
app.registerExtension({
    name: "Element.DisplayInfo",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "EmptyImageRGB_Element") return;

        const onNodeCreated = nodeType.prototype.onNodeCreated;
        nodeType.prototype.onNodeCreated = function () {
            const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
            setupColorPicker(this);
            return r;
        };

        const onConfigure = nodeType.prototype.onConfigure;
        nodeType.prototype.onConfigure = function () {
            const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
            requestAnimationFrame(() => {
                const domWidget = (this.widgets || []).find(w => w.name === "color_picker");
                if (domWidget) {
                    let above = 0;
                    for (const wd of this.widgets || []) {
                        if (wd === domWidget) break;
                        const h = wd.computeSize ? wd.computeSize(this.size[0])[1] : (wd.height ?? 20);
                        above += Math.max(0, h);
                    }
                    this.size[1] = Math.round(above + FIXED_H + 6);
                }
                this.__eeColorPicker?.refreshCanvasRes();
                this.__eeColorPicker?.syncFromWidget();
            });
            return r;
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);
            if (message?.text) this.__eeSetInfo?.(message.text.join(""));
        };
    },
});
