# v4 应用显示方案交接

## 范围

- v4.1 以 v4.0 为基线同步上游正式版 `v2026.1020.23431.杂鱼`（提交 `66d27405e43ba1cc5e8c88dda88ba44f06ac56b8`）；`.github/upstream-stable-release` 锁定同一版本的 DualSense 组件。
- 唯一定制能力为按应用配置显示方案；发布分支为 `release/v4.1`。上一发布分支为 `release/v4.0`，旧发布分支保存在 `archive/release-v3.0`。
- 不新增跨设备接管、旧双显卡恢复增强或控制面板 Desktop 卡片。
- 无应用方案时保持上游行为。驱动、采集、编码与显示恢复算法继续沿用上游。

## 实现

- `src/app_display_profile.*`：字段校验、类型化配置、HDR 兼容性与断开决策。
- `src/process.*`：发布不可变方案表，启动/恢复读取会话快照。
- `src/display_device/parsed_config.cpp`：目标、拓扑和模式覆盖。
- `src/rtsp.*`、`src/stream.cpp`：传递快照，检查 HDR 协商冲突并处理退出策略。
- `src/video.*`：将原有动态分辨率跟随开关扩展为可按会话覆盖。
- 网页编辑器使用共享显示组件；控制面板保持上游子模块。

## 验证边界

自动测试证明配置解析与软件路径，不证明真实显示硬件、HDR、远程 USB 或触摸已在所有设备通过。
旧归档分支的双显卡修复不可作为当前发布版能力描述。
构建缓存、日志和产物不提交。原工作区备份分支与暂存记录保留。

继续开发前同时阅读 `app-display-profile.md` 和 `build-release-notes.md`。
