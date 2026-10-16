// Element_HueSat.js —— Hue→Saturation 曲线节点前端（薄配置）
// 实现见 hue_curve_base.js / ee_node_utils.js
import { registerHueCurveNode } from "./hue_curve_base.js";

registerHueCurveNode({
    extName: "Element_easy.HueSat",
    className: "ElementHueSat",
    logTag: "HueSat",
    title: "Hue vs Saturation",
    liveRoute: "/element_huesat/live_preview",
});
