import { app } from "../../scripts/app.js";
import { api } from "../../scripts/api.js";

app.registerExtension({
    name: "Element_easy.ImageCurve",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "Element_ImageCurve") {
            
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            
            nodeType.prototype.onNodeCreated = function () {
                if (onNodeCreated) onNodeCreated.apply(this, arguments);
				
				const MIN_NODE_WIDTH = 240;
                const MIN_NODE_HEIGHT = 340;  
                
				if (this.size[0] < MIN_NODE_WIDTH) this.size[0] = MIN_NODE_WIDTH;
                if (this.size[1] < MIN_NODE_HEIGHT) this.size[1] = MIN_NODE_HEIGHT;

                const curveWidget = this.widgets.find(w => w.name === "curve_data");
                
                if (curveWidget) {

                    if (curveWidget.inputEl) {
                        curveWidget.inputEl.style.display = "none";
                    }
                    curveWidget.computeSize = () => [0, 0];
                    curveWidget.draw = () => {};
                    curveWidget.hidden = true;
                }

                let curveData = {
                    RGB: [[0.0, 0.0], [1.0, 1.0]],
                    R: [[0.0, 0.0], [1.0, 1.0]],
                    G: [[0.0, 0.0], [1.0, 1.0]],
                    B: [[0.0, 0.0], [1.0, 1.0]]
                };
                let activeChannel = "RGB";
                
                if (curveWidget) {
                    const originalDescriptor = Object.getOwnPropertyDescriptor(curveWidget, 'value') || 
                                               Object.getOwnPropertyDescriptor(Object.getPrototypeOf(curveWidget), 'value');
                    
                    Object.defineProperty(curveWidget, 'value', {
                        get: function() {
                            if (originalDescriptor && originalDescriptor.get) {
                                return originalDescriptor.get.call(this);
                            }
                            return this._curveValue !== undefined ? this._curveValue : "";
                        },
                        set: function(v) {
                            if (originalDescriptor && originalDescriptor.set) {
                                originalDescriptor.set.call(this, v);
                            } else {
                                this._curveValue = v;
                            }
                            if (v && typeof v === 'string' && v.startsWith("{")) {
                                try {
                                    const newData = JSON.parse(v);
                                    if (newData && newData.RGB) {
                                        curveData = newData;
                                        if (typeof draw === 'function') {
                                            requestAnimationFrame(draw);
                                        }
                                    }
                                } catch (e) {}
                            }
                        },
                        configurable: true
                    });
                    
                    if (curveWidget.value && typeof curveWidget.value === 'string' && curveWidget.value.startsWith("{")) {
                        try {
                            curveData = JSON.parse(curveWidget.value);
                        } catch (e) {}
                    } else {
                        curveWidget.value = JSON.stringify(curveData);
                    }
                }

                const DOM_DEFAULT_HEIGHT = 260; 
                const container = document.createElement("div");
                container.style.display = "flex";
                container.style.flexDirection = "column";
                container.style.width = "100%";
                container.style.height = `${DOM_DEFAULT_HEIGHT}px`; 
                container.style.marginTop = "10px";
                container.style.borderRadius = "8px";
                container.style.overflow = "hidden";
                container.style.backgroundColor = "#1a1a1a";
				
                const header = document.createElement("div");
                header.style.display = "flex";
                header.style.height = "20px";
                header.style.flexShrink = "0"; 
                header.style.backgroundColor = "#222";
                
                const channels = [
                    { id: "RGB", color: "#FFF" },
                    { id: "R", color: "#FF4444" },
                    { id: "G", color: "#44FF44" },
                    { id: "B", color: "#4488FF" }
                ];
                
                const buttons = {};
                channels.forEach(ch => {
                    const btn = document.createElement("button");
                    btn.innerText = ch.id;
                    btn.style.flex = "1";
                    btn.style.border = "none";
                    btn.style.cursor = "pointer";
                    btn.style.backgroundColor = ch.id === "RGB" ? "#555" : "transparent";
                    btn.style.color = ch.color;
                    btn.style.fontWeight = "";
					btn.style.fontSize = "10px";
                    
                    btn.onclick = () => {
                        activeChannel = ch.id;
                        Object.values(buttons).forEach(b => b.style.backgroundColor = "transparent");
                        btn.style.backgroundColor = "#555";
                        draw();
                    };
                    buttons[ch.id] = btn;
                    header.appendChild(btn);
                });

                const rcBtn = document.createElement("button");
                rcBtn.innerText = "Rc";
                rcBtn.style.flex = "0.8";
                rcBtn.style.border = "none";
                rcBtn.style.cursor = "pointer";
                rcBtn.style.backgroundColor = "transparent";
                rcBtn.style.color = "#CCC";
                rcBtn.style.fontWeight = "";
				rcBtn.style.fontSize = "10px";
				
                rcBtn.onclick = () => {
                    curveData[activeChannel] = [[0.0, 0.0], [1.0, 1.0]];
                    updateBackend();
                    draw();
                    updateLivePreview(false);
                };
                header.appendChild(rcBtn);

                const rallBtn = document.createElement("button");
                rallBtn.innerText = "Rall";
                rallBtn.style.flex = "0.8";
                rallBtn.style.border = "none";
                rallBtn.style.cursor = "pointer";
                rallBtn.style.backgroundColor = "transparent";
                rallBtn.style.color = "#CCC";
                rallBtn.style.fontWeight = "bold";
				rallBtn.style.fontSize = "10px";
				
                rallBtn.onclick = () => {
                    curveData = {
                        RGB: [[0.0, 0.0], [1.0, 1.0]],
                        R: [[0.0, 0.0], [1.0, 1.0]],
                        G: [[0.0, 0.0], [1.0, 1.0]],
                        B: [[0.0, 0.0], [1.0, 1.0]]
                    };
                    updateBackend();
                    draw();
                    updateLivePreview(false);
                };
                header.appendChild(rallBtn);

                container.appendChild(header);

                const viewArea = document.createElement("div");
                viewArea.style.flex = "1";
                viewArea.style.position = "relative";
                viewArea.style.width = "100%";
                viewArea.style.height = "100%";
                viewArea.style.overflow = "hidden";

                const bgImageLayer = document.createElement("div");
                bgImageLayer.style.position = "absolute";
                bgImageLayer.style.inset = "0"; 
                bgImageLayer.style.backgroundSize = "contain";
                bgImageLayer.style.backgroundPosition = "center";
                bgImageLayer.style.backgroundRepeat = "no-repeat";
                viewArea.appendChild(bgImageLayer);

                const canvas = document.createElement("canvas");
                canvas.style.position = "absolute";
                canvas.style.inset = "0";
                canvas.style.width = "100%";
                canvas.style.height = "100%";
                canvas.style.cursor = "crosshair";
                viewArea.appendChild(canvas);

                container.appendChild(viewArea);
                const ctx = canvas.getContext("2d");

                const widget = this.addDOMWidget("CurveUI", "div", container, { serialize: false, hideOnZoom: false });
                widget.computeSize = function(width) {
                    return [width, parseInt(container.style.height) || DOM_DEFAULT_HEIGHT];
                };
				
                const nodeInstance = this;
                const onResize = this.onResize;
                this.onResize = function(size) {
                    if (onResize) onResize.apply(this, arguments);
                    
					if (size[0] < MIN_NODE_WIDTH) size[0] = MIN_NODE_WIDTH;
                    if (size[1] < MIN_NODE_HEIGHT) size[1] = MIN_NODE_HEIGHT;
                    
                    this.size[1] = size[1];
                    
                    const reservedHeight = 105;
                    let newHeight = size[1] - reservedHeight;
                    
                    if (newHeight < 100) newHeight = 100;
                    
                    container.style.height = `${newHeight}px`;
                    
                    requestAnimationFrame(draw);
                };

                // ==========================================
                // 旁路预览 API 请求（简化队列版）
                // ==========================================
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
                    
                    const satWidget = nodeInstance.widgets.find(w => w.name === "saturation");
                    const previewSizeWidget = nodeInstance.widgets.find(w => w.name === "preview_size");
                    const body = {
                        node_id: nodeInstance.id.toString(),
                        curve_data: JSON.stringify(curveData),
                        saturation: satWidget ? parseFloat(satWidget.value) : 1.0,
                        preview_size: previewSizeWidget ? parseInt(previewSizeWidget.value) : 512
                    };
                    
                    (async () => {
                        try {
                            const response = await api.fetchApi("/element_image_curve/live_preview", {
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
                        } catch(e) {
                            isPreviewPending = false;
                            if (pendingUpdate) {
                                pendingUpdate = false;
                                setTimeout(() => updateLivePreview(isDragging), 0);
                            }
                        }
                    })();
                };

                const satWidget = this.widgets.find(w => w.name === "saturation");
                if (satWidget) {
                    const originalCallback = satWidget.callback;
                    satWidget.callback = function(value) {
                        if (originalCallback) originalCallback.apply(this, arguments);
                        updateLivePreview(false);
                    };
                }

                const previewSizeWidget = this.widgets.find(w => w.name === "preview_size");
                if (previewSizeWidget) {
                    const originalCallback = previewSizeWidget.callback;
                    previewSizeWidget.callback = function(value) {
                        if (originalCallback) originalCallback.apply(this, arguments);
                        updateLivePreview(false);
                    };

                    if (previewSizeWidget.inputEl) {
                        previewSizeWidget.inputEl.addEventListener('change', () => {
                            updateLivePreview(false);
                        });

                        previewSizeWidget.inputEl.addEventListener('input', () => {
                            updateLivePreview(false);
                        });
                    }
                }

                let isDragging = false;
                let dragIndex = -1;
                let lastClickTime = 0;
                const PADDING = 14; 

                const updateBackend = () => {
                    if (curveWidget) {
                        curveWidget.value = JSON.stringify(curveData);
                    }
                    if (app.graph) app.graph.setDirtyCanvas(true);
                };

                const getPos = (e) => {
                    const rect = canvas.getBoundingClientRect();
                    const scaleX = canvas.width / rect.width;
                    const scaleY = canvas.height / rect.height;
                    
                    let mouseX = (e.clientX - rect.left) * scaleX;
                    let mouseY = (e.clientY - rect.top) * scaleY;
                    
                    const innerW = canvas.width - PADDING * 2;
                    const innerH = canvas.height - PADDING * 2;
                    
                    let x = (mouseX - PADDING) / innerW;
                    let y = 1.0 - (mouseY - PADDING) / innerH;
                    
                    return [Math.max(0, Math.min(1, x)), Math.max(0, Math.min(1, y))];
                };

                canvas.addEventListener("mousedown", (e) => {
                    const [x, y] = getPos(e);
                    const pts = curveData[activeChannel];
                    
                    let closestIdx = -1;
                    let minDist = 0.05; 
                    for (let i = 0; i < pts.length; i++) {
                        let dist = Math.hypot(pts[i][0] - x, pts[i][1] - y);
                        if (dist < minDist) {
                            minDist = dist;
                            closestIdx = i;
                        }
                    }

                    if (e.button === 0) { 
                        const now = Date.now();
                        if (now - lastClickTime < 300) {
                            if (closestIdx === -1) {
                                pts.push([x, y]);
                                pts.sort((a, b) => a[0] - b[0]);
                                updateBackend();
                                draw();
                                updateLivePreview(false);
                            }
                            lastClickTime = 0; 
                        } else {
                            if (closestIdx !== -1) {
                                isDragging = true;
                                dragIndex = closestIdx;
                            }
                            lastClickTime = now;
                        }
                    } else if (e.button === 2) { 
                        e.preventDefault();
                        if (closestIdx !== -1 && pts.length > 2) {
                            pts.splice(closestIdx, 1);
                            updateBackend();
                            draw();
                            updateLivePreview(false);
                        }
                    }
                });

                canvas.addEventListener("contextmenu", e => e.preventDefault());

                window.addEventListener("mousemove", (e) => {
                    if (!isDragging || dragIndex === -1) return;
                    const [x, y] = getPos(e);
                    const pts = curveData[activeChannel];
                    
                    let minX = dragIndex > 0 ? pts[dragIndex - 1][0] + 0.02 : 0;
                    let maxX = dragIndex < pts.length - 1 ? pts[dragIndex + 1][0] - 0.02 : 1;
                    
                    pts[dragIndex] = [Math.max(minX, Math.min(maxX, x)), y];
                    
                    draw();
                    updateBackend();
                    updateLivePreview(true);
                });

                window.addEventListener("mouseup", () => {
                    if (isDragging) {
                        isDragging = false;
                        updateBackend();
                    }
                });

                const draw = () => {
                    const clientW = canvas.clientWidth;
                    const clientH = canvas.clientHeight;
                    if (clientW > 0 && clientH > 0) {
                        if (canvas.width !== clientW || canvas.height !== clientH) {
                            canvas.width = clientW;
                            canvas.height = clientH;
                        }
                    }

                    const w = canvas.width;
                    const h = canvas.height;
                    if (w === 0 || h === 0) return;

                    ctx.clearRect(0, 0, w, h);
                    ctx.shadowColor = "rgba(0, 0, 0, 0.5)";
                    ctx.shadowBlur = 1;

                    const innerW = w - PADDING * 2;
                    const innerH = h - PADDING * 2;
                    const toPx = (val) => PADDING + val * innerW;
                    const toPy = (val) => PADDING + (1 - val) * innerH;

                    ctx.strokeStyle = "rgba(255, 255, 255, 0.15)";
                    ctx.lineWidth = 1;
                    ctx.beginPath();
                    for(let i=0; i<=4; i++) {
                        let px = toPx(i / 4);
                        let py = toPy(i / 4);
                        ctx.moveTo(px, toPy(0)); ctx.lineTo(px, toPy(1));
                        ctx.moveTo(toPx(0), py); ctx.lineTo(toPx(1), py);
                    }
                    ctx.stroke();

                    channels.forEach(ch => {
                        if (ch.id !== activeChannel) drawCurve(curveData[ch.id], ch.color, 0.3);
                    });
                    
                    const activeColor = channels.find(c => c.id === activeChannel).color;
                    drawCurve(curveData[activeChannel], activeColor, 1.0);

                    const pts = curveData[activeChannel];
                    ctx.fillStyle = activeColor;
                    pts.forEach(p => {
                        ctx.beginPath();
                        ctx.arc(toPx(p[0]), toPy(p[1]), 4, 0, Math.PI * 2);
                        ctx.fill();
                    });
                };

                const drawCurve = (points, color, alpha) => {
                    if (points.length < 2) return;
                    ctx.strokeStyle = color;
                    ctx.globalAlpha = alpha;
                    ctx.lineWidth = 1.25;
                    ctx.beginPath();
                    
                    const w = canvas.width;
                    const h = canvas.height;
                    const innerW = w - PADDING * 2;
                    const innerH = h - PADDING * 2;
                    const toPx = (val) => PADDING + val * innerW;
                    const toPy = (val) => PADDING + (1 - val) * innerH;

                    if (points[0][0] > 0) {
                        ctx.moveTo(toPx(0), toPy(points[0][1]));
                        ctx.lineTo(toPx(points[0][0]), toPy(points[0][1]));
                    } else {
                        ctx.moveTo(toPx(points[0][0]), toPy(points[0][1]));
                    }

                    for (let i = 0; i < points.length - 1; i++) {
                        let p0 = points[i === 0 ? 0 : i - 1];
                        let p1 = points[i];
                        let p2 = points[i + 1];
                        let p3 = points[i + 2 >= points.length ? i + 1 : i + 2];

                        for (let t = 0; t <= 1; t += 0.05) {
                            let t2 = t * t;
                            let t3 = t2 * t;
                            let cx = 0.5 * ((2 * p1[0]) + (-p0[0] + p2[0]) * t + (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 + (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3);
                            let cy = 0.5 * ((2 * p1[1]) + (-p0[1] + p2[1]) * t + (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 + (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3);
                            
                            cx = Math.max(p1[0], Math.min(p2[0], cx)); 
                            cy = Math.max(0, Math.min(1, cy)); 
                            
                            ctx.lineTo(toPx(cx), toPy(cy));
                        }
                        ctx.lineTo(toPx(p2[0]), toPy(p2[1]));
                    }
                    
                    const lastP = points[points.length - 1];
                    if (lastP[0] < 1) {
                        ctx.lineTo(toPx(1), toPy(lastP[1]));
                    }
                    
                    ctx.stroke();
                    ctx.globalAlpha = 1.0;
                };

                setTimeout(draw, 100);
				
				setTimeout(() => {
                    draw();
                    if (this.onResize) this.onResize(this.size);
                }, 150);
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function(message) {
                onExecuted?.apply(this, arguments);
                
                if (message?.bg_image?.length > 0) {
                    const img = message.bg_image[0];
                    const url = api.apiURL(`/view?filename=${encodeURIComponent(img.filename)}&type=${img.type}&subfolder=${img.subfolder}&t=${Date.now()}`);
                    
                    const curveWidget = this.widgets.find(w => w.name === "CurveUI");
                    if (curveWidget && curveWidget.element) {
                        const viewArea = curveWidget.element.childNodes[1]; 
                        if (viewArea && viewArea.firstChild) {
                            viewArea.firstChild.style.backgroundImage = `url(${url})`;
                        }
                    }
                }
            };
        }
    }
});