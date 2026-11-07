# ICT 科研工作台专业界面改版实施计划

> 在当前工作区按顺序执行，不创建子代理、不提交 Git。修改现有文件前复用已存在的 `*_copy`/`.backup` 副本。

**目标：** 依据 `docs/superpowers/specs/2026-10-23-research-workbench-premium-redesign-design.md`，统一五页、共享框架和关键弹窗，保留现有业务与安全行为。

**技术栈：** Python 3.12、Tkinter/ttk、unittest、PyInstaller、Inno Setup；不增加运行依赖。

## 文件

- `desktop/ict_desktop/ui_theme.py`：颜色、字体、导航、表格、详情和弹窗 token。
- `desktop/ict_desktop/main_window.py`：共享框架、总览、质量、团队、提案与运行页。
- `desktop/ict_desktop/quick_start.py`、`template_dialog.py`：统一向导和只读契约阅读器。
- `desktop/tests/test_ui_design.py`、`test_quick_start.py`、`test_template_dialog.py`：布局、状态、无副作用、可读性回归。
- `desktop/installer/ICTResearchWorkbench.iss`、`desktop/ICTResearchWorkbench.spec`：版本化构建。
- `task.md`、`task_plan.md`、`progress.md`、`findings.md`、`memory/ict/desktop-quality.md`：进度和经验。

## 步骤 1：确认基线和备份

1. 核对工作区状态、现有测试、构建脚本及 `0.1.42` 版本；不覆盖历史产物。
2. 使用已经存在的 `main_window_copy_20261023_pre_0.1.42.py.backup`、`ui_theme_copy_20261023_pre_0.1.42.py.backup`、`test_ui_design_copy_20261023_pre_0.1.42.py.backup`；对需要修改但没有已有副本的文件创建一次副本。
3. 运行当前 UI 专项和桌面全量测试，保存准确基线。

## 步骤 2：主题与应用框架

1. 先在 `test_ui_design.py` 添加主题对比度、导航焦点、标题栏/页内标题层级和状态色行为断言，验证 RED。
2. 更新 `ui_theme.py`，增加有语义的工作区、列表头、检查器头部、状态和弹窗样式；保留所有小字对比度门槛。
3. 在 `main_window.py` 收敛品牌、导航、全局顶栏、页标题和底部范围条，避免重复操作区。
4. 验证交互状态和现有页面导航行为不变。

## 步骤 3：总览与数据质量

1. 为项目身份/就绪边界、四步工作路径、资源台账和离线 CSV 入口写行为与视口测试。
2. 调整总览首屏层级与工作路径对齐；确保断连不盖过本机工作入口，不新增假统计。
3. 为本机预检与服务器报告来源边界、等待/失败/通过/警告状态写回归测试。
4. 重排质量页来源标签、状态、问题和修复建议，保留本地文件不上传语义。

## 步骤 4：团队、提案、运行工作区

1. 先补列表/检查器结构、空状态和操作可见性测试；提案/运行主要动作必须在常用首屏内。
2. 调整团队项目令牌区与检查器，确认令牌提交后清空且从未写日志。
3. 调整提案详情和固定操作区，确认模板/权限/禁用原因可见，不能绕过现有批准条件。
4. 调整运行详情的事件时间线与导出区；不引入取消、重试或新的写操作。

## 步骤 5：弹窗

1. 对快速开始窄屏、滚动正文、固定底栏、错误语义和令牌清空补充必要断言。
2. 对模板阅读器检查标题/分节字号、长字段复制和短屏操作可见性。
3. 对服务设置检查错误与成功状态的视觉统一；不得改变 HTTPS 校验或设置保存行为。
4. 逐项遵循 RED→GREEN；避免只断言新样式名称而不验证用户可见行为。

## 步骤 6：回归与 Windows 包（0.1.49 已完成；实机视觉验收待确认）

1. 色板回归覆盖 14 组关键文字/状态色组合，最低对比度 5.73:1；UI 专项 47 项、全桌面 136 项通过（全量日志 116.877 秒）；`compileall` 通过。
2. 版本化 EXE 与安装包构建成功，不覆盖旧版；安装包 ProductVersion 为 `0.1.49`。
3. EXE SHA-256 `19C70F005E6D94801C6B1204739DE8D1F30C2D1C1B23677A19673D415E215888`；安装包 SHA-256 `E2497342EBDA4B618EED4A07850F9A52218CB40F87532681C124CF6869BDBA60`。
4. PyInstaller 递归归档含 `ict_desktop.main_window`、`ui_theme`、`quick_start` 和 `template_dialog`；测试、构建及归档日志在 `desktop/build/ui-0.1.49-*.log`。
5. README、任务记录和项目 memory 已同步；新包尚未启动，真实窗口、常用尺寸、窄窗和 125% DPI 验收待动作时确认。

## 步骤 7：实机视觉验收（0.1.49 等待动作时确认）

1. 先完成所有独立的源码、测试、构建工作。
2. 启动新编译程序前，按 Computer Use 的动作时确认要求向用户确认；在确认前不运行新的 EXE/安装器。
3. 确认后检查五页、快速开始、服务设置和模板窗口，并核验常用视口、窄窗和 125% DPI；用户开始操作时立即停止输入。
4. 留存新版实机证据，并把尚未验证的视口或状态清楚列为待办。

## 完成门

只有功能回归、Windows 构建和真实窗口验收均分别标记结果后，才可以称为整体完成。用户未允许运行新版前，保持实机验收未完成。
