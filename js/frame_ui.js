import { app } from "../../scripts/app.js";
import { ComfyWidgets } from "../../scripts/widgets.js";

const MODEL_PRESETS = {
    "MiniMax H3": { Div_by: 17, Offset: 5, Fps: 24 },
    "LTX-2":      { Div_by: 8,  Offset: 1, Fps: 24 },
    "Wan":        { Div_by: 4,  Offset: 1, Fps: 16 },
    "Custom":     null,
};

app.registerExtension({
    name: "Element_easy.FrameCalculator",
    async beforeRegisterNodeDef(nodeType, nodeData, app) {
        if (nodeData.name === "FrameCalculator_Element") {

            const onNodeCreated = nodeType.prototype.onNodeCreated;
            nodeType.prototype.onNodeCreated = function () {
                const r = onNodeCreated?.apply(this, arguments);

                const modelW  = this.widgets?.find(w => w.name === "Model");
                const divW    = this.widgets?.find(w => w.name === "Div_by");
                const offsetW = this.widgets?.find(w => w.name === "Offset");
                const fpsW    = this.widgets?.find(w => w.name === "Fps");

                const applyPreset = () => {
                    const preset = MODEL_PRESETS[modelW?.value];
                    if (!preset) return; 
                    if (divW) divW.value = preset.Div_by;
                    if (offsetW) offsetW.value = preset.Offset;
                    if (fpsW) fpsW.value = preset.Fps;
                    app.graph.setDirtyCanvas(true, true);
                };

                if (modelW) {
                    const origCallback = modelW.callback;
                    modelW.callback = function () {
                        origCallback?.apply(this, arguments);
                        applyPreset();
                    };
                    setTimeout(applyPreset, 0);
                }
                return r;
            };

            const onExecuted = nodeType.prototype.onExecuted;
            nodeType.prototype.onExecuted = function (message) {
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
    },
});
