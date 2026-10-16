/*
# Element_listGraph_Curve 前端 —— 基于 Element_SigmaGraphWidget_Curve 派生。
# 与 SigmaGraph 的差异：y 值不限制递减、末端不强制为 0、输出为 int/float 列表，
# 输出数量 = steps（采样位 x_i = i/(steps-1)，首尾落在曲线两端）。
# 交互（曲线编辑/样条插值/预设槽/C-L 模式/撤销）与 SigmaGraph 一致。
# 已移除：P 对齐按钮、custom_sigmas 反向同步监听（本节点无输入端口）。
*/

import { app } from "/../scripts/app.js";
import { $el } from "/../scripts/ui.js";
import { eeMarkForward } from "./ee_canvas_utils.js";
import { isNodes2_0, hideWidgetAndSlot } from "./ee_node_utils.js";


const NODE_CLASS = "Element_listGraph_Curve";
const GRAPH_DATA_NAME = "graph_data";
const STEPS_NAME = "steps";
const CANVAS_TYPE = "LIST_GRAPH_CURVE_CANVAS";
const MIN_POINTS = 2;
const NUM_SLOTS = 8;
const LS_KEY = "list_graph_saveSlots";
const UNDO_LIMIT = 1;
const MIN_NODE_WIDTH = 240;
const MIN_NODE_HEIGHT = 280;
const NON_WIDGET_HEIGHT = 122; // 预览55 + 槽位行24 + 按钮行22 + 边距，canvas 为 flex 自适应
const MIN_WIDGET_HEIGHT = 100;
const GRAB_THRESHOLD = 0.08;
const POINT_RADIUS = 4;
const POINT_COLOR = "#1E88E5";
const CURVE_COLOR = "#fff";
const CONTROL_COLOR = "#ff6b6b";
const GUIDE_COLOR = "#444";


function linearInterpolate(x, points) {
    const sorted = points.slice().sort((a, b) => a.x - b.x);
    
    if (x <= sorted[0].x) return sorted[0].y;
    if (x >= sorted[sorted.length - 1].x) return sorted[sorted.length - 1].y;
    
    for (let i = 0; i < sorted.length - 1; i++) {
        const p0 = sorted[i];
        const p1 = sorted[i + 1];
        
        if (x >= p0.x && x <= p1.x) {
            const t = (x - p0.x) / (p1.x - p0.x);
            return p0.y + t * (p1.y - p0.y);
        }
    }
    
    return sorted[sorted.length - 1].y;
}

function calcLinearValues(points, steps) {
    steps = Math.max(1, steps | 0);
    const p = (points || []).slice().sort((a, b) => a.x - b.x);

    if (p.length < 2) return Array(steps).fill(1.0);

    if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
        p.unshift({ x: 0, y: Math.max(0.0, Math.min(1.0, p[0].y)) });
    if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
        p.push({ x: 1, y: Math.max(0.0, Math.min(1.0, p[p.length - 1].y)) });

    // 输出数量 = steps；N 个采样点 x_i = i/(N-1)，首尾落在曲线两端
    const out = [];
    for (let i = 0; i < steps; i++) {
        const t = steps > 1 ? i / (steps - 1) : 0;
        const y = linearInterpolate(t, p);
        out.push(formatValue(y));
    }
    return out;
}

function computeSplineCoefficients(points) {
    const n = points.length - 1;
    if (n < 1) return [];
    
    const x = points.map(p => p.x);
    const y = points.map(p => p.y);
    const h = [];
    
    for (let i = 0; i < n; i++) {
        h.push(x[i+1] - x[i]);
    }
    
    const A = Array(n+1).fill().map(() => Array(n+1).fill(0));
    const b = Array(n+1).fill(0);
    
    A[0][0] = 1;
    A[n][n] = 1;
    
    for (let i = 1; i < n; i++) {
        A[i][i-1] = h[i-1];
        A[i][i] = 2 * (h[i-1] + h[i]);
        A[i][i+1] = h[i];
        b[i] = 3 * ((y[i+1] - y[i]) / h[i] - (y[i] - y[i-1]) / h[i-1]);
    }
    
    const cPrime = Array(n+1).fill(0);
    const dPrime = Array(n+1).fill(0);
    const M = Array(n+1).fill(0);
    
    cPrime[0] = A[0][1] / A[0][0];
    dPrime[0] = b[0] / A[0][0];
    
    for (let i = 1; i <= n; i++) {
        const denom = A[i][i] - A[i][i-1] * cPrime[i-1];
        if (i < n) cPrime[i] = A[i][i+1] / denom;
        dPrime[i] = (b[i] - A[i][i-1] * dPrime[i-1]) / denom;
    }
    
    M[n] = dPrime[n];
    for (let i = n-1; i >= 0; i--) {
        M[i] = dPrime[i] - cPrime[i] * M[i+1];
    }
    
    const coeffs = [];
    for (let i = 0; i < n; i++) {
        const a = y[i];
        const b_coef = (y[i+1] - y[i]) / h[i] - h[i] * (2*M[i] + M[i+1]) / 3;
        const c = M[i];
        const d = (M[i+1] - M[i]) / (3 * h[i]);
        
        coeffs.push({
            a, b: b_coef, c, d,
            x0: x[i], x1: x[i+1]
        });
    }
    
    return coeffs;
}

function evaluateSpline(x, coeffs) {
    for (let coeff of coeffs) {
        if (x >= coeff.x0 && x <= coeff.x1) {
            const dx = x - coeff.x0;
            const val = coeff.a + coeff.b*dx + coeff.c*dx*dx + coeff.d*dx*dx*dx;
            return Math.max(0.0, Math.min(1.0, val));
        }
    }
    if (coeffs.length === 0) return 0;
    if (x < coeffs[0].x0) {
        return Math.max(0.0, Math.min(1.0, coeffs[0].a));
    }
    const last = coeffs[coeffs.length-1];
    const lastVal = last.a + last.b*(last.x1-last.x0) + last.c*(last.x1-last.x0)**2 + last.d*(last.x1-last.x0)**3;
    return Math.max(0.0, Math.min(1.0, lastVal));
}

function calcSmoothValues(points, steps) {
    steps = Math.max(1, steps | 0);
    const p = (points || []).slice().sort((a, b) => a.x - b.x);

    if (p.length < 2) return Array(steps).fill(1.0);

    if (!p.some((pt) => Math.abs(pt.x) < 1e-6))
        p.unshift({ x: 0, y: Math.max(0.0, Math.min(1.0, p[0].y)) });
    if (!p.some((pt) => Math.abs(pt.x - 1) < 1e-6))
        p.push({ x: 1, y: Math.max(0.0, Math.min(1.0, p[p.length - 1].y)) });

    const coeffs = computeSplineCoefficients(p);
    const out = [];

    // 输出数量 = steps；N 个采样点 x_i = i/(N-1)，首尾落在曲线两端
    for (let i = 0; i < steps; i++) {
        const t = steps > 1 ? i / (steps - 1) : 0;
        let y = evaluateSpline(t, coeffs);
        y = formatValue(y);
        out.push(y);
    }

    return out;
}

function formatValue(val) {
    if (Math.abs(val) < 1e-10) val = 0.0;
    if (Math.abs(val - 1.0) < 1e-10) val = 1.0;
    val = Math.max(0.0, Math.min(1.0, val));
    return Math.round(val * 10000000000) / 10000000000;
}

function strToPts(str) {
    try {
        const parsed = JSON.parse(str);
        let arr = parsed;
        if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.points) {
            arr = parsed.points;
        }
        
        if (
            Array.isArray(arr) &&
            arr.every((o) => typeof o.x === "number" && typeof o.y === "number")
        ) {
            return arr.map(p => ({
                x: p.x,
                y: Math.max(0.0, Math.min(1.0, p.y))
            }));
        }
    } catch { /* ignore */ }

    const nums = str
        .split(/[^0-9.+-]+/)
        .map(parseFloat)
        .filter((n) => !isNaN(n));
    if (nums.length < 2) {
        const y = nums[0] || 1;
        return [{ x: 0, y: Math.max(0.0, Math.min(1.0, y)) }, { x: 1, y: Math.max(0.0, Math.min(1.0, nums[0] != null ? y : 0)) }];
    }
    return nums.map((y, i) => ({ 
        x: i / (nums.length - 1), 
        y: formatValue(y)
    }));
}


function setup(node) {
    if (node._listSetupDone) return;
    node._listSetupDone = true;
    
                       
    const savedSize = node.properties?._ui_size;
    if (savedSize && Array.isArray(savedSize) && savedSize.length === 2) {
        node.size = [
            Math.max(MIN_NODE_WIDTH, Number(savedSize[0]) || MIN_NODE_WIDTH),
            Math.max(MIN_NODE_HEIGHT, Number(savedSize[1]) || MIN_NODE_HEIGHT)
        ];
    } else if (!node.size || node.size[0] < MIN_NODE_WIDTH || node.size[1] < MIN_NODE_HEIGHT) {
        node.size = [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
    }
                       
    node.minSize = [MIN_NODE_WIDTH, MIN_NODE_HEIGHT]; 
    
    if (node.properties === undefined) node.properties = {};
    if (node.properties._curveMode === undefined) {
        node.properties._curveMode = true;
    }
    let isCurveMode = node.properties._curveMode;


    hideWidgetAndSlot(node, GRAPH_DATA_NAME);
    
    if (node.size[0] < MIN_NODE_WIDTH) node.size[0] = MIN_NODE_WIDTH;
    if (node.size[1] < MIN_NODE_HEIGHT) node.size[1] = MIN_NODE_HEIGHT;
    
    const gw = node.widgets.find((w) => w.name === GRAPH_DATA_NAME);
    if (!gw) return;
    const ta = gw.element;
    
    if (ta) {
        ta.style.minHeight = "0px";
        ta.style.height = "0px";
        ta.style.padding = "0px";
        ta.style.border = "none";
        ta.style.overflow = "hidden";
        ta.style.position = "absolute";
        ta.style.visibility = "hidden";
    }

    let initialPts = null;
    if (gw.value && gw.value.trim() !== "") {
        try {
            const parsed = JSON.parse(gw.value);
            if (parsed && typeof parsed === "object" && !Array.isArray(parsed) && parsed.mode) {
                isCurveMode = (parsed.mode === "curve");
                node.properties._curveMode = isCurveMode;
            }
            initialPts = strToPts(gw.value);
        } catch {
            initialPts = null;
        }
    }

    if (!initialPts || initialPts.length === 0) {
        initialPts = [{x: 0, y: 1}, {x: 1, y: 0}];
        const defaultJson = JSON.stringify(initialPts);
        ta.value = defaultJson;
        gw.value = defaultJson;
    } else {
        ta.value = JSON.stringify(initialPts);
    }

    const wrap = $el("div", {
        style: {
            width: "100%",
            height: "100%", 
            position: "relative",
            display: "flex",
            flexDirection: "column",
            overflow: "hidden", 
            boxSizing: "border-box",
            paddingBottom: isNodes2_0() ? "8px" : "0px"
        }
    });
    
    const canvas = $el("canvas", {
        style: {
            width: "100%",
            flex: "1 1 0", 
            minHeight: "0px", 
            background: "#282828", border: "1px solid #555",
            borderRadius: "4px", cursor: "crosshair"
        }
    });
    wrap.appendChild(canvas);

    const preview = $el("textarea", {
        placeholder: "Values preview…",
        readOnly: true,
        style: {
            width: "100%", height: '55px', fontFamily: "monospace",
            background: "#181818", color: "#ccc",
            border: "1px solid #555", borderRadius: "4px",
            boxSizing: "border-box", padding: "4px", resize: "none",
            marginTop: "4px", 
            flexShrink: "0" 
        }
    });
    wrap.appendChild(preview);

    eeMarkForward(wrap);

    // DOM widget 高度随节点高度联动（hue_curve_base 同款范式）。
    // 原 nodes2_0 路径 computeSize 恒返 MIN_WIDGET_HEIGHT(100)，
    // 鼠标拉高节点后多余高度全部变成节点底部空白。
    let currentWidgetHeight = Math.max(
        MIN_WIDGET_HEIGHT,
        (node.properties?._ui_size?.[1] ?? node.size?.[1] ?? 0) - NON_WIDGET_HEIGHT
    );

    const domWidget = node.addDOMWidget(CANVAS_TYPE, "custom", wrap, {
        serialize: true,
        hideOnZoom: false
    });

    if (domWidget) {
        if (isNodes2_0()) {
            domWidget.computeSize = function(width) {
                return [Math.max(MIN_NODE_WIDTH, Number(width) || MIN_NODE_WIDTH), currentWidgetHeight];
            };
            try {
                Object.defineProperty(domWidget, 'min_size', {
                    get: () => [MIN_NODE_WIDTH, MIN_WIDGET_HEIGHT],
                    configurable: true
                });
            } catch(e) {}
        } else {
        }
    }

    const origComputeSize = node.computeSize;
    node.computeSize = function(out) {
        let size = origComputeSize
            ? origComputeSize.apply(this, arguments)
            : [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];

        size[0] = Math.max(MIN_NODE_WIDTH, size[0]);
        size[1] = Math.max(MIN_NODE_HEIGHT, size[1]);
        return size;
    };

    const origOnResize = node.onResize;
    node.onResize = function(size) {
        if (origOnResize) origOnResize.apply(this, arguments);

        const w = Math.max(
            MIN_NODE_WIDTH,
            Number(size?.[0] ?? this.size?.[0]) || MIN_NODE_WIDTH
        );
        const h = Math.max(
            MIN_NODE_HEIGHT,
            Number(size?.[1] ?? this.size?.[1]) || MIN_NODE_HEIGHT
        );

        this.size[0] = w;
        this.size[1] = h;
        if (size) {
            size[0] = w;
            size[1] = h;
        }

        // DOM widget 高度跟随节点高度：拉高节点时曲线区域随之变高，
        // 而不是把多余高度堆成节点底部空白
        currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, h - NON_WIDGET_HEIGHT);
        if (!isNodes2_0() && wrap) {
            wrap.style.height = currentWidgetHeight + "px";
        }
        this.properties = this.properties || {};
        this.properties._ui_size = [w, h];
        
        if (node._listDraw) node._listDraw();
        if (app.graph) app.graph.setDirtyCanvas(true, true);
    };

    
    // 曲线面板上方的按钮行：curve 左对齐面板左缘，reset 右对齐
    const btnBar = $el("div", {
        style: {
            display: "flex",
            gap: "4px",
            alignItems: "center",
            flexShrink: "0",
            marginBottom: "2px"
        }
    });

    const modeBtn = $el("button", {
        textContent: "curve",
        title: "Switch between curve modes (curve: Curve mode, straight: Linear mode)",
        style: {
            height: "20px",
            padding: "0 10px",
            borderRadius: "4px",
            border: "1px solid #555",
            background: isCurveMode ? "#1E88E5" : "#505050",
            color: "#fff",
            cursor: "pointer",
            fontSize: "11px",
            fontWeight: "bold",
            flexShrink: "0"
        }
    });
    btnBar.appendChild(modeBtn);

    const resetBtn = $el("button", {
        textContent: "reset",
        title: "Reset the curve to the default state.)",
        style: {
            height: "20px",
            padding: "0 10px",
            borderRadius: "4px",
            border: "1px solid #555",
            background: "#505050",
            color: "#fff",
            cursor: "pointer",
            fontSize: "11px",
            fontWeight: "bold",
            flexShrink: "0",
            marginLeft: "auto"
        }
    });
    btnBar.appendChild(resetBtn);

    wrap.insertBefore(btnBar, wrap.firstChild);

    function updateModeButtonVisual() {
        if (isCurveMode) {
            modeBtn.textContent = "curve";
            modeBtn.style.background = "#1E88E5";
            modeBtn.title = "Current mode: Curve (Click to switch to straight mode)";
        } else {
            modeBtn.textContent = "straight";
            modeBtn.style.background = "#757575";
            modeBtn.title = "Current mode: straight (Click to switch to curve mode)";
        }
    }

    modeBtn.onclick = () => {
        isCurveMode = !isCurveMode;
        node.properties._curveMode = isCurveMode;
        updateModeButtonVisual();
        applyPoints(strToPts(gw.value));
    };

    const slotBar = $el("div", {
        style: { display: "flex", gap: "4px", marginTop: "4px", alignItems: "center", flexShrink: 0 }
    });
    wrap.appendChild(slotBar);
 
    let slotsData = []; 
    let recordMode = false;
    
    const recBtn = $el("button", { 
        textContent: "💾", 
        title: "Switch save mode (after activation, click the number button to save the current curve)", 
        style: { 
            minWidth: "24px", 
            height: "24px", 
            cursor: "pointer", 
            display: "flex", 
            alignItems: "center", 
            justifyContent: "center", 
            padding: "0",
            lineHeight: "1",
            background: "none",  
            color: "#fff", 
            border: "none", 
            borderRadius: "5px", 
            fontSize: "20px" 
        } 
    });
    
    slotBar.appendChild(recBtn);

    const slotBtns = [];
    
    for (let i = 0; i < NUM_SLOTS; i++) {
        const b = $el("button", {
            textContent: `${i + 1}`,
            disabled: true, 
            style: { 
                flex: "1", 
                minWidth: "16px", 
                height: "24px",
                opacity: "0.3", 
                cursor: "not-allowed", 
                display: "flex", 
                alignItems: "center", 
                justifyContent: "center", 
                padding: "0", 
                fontSize: "14px",
                background: "#888",
                color: "#fff",
                border: "none",
                borderRadius: "5px"
            }
        });
        slotBar.appendChild(b);
        slotBtns.push(b);

        b.onclick = async () => {
            if (recordMode) {
                slotsData[i] = {
                    points: gw.value,
                    curveMode: isCurveMode 
                };
                b.style.opacity = "0.5"; 
                try {
                    await fetch('/element_easy/list_Curve_presets', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/json' },
                        body: JSON.stringify(slotsData)
                    });
                } catch (e) {
                    console.error("[Element_listGraph] Save preset failed", e);
                }
                recBtn.click();
            } else if (slotsData[i]) {
                let preset = slotsData[i];
                let pts;
                let mode = true; 
                
                if (typeof preset === 'object' && preset !== null) {
                    pts = strToPts(preset.points);
                    mode = preset.curveMode !== undefined ? preset.curveMode : true;
                } else {
                    pts = strToPts(preset);
                }
                
                isCurveMode = mode;
                node.properties._curveMode = mode;
                updateModeButtonVisual();
                
                applyPoints(pts);
            }
        };
    }
    
    function updateSlotUI() {
        slotBtns.forEach((b, i) => {
            const preset = slotsData[i];
            const hasData = preset && (typeof preset === 'object' ? preset.points : preset);
            const ok = hasData || recordMode;
            
            b.disabled = !ok;
            
            if (recordMode && hasData) {
                b.style.opacity = "1";
                b.style.cursor = "pointer";
                b.style.background = "#1E88E5";
            } else {
                b.style.opacity = ok ? "1" : "0.3";
                b.style.cursor = ok ? "pointer" : "not-allowed";
                b.style.background = "#888";  
            }
        });
    }
   
    recBtn.onclick = () => {
        recordMode = !recordMode;
        if (recordMode) {
            recBtn.style.background = "#ff4444";
            recBtn.style.border = "1px solid #ff4444";
        } else {
            recBtn.style.background = "none";
            recBtn.style.border = "none";
        }
        updateSlotUI();
    };

    async function loadPresetsFromFile() {
        try {
            const response = await fetch('/element_easy/list_Curve_presets');
            if (response.ok) {
                const data = await response.json();
                if (Array.isArray(data)) {
                    slotsData = data;
                    updateSlotUI();
                }
            }
        } catch (e) {
            console.error("[Element_listGraph] Failed to read preset file", e);
        }
    }
    
    loadPresetsFromFile();

    let undoStack = [];
    function pushUndo(state) {
        undoStack.unshift(state);
        if (undoStack.length > UNDO_LIMIT) undoStack.pop();
    }

    function applyPoints(pts) {
        pushUndo(gw.value);
        const clean = pts.map((p) => ({
            x: Math.round(p.x * 100000) / 100000,
            y: formatValue(p.y)
        }));
        
        const payload = {
            points: clean,
            mode: isCurveMode ? "curve" : "linear"
        };
        const jsonStr = JSON.stringify(payload);
        
        gw.value = jsonStr;
        ta.value = jsonStr;
        draw(clean);
    }

    node._applyPoints = applyPoints;

    const ctx = canvas.getContext("2d");
    
    let _coeffCacheKey = "";
    let _coeffCache = null;
    function getCoeffsCached(pts) {
        const key = JSON.stringify(pts);
        if (key !== _coeffCacheKey) {
          _coeffCacheKey = key;
          _coeffCache = computeSplineCoefficients(pts);
        }
        return _coeffCache;
    }
    
    function draw(overridePts) {
        const pts = overridePts || strToPts(gw.value);
        const dpr = window.devicePixelRatio || 1;
        const w = canvas.clientWidth, h = canvas.clientHeight;
        canvas.width = w * dpr;
        canvas.height = h * dpr;
        ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
        ctx.clearRect(0, 0, w, h);

        ctx.strokeStyle = GUIDE_COLOR;
        ctx.lineWidth = 0.5;
        ctx.beginPath();
        for (let i = 1; i < 10; i++) {
            const x = (i * w) / 10, y = (i * h) / 10;
            ctx.moveTo(x, 0); ctx.lineTo(x, h);
            ctx.moveTo(0, y); ctx.lineTo(w, y);
        }
        ctx.stroke();

        if (pts.length >= 2) {
            ctx.strokeStyle = CURVE_COLOR;
            ctx.lineWidth = 1.5;
            ctx.lineCap = "round";
            ctx.lineJoin = "round";
            ctx.beginPath();

            if (isCurveMode) {
                const coeffs = getCoeffsCached(pts);
                const drawSteps = Math.max(w * 2, 200);
                for (let i = 0; i <= drawSteps; i++) {
                    const t = i / drawSteps;
                    const y = evaluateSpline(t, coeffs);
                    const px = t * w;
                    const py = (1 - Math.max(0.0, Math.min(1.0, y))) * h;
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }
            } else {
                const sorted = pts.slice().sort((a, b) => a.x - b.x);
                for (let i = 0; i < sorted.length; i++) {
                    const px = sorted[i].x * w;
                    const py = (1 - Math.max(0.0, Math.min(1.0, sorted[i].y))) * h;
                    if (i === 0) ctx.moveTo(px, py);
                    else ctx.lineTo(px, py);
                }
            }
            ctx.stroke();

            pts.forEach((p) => {
                const px = p.x * w;
                const py = (1 - Math.max(0.0, Math.min(1.0, p.y))) * h;
                ctx.fillStyle = POINT_COLOR;
                ctx.beginPath();
                ctx.arc(px, py, POINT_RADIUS, 0, 2 * Math.PI);
                ctx.fill();
            });
        }

        const stepsW = Math.round(node.widgets.find((w) => w.name === STEPS_NAME).value || 0);
        const maxValueW = node.widgets.find((w) => w.name === "max_value")?.value ?? 1.0;
        const valueList = isCurveMode
            ? calcSmoothValues(pts, stepsW)
            : calcLinearValues(pts, stepsW);
        preview.value = valueList
            .map((v) => parseFloat((v * maxValueW).toFixed(5)))
            .join(", ");
    }
    
    node._listDraw = draw;

    // steps/max_value 变更后强制刷新预览。
    // 不依赖 widget.callback —— 部分前端版本的值提交路径不触发自定义
    // callback（实测截图：steps 6→7 后预览停留在 6 时刻的值）。
    // onDrawBackground 每帧调用，代价仅为两次属性读取，值变化才重绘。
    let _watchSteps = null, _watchMax = null;
    const _origOnDrawBackground = node.onDrawBackground;
    node.onDrawBackground = function () {
        if (_origOnDrawBackground) _origOnDrawBackground.apply(this, arguments);
        const sw = this.widgets && this.widgets.find((w) => w.name === STEPS_NAME);
        const mw = this.widgets && this.widgets.find((w) => w.name === "max_value");
        const s = sw ? sw.value : null;
        const m = mw ? mw.value : null;
        if (s !== _watchSteps || m !== _watchMax) {
            _watchSteps = s;
            _watchMax = m;
            draw();
        }
    };

    let debounce;
    ta.addEventListener("input", () => {
        clearTimeout(debounce);
        debounce = setTimeout(() => {
            if (ta.value.trim()) draw(strToPts(ta.value));
        }, 200);
    });
    ta.addEventListener("blur", () => {
        if (ta.value.trim()) applyPoints(strToPts(ta.value));
    });
    ta.addEventListener("keydown", (e) => {
        if ((e.ctrlKey||e.metaKey) && e.key==="z" && undoStack.length) {
            e.preventDefault();
            const prev = undoStack.shift();
            gw.value = prev;
            const pts = strToPts(prev);
            ta.value = prev; 
            draw(pts);
        }
    });
    
    resetBtn.onclick = () => {
        pushUndo(gw.value);
        const defaultPoints = [{x: 0, y: 1}, {x: 1, y: 0}];
        applyPoints(defaultPoints);
    };

    let dragIdx = -1;
        let dragPts = null;
    let lastClickTime = 0;
    let lastClickX = 0;
    let lastClickY = 0;
    const DOUBLE_CLICK_DELAY = 300;

    canvas.onpointerdown = (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1 - (e.clientY - rect.top) / rect.height;
        let pts = strToPts(gw.value);

        if (e.button === 2) {
            const idx = pts.findIndex(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
            if (idx > 0 && idx < pts.length - 1 && pts.length > MIN_POINTS) {
                pushUndo(gw.value);
                pts.splice(idx, 1);
                applyPoints(pts);
            }
            e.preventDefault();
            return;
        }

        if (e.button === 0) {
            let existingIdx = pts.findIndex(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);

            if (existingIdx >= 0) {
                dragIdx = existingIdx;
                                dragPts = pts;
            } else {
                pushUndo(gw.value); 
                
                let insertIdx = pts.findIndex(p => p.x > x);
                if (insertIdx === -1) insertIdx = pts.length;
                
                const leftPt = pts[insertIdx - 1] || pts[0];
                const rightPt = pts[insertIdx] || pts[pts.length - 1];
                
                if (Math.abs(rightPt.x - leftPt.x) < 0.01) return; 

                let newY;
                if (isCurveMode) {
                    const coeffs = getCoeffsCached(pts);
                    newY = evaluateSpline(x, coeffs);
                } else {
                    const t = (x - leftPt.x) / (rightPt.x - leftPt.x);
                    newY = leftPt.y + t * (rightPt.y - leftPt.y);
                }
                
                const newX = Math.max(leftPt.x + 0.005, Math.min(rightPt.x - 0.005, x));
                
                const newPoint = { 
                    x: newX,
                    y: formatValue(Math.min(1, Math.max(0, newY))) 
                };
                
                pts.splice(insertIdx, 0, newPoint);
                applyPoints(pts);
                dragIdx = insertIdx;
                                dragPts = pts;
            }

            if (dragIdx >= 0) {
                e.target.setPointerCapture(e.pointerId);
            }
            e.preventDefault();
        }
    };

    canvas.onpointermove = (e) => {
        const rect = canvas.getBoundingClientRect();
        const x = (e.clientX - rect.left) / rect.width;
        const y = 1 - (e.clientY - rect.top) / rect.height;
        const pts = dragPts || strToPts(gw.value);

        if (dragIdx >= 0) {
            const ny = Math.min(1, Math.max(0, y));
            if (dragIdx === 0) {
                pts[dragIdx] = { x: 0, y: ny };
            } else if (dragIdx === pts.length - 1) {
                pts[dragIdx] = { x: 1, y: ny };
            } else {
                const minX = pts[dragIdx - 1].x + 0.005;
                const maxX = pts[dragIdx + 1].x - 0.005;
                const nx = Math.min(maxX, Math.max(minX, x));
                pts[dragIdx] = { x: nx, y: ny };
            }
            draw(pts);
        }

        const over = pts.some(p => Math.hypot(p.x - x, p.y - y) < GRAB_THRESHOLD);
        canvas.style.cursor = dragIdx >= 0 || over ? "pointer" : "crosshair";
    };
    
    canvas.onpointerup = (e) => {
        if (dragIdx >= 0) {
            e.target.releasePointerCapture(e.pointerId);
                if (dragPts) applyPoints(dragPts);         
            dragPts = null;
            dragIdx = -1;
        }
    };
    
    canvas.oncontextmenu = (e) => e.preventDefault();

    const sw = node.widgets.find((w) => w.name === STEPS_NAME);
    const maxValueWidget = node.widgets.find((w) => w.name === "max_value");
    
    if (sw) sw.callback = () => applyPoints(strToPts(ta.value));
    if (maxValueWidget) {
        maxValueWidget.callback = () => {
            node.properties._maxValue = maxValueWidget.value;
            draw();
        };
    }

    const origSerialize = node.onSerialize;
    node.onSerialize = function(o) {
        if (origSerialize) origSerialize.apply(this, arguments);
        this.properties = this.properties || {};
        this.properties._ui_size = [this.size?.[0] || MIN_NODE_WIDTH, this.size?.[1] || MIN_NODE_HEIGHT];
        this.properties._curveMode = isCurveMode;
        const maxV = node.widgets.find((w) => w.name === "max_value")?.value ?? 1.0;
        this.properties._maxValue = maxV;
    };
    
    const origConfigure = node.onConfigure;
    node.onConfigure = function(o) {
        if (origConfigure) origConfigure.apply(this, arguments);
        
        const savedSize = this.properties?._ui_size || o?.properties?._ui_size;
        if (Array.isArray(savedSize) && savedSize.length === 2) {
            const w = Math.max(MIN_NODE_WIDTH, Number(savedSize[0]) || MIN_NODE_WIDTH);
            const h = Math.max(MIN_NODE_HEIGHT, Number(savedSize[1]) || MIN_NODE_HEIGHT);
            this.size = [w, h];
            currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, h - NON_WIDGET_HEIGHT);
        }
        
        if (this.properties?._curveMode !== undefined) {
            isCurveMode = this.properties._curveMode;
            updateModeButtonVisual();
        }
        if (this.properties?._maxValue !== undefined && maxValueWidget) {
            maxValueWidget.value = this.properties._maxValue;
        }
        // 工作流存量数据可能是浮点 steps（老版前端/外部工具写入）。
        // 显示层四舍五入、后端截断会产生"少 1"假象——加载时统一量化，
        // 显示/执行/存档三者一致。
        const _stepsW = this.widgets && this.widgets.find((w) => w.name === STEPS_NAME);
        if (_stepsW) {
            const _n = Number(_stepsW.value);
            if (Number.isFinite(_n) && _n % 1 !== 0) {
                _stepsW.value = Math.round(_n);
            }
        }
        this.minSize = [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
    };

    updateModeButtonVisual();
    applyPoints(strToPts(ta.value));
    new ResizeObserver(() => draw()).observe(canvas);
}

app.registerExtension({
    name: "Element_listGraph_Curve.widget",
    beforeRegisterNodeDef(nt, nd) {
        if (nd.name === NODE_CLASS) {
            
            try {
                if (nd?.input?.required) {
                    if (nd.input.required.graph_data) {
                        nd.input.required.graph_data[1] = {
                            ...(nd.input.required.graph_data[1] || {}),
                            hidden: true,
                            forceInput: false,
                        };
                    }
                }
            } catch (e) {
                console.warn("[ListGraphCurve] nodeData hide patch failed:", e);
            }
            
            const origConfigure = nt.prototype.onConfigure;
            nt.prototype.onConfigure = function(info) {
                origConfigure?.apply(this, arguments);
                setup(this);
            };

            const origNodeCreated = nt.prototype.onNodeCreated;
            nt.prototype.onNodeCreated = function() {
                origNodeCreated?.apply(this, arguments);
                
                if (!this.properties) this.properties = {};
                
                setup(this);
            };      
        }
    },
    
});

if (app.on) {
    app.on("nodeAdded", (n) => { if (n.type === NODE_CLASS) setup(n); });
} else {
    setInterval(() => {
        (app.graph?._nodes||[]).forEach((n) => {
            if (n.type === NODE_CLASS) setup(n);
        });
    }, 100);
}