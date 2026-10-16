// Element_HueHue.js —— Hue→Hue 色相环偏移曲线节点前端（薄配置）
// 实现见 hue_curve_base.js / ee_node_utils.js
import { registerHueCurveNode } from "./hue_curve_base.js";

registerHueCurveNode({
    extName: "Element_easy.HueHue",
    className: "ElementHueHue",
    logTag: "HueHue",
    title: "Hue vs Hue",
    liveRoute: "/element_huehue/live_preview",
});
