# ICT 当前开发发现

## 当前权威状态

- 当前 UI 主线是 `frontend/` React、TypeScript 与 Vite；旧 `desktop/ict_desktop` Tk 客户端只保留兼容用途。依据为根 `README.md`、`frontend/README.md` 与当前源码。
- 截至 2026-11-02，React 编辑器已接入 ICT ExecutionPlan、本机 runtime API、按输出裁剪、CSV 本机运行、SQLite 运行/节点事件与 ArtifactHandle；平台 runs API 仍用于原合成联调链路。
- `workflow_components.py` 至少一个组件绑定本机 CSV executor；其余无 executor 或依赖未满足的节点应明确阻断，不能当作已可运行。
- ICT 自有 `desktop/ict_desktop/manifest_quality.py::inspect_manifest()` 已经由独立本机 runtime 调用；报告仅是 CSV 结构预检，不代表科研结果。
- 本轮目标：按 V4.0 B1 → B2 → B3，于 2026-11-08 前实现电脑端画布工作流闭环；先前五项执行骨架，再接离线 CSV 节点，最后补基础缓存/资源/Worker 监督。手机端暂缓。
- ComfyUI v0.43.0 中可借鉴的实现点已对照源码确认：ready/block 依赖释放、递归祖先输入签名、部分输出验证和 typed node schema；ICT 使用自有协议实现，不复制 GPL-3.0 源码。
- B1 运行前检查已接入：逐节点对照本机登记执行器的权限能力，逐项校验组件依赖 ID/精确版本；CSV 检查器的安装版本来自它自身的契约声明。ArtifactHandle 输入还需保留明确授权状态。
- 当前执行面只有 `local` CSV 预检 executor；`network/platform` 分发未接入，但混合图中缺少执行端的节点会阻断其依赖链，独立本机分支仍可继续。资源准入是声明值上限检查，worker 监督限于同进程任务与重启恢复。
- 真实 Edge 1440×900 隔离浏览器流程已走通缓存工作流→本机 CSV 导入→本机草稿保存→运行成功→报告摘要展示；测试 runtime 使用临时 SQLite/产物目录，平台 API 请求不可用，页面无 JavaScript 异常。已连接后断开服务和平台修订冲突仍待验收。
- 工作流冲突分支现已在画布主区并列显示本机草稿与平台当前修订摘要，保留本机内容，并提供平台版本历史入口；不做自动合并或覆盖。真实 revision 冲突场景仍待浏览器验收。
- 本轮 jsdom 集成验收未能越过测试环境缺少 `window.matchMedia` 的问题，未执行冲突产品断言。随后前端生产构建通过；构建不代替该交互验收。

> 以下较早审计条目按其记录日期保留；如与 2026-11-02 当前状态冲突，以本节及后续闭环接入记录为准。

## 已观察截图（0.1.28，不代表当前源码）

- 首屏内容聚集在上方，窗口下半部留有大块无信息空间，当前布局没有利用纵向空间建立明确的工作路径或最近活动焦点。
- 顶栏有服务状态、快速开始、服务设置；刷新又被放到页面标题下一行，页面工具栏分散。
- 项目身份与科研就绪状态使用相近的平面矩形面板，主次和两者关系不够明确；两面板高度差异较大。
- “项目资源”使用横线分隔的三行宽表，说明、状态和操作混排，当前失联状态下尤其难以快速看出下一步。
- 全屏基底、导航、内容卡片都采用相近的深色大块面；标题明亮，但辅助文本偏暗，层次依赖大片背景而非清晰的排版、对齐和信息分组。
- 当前状态写明 API 不可用、CSV 仍可用及 `research_ready=false`；本机动作可以进一步突出。

## 历史源码结构审计（截至 0.1.36）

- 共享字体是 Microsoft YaHei UI 9pt 正文、8pt 辅助、16pt 页面标题。表格正文与辅助信息因此缺少更鲜明的尺寸层级。
- 全局顶栏包含工作区路径、服务设置、快速开始和连接状态；页面标题/说明另占行，刷新动作另放标题行；数据页也各自重复列表小标题和刷新。
- 当前总览包含项目身份/就绪头部、四步工作路径和资源行，但每步仅有编号/文字，没有可以直达对应页面的动作。布局把第 4 行设成弹性空白。
- 质量、团队、提案、运行均为同一列表/检查器结构。可以保留操作模型，同时优化共享页头、标签层级、状态位置和表格密度。
- 产品仍是 Tkinter/ttk Windows 客户端。将统一调整共享主题，并从可操作的总览工作流开始分阶段重设计。

## 一手设计参考

- VS Code Workbench 将 Activity Bar、侧栏、编辑区、Panel、Status Bar 作为职责不同的持久区域；状态栏信息保持短而少。参考：https://code.visualstudio.com/api/ux-guidelines/overview 和 https://code.visualstudio.com/api/ux-guidelines/status-bar
- GitHub Primer NavList 用当前视图状态和分组来组织侧边导航。参考：https://primer.style/product/components/nav-list/
- Microsoft Fluent 2 强调用间距建立信息关联、保持网格节奏；导航需简洁、可扫读，并按任务目标组织。参考：https://fluent2.microsoft.design/layout 和 https://fluent2.microsoft.design/components/web/react/core/nav/usage/
- 落地推断：借用“区域职责清楚、导航简短、状态精炼、间距表达关系”等原则，保留 ICT 的独立深石墨主题，不复制上述产品皮肤。

## 源码待核对重点

- `desktop/ict_desktop/ui_theme.py`：颜色、字体、按钮、表格与窗口通用样式。
- `desktop/ict_desktop/main_window.py`：主窗口、侧栏、总览、各业务页及共享分栏构造。
- `desktop/ict_desktop/quick_start.py`、`template_dialog.py`、`settings.py`：向导、模板与服务设置窗口。
- `desktop/tests/test_ui_design.py`：已有导航、响应式和状态布局约束；不得用截图之外的静态描述替代运行验收。

## 0.1.40 总览与断连态改进

- 源码审计发现旧总览把项目身份、工作路径和资源目录放在相近的矩形面板中；服务断连时横跨内容区的错误横幅比可继续进行的本机数据预检更醒目。
- 总览身份和路径现使用连续画布，资源目录保留单一边框工作面；工作路径以文字和直接动作呈现。
- 断连提示使用中性底色与青蓝标记，提供“检查本机 CSV”直接入口；顶部仍保留服务连接状态和服务设置入口。
- 新增总览表面层级与离线导航行为测试；UI 专项 28 项、桌面全量 117 项通过。真实窗口与高 DPI 验收待安装 0.1.40 后完成。

## 0.1.41 业务详情检查器

- 复核项目、提案和运行页时发现详情信息以同字号多行段落呈现，字段边界弱；项目详情控件已替换成 `Text` 后，异步选择回调仍使用旧 `Label.configure(text=...)`，触发 `TclError: unknown option "-text"` 并阻止真实数据更新。
- 统一用只读 `tk.Text` 呈现标签和值，ID 使用等宽字体，状态按语义着色；选择内容可复制，详情溢出时显示纵向滚动条。
- 滚轮事件先检查焦点详情框的可滚动方向；详情能滚时消费事件，边界时由页面画布接管。隐藏 Tk root 的测试环境可能令 `Text.yview()` 返回负的小数，因此行为测试比较滚轮前后的视口变化，而不假设绝对正分数。
- 项目加载/失败状态、项目 ID/角色/领域、各数据版本/来源/许可状态/科研就绪标记分别成行；许可登记值保持中性，附加说明要求独立核验。运行详情增加明确的“运行状态”行，并保留合成结果、`synthetic_only=true` 与 `research_ready=false`。
- 新增两项 UI 测试，定向验证详情滚轮、字段结构及状态语义；桌面全量 119 项通过。安装版实机验收仍待进行。
- PyInstaller 使用 `--specpath build\spec` 时，`--icon .\assets\...` 会相对 spec 目录解析；README 构建命令使用 `Resolve-Path` 生成绝对图标路径并通过 `python -m PyInstaller` 调用。

## 2026-10-23 继续改版时的当前事实

本轮用户指示继续处理工作台其他部分，并基于此前“希望像大厂一样设计”的委托，开始落实“科研档案台 + 协作工位”完整方案。浅色方向是用户纠正过的误点，不能再当作确认。正式规格和实施计划分别位于 `docs/superpowers/specs/2026-10-23-research-workbench-premium-redesign-design.md`、`docs/superpowers/plans/2026-10-23-research-workbench-premium-redesign.md`。

当前 CUA 应用清单未检测到工作台窗口；`listWindows` 调用返回 API 不存在，不能枚举隐藏窗口。新版构建后在动作时确认前不运行 EXE，因此不能声称完成真实窗口或 125% DPI 验收。用户要求其余页面继续检查，默认据源码与回归用例逐页推进，保持不连接团队服务、不批准提案、不启动任务。

## 0.1.43 当前源码与构建证据

- `ui_theme.py` 为列表区和详情检查器定义不同 ttk 表面；`main_window.py` 把提案批准、模板查看和运行报告导出收进固定底栏，团队访问令牌区与项目列表分开。Eyebrow 小标题统一取矿物青蓝，已有对比度测试覆盖。
- 四个新增 UI 测试验证列表/检查器角色、底栏动作归属、青蓝区块小标题与团队凭据范围说明；UI 38 项、桌面全量 127 项通过。
- `compileall` 和对照既有副本执行的 diff 空白检查通过。全仓 `git diff --check` 有 LF/CRLF 提示，没有空白错误。
- 0.1.43 EXE SHA-256 `F15C0B64C7EB8F9AA40B4D32FC688E89A52A5EA6856995D1719A76DFDF6DE530`；安装包 ProductVersion `0.1.43`、SHA-256 `5995647CED59027835BEE4D5B766D012C9EA96EA4511E21E1D7710074FFE17D5`。PyInstaller 递归归档包括主窗口、主题、快速开始和模板说明模块。
- 0.1.43 尚未启动或安装；当前应用清单为空。实机视觉、125% DPI 和窄窗口验收仍未完成。


## 2026-10-23 Tk 回归崩溃根因与修复证据

- 全量桌面测试首次在 `test_quick_start_connects_member_and_opens_the_existing_read_only_proposal_page` 附近崩溃，打印 `Image.__del__` 的 `RuntimeError: main thread is not in main loop` 和 `Tcl_AsyncDelete: async handler deleted by the wrong thread`，Windows 退出码 `-2147483645`。
- 按 `systematic-debugging` 逐步隔离：该用例单独运行通过；整个 `test_main_window.py` 运行 20 项通过；包含诊断的完整模块组合得到 faulthandler 栈，崩溃时后台线程处于 `_bootstrap_inner` 垃圾回收阶段，主线程正运行 `QuickStartWizard.check_api`，且正在回收已销毁 Tk 控件。说明问题是前序 Tk 根窗口的 Python 循环引用未在主线程收集，后台线程启动/退出触发了收集。
- `test_main_window.py` 原先没有 `tearDown`；测试只调用 `root.destroy()`，Python 循环回收可能延迟到其他线程。增加 teardown：确保根窗口销毁、清空测试持有的引用，并在主线程 `gc.collect()`。完整套件 128 项、83.921 秒通过，崩溃不再发生。
- 这是测试生命周期问题，不涉及健康检查请求或 Tk 控件被 worker 直接操作；工作线程仍只将结果写入线程安全队列。


## 2026-10-23 0.1.44 构建核验

- 桌面全量 unittest 128 项通过（83.921 秒）；`compileall` 通过，`git diff --check` 无空白错误，只有既有 LF/CRLF 转换提示。
- PyInstaller EXE：`desktop/dist/ICTResearchWorkbench-0.1.44.exe`，SHA-256 `F7FE105097018EEDD78F6656FD065782B6170A17F389CAF943BF825E9BC8A3BC`。
- Inno Setup 安装包：`desktop/dist/installer/ICTResearchWorkbench-Setup-0.1.44.exe`，ProductVersion `0.1.44`，SHA-256 `1B58CFC46D63ABB83AF914B8D59AE31FD6A314696D0B8D573B82B4E7201D0C9D`；安装日志显示成功封装 0.1.44 EXE。
- 递归 CArchive 核验包含 `ict_desktop.main_window`、`ict_desktop.ui_theme`、`ict_desktop.quick_start`、`ict_desktop.template_dialog`。日志：`desktop/build/ui-0.1.44-pyinstaller.log`、`desktop/build/ui-0.1.44-installer.log`、`desktop/build/ui-0.1.44-archive-recursive.log`。
- 没有安装或启动新版；五页/弹窗实机视觉、窄屏和 125% DPI 检查仍未完成。


## 2026-10-23 顶栏服务断连状态层级

- 旧版截图显示服务不可用用红色实心徽章强调；源码 `_set_connection_status` 也将健康检查失败映射到红底 `Connection.Error.TLabel`。这会把服务端不可达与数据/科研审核失败混为同一警报等级。
- 变更映射到 `Connection.Offline.TLabel`：沿用服务状态文字，但使用页面底色和中性辅助色。用户执行操作后出现的错误横幅与字段错误样式保持原级别。
- `test_unavailable_service_uses_subdued_topbar_status` 先失败再通过，验证控件可见文案和实际主题背景/前景。


## 2026-10-23 0.1.45 连接状态修正与交付

- 旧版截图中的顶栏服务断连状态为红色实心徽章；将常驻连接状态降为中性色，页面内真实操作错误继续保留错误层级。新增行为/主题测试先 RED 后 GREEN。
- 全桌面测试 129 项通过（83.049 秒），compileall 和 git diff 检查通过。
- EXE：`desktop/dist/ICTResearchWorkbench-0.1.45.exe`，SHA-256 `3A74DF1583026E45AE3B14A43A335F8542978D3A57AA891D66EB49E66330A584`。安装包：`desktop/dist/installer/ICTResearchWorkbench-Setup-0.1.45.exe`，ProductVersion `0.1.45`，SHA-256 `5BACBA6040475B3F6FBAA55084D6FC5B928A7E36BDD4B934942C8132F5B88CC3`。PyInstaller/Inno/递归归档日志在 `desktop/build/ui-0.1.45-*.log`。
- CArchive 含 `ict_desktop.main_window`、`ui_theme`、`quick_start`、`template_dialog`。未启动新版，真实窗口及 DPI 验收待用户提供窗口画面。
## 2026-10-23 0.1.46 字段识别与打包

- 快速开始、主页面团队访问区和服务设置中的输入控件此前没有直接可见字段名。现统一加“服务地址”或“团队访问令牌”，并以两个共享 ttk 样式适配主表面和凭据条背景；不改变令牌遮挡、生命周期、服务验证或后端调用。
- TDD 验证标签缺失时相关测试失败，修复后快速开始 9 项、UI 定向 2 项通过；再追加实际 ttk 标签样式字号和底色 AA 对比度检查。桌面全量 131 项通过（108.424 秒），`compileall`、`git diff --check` 通过，详细测试输出在 `desktop/build/ui-0.1.46-tests.log`。
- 0.1.46 EXE SHA-256 `7C8C5100B938B0CD9F4BDAF8E82E98722479FD6B84477E5B3E7AF90D6023745F`；安装包 ProductVersion `0.1.46`、SHA-256 `9EC3E176812C2FC7376FCEBFB19FD91957608D3F1F9FA58731AF985578EBB509`。PyInstaller、Inno Setup 与 CArchive 递归日志均位于 `desktop/build/ui-0.1.46-*.log`。
- 用户选择本轮继续处理其他部分，因此未启动程序；真实窗口与 125% DPI 检查继续待办。

## 2026-11-02 当前画布工作流执行缺口

- `frontend/src/App.tsx` contains the React Flow editor and calls workflow CRUD/version/component/validation APIs. Save, version, history, undo/redo and contract validation are wired; the toolbar Run button is explicitly disabled with “科研节点执行器与 DAG 执行服务尚未接入”.
- `backend/app/api/v1/workflows.py` validates versioned graph documents and returns `executable: false`; `backend/app/services/workflow_catalog.py` enforces owner membership, optimistic revisions, graph structure and component contracts.
- `backend/app/api/v1/runs.py` DTO is fixed to `dataset-synthetic-v1` / `research-smoke-v1`, with only queued/running/succeeded/failed states; it cannot represent DAG node runs or offline CSV runs.
- The local CSV helper is safe to reuse as a Python function, but a browser React app cannot call it after a platform API outage without an independent local runtime. Design/runtime boundary remains an implementation decision to resolve from existing packaging and process startup.

### 持久化和测试架构

- `Workflow` / `WorkflowVersion` 是工作流专属表；现有 `Run` 与 `RunEvent` 通过 `RunProposal` 强绑定 synthetic pipeline，不应扩展成通用 DAG 运行记录。工作流执行应新增独立 workflow-run / node-run 模型与 migration。
- backend 测试使用 `unittest` + FastAPI `ASGITransport` + 临时 SQLite；现有测试没有工作流执行覆盖，适合新增独立 `test_workflow_execution.py` 与 `test_workflow_runs_api.py`。
- 当前结构/组件校验与版本持久化已在 `workflow_catalog.py`；执行计划编译需要独立服务，调用现有契约校验，避免把工作流 JSON 校验和节点执行逻辑耦在 API route。

## 2026-11-02 Compiler 与调度器实现事实

- `backend/app/services/workflow_execution.py` 当前将所选目标的祖先节点编译为 `ict.execution.v1`；组件契约哈希和执行参数纳入计划哈希，React Flow `position` 不进入执行计划。
- 编译对所选子图运行 ICT 现有结构与组件契约校验；无关分支未登记组件不会阻断所选输出。重复 ID/悬空端点仍作为图文档级错误拒绝。
- `backend/app/services/workflow_scheduler.py` 是内存执行内核：有界并发、依赖释放、异步外部等待、节点异常隔离和下游阻断。事件/节点结果尚未持久化；正式执行器需传递 ArtifactHandle，避免大数组/模型对象长期驻留调度器内存。
- compiler + scheduler 通过 5 项定向测试。DB 运行记录、执行 API、本机 local runtime、CSV artifact 输入和 UI 连接尚未实现。
## 2026-11-02 本机工作流闭环接入

- 端口必须分开：平台 API 使用 8765，MCP 使用 8766，本机 runtime 默认 8767；`ICT_LOCAL_RUNTIME_PORT` 可覆盖本机 runtime 端口。
- 本机 runtime 与 React 页面分离进程，开发启动脚本复用健康的既有 runtime，只负责关闭自己启动的子进程。生产桌面包尚无 sidecar 生命周期管理。
- 页面 localStorage 只提供已访问项目/工作流的离线导航快照；本机 SQLite/ArtifactHandle 才保存本地草稿、执行记录和文件。二者均不能代表平台最新权限。
- 待同步本机草稿若基于旧 revision，需保留其内容与预期 revision，阻止静默覆盖；服务端乐观并发校验仍是最终保护。
- 首个离线闭环只包含 CSV 清单结构预检，不是完整科研验证或研究结论；其他 network/platform 组件必须按实际依赖阻断。
- 代码构建和浏览器离线验收需分开记录；没有完整浏览器证据时，不宣称断网端到端已验收。
- 2026-11-02 已加入 SQLite Input Signature 缓存（使用产物内容哈希、组件/实现版本、参数、依赖和运行环境），缓存命中仍保存新的节点运行记录；CSV 结构预检可复用前次的内容寻址报告产物。
- 本机资源准入按组件声明检查请求、限制活动运行和节点并发，并在异常 task/进程重启后标注失败；这是保守准入与恢复机制，不是 OS 级 CPU/内存硬限制或独立 worker 进程隔离。
- 当前只注册了可离线运行的本机 CSV 预检节点；网络直连节点和平台云节点虽已是设计上的不同执行目标，实际工作流 executor 仍待接入。
- Uvicorn factory 必须能以零参数创建 runtime，因为启动脚本用 `--factory`；默认 runtime 数据目录修复后，实际 Uvicorn application startup、health 和 `5173` CORS preflight 均通过。手工 API 纵向切片确认首次 CSV run 成功、同输入第二次为 `CACHED`，每次都保留 Run/NodeRun 历史。
- 运行产物不能只展示 ArtifactHandle 元数据；当前结构报告读取接口先按登记 handle 解析路径、校验 SHA-256、限制 JSON 类型和大小，再通过浏览器面板展示汇总字段。
- `WorkflowEditor.handleRunWorkflowLocally` 会将当前画布保存到本机 runtime 草稿，再用所选输出目标提交本机运行；该执行路径不依赖平台 API 的在线状态。
- 混合执行提示应基于所选输出的祖先闭包和本机组件目录的 `execution_available`，避免未选择的 network/platform 分支造成错误提示；本机调度器仍会阻断缺少执行器的节点及其依赖下游。
- 运行前提示只解释当前部分成功/阻断行为，不代替 `network/platform` 执行器；两类执行器仍未接入。

## 2026-11-02 Crossref network executor 实现事实

- 网络节点固定为 `https://api.crossref.org/works/{DOI}`；URL 只能由已校验 DOI 生成，禁止工作流文档注入 URL 或代码。运行确认只展示本次所选祖先闭包中的 DOI；确认前没有网络请求。
- adapter 使用锁定的 `httpx==0.28.1`，请求并发上限 1、连接超时 5 秒/总超时 20 秒、响应体上限 2 MiB、关闭重定向且不重试；HTTP/网络错误通过 `WorkflowNodeFailure` 返回，不拖停独立分支。
- Crossref 只输出有限公共书目字段，不读取摘要；产物权限标记为 `public_metadata`，报告访问校验本机登记的 handle、内容 SHA-256、JSON 类型、2 MiB 上限、固定主机与 DOI 一致性。读取接口重建字段白名单，不直接返回存档 JSON 的附加键。
- network target 用自身 permission capability map、精确依赖核对和独立资源预算；平台目标仍没有 Worker adapter。桌面 EXE 打包网络 adapter `.py` 供实现摘要使用，并拷入 `httpx` 模块及 dist-info 供运行时依赖检查。
- 2026-11-02 build+smoke 已确认 EXE 能提供 loopback UI/runtime、network 和 local CSV executor 可用；验收未触发 live Crossref，故网络服务真实响应/429/错误行为仍未实际验收。

## 2026-11-02 Windows 生产桌面包核验

- `desktop/workflow_shell.py` 把 loopback FastAPI 与构建后的 React 静态资源放到同一 origin；生产 API URL 可从 `window.location.origin` 解析，开发/预览脚本仍通过 `VITE_LOCAL_RUNTIME_URL` 显式连接独立 runtime。
- PyInstaller spec 的 data tuple 第二项是目标目录，不是完整目标文件名；前端资源按源文件父目录归档，运行时才能从 `_MEIPASS/frontend/dist` 找到 `index.html` 与相对静态资源。
- CSV executor 在冻结包里动态导入 ICT 自有 `ict_desktop.manifest_quality`，因此 checker `.py` 放在 `_MEIPASS/desktop/ict_desktop`，adapter 源放在 `_MEIPASS/app/services` 供依赖/实现摘要读取。
- Windows onefile 外层 bootloader 会启动同路径解包子进程；诊断 smoke 若强制结束外层进程，需要先核对子进程 EXE 路径再回收。正常 app 路径等待 Edge app 窗口关闭后有序停止 Uvicorn runtime。
- 本次 EXE 实际验证了健康接口、静态页面、会话和 CSV executor；这证明便携包本地启动能力，不代表已测试 Edge app 窗口、多轮 CSV DAG 执行或 network/platform executor。

## 2026-11-02 ComfyUI 源码对照与断连验收准备

- 本地源码包位于 `E:/comfyuisource/ComfyUI-master`，许可证文件原文标明 GPL-3.0；ICT 根目录没有声明 GPL 兼容许可证，因此沿用算法和边界设计，不直接移植 ComfyUI 源文件。
- ComfyUI `comfy_execution/graph.py` 用 pending 节点、依赖阻塞计数和 `get_ready_nodes()` 驱动静态图，并通过 external block/unblock 暂停等待异步工作；ICT 的 `workflow_scheduler.py` 已有对应的 Ready/Blocked 状态和 `WAITING_EXTERNAL`。
- ComfyUI `comfy/comfy_types/node_typing.py` 以 `IO(StrEnum)` 声明端口类型，并将 required/optional 输入与输出契约挂到节点定义；ICT 已有版本化组件契约、类型化端口和参数 Schema。
- ICT `workflow_execution.py` 已独立编译编辑图、按输出节点回溯祖先闭包并生成 `ExecutionPlan`；该机制不依赖 ComfyUI Prompt JSON。
- 当前前端手动断开函数会清除 `projectId` 并返回工作台项目页。需用隔离浏览器检查：打开的工作流是否能在平台连接中断后保留本地执行上下文；若手动断开路径丢失上下文，应修正后再验收。
- 本机未预装 Python Playwright。已将 Playwright 1.64.1 与依赖安装到系统临时目录 `ict_workflow_acceptance_pw_20261102`，没有改动项目依赖；Edge 已安装，可用于隔离上下文验收。安装输出出现系统级 OpenTelemetry 版本提示，但目标包安装成功。
- 本机 Python 3.12 已有 FastAPI 0.136.3 与 Uvicorn 0.49.0；`local_runtime.py` 从 `ICT_LOCAL_RUNTIME_DIR`/`ICT_LOCAL_RUNTIME_PORT` 读取存储目录与端口，可启动独立临时 runtime 验收。
- 本机接口先申请临时 session token，再用 `X-ICT-Local-Token` 调用组件目录、CSV 上传、工作流草稿与运行接口；平台 token 不参与本机 runtime 请求。
- `disconnect()` 是显式设置页动作，当前会清空活动项目上下文；意外平台 API 失败时组件状态与打开的编辑器由另一条路径处理。需要分别验收“当前编辑器中途平台请求失败”和“页面重载后用缓存恢复工作流”。
- 一次命令在已切换到 `backend` 工作目录后仍使用带 `backend/` 前缀的相对路径，导致本地文件读取失败；原因仅为路径重复，后续从当前目录用 `app/...` 访问，不再递归搜索。
- CSV 预检组件通过必填参数 `parameters.artifact_id` 引用本机 ArtifactHandle，组件本身不要求上游输入端口；runtime 有独立临时目录和端口，可在平台 API 模拟离线时跑真实 CSV checker。
- 工作台“最近打开的工作流”在 `projects.status === idle` 时只显示“连接项目服务后，才能验证并显示本机保存的工作流记录”，因此断开后用户导航回缓存工作流的入口可能缺失；还需实测重新加载/当前画布两条路径。
- `WorkflowEditor` 在无平台 token 时会先读取浏览器缓存工作流，尝试用独立 runtime 的本机草稿覆盖图；平台 API 请求失败也会回退同一缓存路径。`handleRunWorkflowLocally()` 先写本机草稿，再提交本机 run，不调用平台 API。
- 工作台最近工作流列表仍需平台项目目录验证；手动断开会清除路线且列表不提供离线入口。已打开的编辑器在平台 API 中途失败和页面重载后通过带 ID URL 恢复，均应单独验收。
- 本机运行详情需先在“运行历史”中选择 run；“产物”标签随后展示输入 ArtifactHandle、报告 ArtifactHandle 和 `CSV 结构预检摘要`，报告内容通过受限本机报告 API 按 handle 读取。单纯读取报告接口 200 不代表 UI 报告已渲染。
- 项目内真实导航顺序为：工作台项目项 → 项目页“工作流”标签 → 已登记流程“继续编辑”；打开处理器会记录本机最近工作流 ID。可据此验收连接/修订冲突/断开后的完整恢复，而不必手写浏览器历史。
- 修订冲突对照只有在本机 `workflow-pending-sync:<id>` 为 `true` 且本机缓存与平台返回不同内容时出现；平台保存新修订时应保留本机 `revision` 与 graph，版本历史入口只在仍有平台凭据时可用。
- 连接→断开→最近工作流检查发现实际渲染门槛遗漏：缓存 fallback 状态已 ready 且有行，离线权限提示可见；但 `<ul>` 的显示条件仍额外要求 `projects.status === 'ready'`。显式断开会把目录状态置为 `idle`，因此入口被隐藏。修复应仅移除这一在线目录状态门槛，保持缓存行自身的结构/归属校验。


## 2026-11-04 最新便携包的本机模板入口

- 空的隔离 runtime 首次启动后，桌面工作台可通过“新建本机项目”真实调用本机项目 API 并进入项目详情；未配置平台令牌。
- 模板市场的 `CSV 结构预检与描述统计` 本机内置模板可读取本机项目选择项；点击“添加并打开工作流”走 loopback `/api/v1/local/workflow-templates` 和项目 scoped `workflows/from-template`，返回 201，随后路由进入本机 workflow ID。没有调用平台注册模板 API。
- Playwright 对 hash 路由误用等待整页导航会超时；验收应等 `window.location.hash` 或工作流画布 DOM，不能据 wait_for_url 的 load 等待超时判定创建失败。
- 当前最新包完整 CSV 闭环仍在进行：尚未核实导入、参数、运行报告及 runtime 重启后的恢复。

- 最新便携包模板画布由组件 registry 提供节点能力状态；四节点均显示“本机可用”。CSV 源节点必须通过受控的本机文件导入生成 ArtifactHandle，之后把其 ID 填入节点参数；节点描述已明确文件不上传。

## 2026-11-04 最新便携包本机闭环复核结果

- 在平台项目服务未配置、没有平台 token 的独立 runtime 中，工作台本机项目卡片、项目详情、项目工作流和最近运行数据均可用；该范围依赖本机 loopback runtime 与本地副本，不表示未下载的项目也能离线打开。
- 内置 CSV 模板生成四节点 DAG：CSV 来源 → 字段选择 → 结构预检与描述统计两个末端；选择两个报告输出后依赖闭包为 4 个节点，运行时四节点均成功。
- CSV 来源的 `artifact_id` 是必填图参数。缺失时本机校验正确阻断；通过源节点受控文件导入并显式保存后，运行计划引用真实本机 ArtifactHandle。此次首轮模板草稿未保留 source handle，重新导入与保存后才通过；原因未定位到产品代码，本轮没有代码更改。
- 最新包 `desktop/dist/workflow-app-20261104-offline-project-open-v3/ICTWorkflowWorkbench.exe` 在相同临时 `LOCALAPPDATA`、端口 `18826` 重启后，项目、修订、运行状态与报告仍可读取。隔离 runtime 数据位置：`%TEMP%\ict_nov10_basic_loop_current_package_20261104\ICT\WorkflowWorkbench`。
- 结构预检结果 `research_result=false`，4 行、4 字段、0 个问题；描述统计同样只提供探索性分布，不含检验或科研结论。CSV 经过字段选择后不含 `unused_column`。
- 本轮报告面板可在底部“校验”区选择输出目标；检查侧栏的“运行配置”当前禁用并提示服务未接入，这不妨碍已实现的本机输出目标选择与运行。
- 首轮运行后重启恢复路径已完成；宽屏桌面端视觉验收仍需在完整桌面浏览器窗口下单独进行，因为本轮内嵌浏览器视口为 516 px。

## 2026-11-04 最新便携包复现状态映射与执行环境详情

- 在 `workflow-app-20261104-offline-project-open-v3` 的本机复现任务 UI 中，状态映射实际可见：任务 `awaiting_review` →“待复核”；运行/节点 `SUCCEEDED` →“成功”；事件 `QUEUED`/`RUNNING`/`READY`/`SUCCEEDED` 映射为“排队中 / 运行中 / 就绪 / 成功”。不能仅以类型测试代替这条真实 UI 证据。
- 本机 task workflow 的快捷 CSV 结构预检节点在复现任务下可保存、校验并运行；输出读取为结构预检 ArtifactHandle，标签保持“非科研结果”。任务详细页说明运行证据仅在本机、不自动同步，复现任务专属同步入口仍未接入。
- “CSV 描述统计摘要”组件详情由注册目录契约填充执行位置、executor binding/version、依赖、资源、权限：本机、不依赖平台；`ict.local.csv_descriptive_summary@1.0.0`；无额外依赖；120 秒、500 mCPU、512 MB、0 GPU、100 MiB 输入上限；使用 `input_signature` 缓存。
- 当前 v3 包较早的 `component-environment` 包新；已有的 v3 可用于核验这些组件详情与运行状态改动。IAB 视口约 501 px，仅功能复核，不作为 1280+ 宽屏签收。

## 2026-11-04 工作台断连时项目打不开

- 本机项目与平台项目使用不同 ID；显式同步关系通过本机项目的 `platform_project_id` 保存。
- 工作台打开动作此前直接将卡片 ID写入路由；项目详情页按 `local-project-*` 前缀决定本机/平台加载方式，因此从平台项目入口不能进入已有本机工作副本。
- 修复策略：平台状态不是 `connected` 时优先用 `id` 或 `platform_project_id` 找到本机目录项并导航到其本机 ID；直接深链接也执行相同回退。项目详情请求检测到平台级不可用错误时同步更新全局状态并触发回退。连接成功时仍打开平台项目。
- 无本机副本的远端项目在断网时不能恢复服务器专有内容；保留平台列表缓存的项目摘要入口并清楚区分缺失的工作流/数据目录。

## 2026-11-04 当前离线路由修复已进入便携包

- 前端 `npm run build` 和独立目录的 PyInstaller 构建成功；v3 便携包保持不变。新包：`desktop/dist/workflow-app-20261104-offline-linked-project-routing/ICTWorkflowWorkbench.exe`，SHA-256 `907DD3D6E27AC728DDCD332C26EF86B98F579A1DB7C21BF3EC7B2A46E7F63A8A`。
- 隔离 `LOCALAPPDATA` 启动时 health 为 local，平台服务未监听；静态首页和 JS bundle 均为 200，bundle 包含离线项目映射标识。端口 18828 已释放。
- 浏览器脚本已在隔离 runtime 保存合成平台项目与本机项目 ID 映射，但刷新后的卡片点击/深链接断言未执行。不能把打包 smoke 等同于离线 UI 路由验收。

## 2026-11-04 断连平台卡片到本机副本

- 只监听 loopback 的模拟项目服务返回 1 项合成平台项目；对应本机 runtime 项目同步状态为 `synced`，`platform_project_id` 与卡片 ID 一致。
- 点击工作台平台项目卡片后，模拟详情 API 503；App 更新平台服务不可用状态，映射 effect 将 `#workbench/projects/platform-project-offline-map-acceptance` 切换到匹配的 `#workbench/projects/local-project-*`，并渲染本机详情页。
- 初次模拟连接因测试服务器未处理 CORS OPTIONS 501 失败；增加只允许 `http://127.0.0.1:5173` 的预检处理后连接成功。这是模拟器配置问题，非产品缺陷。
- 未映射到本机副本的远端项目仍不能还原未缓存服务端数据；此验证只覆盖已有本机副本的断连回退路径。

## 2026-11-04 默认启动包版本滞后

- 工作台离线路由源码已更新，但正式打包脚本的默认目标 `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe` 仍停留在 2026-11-02；此前的 2026-11-04 编号 EXE 未替代用户常用默认目标。
- 这类“我这里测试通过、用户运行仍失败”的复发，先核对用户启动路径和该路径二进制时间/哈希，再决定是源码故障还是交付遗漏。
- 正式目标包重建后，隔离无平台服务页面已从本机项目卡片进入项目详情。远端平台对象缺少本机副本时，仍不能恢复未缓存的服务端内容。

## 2026-11-04 未连接平台服务的默认包项目打开复核

- 当前正式默认 EXE 在隔离环境中实测：平台令牌为空时，本机项目卡片可打开本机详情；有 `platform_project_id` 映射的缓存平台卡片会跳转到 `local-project-*` 本机副本。
- 已显示项目名称、设备本机副本状态和工作流入口。平台服务请求未发出；关闭隔离运行端口 18834/18835。
- 默认包 SHA-256：`541F4B6AD11BD0BE79A36ED29DD3F7681C6A06FE2DE1233FCC6C08D25B0CDA89`。
- 适用边界：没有本机映射/副本且没有已缓存详情的远端项目，无法离线还原其服务端数据；不能把该对象当作本机项目展示。未运行自动化测试。

## 2026-11-04 断连时项目卡片可见但详情打不开

- 源码显示，平台与本机详情页的目录摘要回退分别调用 `cachedProjectSummaryDetail(id)` 和 `cachedLocalProjectSummaryDetail(id)`，两者只查 localStorage；`Workbench` 已持有当前项目列表，但此前没有把对应条目传给详情页。
- 因此，当工作台已有列表数据而浏览器存储缺少该项目摘要时，点击卡片会进入详情路由，却可能显示“没有本机缓存”。本轮把当前已加载且 ID 匹配的目录项作为摘要来源，优先级高于再次读取存储。
- 摘要只含项目列表字段；工作流、数据集和运行目录按各自缓存状态显示。平台授权拒绝及 API JSON 404 不使用摘要覆盖。
- 当前验证只覆盖类型检查、生产构建及便携包 health/static smoke；内嵌浏览器控制调用超时，实际卡片点击还未复核。

## 2026-11-04 项目可见但缓存工作流画布无法打开

- 隔离页面显示项目详情和缓存工作流目录，画布按钮 disabled；`LocalProjectDetailPage` 的 `isCachedSnapshot` 同时阻断按钮和 `WorkflowEditor` 路由。编辑器本身已有完整工作流图的 localStorage 回退，因此阻塞在项目页入口/路由门槛。
- 只允许项目归属匹配的完整工作流图缓存离线打开；工作流摘要缓存不包含节点图，不能据此伪造可打开的画布。运行时不可用时，本机数据库保存、工作流新建和运行仍不可用。
- 重复反馈与用户仍看到旧行为有关：系统登记的 `E:\AAAAcom\icttest\ICTResearchWorkbench.exe` 时间为 2026-10-21，早于离线路由修复。更新前先留存旧版及此前当前包副本；新构建已同步到默认包和登记入口。
- 本次生产构建完成；实际启动新 EXE 的后置 UI 点击验收未完成，因为隔离启动命令被本机执行策略拒绝。不能把构建结果写成 UI 实测通过。

## 2026-11-04 断连项目复核发现开发服务已停止

- 用户当前浏览器标签仍在 5173，但操作系统没有该端口监听进程；旧标签仍保留页面，不代表服务可刷新或重新加载。
- 恢复 `npm.cmd run dev` 后，5173 返回 200；本机 runtime 8767 health 正常且 `platform_required=false`。平台服务保持未连接。
- 在工作台实点合成缓存平台项目卡片，进入项目概览成功。该平台摘要只有项目列表信息，因此工作流/数据内容仍显示未缓存；这不能代替用户实际项目验收。
- 当前源代码和默认桌面包路径均已有此前离线摘要回退，源码此轮未再更改。用户真实项目若仍失败，需拿到对应卡片名称和可见错误，区分无本机副本、未缓存子内容及权限错误。

## 2026-11-04 当前默认包基本组件复核补充

- 正式默认 EXE `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe` 当前 SHA-256 为 `6898E6DE67577DD05637C3EAE68A325EFF85EEB29A890A4AC81FD9DEB611A9A6`。隔离启动时平台服务关闭，health 报告 `mode=local`、`platform_required=false`、`frontend_served=true`。
- 新建隔离本机项目并从本机模板市场创建 CSV DAG；受控导入合成文件，显式保存草稿，刷新后 ArtifactHandle 仍存在。校验后来源、选列、结构预检、描述统计四节点全部成功。
- 两个输出均为 3 行/4 列；字段仅 `record_id, group_id, split, label`。报告保持“非科研结果/非科研结论”。
- 结束后以相同隔离 `LOCALAPPDATA` 和端口重启默认 EXE；项目、工作流 revision、成功 run、节点状态和报告仍可读。复核未访问平台 API、Crossref 或外网。
