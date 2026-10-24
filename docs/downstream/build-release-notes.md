# 构建与发布

- 依赖 Node 26.7+（低于 27）、npm 11.19+、MSYS2 UCRT64、Rust MSVC 工具链。
- 网页检查：`npm.cmd run lint:webui`，`node --test --test-isolation=none "src_assets/common/assets/web/tests/*.test.js"`。
- 原生检查：全新 CMake 构建目录启用 `BUILD_TESTS=ON`，构建后 `ctest --test-dir build --output-on-failure --no-tests=error`。
- 工作流检查：`actionlint .github/workflows/main.yml`。
- 正式发布手动触发 `main.yml`，使用发布分支或已验证提交；填写 `publish-release=true`、版本标签、名称和 `prerelease=false`。
- 不预先推送发布标签；完整构建、测试与上传产物成功后，工作流创建附注标签并发布。
- 准备任务把引用解析为精确提交；虚拟显示器辅助测试通过后才运行 Windows 构建及发布。
- Inno Setup 暂继续固定 6.7.3，校验官方 GitHub 资产摘要，不引入未经验证的镜像。
- DualSense 清单来自锁定上游正式版，需与锁定控制面板源码协议、版本及资产摘要一致。
- 六项发布资产：安装版、便携版、DualSense ZIP、DualSense 清单、SHA256SUMS.txt、checksums.json。
- 云端成功后检查正式发布状态、标签提交与六项资产；未经完整成功不能报告发布完成。

v4.1 以 v4.0 为基线同步上游正式版 `v2026.1020.23431.杂鱼`；DualSense 可选组件继续锁定同一正式版。上游控制面板结构或插件变化时适配打包脚本；不把归档分支增强功能自动合并回来。
