import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

console.log(">>> Element_easy JS: Loaded successfully! <<<");

app.registerExtension({
    name: "Element.DisplayInfo",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        // 这里的名字必须匹配日志中看到的 'Class: EmptyImageRGB_Element'
        if (nodeData.name === "EmptyImageRGB_Element") {
            
            function ensureInfoWidget(node) {
                const widgetName = "info_display";
                if (node.widgets && node.widgets.find(w => w.name === widgetName)) {
                    return;
                }
                
                // 创建组件
                const w = ComfyWidgets["STRING"](
                    node, 
                    widgetName, 
                    ["STRING", { multiline: true }], 
                    app
                ).widget;
                
                w.inputEl.readOnly = true;
                w.inputEl.style.opacity = 0.6;
                w.inputEl.style.fontSize = "12px";
                w.value = "Ready to generate...";
            }

            // 1. 创建节点时
            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated ? onNodeCreated.apply(this, arguments) : undefined;
                ensureInfoWidget(this);
                return r;
            };

            // 2. 刷新页面/加载已有工作流时
            const onConfigure = nodeType.prototype.onConfigure;
            nodeType.prototype.onConfigure = function () {
                const r = onConfigure ? onConfigure.apply(this, arguments) : undefined;
                ensureInfoWidget(this);
                return r;
            };

            // 3. 运行结束时
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
                onExecuted?.apply(this, arguments);
                if (message && message.text) {
                    const widgetName = "info_display";
                    const w = this.widgets?.find((w) => w.name === widgetName);
                    if (w) {
                        w.value = message.text.join("");
                        this.onResize?.(this.size);
                    }
                }
            };
        }
    },
});