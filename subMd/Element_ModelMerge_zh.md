# Model Merge (Curve) 使用说明

用一条深度曲线决定每个 block 取 model1 的比例，把 model2 按深度混进 model1。

**类别**：`Element_easy/model`，输出：`model`（MODEL）

---

## 一、节点与接法

    model1 ──┐
    model2 ──┴─► Model Merge (Curve) ──► model
                  model_type = 对应模型
                  可选：Model Merge <家族> Extras ──► extras

- **Model Merge (Curve)**：合并本体，曲线节点自己完成合并，不需要额外的连接节点。
- **8 个 Extras 节点**：`Model Merge Krea2 / MOSS Image / Qwen Image / MiniMax H3 / Auraflow / LTXV / SDXL / WAN 2.1 Extras`，负责非 block 层和小旁支 block 组的比例。

## 二、曲线怎么读

- 横轴 x：归一化深度，0 = 最靠输入，1 = 最靠输出（按该家族的 block 顺序依次排列）。
- 纵轴 y：该深度取 **model1** 的比例。`1.0` = 全取 model1，`0` = 全取 model2，`0.5` = 各一半。
- 默认平线 1.0，即不做合并；把整条线拉到 0.5 就是全深度 50/50。
- 画布上的两条虚线是参考线：横线 y=0.5、竖线 x=0.5。

**操作**

| 操作 | 效果 |
|---|---|
| 左键点空白处 | 在曲线上插入一个点并进入拖动 |
| 拖动圆点 | 调整该深度比例（首尾点只能改 y） |
| 右键点中间的点 | 删除该点 |
| `Ctrl+Z` | 撤销上一步 |
| `curve` / `straight` | 切换曲线 / 直线模式 |
| `reset` | 恢复默认平线 1.0 |

曲线下方的预览框实时列出当前采样比例，便于核对。

## 三、Extras 与非 block 层

非 block 层没有深度顺序，所以不放在曲线上，由 Extras 节点单独给比例：

- 不接 `extras` 端口时，这些层全部按 1.0 处理（只取 model1）。
- 每个滑杆都是 0~1，含义与曲线的 y 相同（1.0 = 只取 model1）。
- 接了 Extras 时，`model_type` 必须选同一家族，接错会直接报错。

## 四、各家族覆盖范围

| 家族 | 曲线覆盖的主 block 栈 | Extras 节点 |
|---|---|---|
| Krea2 | `blocks`（最多 28） | Model Merge Krea2 Extras |
| MOSS Image | `layers`（最多 42） | Model Merge MOSS Image Extras |
| Qwen Image | `transformer_blocks`（最多 60） | Model Merge Qwen Image Extras |
| MiniMax H3 | `blocks`（最多 50） | Model Merge MiniMax H3 Extras |
| Auraflow | `double_layers` + `single_layers` | Model Merge Auraflow Extras |
| LTXV | `transformer_blocks`（最多 28） | Model Merge LTXV Extras |
| SDXL | `input_blocks` → `middle_block` → `output_blocks` | Model Merge SDXL Extras |
| WAN 2.1 | `blocks`（30 / 40 自动） | Model Merge WAN 2.1 Extras |

- 运行时按 model2 实际的 key 探测 block 数量，WAN 2.1 的 30/40 不需要手选；预览框对 WAN 2.1 固定按 40 显示。
- 未覆盖到的 key（包括没接 Extras 时的小旁支）保持 1.0，即原样取 model1。

## 五、预设

- 点 `REC` 进入保存模式（按钮变红），再点下方 1~8 中任一数字，把当前曲线存到该槽位。
- 直接点数字即载入对应槽位的曲线。
- 预设保存在 `presets/Model_Merge_Curve_presets.json`，所有 Model Merge (Curve) 节点共用这 8 个槽位。

## 六、注意

- 曲线数据损坏或无效时，节点按平线 1.0 处理（不合并），不会误把后段全换成 model2。
- 合并输出经过 `add_patches`，与 ComfyUI 原生模型合并节点一致，可在之后继续接 LoRA / 其他合并节点。
