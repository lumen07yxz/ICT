# ICT 科研工作台 UI 改进实施计划

> **执行方式：** 在当前会话逐步实施；不创建子代理、不提交 Git。

**目标：** 逐页提高 ICT Windows 科研工作台的可读性、层级、辨识度和操作效率，并用真实运行状态验证。

**架构：** 保持 Tkinter/ttk 与现有业务数据流；由 `ui_theme.py` 统一颜色、字体、按钮、导航和表格，再由 `main_window.py` 和各对话框补齐页面信息架构。行为约束用现有桌面单元测试守护，打包后用实际窗口截图验收。

**技术栈：** Python 3.12、Tkinter/ttk、unittest、PyInstaller、Inno Setup。

---

## 文件职责

- `desktop/ict_desktop/ui_theme.py`：共享设计令牌、字体层级、控件状态。
- `desktop/ict_desktop/main_window.py`：固定导航/顶栏、总览和四个业务页。
- `desktop/ict_desktop/quick_start.py`、`template_dialog.py`、`settings.py`：后续阶段统一对话框表现。
- `desktop/tests/test_ui_design.py`：导航、页面状态、窗口布局、无副作用入口的回归检查。
- `desktop/installer/ICTResearchWorkbench.iss`：Windows 安装包版本。
- 根目录 `README.md`、`task.md`、`memory/ict/desktop-quality.md`：用户文档、阶段进度和持续决策记录。

## 任务 1：共享设计令牌与总览工作流动作

**涉及文件：**

- 修改 `desktop/tests/test_ui_design.py`
- 修改 `desktop/ict_desktop/ui_theme.py`
- 修改 `desktop/ict_desktop/main_window.py`

1. 在 `UiDesignTests` 添加字号约束：读取 `FONTS`，断言正文至少 10pt、辅助至少 9pt、页面标题至少 20pt；读取 `Title.TLabel` 和 `Body.TLabel` 样式，确认字体与共享 token 一致。
2. 添加工作流导航行为测试：对 `overview_workflow_actions` 的四个按钮逐一 `invoke()`，断言 `_active_page` 按顺序为 `projects`、`quality`、`proposals`、`runs`；这些入口必须调用现有页面导航，不访问 API、不提交令牌。
3. 运行 `..\.venv\Scripts\python.exe -m unittest desktop.tests.test_ui_design.UiDesignTests.test_design_typography_tokens desktop.tests.test_ui_design.UiDesignTests.test_overview_workflow_actions_navigate_without_service_calls -v`，确认它因新字号/按钮尚未实现而失败。
4. 在 `ui_theme.py` 更新低饱和矿物青、深石墨/蓝灰表面、可读的次级文本和 10/9/20pt 字号体系；按钮/选中/焦点/表格样式统一引用 token，保持语义状态色。
5. 在总览步骤结构中加入四个真实按钮，分别绑定现有 `show_projects`、`show_quality`、`show_proposals`、`show_runs`，并保留描述、重排逻辑与合成范围提示。
6. 重跑两条新测试；再运行 `..\.venv\Scripts\python.exe -m unittest desktop.tests.test_ui_design -v` 和 `..\.venv\Scripts\python.exe -m compileall -q desktop\ict_desktop`。

## 任务 2：页头、表格和状态系统逐页收敛

**涉及文件：** `desktop/ict_desktop/main_window.py`、`desktop/tests/test_ui_design.py`。

1. 逐页检查现有页面标题、说明、刷新和连接入口；保持固定全局顶栏只放服务状态与全局动作。
2. 让数据质量、团队项目、提案、运行页的列表标题和刷新操作使用同一结构；项目检查器、提案检查器、运行时间线维持相邻布局。
3. 让连接、加载、空记录、失败、选中和禁用状态保持文字表达，并以同一间距和强调色呈现。
4. 为每个改动先写对应的回归断言并确认失败，再改实现；每页完成后运行相关单测。

## 任务 3：向导、服务设置与模板阅读器统一

**涉及文件：** `desktop/ict_desktop/quick_start.py`、`template_dialog.py`、`main_window.py`、`tests/test_quick_start.py`、`tests/test_template_dialog.py`、`tests/test_ui_design.py`。

1. 在保持令牌只驻留内存、服务地址 HTTPS 校验、模板只读等约束下，统一窗口页头、正文宽度、分节间距和固定底部操作区。
2. 以现有窄窗/滚动/关闭清理测试为基线，增加必要的真实行为断言，再逐个改版。

## 任务 4：运行验收与 Windows 交付

**涉及文件：** `desktop/installer/ICTResearchWorkbench.iss`、根目录 README/task/memory。

1. 运行桌面相关单元测试、compileall、`git diff --check`；记录所有输出与失败。
2. 构建新版本 EXE 和安装器；用归档递归清单确认页面、主题和对话框模块存在，核对安装包 `ProductVersion` 与 SHA-256。
3. 通过 Computer Use 查看总览、质量、团队、提案和运行页，以及快速开始、设置和模板窗口；检查 100%/125% 缩放、长文本滚动和窗口尺寸。
4. 如检测到用户正操作窗口，停止 UI 输入，完成独立静态工作并将可视验收保持为未完成。

## 当前范围与验收边界

本轮先完成任务 1。任务 2–4 继续对应根目录 `task_plan.md` 的阶段，不因为一次打包成功就声明整体目标完成。安装和发布需在用户明确要求后进行。
