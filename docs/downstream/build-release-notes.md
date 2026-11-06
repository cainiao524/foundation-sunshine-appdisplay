# 构建与发布

- 依赖 Node 26.7+（低于 27）、npm 11.19+、MSYS2 UCRT64、Rust MSVC 工具链。
- 网页检查：`npm.cmd run lint:webui`，`node --test --test-isolation=none "src_assets/common/assets/web/tests/*.test.js"`。
- 原生检查：全新 CMake 构建目录启用 `BUILD_TESTS=ON`，构建后 `ctest --test-dir build --output-on-failure --no-tests=error`。
- 工作流检查：`actionlint .github/workflows/main.yml .github/workflows/sync-upstream.yml`。
- 正式发布手动触发 `main.yml`，使用发布分支或已验证提交；填写 `publish-release=true`、版本标签、名称和 `prerelease=false`。
- 当前工作流的 `source-ref` 需包含自动发布脚本；构建启用自动化之前的历史源码时，选择对应的历史发布分支运行其原有工作流。
- 控制面板和触控笔插件统一从锁定子模块源码构建；工作流不再接受单独的 GUI 产物下载入口。
- 编译缓存仅由 `master` 与 `release/*` 分支在编译成功后保存，并清理同一分支的旧缓存；PR 仅恢复缓存。
- 不预先推送发布标签；完整构建、测试与上传 Actions 产物成功后，工作流创建附注标签、上传草稿并核对六项资产，再正式发布。
- 准备任务把引用解析为精确提交；虚拟显示器辅助测试通过后才运行 Windows 构建及发布。
- Inno Setup 暂继续固定 6.7.3，校验官方 GitHub 资产摘要，不引入未经验证的镜像。
- DualSense 清单来自锁定上游正式版，需与锁定控制面板源码协议、版本及资产摘要一致。
- 六项发布资产：安装版、便携版、DualSense ZIP、DualSense 清单、SHA256SUMS.txt、checksums.json。
- 云端成功后检查正式发布状态、标签提交与六项资产；未经完整成功不能报告发布完成。

## 自动同步正式版

`Sync upstream stable` 位于默认分支 `master`，每 6 小时检查
`AlkaidLab/foundation-sunshine` 的最新正式 Release，忽略预发布。
计划时间为台北时间 02:17、08:17、14:17、20:17；GitHub 的定时任务可能延迟。
没有新正式版时不构建、不创建新发布。可在 Actions 手动 Run workflow，
勾选 `check-only` 只读检查，取消勾选则立即执行同步或恢复待完成版本。

- `.github/upstream-stable-release` 和 `.github/upstream-stable-commit` 固定已同步上游版本及提交。
- `.github/upstream-sync-state.json` 记录上游映射与本仓库版本。自动版本从 `v4.3` 开始，递增次版本并跳过已存在的同系列标签。
- 从 `master` 创建 `codex/upstream-sync-pending` 候选，普通三方合并保留 App Display 改动；子模块使用合并后的 gitlink，禁止 `submodule update --remote`。
- `.github/workflows/` 由下游维护，自动合并保留当前 `master` 的工作流。上游 CI 变更列入 `.github/upstream-workflow-changes.json` 和 Actions 摘要，由维护者另行接入，避免丢失发布门槛或依赖具有工作流写权限的长期凭据。
- 直接调用 `main.yml`，全部测试、打包和发布使用候选的精确提交，不依赖机器人推送触发下一次工作流。
- 六项资产验证包括 GitHub SHA256、下载后 SHA256、两种校验清单、ZIP CRC、便携包所需文件及 DualSense 清单一致性。
- 发布验证成功后才快进 `master`。候选分支保留，后续任务可识别已完成版本；旧发布分支及标签保留。
- 调度流程串行且不会取消正在发布的版本；只使用当前运行的 `GITHUB_TOKEN`，无需个人长期 token。

### 失败与恢复

合并冲突、上游标签被移动、历史倒退、候选构建期间 `master` 被人工更新，均停止自动推进。
错误和冲突文件在 Actions 日志与任务摘要中；失败通知沿用 GitHub 账号的 Actions 通知设置。
网络、构建或草稿上传失败可用 **Re-run failed jobs** 或再次 **Run workflow** 重试，
保留同一候选提交与版本号。同名标签指向其他提交、非本流程创建的草稿、已发布但资产不完整的版本不会被自动覆盖。
若发布已完成但推进分支失败，下次检查会直接重新验证已发布资产，再尝试推进，无需重复构建。

冲突需维护者处理并验证后更新候选；如果 `master` 已改变，需要手动协调候选基线。
这类状态不会以强制覆盖或静默丢弃候选来解决。暂停定时同步可在 Actions 页面 Disable workflow，之后可 Enable workflow 恢复。
GitHub 可能在公开仓库连续 60 天无活动时停用定时任务，需要重新启用。

这里自动化的是仓库同步和发版；锁定控制面板仍使用上游更新源，客户端更新源不随本流程变更。

v4.2 在 v4.1 应用显示方案及修复的基础上同步上游正式版 `v2026.1031.121458.杂鱼`（提交 `204a96826606b3a34cf2cd813aed0f0a9bba7db0`）；DualSense 可选组件锁定同一正式版。MAT 软件回归与 VDD 检查均为 Windows 构建及发布的前置条件，并使用同一精确提交。上游控制面板结构或插件变化时适配打包脚本；不把归档分支增强功能自动合并回来。
