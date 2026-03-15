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
                const MIN_NODE_HEIGHT = 380;  // 增加高度以容纳新参数
                
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
                
                // 隐藏 output_mode 原生控件
                const outputModeWidget = this.widgets.find(w => w.name === "output_mode");
                if (outputModeWidget) {
                    outputModeWidget.computeSize = () => [0, 0];
                    outputModeWidget.draw = () => {};
                    if (outputModeWidget.inputEl) {
                        outputModeWidget.inputEl.style.display = "none";
                    }
                    outputModeWidget.hidden = true;
                    if (outputModeWidget.value === undefined || outputModeWidget.value === null) {
                        outputModeWidget.value = false;
                    }
                }
                
/*                 // =============== 添加独立的 Load 按钮 ===============
                this.addWidget("button", "Load (Execute Selected)", "load_btn", async () => {
                    try {
                        const p = await app.graphToPrompt();
                        const prompt = p.output;
                        const selectedNodeId = String(this.id);
                        
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
                        
                        if (Object.keys(isolatedPrompt).length === 0) {
                            console.warn("No dependencies found for node", selectedNodeId);
                            return;
                        }
                        
                        const response = await api.fetchApi("/prompt", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                client_id: api.clientId,
                                prompt: isolatedPrompt,
                                extra_data: p.workflow ? { extra_pnginfo: { workflow: p.workflow } } : {}
                            })
                        });
                        
                        if (!response.ok) {
                            const error = await response.json();
                            throw new Error(error.error || "Failed to queue prompt");
                        }
                        
                        console.log("Successfully queued selected node execution");
                        
                    } catch (err) {
                        console.error("Failed to execute isolated node:", err);
                    }
                }); */

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

                const DOM_DEFAULT_HEIGHT = 290; 
                const container = document.createElement("div");
                container.style.display = "flex";
                container.style.flexDirection = "column";
                container.style.width = "100%";
                container.style.height = `${DOM_DEFAULT_HEIGHT}px`; 
                container.style.marginTop = "10px";
                container.style.borderRadius = "6px";
                container.style.overflow = "hidden";
                container.style.backgroundColor = "#transparent";
                
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
                viewArea.style.backgroundColor = "#1a1a1a";
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
                    
                    const reservedHeight = 105; // 调整以适应新增的组件
                    let newHeight = size[1] - reservedHeight;
                    
                    if (newHeight < 100) newHeight = 100;
                    
                    container.style.height = `${newHeight}px`;
                    
                    requestAnimationFrame(draw);
                };

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
                    const frameWidget = nodeInstance.widgets.find(w => w.name === "frame_index"); // 新增获取帧控件

                    const body = {
                        node_id: nodeInstance.id.toString(),
                        curve_data: JSON.stringify(curveData),
                        saturation: satWidget ? parseFloat(satWidget.value) : 1.0,
                        preview_size: previewSizeWidget ? parseInt(previewSizeWidget.value) : 512,
                        frame_index: frameWidget ? parseInt(frameWidget.value) : 0 // 传递指定帧
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
                    satWidget.computeSize = () => [0, 0];
                    satWidget.draw = () => {};
                    if (satWidget.inputEl) {
                        satWidget.inputEl.style.display = "none";
                    }
                    satWidget.hidden = true;
                }
                
                const paramsToBind = ["preview_size", "frame_index"];
                paramsToBind.forEach(paramName => {
                    const w = this.widgets.find(widget => widget.name === paramName);
                    if (w) {
                        const originalCallback = w.callback;
                        w.callback = function(value) {
                            if (originalCallback) originalCallback.apply(this, arguments);
                            updateLivePreview(false);
                        };
                
                        if (w.inputEl) {
                            w.inputEl.addEventListener('change', () => updateLivePreview(false));
                            w.inputEl.addEventListener('input', () => updateLivePreview(false));
                        }
                    }
                });
                                
                // ========== Sat 滑条 ==========
                const satControlArea = document.createElement("div");
                satControlArea.style.display = "flex";
                satControlArea.style.alignItems = "center";
                satControlArea.style.height = "24px";
                satControlArea.style.flexShrink = "0";
                satControlArea.style.backgroundColor = "#1a1a1a";
                satControlArea.style.padding = "0 10px";
                satControlArea.style.borderTop = "1px solid #333";
                satControlArea.style.gap = "8px";
                satControlArea.style.borderRadius = "0 0 6px 6px";
                
                const satLabel = document.createElement("span");
                satLabel.innerText = "Sat";
                satLabel.style.color = "#CCC";
                satLabel.style.fontSize = "10px";
                satLabel.style.fontWeight = "bold";
                satLabel.style.width = "28px";
                satLabel.style.flexShrink = "0";
                satControlArea.appendChild(satLabel);
                
                // 创建滑条
                const satSlider = document.createElement("input");
                satSlider.type = "range";
                satSlider.min = "0";
                satSlider.max = "2";
                satSlider.step = "0.01";
                satSlider.style.flex = "0.85";
                satSlider.style.height = "2px";
                satSlider.style.accentColor = "#FFFFFF";
                
                satSlider.id = "sat-slider-" + this.id;
                
                satControlArea.appendChild(satSlider);
                
                // 数值显示
                const satValueDisplay = document.createElement("span");
                satValueDisplay.style.color = "#ffffff";
                satValueDisplay.style.fontSize = "10px";
                satValueDisplay.style.fontFamily = "";
                satValueDisplay.style.width = "20px";
                satValueDisplay.style.textAlign = "right";
                satValueDisplay.style.flexShrink = "0";
                satControlArea.appendChild(satValueDisplay);
                
                const styleId = "sat-style-" + this.id;
                if (!document.getElementById(styleId)) {
                    const style = document.createElement("style");
                    style.id = styleId;
                    style.textContent = `
                        #${satSlider.id} {
                            -webkit-appearance: none !important;
                            appearance: none !important;
                        }
                        #${satSlider.id}::-webkit-slider-thumb {
                            -webkit-appearance: none !important;
                            appearance: none !important;
                            width: 8px !important;
                            height: 8px !important;
                            background: #FFFFFF !important;
                            border-radius: 50% !important;
                            margin-top: -3px !important;
                            border: none !important;
                            box-shadow: none !important;
                        }
                        #${satSlider.id}::-webkit-slider-runnable-track {
                            height: 2px !important;
                            background: #333 !important;
                            border-radius: 2px !important;
                        }
                    `;
                    document.head.appendChild(style);
                }
                
                
                const initialValue = satWidget ? parseFloat(satWidget.value) : 1.0;
                satSlider.value = initialValue;
                satValueDisplay.innerText = initialValue.toFixed(2);
                
                satSlider.addEventListener("input", (e) => {
                    const val = parseFloat(e.target.value);
                    satValueDisplay.innerText = val.toFixed(2);
                    if (satWidget) satWidget.value = val;
                    updateLivePreview(true);
                });
                
                satSlider.addEventListener("change", (e) => {
                    const val = parseFloat(e.target.value);
                    if (satWidget) satWidget.value = val;
                    updateLivePreview(false);
                });
                

                let satValueInternal = initialValue;
                Object.defineProperty(satWidget, "value", {
                    get: () => satValueInternal,
                    set: (v) => {
                        satValueInternal = parseFloat(v);
                        if (satSlider) satSlider.value = satValueInternal;
                        if (satValueDisplay) satValueDisplay.innerText = satValueInternal.toFixed(2);
                    },
                    configurable: true
                });
                
                // 双击数值重置
                satValueDisplay.style.cursor = "pointer";
                satValueDisplay.title = "双击重置为 1.0";
                satValueDisplay.addEventListener("dblclick", () => {
                    satSlider.value = "1.0";
                    satValueDisplay.innerText = "1.00";
                    if (satWidget) satWidget.value = 1.0;
                    updateLivePreview(false);
                });
                
                container.appendChild(satControlArea);
                
/*                 // =============== 模式切换按钮 (Preview / Output) ===============
                const modeControlArea = document.createElement("div");
                modeControlArea.style.display = "flex";
                modeControlArea.style.alignItems = "center";
                modeControlArea.style.alignSelf = "stretch";
                modeControlArea.style.width = "100%";
                modeControlArea.style.height = "28px";
                modeControlArea.style.flexShrink = "0";
                modeControlArea.style.backgroundColor = "transparent";
                modeControlArea.style.padding = "0 0px";
                modeControlArea.style.borderTop = "none";
                modeControlArea.style.gap = "8px";
                modeControlArea.style.boxSizing = "border-box";
                                
                // 创建单按钮开关
                const modeBtn = document.createElement("button");
                modeBtn.innerText = "output";
                modeBtn.style.flex = "0 0 auto";
				modeBtn.style.lineHeight = "20px";
                modeBtn.style.width = "60px";
                modeBtn.style.marginLeft = "auto";
				modeBtn.style.marginTop = "3px";
                modeBtn.style.height = "22px";
                modeBtn.style.border = "none";
                modeBtn.style.borderRadius = "6px";
                modeBtn.style.cursor = "pointer";
                modeBtn.style.fontSize = "10px";
                modeBtn.style.fontWeight = "bold";
                modeBtn.style.transition = "all 0.2s ease";
                modeBtn.style.display = "flex";
                modeBtn.style.alignItems = "center";
                modeBtn.style.justifyContent = "center";
                modeBtn.style.padding = "0";
                
                
                const updateModeUI = (isOutput) => {
                    if (isOutput) {
                        modeBtn.style.backgroundColor = "#4CAF50";
                        modeBtn.style.color = "#FFF";
                    } else {
                        modeBtn.style.backgroundColor = "#555";
                        modeBtn.style.color = "#CCC";
                    }
                };
                
                let currentMode = outputModeWidget ? outputModeWidget.value : false;
                updateModeUI(currentMode);
                
                modeBtn.onclick = () => {
                    currentMode = !currentMode;
                    if (outputModeWidget) outputModeWidget.value = currentMode;
                    updateModeUI(currentMode);
                    if (app.graph) app.graph.setDirtyCanvas(true);
                };
                
                modeControlArea.appendChild(modeBtn);
                
                container.appendChild(modeControlArea); */
                
                // =============== 模式切换区域 (包含 Load 和 Output 按钮) ===============
                const modeControlArea = document.createElement("div");
                modeControlArea.style.display = "flex";
                modeControlArea.style.alignItems = "center";
                modeControlArea.style.alignSelf = "stretch";
                modeControlArea.style.width = "100%";
                modeControlArea.style.height = "32px";
                modeControlArea.style.flexShrink = "0";
                modeControlArea.style.backgroundColor = "transparent";
                modeControlArea.style.padding = "0 0px";
                modeControlArea.style.borderTop = "none";
                modeControlArea.style.gap = "8px";
                modeControlArea.style.boxSizing = "border-box";
                
                // Load 按钮 (左边)
                const loadBtn = document.createElement("button");
                loadBtn.innerText = "Load";
                loadBtn.style.flex = "7";
                loadBtn.style.width = "auto";
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
                loadBtn.style.transition = "all 0.2s ease";
                
                loadBtn.onclick = async () => {
                    try {
                        const p = await app.graphToPrompt();
                        const prompt = p.output;
                        const selectedNodeId = String(this.id);
                        
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
                        
                        if (Object.keys(isolatedPrompt).length === 0) {
                            console.warn("No dependencies found for node", selectedNodeId);
                            return;
                        }
                        
                        const response = await api.fetchApi("/prompt", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({
                                client_id: api.clientId,
                                prompt: isolatedPrompt,
                                extra_data: p.workflow ? { extra_pnginfo: { workflow: p.workflow } } : {}
                            })
                        });
                        
                        if (!response.ok) {
                            const error = await response.json();
                            throw new Error(error.error || "Failed to queue prompt");
                        }
                        
                        console.log("Successfully queued selected node execution");
                        
                    } catch (err) {
                        console.error("Failed to execute isolated node:", err);
                    }
                };
                
                modeControlArea.appendChild(loadBtn);
                
                // Output 按钮 (右边，靠右对齐)
                const modeBtn = document.createElement("button");
                modeBtn.innerText = "output";
                modeBtn.style.flex = "3";
                modeBtn.style.width = "auto";
				modeBtn.style.lineHeight = "22px";
                //modeBtn.style.marginLeft = "auto";  // 靠右对齐
                modeBtn.style.height = "24px";
				modeBtn.style.marginTop = "8px";
                modeBtn.style.border = "none";
                modeBtn.style.borderRadius = "8px";
                modeBtn.style.cursor = "pointer";
                modeBtn.style.fontSize = "10px";
                modeBtn.style.fontWeight = "bold";
                modeBtn.style.transition = "all 0.2s ease";
                
                const updateModeUI = (isOutput) => {
                    if (isOutput) {
                        modeBtn.style.backgroundColor = "#56915a";
                        modeBtn.style.color = "#FFF";
                    } else {
                        modeBtn.style.backgroundColor = "#555";
                        modeBtn.style.color = "#CCC";
                    }
                };
                
                let currentMode = outputModeWidget ? outputModeWidget.value : false;
                updateModeUI(currentMode);
                
                modeBtn.onclick = () => {
                    currentMode = !currentMode;
                    if (outputModeWidget) outputModeWidget.value = currentMode;
                    updateModeUI(currentMode);
                    if (app.graph) app.graph.setDirtyCanvas(true);
                };
                
                modeControlArea.appendChild(modeBtn);
                container.appendChild(modeControlArea);
				

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

                    ctx.strokeStyle = "rgba(255, 255, 255, 0.25)";
                    ctx.lineWidth = 0.5; // 网格线宽
                    ctx.beginPath();
                    for(let i=0; i<=4; i++) {
                        let px = Math.round(toPx(i / 4)) + 0.5;
                        let py = Math.round(toPy(i / 4)) + 0.5;
                        let startX = Math.round(toPx(0)) + 0.5;
                        let endX = Math.round(toPx(1)) + 0.5;
                        let startY = Math.round(toPy(0)) + 0.5;
                        let endY = Math.round(toPy(1)) + 0.5;
                        
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

                // ======= 动态更新 Frame 的最大值 =======
                if (message?.batch_size?.length > 0) {
                    const maxFrameIndex = message.batch_size[0] - 1;
                    const frameWidget = this.widgets.find(w => w.name === "frame_index");
                    if (frameWidget) {
                        frameWidget.options.max = maxFrameIndex;
                        if (frameWidget.value > maxFrameIndex) {
                            frameWidget.value = maxFrameIndex;
                        }
                    }
                }
                
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
                // 强制同步 DOM 状态到 widget 值
                setTimeout(() => {
                    const satWidget = this.widgets.find(w => w.name === "saturation");
                    const outputModeWidget = this.widgets.find(w => w.name === "output_mode");
                    
                    if (satWidget) {
                        const currentVal = parseFloat(satWidget.value);
                        satWidget.value = currentVal;
                    }
                    if (outputModeWidget) {
                        const currentVal = outputModeWidget.value === "true" || outputModeWidget.value === true;
                        outputModeWidget.value = currentVal;
                    }
                }, 50);
            };
        }
    }
});
