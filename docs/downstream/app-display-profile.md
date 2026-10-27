# 应用显示方案契约

没有 `display-target` 时整个方案关闭。启用方案的非法值在保存前拒绝。

| 字段 | 值与行为 |
| --- | --- |
| `display-target` | `physical` / `virtual` |
| `display-output-name` | 物理显示器标识；为空时优先主物理屏、再活动物理屏，不选 Zako 虚拟屏 |
| `display-device-prep` | 上游五种拓扑值；缺省或空值继承全局，编辑器可切回继承 |
| `display-resolution-mode` | 空值继承、`no_operation` 保持、`client` 使用客户端尺寸 |
| `display-resolution` | 固定宽高，正整数且每边不超过 16384；填写时优先于模式选项 |
| `display-refresh-rate-mode` | 空值继承、`no_operation` 保持、`client` 使用客户端刷新率 |
| `display-refresh-rate` | 大于零、不超过 1000，最多六位小数；填写时优先于模式选项 |
| `display-hdr` | 空值继承、`no_operation` 保持、`client` 跟随、`on` / `off` 固定 |
| `display-disconnect-action` | 空值继承、`keep` 保持、`restore` 恢复 |
| `display-dynamic-resolution-follow-display` | 空值继承全局、`enabled` / `disabled` |

固定值只约束主机显示模式，编码尺寸和帧率仍由客户端协商。应用指定的模式优先于全局手动模式；未覆盖的维度继续使用上游规则。编辑器明确显示固定值正在覆盖策略，清除固定值后恢复原先选择的策略。

保持只表示不主动修改现有模式，首次创建虚拟屏仍需执行上游初始模式流程。
固定关闭 HDR 与不使用 RTX HDR 的 HDR 串流不兼容；固定开启 HDR 与 RTX HDR 不兼容。启动和握手均检查冲突。

应用方案在启动/恢复时建立快照，运行中编辑不会改变当前会话。最后一个非控制视频会话断开时决定是否恢复；应用结束仍沿用上游恢复路径，不以 `keep` 阻止清理。

同步上游必须验证：无方案、默认物理/指定物理/虚拟、拓扑继承及五种显式拓扑、两种模式策略组合、小数固定刷新率、固定值启停后的提示与策略、恢复时零模式、HDR 冲突与断开策略。
