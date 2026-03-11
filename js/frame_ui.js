import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

app.registerExtension({
    name: "Element_easy.FrameCalculator",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "FrameCalculator_Element") {
            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function(message) {
                onExecuted?.apply(this, arguments);
                if (this.widgets && message.text) {
                    let textWidget = this.widgets.find(w => w.name === "feedback_display");
                    if (!textWidget) {
                        textWidget = ComfyWidgets["STRING"](this, "feedback_display", ["STRING", { multiline: true }], app).widget;
                        textWidget.inputEl.readOnly = true; 
                        textWidget.inputEl.style.backgroundColor = "#222"; 
                    }
                    textWidget.value = message.text[0];
                }
            };
        }
    }
});