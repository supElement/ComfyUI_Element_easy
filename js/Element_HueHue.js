import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Element_easy.HueHue",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name !== "ElementHueHue") return;

        // ====== 定义层隐藏（Nodes2.0）======
        try {
            if (nodeData?.input?.required) {
                if (nodeData.input.required.curve_data) {
                    nodeData.input.required.curve_data[1] = {
                        ...(nodeData.input.required.curve_data[1] || {}),
                        hidden: true,
                        forceInput: false,
                    };
                }
                if (nodeData.input.required.output_mode) {
                    nodeData.input.required.output_mode[1] = {
                        ...(nodeData.input.required.output_mode[1] || {}),
                        hidden: true,
                        forceInput: false,
                    };
                }
            }
        } catch (e) {
            console.warn("[HueHue] nodeData hide patch failed:", e);
        }

        const onNodeCreated = nodeType.prototype.onNodeCreated;

        nodeType.prototype.onNodeCreated = function () {
            if (onNodeCreated) onNodeCreated.apply(this, arguments);

            const MIN_NODE_WIDTH = 260;
            const MIN_NODE_HEIGHT = 350;

            const isNodes2_0 =
                !!document.querySelector("comfy-app") ||
                !!document.querySelector(".comfy-vue") ||
                (window.comfyAPI && window.comfyAPI.vue);

            if (this.size[0] < MIN_NODE_WIDTH) this.size[0] = MIN_NODE_WIDTH;
            if (this.size[1] < MIN_NODE_HEIGHT) this.size[1] = MIN_NODE_HEIGHT;

            // ====== 先引用 再隐藏 ======
            const curveWidget = this.widgets?.find(w => w.name === "curve_data");
            const outputModeWidget = this.widgets?.find(w => w.name === "output_mode");

            const hideWidgetAndSlot = (widgetName) => {
                const w = this.widgets?.find(x => x.name === widgetName);
                if (w) {
                    w.type = "hidden";
                    w.hidden = true;
                    w.computeSize = () => [0, 0];
                    w.draw = () => {};
                    if (w.inputEl) {
                        w.inputEl.style.display = "none";
                        if (w.inputEl.parentElement) w.inputEl.parentElement.style.display = "none";
                    }
                }
                if (this.inputs) {
                    const idx = this.inputs.findIndex(i => i.name === widgetName);
                    if (idx !== -1) this.removeInput(idx);
                }
            };

            hideWidgetAndSlot("curve_data");
            hideWidgetAndSlot("output_mode");

            if (outputModeWidget && (outputModeWidget.value === undefined || outputModeWidget.value === null)) {
                outputModeWidget.value = false;
            }

            let curvePoints = [];
            let lutData = new Array(512).fill(1.0);

            const parseData = (str) => {
                try {
                    const d = JSON.parse(str);
                    if (d && d.points) curvePoints = d.points;
                    if (d && d.lut) lutData = d.lut;
                } catch (e) {}
            };
            if (curveWidget && curveWidget.value) parseData(curveWidget.value);

            const DOM_DEFAULT_HEIGHT = 260;
            const NON_WIDGET_HEIGHT = 90; 
            const MIN_WIDGET_HEIGHT = 200;
            let currentWidgetHeight = DOM_DEFAULT_HEIGHT;

            if (this.properties?._ui_size?.[1]) {
                const savedH = this.properties._ui_size[1];
                currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, savedH - NON_WIDGET_HEIGHT);
            } else if (this.size?.[1] >= MIN_NODE_HEIGHT) {
                currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, this.size[1] - NON_WIDGET_HEIGHT);
            }

            const container = document.createElement("div");
            container.style.display = "flex";
            container.style.flexDirection = "column";
            container.style.width = "100%";
            container.style.height = "100%";
            container.style.borderRadius = "6px";
            container.style.overflow = "hidden";
            container.style.backgroundColor = "transparent";
            container.style.margin = "0";
            container.style.padding = "0";
            container.style.boxSizing = "border-box";

            // Header
            const header = document.createElement("div");
            header.style.display = "flex";
            header.style.height = "20px";
            header.style.flexShrink = "0";
            header.style.backgroundColor = "#222";
            header.style.alignItems = "center";
            header.style.padding = "0 10px";

            const titleSpan = document.createElement("span");
            titleSpan.innerText = "Hue vs Hue";
            titleSpan.style.color = "#CCC";
            titleSpan.style.fontSize = "11px";
            titleSpan.style.flex = "1";
            header.appendChild(titleSpan);

            const resetBtn = document.createElement("button");
            resetBtn.innerText = "Reset";
            resetBtn.style.border = "none";
            resetBtn.style.cursor = "pointer";
            resetBtn.style.backgroundColor = "#555";
            resetBtn.style.color = "#FFF";
            resetBtn.style.fontSize = "10px";
            resetBtn.style.borderRadius = "4px";
            resetBtn.style.padding = "2px 8px";
            resetBtn.onclick = () => {
                curvePoints = [];
                updateBackend();
                draw();
                updateLivePreview(false);
            };
            header.appendChild(resetBtn);
            container.appendChild(header);

            // View Area
            const viewArea = document.createElement("div");
            viewArea.style.flex = "1";
            viewArea.style.position = "relative";
            viewArea.style.width = "100%";
            viewArea.style.height = "100%";
            viewArea.style.backgroundColor = "#1a1a1a";

            const bgImageLayer = document.createElement("div");
            bgImageLayer.style.position = "absolute";
            bgImageLayer.style.inset = "0";
            bgImageLayer.style.backgroundSize = "contain";
            bgImageLayer.style.backgroundPosition = "center";
            bgImageLayer.style.backgroundRepeat = "no-repeat";
            bgImageLayer.style.opacity = "0.8";
            viewArea.appendChild(bgImageLayer);

            const PADDING = 14;
            const gradBar = document.createElement("div");
            gradBar.style.position = "absolute";
            gradBar.style.bottom = `${PADDING - 0}px`;
            gradBar.style.left = `${PADDING}px`;
            gradBar.style.right = `${PADDING}px`;
            gradBar.style.height = "4px";
            gradBar.style.borderRadius = "0px";
            //gradBar.style.background = "linear-gradient(to right, #FF0000, #FFFF00, #00FF00, #00FFFF, #0000FF, #FF00FF, #FF0000)";
			const a = 0.7; 
            gradBar.style.background = `linear-gradient(
              to right,
              rgba(255, 0, 0, ${a}),
              rgba(255, 255, 0, ${a}),
              rgba(0, 255, 0, ${a}),
              rgba(0, 255, 255, ${a}),
              rgba(0, 0, 255, ${a}),
              rgba(255, 0, 255, ${a}),
              rgba(255, 0, 0, ${a})
            )`;
            gradBar.style.zIndex = "2";
            gradBar.style.pointerEvents = "none";
            viewArea.appendChild(gradBar);

            const canvas = document.createElement("canvas");
            canvas.style.position = "absolute";
            canvas.style.inset = "0";
            canvas.style.width = "100%";
            canvas.style.height = "100%";
            canvas.style.cursor = "crosshair";
            canvas.style.zIndex = "3";
            viewArea.appendChild(canvas);

            container.appendChild(viewArea);
            const ctx = canvas.getContext("2d");

            // DOMWidget
            const widget = this.addDOMWidget("CurveUI", "div", container, { serialize: true, hideOnZoom: false });
            const nodeInstance = this;
            
            if (widget?.element) {
                widget.element.style.margin = "0";
                widget.element.style.padding = "0";
                widget.element.style.boxSizing = "border-box";
                widget.element.style.width = "100%";
            }
            
            widget.computeSize = function (width) {
                const w = Math.max(
                    MIN_NODE_WIDTH,
                    Number(width) || Number(nodeInstance?.size?.[0]) || MIN_NODE_WIDTH
                );
                return [w, currentWidgetHeight];
            };
            
            const origComputeSize = this.computeSize;
            this.computeSize = function (out) {
                let size = origComputeSize
                    ? origComputeSize.apply(this, arguments)
                    : [MIN_NODE_WIDTH, MIN_NODE_HEIGHT];
            
                const trueMinHeight = size[1] - currentWidgetHeight + MIN_WIDGET_HEIGHT;
            
                size[0] = Math.max(MIN_NODE_WIDTH, size[0]);
                size[1] = Math.max(MIN_NODE_HEIGHT, trueMinHeight);
                return size;
            };
            
            const onResize = this.onResize;
            this.onResize = function (size) {
                if (onResize) onResize.apply(this, arguments);
            
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
            
                currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, h - NON_WIDGET_HEIGHT);
            
                this.properties = this.properties || {};
                this.properties._ui_size = [w, h];
            };

            let resizeRaf = null;
            const resizeObserver = new ResizeObserver((entries) => {
                if (resizeRaf) return;
                resizeRaf = requestAnimationFrame(() => {
                    for (let entry of entries) {
                        const { width, height } = entry.contentRect;
                        if (width > 0 && height > 0 && (canvas.width !== width || canvas.height !== height)) {
                            canvas.width = width;
                            canvas.height = height;
                            draw();
                        }
                    }
                    resizeRaf = null;
                });
            });
            resizeObserver.observe(viewArea);

            // Bottom controls
            const modeControlArea = document.createElement("div");
            modeControlArea.style.display = "flex";
            modeControlArea.style.alignItems = "center";
            modeControlArea.style.width = "100%";
            modeControlArea.style.flexShrink = "0";
            modeControlArea.style.gap = "8px";
            modeControlArea.style.boxSizing = "border-box";
            modeControlArea.style.marginBottom = isNodes2_0 ? "8px" : "0px";

            const loadBtn = document.createElement("button");
            loadBtn.innerText = "Preview";
            loadBtn.style.flex = "7";
            loadBtn.style.height = "24px";
            loadBtn.style.lineHeight = "22px";
            loadBtn.style.marginTop = "8px";
            loadBtn.style.border = "none";
            loadBtn.style.borderRadius = "8px";
            loadBtn.style.cursor = "pointer";
            loadBtn.style.fontSize = "10px";
            loadBtn.style.fontWeight = "bold";
            loadBtn.style.backgroundColor = "#4f5d6d";
            loadBtn.style.color = "#FFF";
            loadBtn.onclick = async () => {
                try {
                    const p = await app.graphToPrompt();
            
                    const prompt = p?.output || p?.prompt || p;
                    if (!prompt || typeof prompt !== "object") {
                        console.error("[HueHue] graphToPrompt() returned invalid prompt:", p);
                        return;
                    }
            
                    const selectedNodeId = String(this.id);
                    const isolatedPrompt = {};
            
                    const traceDependencies = (nodeId) => {
                        if (!prompt[nodeId] || isolatedPrompt[nodeId]) return;
                        isolatedPrompt[nodeId] = prompt[nodeId];
            
                        const inputs = prompt[nodeId].inputs || {};
                        for (const key in inputs) {
                            const val = inputs[key];
                            if (Array.isArray(val) && val.length === 2) {
                                traceDependencies(String(val[0]));
                            }
                        }
                    };
            
                    traceDependencies(selectedNodeId);
            
                    if (Object.keys(isolatedPrompt).length === 0) {
                        console.warn("[HueHue] isolatedPrompt is empty. selectedNodeId =", selectedNodeId);
                        return;
                    }
            
                    const payload = {
                        client_id: api.clientId,
                        prompt: isolatedPrompt,
                    };
            
                    if (p?.workflow) {
                        payload.extra_data = { extra_pnginfo: { workflow: p.workflow } };
                    }
            
                    const resp = await api.fetchApi("/prompt", {
                        method: "POST",
                        headers: { "Content-Type": "application/json" },
                        body: JSON.stringify(payload),
                    });
            
                    if (!resp.ok) {
                        const txt = await resp.text().catch(() => "");
                        console.error("[HueHue] /prompt failed:", resp.status, txt);
                    }
                } catch (err) {
                    console.error("[HueHue] Failed to execute isolated node:", err);
                }
            };
            modeControlArea.appendChild(loadBtn);

            const modeBtn = document.createElement("button");
            modeBtn.innerText = "Multi Img";
            modeBtn.style.flex = "3";
            modeBtn.style.height = "24px";
            modeBtn.style.lineHeight = "22px";
            modeBtn.style.marginTop = "8px";
            modeBtn.style.border = "none";
            modeBtn.style.borderRadius = "8px";
            modeBtn.style.cursor = "pointer";
            modeBtn.style.fontSize = "10px";
            modeBtn.style.fontWeight = "bold";

            const updateModeUI = (isOutput) => {
                modeBtn.style.backgroundColor = isOutput ? "#56915a" : "#222";
                modeBtn.style.color = isOutput ? "#FFF" : "#CCC";
            };

            let currentMode = outputModeWidget ? !!outputModeWidget.value : false;
            updateModeUI(currentMode);

            modeBtn.onclick = () => {
                currentMode = !currentMode;
                if (outputModeWidget) outputModeWidget.value = currentMode;
                updateModeUI(currentMode);
                app.graph?.setDirtyCanvas(true);
            };
            modeControlArea.appendChild(modeBtn);
            container.appendChild(modeControlArea);

            // ====== Live preview ======
            let lastPreviewTime = 0;
            let pendingUpdate = false;
            let isPreviewPending = false;

            const updateLivePreview = (isDragging = false) => {
                const now = Date.now();
                const interval = isDragging ? 16 : 33;

                if (now - lastPreviewTime < interval) {
                    if (!pendingUpdate) {
                        pendingUpdate = true;
                        setTimeout(() => {
                            pendingUpdate = false;
                            updateLivePreview(isDragging);
                        }, interval - (now - lastPreviewTime));
                    }
                    return;
                }
                if (isPreviewPending) {
                    pendingUpdate = true;
                    return;
                }

                lastPreviewTime = now;
                pendingUpdate = false;
                isPreviewPending = true;

                const previewSizeWidget = nodeInstance.widgets?.find(w => w.name === "preview_size");
                const frameWidget = nodeInstance.widgets?.find(w => w.name === "frame_index");

                const body = {
                    node_id: nodeInstance.id.toString(),
                    curve_data: JSON.stringify({ points: curvePoints, lut: Array.from(lutData) }),
                    preview_size: previewSizeWidget ? parseInt(previewSizeWidget.value) : 512,
                    frame_index: frameWidget ? parseInt(frameWidget.value) : 0
                };

                (async () => {
                    try {
                        const response = await api.fetchApi("/element_huehue/live_preview", {
                            method: "POST",
                            body: JSON.stringify(body)
                        });

                        isPreviewPending = false;
                        if (pendingUpdate) {
                            pendingUpdate = false;
                            setTimeout(() => updateLivePreview(isDragging), 0);
                        }

                        if (response.ok) {
                            const img = await response.json();
                            if (img.filename) {
                                const url = api.apiURL(`/view?filename=${encodeURIComponent(img.filename)}&type=${img.type}&subfolder=${img.subfolder}&t=${Date.now()}`);
                                const imgLoader = new Image();
                                imgLoader.onload = () => {
                                    if (bgImageLayer) bgImageLayer.style.backgroundImage = `url(${url})`;
                                };
                                imgLoader.src = url;
                            }
                        }
                    } catch (e) {
                        isPreviewPending = false;
                        if (pendingUpdate) {
                            pendingUpdate = false;
                            setTimeout(() => updateLivePreview(isDragging), 0);
                        }
                    }
                })();
            };

            ["preview_size", "frame_index"].forEach(paramName => {
                const w = this.widgets.find(widget => widget.name === paramName);
                if (w) {
                    const originalCallback = w.callback;
                    w.callback = function (value) {
                        if (originalCallback) originalCallback.apply(this, arguments);
                        updateLivePreview(false);
                    };
                    if (w.inputEl) {
                        w.inputEl.addEventListener("change", () => updateLivePreview(false));
                        w.inputEl.addEventListener("input", () => updateLivePreview(false));
                    }
                }
            });

            // LUT
            const LUT_SIZE = 512;
            const BASE_Y = 0.5;
            const HUE_ANCHORS = [0 / 6, 1 / 6, 2 / 6, 3 / 6, 4 / 6, 5 / 6];
            const EPS = 1e-6;
            const ANCHOR_INJECT_RADIUS = 0.06;

            const wrap01 = (x) => ((x % 1) + 1) % 1;
            const clamp01 = (v) => Math.max(0, Math.min(1, v));
            const circDist = (a, b) => {
                const d = Math.abs(a - b);
                return Math.min(d, 1 - d);
            };

            const sanitizeUserPoints = (pts) => {
                const out = [];
                for (const p of (pts || [])) {
                    if (!Array.isArray(p) || p.length < 2) continue;
                    let x = wrap01(Number(p[0]));
                    if (x > 1 - EPS) x = 0.0;
                    let y = clamp01(Number(p[1]));
                    if (Number.isFinite(x) && Number.isFinite(y)) out.push([x, y]);
                }
                out.sort((a, b) => a[0] - b[0]);

                const merged = [];
                for (const p of out) {
                    if (!merged.length || Math.abs(p[0] - merged[merged.length - 1][0]) > 0.003) merged.push(p);
                    else merged[merged.length - 1] = p;
                }
                return merged;
            };

            const buildWorkingPoints = (userPts) => {
                return sanitizeUserPoints(userPts);
            };

            const generateLUT = () => {
                const pts = buildWorkingPoints(curvePoints);
                const n = pts.length;
                lutData = new Float32Array(LUT_SIZE);

                if (n < 2) {
                    if (n === 1) {
                        const v = clamp01(pts[0][1]) * 2.0; // 0.5 -> 1.0
                        lutData.fill(v);
                    } else {
                        lutData.fill(1.0);
                    }
                    return;
                }

                const x = pts.map(p => p[0]);
                const y = pts.map(p => p[1]);

                const h = new Array(n);
                const d = new Array(n);
                for (let i = 0; i < n; i++) {
                    const x0 = x[i];
                    const x1 = (i === n - 1) ? (x[0] + 1.0) : x[i + 1];
                    h[i] = Math.max(EPS, x1 - x0);
                    d[i] = (y[(i + 1) % n] - y[i]) / h[i];
                }

                const m = new Array(n).fill(0);
                for (let i = 0; i < n; i++) {
                    const im1 = (i - 1 + n) % n;
                    const d0 = d[im1], d1 = d[i];
                    if (d0 * d1 <= 0) { m[i] = 0; continue; }
                    const h0 = h[im1], h1 = h[i];
                    const w1 = 2 * h1 + h0, w2 = h1 + 2 * h0;
                    m[i] = (w1 + w2) / (w1 / d0 + w2 / d1);
                }

                for (let i = 0; i < n; i++) {
                    const i1 = (i + 1) % n;
                    if (Math.abs(d[i]) < EPS) {
                        m[i] = 0; m[i1] = 0; continue;
                    }
                    const a = m[i] / d[i], b = m[i1] / d[i];
                    const s = a * a + b * b;
                    if (s > 9) {
                        const t = 3 / Math.sqrt(s);
                        m[i] = t * a * d[i];
                        m[i1] = t * b * d[i];
                    }
                }

                for (let k = 0; k < LUT_SIZE; k++) {
                    let xs = k / (LUT_SIZE - 1);
                    if (xs >= 1.0) xs = 0.0;
                    if (xs < x[0]) xs += 1.0;

                    let seg = 0;
                    while (seg < n - 1 && xs >= x[seg + 1]) seg++;

                    const x0 = x[seg];
                    const x1 = (seg === n - 1) ? (x[0] + 1.0) : x[seg + 1];
                    const y0 = y[seg];
                    const y1 = y[(seg + 1) % n];
                    const hs = x1 - x0;
                    const t = (xs - x0) / hs;
                    const t2 = t * t, t3 = t2 * t;

                    const h00 = 2 * t3 - 3 * t2 + 1;
                    const h10 = t3 - 2 * t2 + t;
                    const h01 = -2 * t3 + 3 * t2;
                    const h11 = t3 - t2;

                    let yy = h00 * y0 + h10 * hs * m[seg] + h01 * y1 + h11 * hs * m[(seg + 1) % n];
                    yy = clamp01(yy);
                    lutData[k] = yy * 2.0;
                }

                lutData[LUT_SIZE - 1] = lutData[0];
            };

            const updateBackend = () => {
                generateLUT();
                const dataStr = JSON.stringify({
                    points: curvePoints,
                    lut: Array.from(lutData)
                });
                if (curveWidget) {
                    curveWidget.value = dataStr;
                }
                this.properties = this.properties || {};
                this.properties.curve_data = dataStr;
                if (app.graph) app.graph.setDirtyCanvas(true);
            };

            // Interaction
            let isDragging = false;
            let dragIndex = -1;

            const getPos = (e) => {
                const rect = canvas.getBoundingClientRect();
                const scaleX = canvas.width / rect.width;
                const scaleY = canvas.height / rect.height;
                const mouseX = (e.clientX - rect.left) * scaleX;
                const mouseY = (e.clientY - rect.top) * scaleY;

                const innerW = canvas.width - PADDING * 2;
                const innerH = canvas.height - PADDING * 2;
                const x = (mouseX - PADDING) / innerW;
                const y = 1.0 - (mouseY - PADDING) / innerH;
                return [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))];
            };

            canvas.addEventListener("dblclick", (e) => {
                const [x, y] = getPos(e);
                curvePoints.push([x, y]);
                curvePoints.sort((a, b) => a[0] - b[0]);
                updateBackend();
                draw();
                updateLivePreview(false);
            });

            canvas.addEventListener("mousedown", (e) => {
                const [x, y] = getPos(e);
                let closestIdx = -1, minDist = 0.05;
                for (let i = 0; i < curvePoints.length; i++) {
                    const dxRaw = Math.abs(curvePoints[i][0] - x);
                    const dx = Math.min(dxRaw, 1 - dxRaw); // hue环形距离
                    const dy = Math.abs(curvePoints[i][1] - y);
                    const dist = Math.hypot(dx, dy);
                    if (dist < minDist) { minDist = dist; closestIdx = i; }
                }

                if (e.button === 0) {
                    if (closestIdx !== -1) {
                        isDragging = true;
                        dragIndex = closestIdx;
                    }
                } else if (e.button === 2) {
                    e.preventDefault();
                    if (closestIdx !== -1) {
                        curvePoints.splice(closestIdx, 1);
                        updateBackend();
                        draw();
                        updateLivePreview(false);
                    }
                }
            });

            canvas.addEventListener("contextmenu", e => e.preventDefault());

            let dragRaf = null;
            let pendingDragEvent = null;
            
            window.addEventListener("mousemove", (e) => {
                if (!isDragging || dragIndex === -1) return;
                pendingDragEvent = e;
                if (dragRaf) return;
            
                dragRaf = requestAnimationFrame(() => {
                    const ev = pendingDragEvent;
                    pendingDragEvent = null;
                    dragRaf = null;
                    if (!ev || !isDragging || dragIndex === -1) return;
            
                    const [x, y] = getPos(ev);
                    const minX = dragIndex > 0 ? curvePoints[dragIndex - 1][0] + 0.01 : 0;
                    const maxX = dragIndex < curvePoints.length - 1 ? curvePoints[dragIndex + 1][0] - 0.01 : 1;
                    curvePoints[dragIndex] = [Math.max(minX, Math.min(maxX, x)), y];
            
                    generateLUT();
                    draw();
                    updateLivePreview(true);
                });
            });

            window.addEventListener("mouseup", () => {
                if (isDragging) {
                    isDragging = false;
                    if (dragRaf) {
                        cancelAnimationFrame(dragRaf);
                        dragRaf = null;
                    }
                    pendingDragEvent = null;
                    updateBackend();
                }
            });

            const draw = () => {
                const w = canvas.width, h = canvas.height;
                if (!w || !h) return;

                ctx.clearRect(0, 0, w, h);

                const innerW = w - PADDING * 2;
                const innerH = h - PADDING * 2;
                const toPx = (val) => PADDING + val * innerW;
                const toPy = (val) => PADDING + (1 - val) * innerH;

                ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(toPx(0), toPy(0.5));
                ctx.lineTo(toPx(1), toPy(0.5));
                for (let i = 1; i <= 5; i++) {
                    const px = Math.round(toPx(i / 6)) + 0.5;
                    ctx.moveTo(px, toPy(0));
                    ctx.lineTo(px, toPy(1));
                }
                ctx.stroke();
				
                // 边框
                const left = Math.round(toPx(0)) + 0.5;
                const right = Math.round(toPx(1)) + 0.5;
                const top = Math.round(toPy(1)) + 0.5;
                const bottom = Math.round(toPy(0)) + 0.5;
                ctx.strokeStyle = "rgba(255, 255, 255, 0.35)";
                ctx.lineWidth = 1;
                ctx.beginPath();
                ctx.moveTo(left, top);    ctx.lineTo(right, top);     
                ctx.moveTo(left, bottom); ctx.lineTo(right, bottom);  
                ctx.moveTo(left, top);    ctx.lineTo(left, bottom);   
                ctx.moveTo(right, top);   ctx.lineTo(right, bottom);  
                ctx.stroke();

                if (lutData.length > 0) {
                    ctx.strokeStyle = "#FFFFFF";
                    ctx.lineWidth = 2;
                    ctx.shadowColor = "rgba(0,0,0,0.8)";
                    ctx.shadowBlur = 3;
                    ctx.beginPath();
                    for (let i = 0; i < lutData.length; i++) {
                        const x = i / (lutData.length - 1);
                        const y = lutData[i] / 2.0;
                        if (i === 0) ctx.moveTo(toPx(x), toPy(y));
                        else ctx.lineTo(toPx(x), toPy(y));
                    }
                    ctx.stroke();
                    ctx.shadowBlur = 0;
                }

                ctx.fillStyle = "#FFFFFF";
                ctx.strokeStyle = "#000000";
                ctx.lineWidth = 1.5;
                curvePoints.forEach(p => {
                    ctx.beginPath();
                    ctx.arc(toPx(p[0]), toPy(p[1]), 5, 0, Math.PI * 2);
                    ctx.fill();
                    ctx.stroke();
                });
            };

            const _onSerialize = this.onSerialize;
            this.onSerialize = function (o) {
                if (_onSerialize) _onSerialize.apply(this, arguments);
                this.properties = this.properties || {};
                this.properties.curve_data = JSON.stringify({
                    points: curvePoints || [],
                    lut: Array.from(lutData || [])
                });

                this.properties._ui_size = [this.size?.[0] || MIN_NODE_WIDTH, this.size?.[1] || MIN_NODE_HEIGHT];
                const cw = this.widgets?.find(w => w.name === "curve_data");
                if (cw) cw.value = this.properties.curve_data;
            };
            
            const _onConfigure = this.onConfigure;
            this.onConfigure = function (o) {
                if (_onConfigure) _onConfigure.apply(this, arguments);
            
                const savedSize = this.properties?._ui_size || o?.properties?._ui_size;
                if (Array.isArray(savedSize) && savedSize.length === 2) {
                    const w = Math.max(MIN_NODE_WIDTH, Number(savedSize[0]) || MIN_NODE_WIDTH);
                    let h = Math.max(MIN_NODE_HEIGHT, Number(savedSize[1]) || MIN_NODE_HEIGHT);
                    currentWidgetHeight = Math.max(MIN_WIDGET_HEIGHT, h - NON_WIDGET_HEIGHT);
                    h = Math.max(MIN_NODE_HEIGHT, currentWidgetHeight + NON_WIDGET_HEIGHT); // 统一回写
                    this.size = [w, h];
                }
            
                let restored = this.properties?.curve_data;
                if (!restored && o?.properties?.curve_data) restored = o.properties.curve_data;
            
                if (!restored && Array.isArray(o?.widgets_values) && this.widgets?.length) {
                    const idx = this.widgets.findIndex(w => w.name === "curve_data");
                    if (idx >= 0) restored = o.widgets_values[idx];
                }
            
                if (restored) {
                    try {
                        const d = JSON.parse(restored);
                        curvePoints = Array.isArray(d?.points) ? d.points : [];
                        lutData = Array.isArray(d?.lut) ? d.lut : lutData;
                        const cw = this.widgets?.find(w => w.name === "curve_data");
                        if (cw) cw.value = restored;
                    } catch (e) {}
                }
            
                setTimeout(() => {
                    generateLUT();
                    draw();
                    if (this.onResize) this.onResize(this.size);
                    
                    if (this.setSize && this.size) {
                        this.setSize([this.size[0], this.size[1]]);
                    }
                    app.graph?.setDirtyCanvas(true, true);
                }, 0);
            };
        };

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            onExecuted?.apply(this, arguments);

            if (message?.batch_size?.length > 0) {
                const maxFrameIndex = message.batch_size[0] - 1;
                const frameWidget = this.widgets.find(w => w.name === "frame_index");
                if (frameWidget) {
                    frameWidget.options.max = maxFrameIndex;
                    if (frameWidget.value > maxFrameIndex) frameWidget.value = maxFrameIndex;
                }
            }

            if (message?.bg_image?.length > 0) {
                const img = message.bg_image[0];
                const url = api.apiURL(`/view?filename=${encodeURIComponent(img.filename)}&type=${img.type}&subfolder=${img.subfolder}&t=${Date.now()}`);
                const curveUI = this.widgets.find(w => w.name === "CurveUI");
                if (curveUI?.element) {
                    const viewArea = curveUI.element.childNodes[1];
                    if (viewArea?.firstChild) viewArea.firstChild.style.backgroundImage = `url(${url})`;
                }
            }

            setTimeout(() => {
                const outputModeWidget = this.widgets.find(w => w.name === "output_mode");
                if (outputModeWidget) outputModeWidget.value = (outputModeWidget.value === true || outputModeWidget.value === "true");
            }, 30);
        };
    }
});