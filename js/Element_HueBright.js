// Element_HueBright.js —— Hue→Brightness 曲线节点前端（薄配置）
// 实现见 hue_curve_base.js / ee_node_utils.js
import { registerHueCurveNode } from "./hue_curve_base.js";

registerHueCurveNode({
    extName: "Element_easy.HueBright",
    className: "ElementHueBright",
    logTag: "HueBright",
    title: "Hue vs Brightness",
    liveRoute: "/element_huebright/live_preview",
});
