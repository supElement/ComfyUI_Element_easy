import { app } from "../../scripts/app.js";

app.registerExtension({
    name: "Element.ValueRemap",
    async beforeRegisterNodeDef(nodeType, nodeData) {
        if (nodeData.name !== "Element_Value_Remap") return;

        const onExecuted = nodeType.prototype.onExecuted;
        nodeType.prototype.onExecuted = function (message) {
            const r = onExecuted?.apply(this, arguments);
            const text = message?.value_text;
            if (Array.isArray(text)) {
                if (this.outputs?.[0]) this.outputs[0].label = `${text[0]} float`;
                if (this.outputs?.[1]) this.outputs[1].label = `${text[1]} int`;
                this.setDirtyCanvas?.(true, true);
            }
            return r;
        };
    },
});
