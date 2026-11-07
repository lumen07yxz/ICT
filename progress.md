# UI 重设计进度

## 2026-11-06 工作台本机最近运行摘要

- 对照 V4.0 UI-6.1，工作台缺少可继续查看的最近运行；本机运行接口按工作流返回带状态、时间与运行 ID 的列表，平台项目运行响应没有工作流 ID。
- 右侧辅助栏新增紧凑的本机最近运行列表，按最近打开的本机工作流读取各自最新运行，显示状态、时间、工作流和项目；点击进入所属工作流，工作流编辑器会自动读取最新运行。
- 浏览器缓存的本机项目目录不再显示旧运行状态；目录引用在平台权限清理时保留。摘要样式限定为 901px 及以上桌面宽度。
- 2026-11-07 完成隔离 Runtime/Vite 桌面目视复核（当前预览 1139×642）：本机项目为 0 时摘要保持可见并说明如何产生真实记录，快捷入口仍在首屏可见；没有创建项目或运行记录。复核后停止隔离服务，并确认 5173、18766 端口均已释放。
- 未运行测试、类型检查或构建。平台最近运行仍缺工作流级归属数据；手机端按用户要求暂缓。

## 2026-11-06 模板市场双来源断连空态

- 默认“全部来源”无可显示模板时，原先只渲染一条本机 Runtime 错误横幅，平台未连接状态只在左栏可见。现在统一结果区并列呈现本机与平台来源状态，并根据平台目录的真实状态说明配置、重试或无已发布模板。
- 单独浏览“本机内置”时，Runtime 未连接和本机目录为空均显示完整空态；平台目录继续使用已有服务入口与模板复用流程说明。
- 搜索不可用时，提示改为当前来源对应的原因，并将无障碍描述关联到实际显示的目录空态标题。
- 1280×720 核对全部来源/本机/平台三种状态；1440×900 核对平台目录引导。无本机 Runtime 与平台令牌，未加载或伪造模板数据。
- Vite 使用隔离 Runtime 地址 `127.0.0.1:18766`；Runtime 请求失败后显示真实不可用态，未读取用户项目数据或令牌。Vite 已停止，确认 15175/18766 端口无监听。
- 未运行测试、类型检查或构建；Runtime/平台连接后的真实模板、有数据的筛选与默认桌面包待后续复核，手机端按用户要求暂缓。

## 2026-11-06 工作台与模板市场断连状态精修

- 901×720 桌面预览发现“新建本机项目”按钮标题易被压行；增加桌面专用不换行规则，窄屏规则不变。
- 按用户确认采用统一模板浏览区。当前模板市场已有单一结果区和“全部来源 / 本机内置 / 平台目录”切换；本轮核对了各来源真实状态。
- 修正本机模板目录网络错误文案，将“项目服务”改为“本机运行时”；平台服务断连副文案会根据本机目录状态显示，不再误报本机模板已可用。页面说明本机模板由 Runtime 加载，可在平台服务断开时使用。
- 在 901×720 隔离 Vite 预览核对工作台按钮、模板平台/本机来源状态。Runtime 未启动，本机模板读取失败属预期断连状态；未读取项目数据或令牌，未调用平台 API。
- 用户确认质量报告无结果时收起六项摘要为紧凑“尚未检查”状态；有真实报告后再显示六项服务数据。该调整已在上一轮完成桌面目视复核。
- 未运行测试、类型检查或构建；默认桌面包和接入服务后的真实数据态仍待后续检查，手机端按用户要求暂缓。

## 2026-11-06 项目数据页空状态工具栏精简

- V4.0 UI-9.1 要求数据集列表支持搜索、类型/来源/质量状态/更新时间筛选以及卡片/表格切换；当前实现把全部控件无条件放入空目录，搜索与筛选都被禁用。
- 将过滤工具栏仅在存在数据集版本时显示；空列表的开发态预览只保留卡片/表格切换，以便检查两种空态。真实数据出现后，原筛选行及 V4.0 字段保留。
- 使用新建的临时空 Runtime 数据目录和隔离 Vite，在 1280×720 检查卡片与表格空态；无任务/数据文件，没有读取或修改用户项目。Vite 仅记录 App.tsx/App.css HMR 更新，没有运行测试、类型检查或构建。
- 停止 Runtime/Vite 并确认 15173、18765 端口无监听。真实项目的已填充目录、默认桌面包和手机端未复核（手机端按用户要求暂缓）。

## 2026-11-06 论文复现页平台服务入口

- 当前代码原先在缺少项目服务令牌时禁用“新建平台任务”，服务连接原因只放在悬停提示；V4.0 UI-13.1 与现有设置路由均提供“服务配置”入口。
- 改为缺少令牌时显示可操作的“连接平台服务”，导航到 `#settings/service`；令牌已配置时仍使用原平台任务创建流程，本机任务流程不变。
- 1280×720 隔离页面确认按钮清晰可见；点击后无副作用地打开服务配置页，未填写令牌、连接平台或创建任务。
- 当前预览只启动 Vite，未启动本机 Runtime，因此浏览器记录本机项目目录请求失败并回退到浏览器缓存；该错误不来自平台请求。Vite 已停止，15173 端口已释放。未运行测试、类型检查或构建；令牌已配置时的流程、默认桌面包和手机端未复核（手机端按用户要求暂缓）。

## 2026-11-06 论文复现列表空态精简

- 按 V4.0 UI-11.3 和现有桌面页面检查论文复现/实验核验任务列表；发现真实数据已加载且当前类型没有任务时，搜索、状态筛选、项目筛选仍保持可操作。
- 更新 `Reproductions`：当前类型有任务或已有筛选条件时继续显示原筛选行；真实空列表时收起筛选控件，并在空态保留“刷新任务”；筛选后没有匹配项仍显示筛选和清除操作。
- 在 1280×720 隔离 Runtime/Vite 页面目视确认空态控件与任务说明；当前预览无任务记录，未创建或修改任务。Vite 记录到 `App.tsx` 热更新。
- 已停止临时 Runtime/Vite，确认 15173、18765 端口无监听。未运行测试、类型检查或构建；含真实任务列表的筛选表现、默认桌面包及手机端未复核（手机端按用户要求暂缓）。

## 2026-10-22

- 重新核对根目录 `task.md`、项目 memory、当前安装包与源码交付路径；无工作台进程后，通过 Computer Use 启动并检查本地 0.1.36 窗口。
- 窗口截图证明上一轮细边框调整不足以完成整体目标：总览仍有明显纵向空白、页面操作分散、辅助文字和资源状态层级弱。将本轮范围扩大到完整视觉系统与五个页面。
- 读取 `redesign-existing-projects`、`planning-with-files`、`computer-use`、`web-access` 技能；访问 GitHub Primer、VS Code Workbench、Fluent 2 官方 UI 指南，相关发现写入 `findings.md`。
- Web Access Edge 预检显示 Node v26.3.0、Edge 调试端口 12957 可用；CDP Proxy 正监听 3456。代理按技能保持运行。
- 当前阶段：证据审计与视觉方向。下一步读取已展示的主窗口/主题源码原文，明确可直接落地的改造点，再实施与验收。

## 继续审计与设计

- 证据更正：第一个截图属于 `icttest` 的旧 0.1.28，而非 0.1.36。通过进程路径和 SHA-256 已区分；当前源代码包为 0.1.36。
- 直接启动工作区 0.1.36 后，Computer Use 检测到用户输入；按技能安全规则立即停止 UI 输入。当前不把该轮视为界面验收。
- 展示并审阅共享字体、顶栏、总览四步工作路径及四个数据页源代码；确定当前阶段做共享类型/颜色和总览工作流按钮，后续继续页面统一。
- 建立 `task_plan.md`、`findings.md`、`progress.md`，并创建 UI 设计规格与实现计划；所有项目文件均按当前任务目标组织。
- **错误与恢复：** `sky.launch_app` 按已登记应用路径启动 0.1.28；比对 SHA-256 后，改用本地 0.1.36 的绝对路径启动并按 Computer Use 检测停止输入。无版本猜测。

### 安全边界

- 本轮仅查看本地合成演示断连态；未输入团队令牌、连接外部服务、创建/审批提案或启动任务。
- 当前截图来自启动 `desktop/dist/ICTResearchWorkbench.exe` 后的实际窗口，不是 HTML 仿图。

## 2026-10-23 业务页层级与 0.1.37 构建

- [x] 复核当前分支、任务计划、桌面测试与 0.1.36 交付文件；确认当前 0.1.36 EXE SHA-256 为 `8AB5BFC071F059C569FAC1DB8B5C6EEFF9A4E5877B492F3A0BFE56B9EFAEF9B`，将 0.1.37 产物改为独立文件名，避免覆盖旧版。
- [x] 原有主窗口、主题与 UI 测试备份均存在；依据现有业务页实际控件，提案与运行列表补上第二层标题，质量页移除与常驻侧栏重复的“返回项目总览”。
- [x] 新增 UI 行为测试先 RED（提案标题属性尚不存在），实现后 UI 专项 24 项通过；全量桌面回归初次发现旧导航断言失效，更新为侧栏导航后单测和桌面全量 111 项通过。
- [x] `python -m compileall -q desktop\ict_desktop desktop\tests` 与 `git diff --check` 通过。
- [x] PyInstaller 与 Inno Setup 构建成功；ProductVersion 为 0.1.37。EXE SHA-256：`0556DAC446869DB3322B99C696AD0F01541E29B28C108A9017FFD9A93B264982`；安装包 SHA-256：`64090DF682A6440E46461E770FC8647498E8D4B5275AEFEEFE54C1DBB5A43FE4`。
- [x] PyInstaller 递归归档含 `ict_desktop.main_window`、`ui_theme`、`quick_start` 和 `template_dialog`；Inno 编译日志确认安装器封装 `ICTResearchWorkbench-0.1.37.exe`，安装后仍使用标准程序名。
- [x] 更新 README 的版本化构建命令与功能说明；构建日志和归档清单保存在 `desktop/build/ui-0.1.37-*.log`。
- [ ] 未安装或启动 0.1.37；五页真实窗口、向导/设置/模板弹窗、窄屏及 125% 缩放的视觉检查继续待办。当前用户截图仍属于旧 0.1.28，不能代表 0.1.37。

## 2026-10-23 底栏状态语义与 0.1.38 构建

- [x] 源码审计发现常驻的 `SYNTHETIC_ONLY` 范围说明使用警告金色，容易与真正的质量警告混淆；改用工作台青蓝信息色，保留金色给警告状态。
- [x] 新增样式行为测试先 RED（底栏仍取到 `#E4C783`），改为 `#86CDD1` 后，状态语义和 AA 对比度定向测试通过。
- [x] UI 专项 24 项、桌面全量 112 项通过；`compileall`、`git diff --check` 通过。
- [x] PyInstaller 与 Inno Setup 构建成功；安装包 ProductVersion 为 0.1.38。EXE SHA-256：`3800C5550B4D5DCA03955F53437411433C02A462253C2371248DB92CD3CF0B4F`；安装包 SHA-256：`7848998BD2D80744F3F49CC440BDCB862A649369199A9DB23C67E1816D68B631`。0.1.37 交付文件保留。
- [x] 递归归档含 `ict_desktop.main_window`、`ui_theme`、`quick_start` 和 `template_dialog`；Inno 编译日志确认封装 0.1.38 版本化 EXE。
- [x] 更新 README、任务计划、`task.md` 与 memory；构建日志和归档清单在 `desktop/build/ui-0.1.38-*.log`。
- [ ] 只读注册表仍显示旧安装 0.1.21；0.1.38 尚未安装或启动。新版五页和弹窗真实视觉、窄窗口与 125% 缩放验收仍未完成；旧 0.1.28 截图不代表新版。

## 2026-10-23 字号层级统一与 0.1.39 构建

- [x] 桌面全量回归完成：115 项通过；新增字体层级、连接错误可读字号和模板契约小标题字号测试均通过。UI 专项 26 项，模板对话框专项 4 项。
- [x] 主题新增共享字体令牌供品牌、眉题、卡片标题、状态提示、向导标题、项目标题和契约分节使用；服务连接错误信息从 9pt 调整为正文 10pt。
- [x] 错误的测试副本 `test_template_dialog_copy_20261023_typography.py` 已改为 `.py.backup`，全量发现数量回到实际测试集合；备份没有被删。
- [x] 构建 0.1.39 EXE 和 Windows 安装包；安装器 ProductVersion 为 0.1.39，递归归档含 `ict_desktop.main_window`、`ui_theme`、`quick_start`、`template_dialog`。EXE SHA-256：`D9060F4A8D59619D2928D83CC80A168F980E38FC8EA1DF4A56C7C2443ED62F6A`；安装包 SHA-256：`AEBC407FA234EB9F6851F6D7BEA035D15854B4EB0E7016AEABD4110512C7198F`。0.1.38 产物保留；构建日志为 `desktop/build/ui-0.1.39-pyinstaller.log`、`desktop/build/ui-0.1.39-installer.log`、`desktop/build/ui-0.1.39-archive-recursive.log`。
- [ ] 仍未安装/启动 0.1.39；需要真实窗口逐页检查、窄窗口和 125% 缩放验收。当前注册表仍记录 0.1.21，不能以源码或旧 0.1.28 截图代替新版视觉证据。

## 2026-10-23 总览信息层级与 0.1.40 构建

- [x] 旧版截图与当前源码审计确认总览仍有多块等权矩形面板；项目身份和工作路径调整为连续画布，资源目录改为唯一有边界工作面。
- [x] 服务断连提示采用中性表面和青蓝标记，新增“检查本机 CSV”直达动作；单测证明不用团队令牌也能导航到本机预检。
- [x] 两项新 UI 测试先 RED 后 GREEN；桌面全量 117 项通过，其中 UI 专项 28 项。`compileall` 和 `git diff --check` 通过。
- [x] PyInstaller、Inno Setup 构建成功；安装包 ProductVersion 为 0.1.40。EXE SHA-256：`5095BD52CB4E919D9EF7B33AFE2A2C2182E933AEE99D85651F87A6C507AF6C82`；安装包 SHA-256：`E518FA9D4A0729232E3705791E28FCFCEEF8A337F36C25679BFD637A2312C09A`。归档包含主窗口、主题、快速开始和模板说明模块；0.1.39 仍在。
- [ ] 当前没有工作台进程，注册表仍记录 0.1.21；0.1.40 未安装/启动。五页、弹窗、窄窗口与 125% 缩放实机验收待继续。

## 2026-10-23 业务详情字段化与 0.1.41 预览包

- [x] 修复团队项目选中详情仍调用 `Label.configure(text=...)` 的 Tk 回调错误，并为项目、提案、运行详情统一成可复制的标签/值文本区。
- [x] 详情内部滚动优先于整页滚动；许可状态用中性色、运行状态单列显示，项目读取状态与科研就绪核验说明保持明确。
- [x] 两项新增 UI 测试按 RED→GREEN 完成；5 项定向检查通过，桌面全量 119 项通过。
- [x] PyInstaller、Inno Setup 构建与递归归档核验通过；安装器 ProductVersion 为 0.1.41，归档含主窗口、主题、快速开始和模板说明模块。EXE SHA-256：`9407B0A3BCD926B53DAA68D7BA7F32A0219C8DDD660B44467767DAA6348A3609`；安装包 SHA-256：`1831683E0B8B5B40B23EB197301A75ACC00053DF98A3223CA8CD74D0F10A29CB`。完整构建日志在 `desktop/build/ui-0.1.41-*.log`。
- [ ] 注册表仍显示 0.1.21，0.1.41 尚未安装/启动；真实新版窗口与 125% 缩放验收待继续。

## 2026-10-23 实际窗口验收修正与 0.1.42

- [x] 0.1.41 预览检查五页、快速开始、服务设置；记录断连总览首屏溢出、质量页内容过短造成的纵向空白、提案/运行页操作位于首屏下方等问题。未连接团队或执行有副作用操作。
- [x] 四项新增 UI 回归用例先 RED 后 GREEN；桌面全量 123 项通过。
- [x] 源码已调整质量页内容高度、总览首屏资源间距和列表默认行数；Windows DWM 标题栏设置结果已提升到 INFO/WARN 诊断。
- [x] `compileall`、`git diff --check`、0.1.42 PyInstaller/Inno Setup 构建与递归归档核验通过；安装包 ProductVersion 为 0.1.42。EXE SHA-256：`3D914C82F5DBE8AD6348C38E8387D0D574A55948745BA666C58C02A52524D58D`；安装包 SHA-256：`ED8C31B026492F2E8ECA62D06C35B9894F3A4919B73395840B529AB7BC8B309F`。
- [ ] 启动新编译的 0.1.42 需要遵循 Windows 操作技能的动作时确认；之后复核布局和标题栏日志。
- [ ] 窄窗口及 125% DPI 真实窗口验收仍待完成；安装版登记继续是 0.1.21。

## 2026-10-23 工作台整体设计改版方向

- [x] 按用户最新反馈重新审视 0.1.41 实际画面和当前源码；保留深石墨主题，确认现有第一轮可用性调整尚未建立鲜明的科研软件视觉识别。
- [x] 整体范围明确为五个业务页面、快速开始、服务设置与模板说明弹窗；API、权限、令牌只驻内存、合成数据标识保持不变。
- [x] 三种深色结构对比稿已通过本地服务器提供，HTTP 200；服务器进程仍运行，但预览事件目录无选择记录，Codex 浏览器打开状态为 queued。
- [ ] 推荐“科研档案台 + 协作工位”混合结构，设计审批待用户回复；批准后写规格并进入完整实现。

## 2026-10-23 专业界面改版规格与实施计划

- 用户明确希望达到成熟企业级科研软件设计，并要求继续处理剩余页面。本轮将其“继续弄其他部分”理解为继续执行此前专业改版委托，不要求其再从视觉稿中点选方向。
- 已创建 `docs/superpowers/specs/2026-10-23-research-workbench-premium-redesign-design.md` 与 `docs/superpowers/plans/2026-10-23-research-workbench-premium-redesign.md`；范围含五个页面、快速开始、服务设置、模板阅读器。
- 实施路线：主题和共享框架 → 总览与数据质量 → 团队/提案/运行工作区 → 弹窗 → 桌面回归与 Windows 包 → 经动作时确认后进行新版实机验收。
- 目前未检测到运行中的工作台窗口，因此源码结构可继续改进，但不能把代码/测试结果冒充新版实机视觉验收。
- 实施中的重点风险仍为业务边界：不改 API、角色、令牌仅驻内存、只读模板契约、批准条件、合成数据标识；医疗模块继续暂缓。

## 2026-10-23 0.1.43 页面结构实现与构建

- [x] 新增列表/检查器职责差异、团队访问条分层、提案审核与运行报告固定底栏、青蓝区块眉题四项 UI 约束；新测试均先 RED 后 GREEN。
- [x] UI 专项 38 项通过；桌面全量 127 项通过；`compileall`、源码副本差异空白检查和 `git diff --check` 通过（Git 仅报告既有 LF/CRLF 转换提示）。
- [x] PyInstaller 与 Inno Setup 构建 0.1.43 成功；ProductVersion `0.1.43`，递归归档包含 `ict_desktop.main_window`、`ui_theme`、`quick_start` 和 `template_dialog`。
- [ ] CUA 当前没有工作台应用窗口；新版真实窗口、窄窗口和 125% DPI 目视验收仍待动作时确认。


## 2026-10-23 0.1.44 顶栏层级与桌面回归修复

- 面包屑改为固定工作区“科研工作区”，不再重复当前页标题；五个主页面标题旁显示 01–05 页码，清楚区分工作区上下文与页面位置。
- 新增导航回归断言先 RED 后 GREEN；UI 专项与其他检查已覆盖新页码/上下文。
- 全桌面回归首跑在快速开始测试期间以 `Tcl_AsyncDelete` 崩溃退出，退出码 `-2147483645`。通过 faulthandler 复现发现后台健康线程结束时触发垃圾回收，析构了此前测试遗留的 Tk 图片/Tcl 解释器。单测隔离可过；主窗口测试缺少统一 teardown。
- 已给主窗口测试增加主线程统一销毁、清空根窗口引用并 `gc.collect()`；完整桌面回归 128 项通过，83.921 秒，无 Tk 跨线程析构错误。
- [x] `compileall`、`git diff --check` 和源码/文档副本差异空白检查通过；Git 仅报告既有 LF/CRLF 转换提示。PyInstaller、Inno Setup 与递归归档通过，ProductVersion 为 0.1.44。
- [x] EXE SHA-256：`F7FE105097018EEDD78F6656FD065782B6170A17F389CAF943BF825E9BC8A3BC`；安装包 SHA-256：`1B58CFC46D63ABB83AF914B8D59AE31FD6A314696D0B8D573B82B4E7201D0C9D`。归档包含主窗口、主题、快速开始与模板说明模块。
- [ ] 真实窗口逐页、窄屏及 125% DPI 检查仍需在动作时确认后启动 0.1.44。


## 2026-10-23 连接状态视觉修正：0.1.45

- 用户旧版截图中顶栏“服务连接：不可用”以整块红底显示，像审核失败；源码仍保留该权重。将其作为持续状态改为低权重中性文字，真正操作错误继续显示在页面错误说明中。
- 新增 `test_unavailable_service_uses_subdued_topbar_status`；先 RED（仍为 `Connection.Error.TLabel`），实现后 GREEN。
- 0.1.45 桌面全量测试与 Windows 构建待运行。


## 2026-10-23 顶栏连接状态修正与 0.1.45 构建

- 0.1.45 将顶栏“服务连接：不可用”改成中性弱提示，避免连接状态被视觉误读为审核失败；页面内实际操作错误仍保留独立反馈。新增测试 RED→GREEN。
- 桌面全量 129 项通过（83.049 秒），`compileall`、`git diff --check` 和源码副本空白核验通过。
- EXE SHA-256：`3A74DF1583026E45AE3B14A43A335F8542978D3A57AA891D66EB49E66330A584`；安装包 ProductVersion `0.1.45`，SHA-256：`5BACBA6040475B3F6FBAA55084D6FC5B928A7E36BDD4B934942C8132F5B88CC3`。递归归档包含主窗口、主题、快速开始和模板说明。
- 实机五页/三弹窗、窄屏和 125% DPI 检查仍未完成；当前 CUA 原生应用清单为空，须由用户提供新版窗口画面。
## 2026-10-23 字段标签优化与 0.1.46 构建

- 快速开始的服务地址与团队访问令牌、团队项目访问区的令牌、服务设置地址均添加了可见字段标签；标签样式使用共享主题字号与对应表面底色。
- 回归测试先 RED 后 GREEN；快速开始 9 项、两个 UI 定向检查通过。追加字段标签的实际 ttk 字体/底色 AA 对比度检查后，桌面全量 131 项通过（108.424 秒），详细输出：`desktop/build/ui-0.1.46-tests.log`。
- `compileall`、`git diff --check`、PyInstaller、Inno Setup 和递归归档核验通过；安装器 ProductVersion `0.1.46`。
- EXE SHA-256 `7C8C5100B938B0CD9F4BDAF8E82E98722479FD6B84477E5B3E7AF90D6023745F`；安装包 SHA-256 `9EC3E176812C2FC7376FCEBFB19FD91957608D3F1F9FA58731AF985578EBB509`。
- 实机逐页、弹窗、窄屏和 125% DPI 检查仍待窗口画面；本轮未启动新程序。


## 2026-10-23 0.1.46 实机首轮视觉验收

- 经用户确认，启动工作区内 0.1.46 并检查五个页面：项目总览、数据质量、团队项目、智能体提案、运行记录。当前视口均可正常导航，未见明显裁切。
- 检查快速开始第 1 步和服务设置弹窗；未保存或连接服务，未输入团队令牌，未审批提案或启动任务。服务连接不可用，因此团队项目、提案和运行数据为空。
- 模板说明未能在未连接项目、未选择提案时打开。Computer Use 检测到新用户输入并报告窗口最小化后，停止 UI 操作且没有重新激活窗口。
- 未完成窄窗口、1200×800 / 1366×768、125% DPI 和已连接状态下模板弹窗验收；这些仍是设计改版的未完成项。


## 2026-10-24 0.1.47 焦点与空状态视觉优化

- 截图中导航焦点描边呈金色，与矿物青蓝主题及“金色用于真实警告”的语义冲突；将 8 种交互样式的键盘焦点色统一为青蓝，并保留 3:1 以上焦点对比度。
- 项目目录、AgentArts 提案队列、运行记录空状态增加各自的线性对象标记；不插入假数据、指标或新操作。
- 两项 TDD 测试先 RED 后 GREEN；全桌面 133 项通过（保存日志：`desktop/build/ui-0.1.47-tests.log`），`compileall` 通过。
- PyInstaller、Inno Setup 成功构建；EXE SHA-256 `7A702E02D36A90601347F9BE240DB4DCD8D64522308C6A763BEF6CF0C7DA4F18`，安装包 ProductVersion `0.1.47`、SHA-256 `7368D0839447DE5759282BDFDB03B849E7A2EB226C6EB4822F084BB23D80D495`。归档已核验主窗口、主题、快速开始、模板说明模块。
- 新版需在动作时确认后做真实窗口复验；窄窗口、常用尺寸、125% DPI 和已连接状态下模板说明仍待验收。

## 2026-10-24 0.1.48 窄屏工作区重排

- 质量、团队、提案和运行页工作区在 900px 以下切换为上下分区，宽屏恢复左右分栏，继续支持拖动分隔条。
- 质量页按两个面板的实际请求高度更新滚动区域；在 1000×720 和 1366×768 检查时，两栏均完整可见，质量页长内容仍可滚动。
- UI 专项 46 项、桌面全量 135 项通过；`compileall`、PyInstaller、Inno Setup 和递归归档核验通过。EXE/安装包 SHA-256：`B4F829E55C35F0F8D385CA32FE163069A2834D92E31016CE9729AFB2F1BD0DD1` / `696A112769EC0C1DDED0D2819214523FF00839E40D4C4F1C79955F541F6F67FC`。
- 新版尚未启动；1200×800、125% DPI、五页实机截图和已连接状态模板说明仍未验收，等待对 0.1.48 的动作时确认。

## 2026-10-24 0.1.49 中性石墨与矿物青绿主题

- 色板向中性石墨和低饱和矿物青绿收敛，保留现有深色方向和状态语义；14 组关键文字/状态色对比度最低 5.73:1。
- 色板回归先 RED 后 GREEN；UI 专项 47 项、桌面全量 136 项通过，compileall 通过。
- PyInstaller/Inno Setup/归档核验通过。EXE/安装包 SHA-256：`19C70F005E6D94801C6B1204739DE8D1F30C2D1C1B23677A19673D415E215888` / `E2497342EBDA4B618EED4A07850F9A52218CB40F87532681C124CF6869BDBA60`。
- 0.1.49 尚未启动；真实窗口、常用/窄视口、125% DPI 和已连接状态模板说明仍待动作时确认。

## 2026-10-24 0.1.46 用户授权复查

- 经用户明确授权，从工作区绝对路径启动 `desktop/dist/ICTResearchWorkbench-0.1.46.exe`；在 1802×1218 桌面视口逐页截图复核项目总览、数据质量、团队项目、智能体提案和运行记录，五页均可切换，未见明显裁切。
- 查看快速开始第 1/4 步和服务设置弹窗。只读检查地址字段和提示，未输入或保存任何信息，未连接服务、未输入令牌。
- 从总览打开“查看模板提案”后进入提案页；无团队连接且未选中提案时，固定模板说明无法打开。没有审批提案或启动任务。
- 此次仅检查 0.1.46。窄窗口、常用尺寸和 125% DPI 未测；0.1.49 仍未启动，需另行授权后才能检查。
## 2026-10-24 0.1.50 列表滚动条按需显示

- 依据 0.1.46 真实截图和当前主窗口代码，修复团队项目、提案和运行表格总是占据一行横向滚动条的问题；默认列宽收窄，完整字段继续由右侧检查器展示。
- 横向滚动条仅在 Treeview 的可视范围确有溢出时显示；监听横向视图变化和窗口尺寸变化，在 Tk 布局稳定后更新；缩窄窗口或长列仍可横向查看。
- 新增行为测试先 RED 后 GREEN，覆盖三表宽屏隐藏、实际溢出显示和恢复后隐藏。UI 专项 48 项通过（74.134 秒）；桌面全量 137 项通过（124.247 秒）；`compileall` 与 `git diff --check` 通过。
- PyInstaller 与 Inno Setup 构建成功，递归 CArchive 含 `ict_desktop.main_window`、`ui_theme`、`quick_start` 和 `template_dialog`。EXE SHA-256 `68B80C33DECC8C03C367AD6343E4350AFC9DA5F946396D23E56B565EFCE4D88D`；安装包 ProductVersion `0.1.50`、SHA-256 `EDF8F687DB7ACDE1DA736AE9BAED7DB4621116DA9C9358A54DFF09D780A44890`。构建日志位于 `desktop/build/ui-0.1.50-*.log`。
- 0.1.50 尚未启动；真实窗口截图、常用/窄视口和 125% DPI 验收待动作时确认。未输入令牌、未连接服务、未审批提案、未启动任务。
## 2026-10-24 0.1.46 再次实机截图核对

- 按本轮明确授权检查工作区内正在运行的 0.1.46；在 1802×1218 依次查看项目总览、数据质量、团队项目、智能体提案和运行记录，并查看快速开始第 1/4 步、服务设置弹窗。
- 五个页面均正常切换；断连状态下团队/提案/运行显示说明性空状态。提案与运行列表横向滚动条可见；质量页表单按内容高度排布，下面保留较多背景留白。快速开始与设置弹窗均未保存任何值。
- 无令牌输入、服务连接、审批、任务启动或报告导出。模板说明因未连接团队账号且无选中提案，本次没有打开。
- 本轮只授权 0.1.46；0.1.50 安装包尚未启动，常用/窄视口与 125% DPI 仍待新版截图验收。

## 2026-10-24 0.1.51 原生深色标题栏映射时机

- 应用日志与 0.1.46 实机截图共同暴露标题栏仍为浅色：四项 `DwmSetWindowAttribute` 都在 `mapped=False` 时返回成功，但视觉状态未应用。微软文档确认属性用于标准顶层窗口框架。
- 新增测试先 RED：窗口未映射时断言 DWM 调用数为 0，旧实现实际调用 4 次；修复后窗口映射后经 `after_idle` 执行一次性 DWM 设置。标题/边框/文字色与 API 属性值保持原样。
- 两项标题栏定向测试通过；桌面全量 138 项通过（122.181 秒），日志 `desktop/build/ui-0.1.51-tests.log`；`compileall` 通过。
- PyInstaller、Inno Setup 与递归 CArchive 检查通过，包内含 `main_window`、`ui_theme`、`quick_start`、`template_dialog`。EXE SHA-256 `4328E5AB4CE4F6CEF20B20E73BFF2945169B878EA98608EDC5A7A7AB48256750`；安装包 ProductVersion `0.1.51`、SHA-256 `FB9F8CCFC9ABBD620A2FCDBA1A9B3B71CE729DB14EDD6A8DC86D3D60DDC6335C`。
- 0.1.51 尚未启动；真实窗口、窄视口、常见尺寸和 125% DPI 验收待确认。

## 2026-10-24 0.1.52 队列与检查器宽度

- 将团队项目、提案和运行页的初始列表/检查器分栏从 40:60 调整为 5:4；列表承担队列扫描，检查器仍保留约 44% 宽度。质量页显式使用 1:1，不受默认比例影响。
- TDD：新增队列比例回归，先 RED（旧配置 0.4，预期 5/9），再 GREEN；UI 专项 50 项通过，桌面全量 139 项通过（93.812 秒）。
- compileall、PyInstaller、Inno Setup 和递归 CArchive 模块检查通过；日志位于 `desktop/build/ui-0.1.52-*.log`。
- EXE SHA-256 `8980B32688D71E66307A791D35D70C1C639A35A6B867A118DA2074ECCB0BA6E7`；安装包 SHA-256 `B0B6FC740D90E569BD674D596074660386BF9AE7A539261CCB6F6E2AD5CCB6E9`，ProductVersion `0.1.52`。新包尚未启动，真实窗口验收待确认。

## 2026-10-24 0.1.53 响应式分隔条稳定性与用户比例保留

- 实机几何测试发现：从 1000×720 窄工作区切到 1366×768 后，质量页的水平分栏实际约为 45:55，偏离预期的均分；用户自定义比例跨越窄宽断点时也被还原为默认 5:4。
- TDD 先 RED：真实几何断言复现 0.45≠0.50；比例保留断言复现 0.555≠0.67。第一次按每次 `<Configure>` 立即刷新导致 Tk 布局回调忙循环，已终止本轮测试进程并改为只在方向变化时 120ms 防抖；最终两项测试均通过。
- 鼠标释放时保存用户的横/竖向分栏比例；跨断点返回原方向后恢复。窗口尺寸稳定后再按目标比例定位分隔条，避免按中间宽度定位。
- UI 专项 51 项、桌面全量 140 项通过（133.102 秒）；compileall、PyInstaller、Inno Setup、递归 CArchive 检查通过。日志 `desktop/build/ui-0.1.53-*.log`。
- EXE SHA-256 `D3DEAC979517D595DDE4C0E4AB58816D7C6D3B12351D67D66AE30CB0A66B3CF2`；安装包 ProductVersion `0.1.53`、SHA-256 `5604C2032823E8FA8E83A47F6CC78189B7262761B1A96ECB67F42F98FEC44C6E`。真实窗口验收仍待确认。

### 0.1.53 补充视口验证

- 将窄/常用/宽工作区几何断言覆盖为 1000×720、1200×800、1366×768；1200×800 和 1366×768 下核对四个工作区实际分隔比例，1000×720 下核对纵向堆叠。
- 定向测试 1 项通过（13.234 秒），日志 `desktop/build/ui-0.1.53-viewport-tests.log`。这次只扩充测试，未改程序代码或重建安装包。

## 2026-11-02 画布工作流闭环启动

- 按 V4.0 B1/B2/B3 与用户 11-08 截止目标建立活动计划；本轮目标为真实执行与本机 CSV 离线检查，不把保存/契约校验误报为运行闭环。
- 核实现有 React/Vite 主线、workflow draft/version/contract APIs、`executable=false`、四个 executor_binding 为空、runs API 只覆盖 synthetic smoke；旧 Tk `inspect_manifest()` 可复用但未接 React。
- 发现 `findings.md` 开头仍称 Tk 为当前产品主线，已修正为 React/V4.0，并记录本轮执行缺口。
- 本轮尚未修改产品代码；下一步检查当前 WorkflowEditor 的 Run 按钮、API 配置、数据库模型/migration、Worker dispatch 和测试架构，然后按 TDD 从 B1 写第一个失败用例。

### 画布编辑器/API 现状核对
- `frontend/src/App.tsx` 已连保存、版本、历史、撤销/重做和校验；Run 按钮仍 disabled，明确提示 executor/DAG service 未接入。
- `frontend/src/api/workflows.ts` 只提供 workflow catalog/CRUD/validation/version API，没有 workflow run API；`WorkflowValidation` 类型将 `executable` 固定为 false。
- `backend/app/api/v1/runs.py` 只接受合成 `research-smoke-v1` Run DTO，不可复用于画布 DAG。
- 当前源代码有旧 Tk 通用 CSV 检查器；本机离线执行仍需新 runtime/持久状态边界。

### 路径核对错误
- 误查 `backend/app/config.py`、`backend/tests/test_workflows.py`、`backend/tests/conftest.py`，当前仓库不存在这些路径；没有文件被修改。下一步改用目录清单定位实际设置和工作流测试文件。

### 持久化/测试边界核对

- `Workflow`/`WorkflowVersion` 独立存储；现有 `Run`/`RunEvent` 是批准后 synthetic proposal 的固定链路，需新增 workflow-run 与 node-run 表，避免破坏兼容数据。
- backend 当前以 `unittest` + `ASGITransport` + 临时 SQLite 验证 API；未发现 workflow execution tests，后续新增专用测试文件和 Alembic 0007 migration。
- 已按文件清单定位之前误判不存在的 workflow APIs/tests；测试目录实际没有 workflow-run 覆盖。

## 2026-11-02 Workflow Compiler 与 Ready Queue 首轮实现

- 用户本轮要求以 P0 前五项优先：编译独立 ExecutionPlan、类型化 Schema、输出闭包、Ready Queue/依赖阻塞、异步状态；再接本机 CSV，补基础缓存/资源/worker 监督。ComfyUI 源码用于参考适配，不将其 Prompt/编辑器 JSON 当 ICT 格式。
- 编译器测试先 RED（模块不存在）；实现 `backend/app/services/workflow_execution.py` 后通过：输出祖先闭包、稳定拓扑序、画布坐标不影响 SHA-256、未知目标拒绝、所选环路拒绝、目标外无效组件裁剪。
- 新增 `backend/app/services/workflow_scheduler.py`，支持有界并发 ready queue、`WAITING/READY/RUNNING/WAITING_EXTERNAL/SUCCEEDED/FAILED/BLOCKED/CANCELLED` 等状态、异步外部等待、失败下游阻断与独立分支继续。
- 调度器测试先 RED（模块不存在）后 GREEN，定向用例通过；故障路径日志带节点 ID，API 错误码不包含异常原文。
- 尚未把运行状态写入数据库、尚无工作流运行 API、前端 Run 仍禁用、本机 CSV executor 未连接；本次属于 B1 引擎骨架，不是最终闭环。
- 调度器定向测试暴露遗漏 `heapq` 导入；定位后修正并重跑通过。未调用生产服务或修改数据。
### 2026-11-02 本机工作流运行与电脑端接入

- 接入独立本机 runtime 与持久化运行记录、节点事件和 ArtifactHandle；开发启动脚本自动启动/复用端口 8767 runtime，与平台 8765、MCP 8766 分离。
- 编辑器支持本机缓存工作流入口、CSV 文件导入、本机输出目标运行与取消，并显示运行历史、节点事件和产物引用；预检报告显式声明“非科研结果”。
- 离线编辑草稿与平台同步状态分离；检测到平台有新修订时保留本机草稿并提示冲突，不自动覆盖平台。
- 根 README 与 React README 已更新为当前执行能力与开发/生产边界。
- 追加 B3 基础版：确定性本机 Input Signature 缓存（内容哈希/组件摘要/版本/参数/上游产物/运行环境）、本机资源请求准入与活动运行并发上限、后台 task 异常记录及重启恢复。
- `npm run build`、Python `py_compile`、Node `--check`、`git diff --check` 均通过；Vite 仅提示 JS chunk 约 675 kB，超过 500 kB 建议值。
- 本轮未运行自动化测试，也未做浏览器断网端到端验收。当前 11/08 演示闭环代码接入进度约 80%（粗略按验收子项估算，不是全产品完成率）。
- 后续补入 `npm run preview:local`，供生产构建预览配套本机 runtime；检查启动代码时发现 Uvicorn `--factory` 调用缺少 `root` 参数，已让 runtime factory 默认读取本机数据目录，并把 CORS 动态端口匹配限制到 loopback origin。最终 `npm run build`、Python `py_compile`、Node `--check`、`git diff --check` 均通过；没有运行测试套件或启动浏览器端到端流程。
- 后续启动实际 runtime 时验证了 factory 修复：Uvicorn 完成 application startup，`8767/health` 返回 200，`5173` 的 CORS preflight 通过。用隔离临时目录做手工 API 流程：CSV 导入、工作流草稿保存、首次 Run `SUCCEEDED`、第二次 Run 的 NodeRun `CACHED`、历史 2 条；产物 JSON 的标签为“结构预检，非科研结果”，产物来源含首次 run ID。
- 现有浏览器 UI server `5173` 保持运行，正式本机 runtime `8767` 保持运行；隔离验证 runtime 已关闭。临时目录 `%TEMP%\ICT-local-runtime-e2e-20261102` 尚未清理：递归删除命令被自动安全策略拒绝，未尝试绕过。
- 继续补齐产物可读性：新增只读取已登记 `application/json` 且类型为 `csv_manifest_structural_preflight` 的 API；校验内容 SHA-256、2 MiB 上限和 `research_result=false`。电脑端“产物”面板展示结构状态、行数、字段、拆分计数及前 12 项检查问题。用已保存的隔离运行记录实际读取该 API，返回内容符合报告标签与非科研结果边界。
- 仍待浏览器画布上的实际交互验收；以上是 runtime/API 纵向切片证据，不等同于浏览器端到端验收。

## 2026-11-02 ComfyUI 源码适配复核

- 对照本机 ComfyUI v0.43.0：`comfy_execution/graph.py` 的 ready/block 计数、`comfy_execution/caching.py` 的递归祖先输入签名、`execution.py` 的部分输出验证，以及 `node_typing.py` 的类型化端口契约。
- ICT 已以自有数据结构接入对应首版机制：输出目标祖先裁剪、静态 ready queue/依赖阻塞、异步外部等待、typed schema、输入内容哈希缓存和 ArtifactHandle。未复制 ComfyUI 源码。
- 当时识别的缺口（已由下方后续记录补齐）：permission/dependency 尚未形成逐节点授权与安装版本解析；`network/platform` executor 未接入；资源准入不等于 OS 硬限额；后台监督在同一 runtime 进程内。
- ComfyUI `LICENSE` 标注 GPL-3.0，ICT 根目录没有 `LICENSE`/`COPYING`；没有将 GPL 源文件拷入 ICT。本轮更新统一方案、任务、进度、发现和 memory 记录，不改产品代码，不运行测试。

## 2026-11-02 本机执行前能力校验与闭环验收

- 本机 runtime 现在按节点检查 execution target、登记执行器绑定、权限能力、依赖 ID/精确版本、资源请求与输入产物授权状态。CSV 预检依赖版本从 ICT 自有 `manifest_quality.py` 的版本契约读取，并和组件 Schema 的要求比对。
- 组件目录返回 `execution_blockers`，电脑端组件列表/属性面板将依赖、权限和执行目标问题说明给用户。缺少 `network/platform` executor 时按节点阻断；独立本机分支可继续。
- 复用 ICT 自有 `inspect_manifest()` 和版本化组件 Schema；ComfyUI 继续作为调度/缓存机制参照，未复制 GPL-3.0 源码。
- `frontend` 目录 `npm run build` 通过（178 modules；JS 680.33 kB、CSS 236.94 kB）；Vite 保留 JS chunk 超过 500 kB 的提示。相关 Python 文件 `py_compile` 通过，`git diff --check` 通过（只有 LF→CRLF 提示）。
- 隔离 ASGI 手工验收：CSV 组件可运行；首跑 `SUCCEEDED`、再次运行 `CACHED`，两条运行记录均保留；混合图为 `PARTIALLY_SUCCEEDED`，CSV 分支 `CACHED`、平台节点 `BLOCKED`；错误依赖版本返回 `COMPONENT_DEPENDENCY_UNAVAILABLE`，权限超出返回 `LOCAL_PERMISSION_UNAVAILABLE`。
- 本轮未运行自动化测试套件。实际浏览器画布端到端、平台断开时的桌面交互、Windows 生产 sidecar、network/platform executor 和其他本机组件仍未验收/接入；当前闭环代码接入约 85%（阶段估算）。

### 2026-11-02 真实浏览器离线闭环验收

- 使用现有 5173 Vite 页面与 Edge 1440×900。浏览器上下文只注入隔离的缓存项目/工作流；本机 runtime API 由同进程 ASGI app 提供，SQLite 和产物目录在临时目录中，未写入用户正在运行的 8767 runtime。
- 平台项目 API 保持不可用；页面从缓存恢复工作流，选择测试 CSV 后完成本机导入、本机草稿保存、提交运行、状态轮询至“成功”，并在“产物”面板读取结构摘要：状态“通过”、1 行、字段与 train 拆分计数正确，报告注明“非科研结果”。
- 浏览器返回 HTTP 200、无 JavaScript 页面异常；项目详情请求的 `ERR_ABORTED` 是平台 API 不可用时的预期请求失败，独立本机运行链路成功。完整画面保存在 `artifacts/workflow-offline-browser-e2e-20261102.png`。
- 本验收证明已有缓存的项目/工作流可在平台 API 不可用时使用本机 CSV 执行器；尚不证明已连接会话中途断网、本机草稿与平台新修订冲突处理、生产 sidecar 或其他执行器能力。
- 按最新 P0 清单对齐 V4.0：在基础缓存、资源准入和任务监督阶段纳入 `local / network / platform` 最小执行路由；平台不可用不阻断纯本机分支，恢复连接后显式同步并保留 revision 冲突保护。独立 Worker 进程池、GPU 动态调度和多层共享缓存仍后置。
- 冲突保护的浏览器验收本轮未完成：隔离 Edge 脚本先后遇到 init-script 参数错误、重复导航按钮定位和桌面 profile 按钮不可见，最终未触达工作流逻辑；未观察到产品通过或失败。根据工作区规则停止重复尝试，该项继续列为待验收。
- 2026-11-02 冲突对照 UI 已接入编辑器主区：本机草稿与平台当前修订并列显示名称、修订号、不可变版本、节点/连线数及节点标题，并提供平台版本历史入口；不自动覆盖或合并。本轮 jsdom 集成验收因测试环境缺少 `window.matchMedia` 未触发产品断言，真实平台 revision 冲突仍待浏览器验收。
- 前端 `npm run build` 通过：178 modules，CSS 240.24 kB、JS 683.19 kB；Vite 保留 JS chunk 超过 500 kB 的提示。本轮尝试的 jsdom 冲突用例因缺少 `window.matchMedia` 在产品断言前退出，自动化测试验收仍未完成。

## 2026-11-02 混合执行目标的本机运行提示

- 源码核对确认，编辑器本机运行会先把当前画布写入独立本机草稿，再向本机 runtime 提交所选输出目标；运行请求不经过平台 API。
- 编辑器现在只统计所选目标祖先闭包中没有本机执行器的节点。混合图存在本机可运行节点时，运行前说明这些节点及依赖它们的下游会被阻断，未依赖它们的本机分支可继续；无关分支不影响提示。
- 当前 `network/platform` 执行器仍未接入；此提示用于解释现有部分运行行为，不代表增加了相关执行能力。
- `frontend` 目录 `npm run build` 通过：178 modules，CSS 240.95 kB、JS 683.91 kB。Vite 保留 JS chunk 大于 500 kB 的提示。`git diff --check` 退出码为 0；未运行自动化测试，未做新的浏览器交互验收。

## 2026-11-02 Windows 便携式工作流桌面包

- 新增 `desktop/workflow_shell.py`：生产 React UI 与本机 FastAPI runtime 使用同一 loopback origin；运行数据、日志和 Edge profile 位于 `%LOCALAPPDATA%\\ICT\\WorkflowWorkbench`，启动器提供单实例保护、端口选择及诊断模式。
- 新增 `desktop/ICTWorkflowWorkbench.spec` 与 `desktop/build_workflow_app.ps1`，封装前端 dist、自有 CSV 检查器和实现摘要源文件。构建产物 `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe`，23,778,661 bytes；SHA-256 `7B9FF0F611FDF155ED1CA3D4FC9FAAAA70346EA6D91C65C8BCF96A9B4F3DC01C`。
- `npm run build` 和 PyInstaller 6.22.3 构建成功；Vite 提示主 JS chunk 超过 500 kB，约 684 kB。归档核对确认 `frontend/dist/index.html`、JS/CSS 与 ICT CSV checker/executor 实现按 runtime 路径打包。
- 隔离 smoke 在 `%TEMP%` 数据目录与端口 18767 启动产物：`/health` 为 local 且 `frontend_served=true`，首页及 JS/CSS 为 HTTP 200，本机会话创建成功，`ict.data.csv_manifest_preflight.execution_available=true`。没有打开 Edge，也没有调用平台或外网服务。
- PyInstaller onefile 会由 bootloader 启动解包子进程；直接终止外层 smoke PID 会留下子进程。已核对子进程路径与本次 EXE 一致后结束它，确认 18767 已释放。正常桌面路径中，Edge 进程退出后 launcher 的 `finally` 会关闭 Uvicorn；本轮未实开 Edge 窗口验证该路径。
- 本轮未构建 Inno Setup 安装器，未做正常 Edge app 窗口视觉/交互验收；`network/platform` executor、已连接会话中途断网和真实 revision 冲突交互仍未完成。未运行自动化测试套件。

## 2026-11-02 固定端点 Crossref network executor

- `workflow_components.py` 登记 `ict.paper.crossref_metadata`：只访问固定 `https://api.crossref.org/works/{DOI}`，声明 network 权限、`httpx@0.28.1`、20 秒超时和 CPU/内存上限；无任意 URL、凭据输入、文件上传或自动重试。
- 本机 runtime 验证网络 executor binding、权限和精确依赖版本，独立网络资源准入上限为 30 秒/250 mCPU/128 MB/GPU 0；请求并发限制为 1。用户逐次确认后才发请求，scheduler 持久化既有 `WAITING_EXTERNAL` 状态和节点结果。
- 只把 Crossref 白名单书目信息保存为 `public_metadata` ArtifactHandle；报告读取再校验登记 handle、SHA-256、大小、类型、来源域名与 DOI，仅返回有限字段并明确标记非科研结果。
- React 画布组件目录展示该网络节点；运行前按本次选择的输出祖先闭包提示并请求确认；产物面板显示 DOI、题名、作者、出版信息、来源和核验说明。
- Python `compileall`、`npm run build`、PyInstaller 6.22.3 便携 EXE 均通过。最终 EXE 为 24,223,622 bytes，SHA-256 `4D670F33CE7FD6E83B6ECDC7DB36A196F0DF029C61AD20647F935FA14E222D40`；归档含网络 adapter 源文件、httpx 模块和版本元数据。最终 JS chunk 688.65 kB，Vite 保留超过 500 kB 的建议提示。
- 隔离 EXE smoke：health `ok`、首页 HTTP 200、Crossref 与 CSV 组件 `execution_available=true`、依赖为 `httpx@0.28.1`；没有发送 DOI 请求或调用平台 API。根 README 与 React README 已同步执行边界。未运行自动化测试，也未实际请求 live Crossref；Edge app 交互验收、平台 Worker adapter、连接中途断网及 revision 冲突验收仍待办。

## 2026-11-02 ComfyUI 对照后的浏览器验收准备

- 复核 ComfyUI `graph.py` Ready Queue/外部等待与 `node_typing.py` 类型契约；ICT 已有自有实现。因源码包许可证为 GPL-3.0，当前只按机制适配，没有复制源码。
- 系统 Python 未预装 Playwright；将 Playwright 1.64.1 安装到临时目录 `ict_workflow_acceptance_pw_20261102`，项目依赖未改动。pip 输出 OpenTelemetry 版本约束提示，但临时目标安装成功。
- 隔离 Edge 首次加载 `http://127.0.0.1:5173/#workbench`，等待 networkidle 后检查 DOM 与页面异常；HTTP 200、无 pageerror。截图保存在系统 TEMP 的 `ict_workflow_recon_20261102.png`，可视内容为真实空项目态，没有伪造数据。
- 下一步使用路由拦截模拟平台连接/修订响应，并将 local runtime 路由到隔离临时目录；不连接现有 8767 用户 runtime，不写入其数据。

- 浏览器验收路径复核发现：设置页“断开连接”会清空当前 projectId 并跳回项目列表；这与“已打开画布后平台失联但继续本机运行”是不同情形，需分开实操，确认是否要保留画布上下文。
- `backend/app/local_runtime.py` 支持通过 `ICT_LOCAL_RUNTIME_DIR` 和 `ICT_LOCAL_RUNTIME_PORT` 指定独立数据目录/端口，可用于避免写入现有 8767 runtime。一次递归搜索范围过大、10 秒后仍运行，已中断；后续只查精确路径。

- 验收路径的具体设计：断连/平台请求失败时，工作台最近工作流从已缓存项目/工作流读取离线入口，明确标为本机副本且平台权限未验证；打开后走独立 runtime 本机保存/运行，平台同步/版本操作仍需重连。
- `canRunLocal` 只依赖已加载工作流、本机 runtime/组件目录、所选目标闭包和 CSV ArtifactHandle，不要求项目 API token；工作流断连读取会优先使用平台副本缓存并尝试合并本机草稿。
- CSV smoke 数据格式来自 ICT 检查器要求的 `record_id,group_id,split,label` 表头；本轮用隔离 runtime 实际运行。
- 路径排错：两次文件读取命令在 backend 工作目录中重复添加 backend/frontend 前缀而失败，改用绝对路径成功；后续文件读取统一用绝对路径。无产品文件受影响。

- 浏览器测试数据模型已核实：项目目录可从 `ict-research-workbench-project-list-cache` 读取，最近记录保存项目/工作流 ID，工作流详情缓存有 owner 与 graph；CSV node 的本机文件由 `parameters.artifact_id` 引用。
- 计划先以隔离 Playwright 场景验证“无平台 token 时显示缓存工作流入口”确实失败，再改工作台最近列表；随后通过 18767 临时 runtime 路由改写执行真实 CSV 运行。平台 API 8765 和现有 runtime 8767 均不写数据。
- 首次离线入口 E2E 失败在测试数据注入：Python `repr()` 生成的单引号对象字面量不是合法 JavaScript，导致 localStorage fixtures 未载入；页面仍是正常空态，不能据此判断功能失败。修正为 `json.dumps()` 生成 JSON/JavaScript 字面量并收集 pageerror 后重跑。

- TDD 离线入口实测：同一隔离 Edge 场景先在旧实现失败（项目缓存存在，但工作流列表提示无法验证、没有打开按钮）；修复后通过（平台权限未验证提示、缓存副本标记和“本机打开”按钮均出现，pageerror 为空）。
- 变更仅在 `frontend/src/App.tsx`：最近工作流无平台 token/目录请求失败时，从通过结构校验的项目列表/详情缓存与工作流详情恢复最多 5 条本机记录；不在线时不清理无法验证的 ID；明确本机副本提示；平台拒绝响应不回退到缓存。
- 断连导航入口现已可用；下一步在隔离 18767 runtime 里导入正确 CSV、保存草稿并运行，再检查报告“结构预检，非科研结果”。
- 首次本机 CSV UI 运行检查只等了“运行”按钮可见，没有等工作流/组件目录加载完成；检查时页面仍为读取中，提前退出引发 Playwright route 的取消回调。独立 runtime health、CSV 目录、导入、draft 读取均返回 HTTP 200/201。测试脚本需等待按钮启用，并在 `finally` 关闭浏览器后重跑；尚未提交 run。
- 隔离 runtime 已收到真实 UI 提交并执行 CSV 节点：服务日志记录 `POST /runs` 202、run `6cc80b0a-5798-4f55-a822-90fbf19b2270` 状态 `SUCCEEDED`，本机报告 GET 200。浏览器脚本随后等待一个过于严格的报告标题 locator 并在截图前退出；该次只证明真实运行和报告 API 成功，还未证明产物文字已在 UI 可见。下一步改为保存截图并检查报告区实际文案，避免凭猜测定位。

- 真实离线 UI 闭环通过（Edge 1440×900，隔离 localStorage/runtime）：无平台 token 时“本机打开”已缓存工作流；等待运行按钮启用后点击，本机 CSV node 成功。run `6cc80b0a-5798-4f55-a822-90fbf19b2270` 为 `SUCCEEDED`，产物 ArtifactHandle/哈希可见；报告 UI 展示结构通过、2 行、4 字段、2 类标签、0 问题，并明确“非科研结果”。浏览器 pageerror 为空，截图 `C:/Users/lumen/AppData/Local/Temp/ict_workflow_offline_report_20261102.png`。
- 先前严格标题 locator 的失败已定位为查询方式不可靠：页面经“运行历史”选中 run 后报告区真实渲染；测试改为检查报告容器后通过。该轮页面截图目视复核通过。
- 连接→冲突→断开全流程脚本在连接成功、进入项目目录后停在项目按钮定位：宽正则同时匹配项目卡片和其操作菜单，Playwright 严格模式报歧义。清理逻辑又在 `sync_playwright` context 退出后运行，导致次级 Event loop closed。原因均是临时脚本 selector/关闭顺序，尚未触达后续产品交互；改用 `.project-card` 精确定位，并在 Playwright context 内关闭资源后重跑。
- 连接/服务模拟和项目导航现已通过：项目卡片、项目详情、工作流标签均能到达，平台接口 mock 返回了修订 2。全流程第二次停在 CTA 文案断言：项目“工作流”专页真实按钮为“打开画布”，不是概览组件里的“继续编辑”。按渲染 DOM 改用 `.project-workflow-panel` 范围的“打开画布”定位后继续；仍未触达冲突与断开阶段。
- 第三轮已按 DOM 修正工作流按钮文案，修订冲突提示与“本机修订 1 / 平台修订 2”断言均通过；随后测试 helper 调用 `expect.poll` 失败，因为当前 Python Playwright 1.64.1 的同步 `expect` 没有该方法。改为用页面等待后检查已记录的版本历史请求，不涉及产品代码。


## 2026-11-02 离线工作流入口与画布断网验收

- 修复 `DashboardRecentWorkflows` 的显示门槛：断开平台会让项目目录回到 `idle`，缓存工作流虽已解析仍被 `projects.status === 'ready'` 隐藏；现在列表按有效的本机缓存状态渲染。
- 隔离 Edge 浏览器用 mock 平台依次验证连接、发现本机修订 1 / 平台修订 2 冲突、查看版本历史、画布打开后模拟 API 503 并从原画布本机运行、断开连接后从工作台本机缓存副本重新打开运行。两次运行均 `SUCCEEDED`，节点 `CACHED`，无页面异常。
- 本机 CSV 报告 UI 等待到完整状态后显示：结构通过、2 行、字段 `record_id/group_id/split/label`、2 个标签类别、0 个问题；清楚标记“非科研结果”。模拟服务场景不等同真实平台验收，真实修订冲突服务仍列待办。
- `npm run build` 通过（178 modules）；`git diff --check` 退出码 0，仅提示仓库现有文件行尾将转换。Vite 保留主 JS chunk 超 500 kB 的建议。
- 本轮只使用隔离 runtime 18767 和临时数据目录，已停止；没有写入用户 runtime 8767，也没有向真实平台 API 发送请求。
- ComfyUI 源码复核到 `graph.py` 的 blockCount/ready-node 与 external wait 机制、`node_typing.py` 的 `IO` 类型契约；ICT 用自有实现适配。源码包 LICENSE 为 GPL-3.0，未复制其源码。

## 2026-11-02 本机 CSV 类型化输入 DAG

- 新增本机 CSV ArtifactHandle 源节点和强类型 `CsvArtifactRef` 连线输入版预检组件；执行计划会按画布边连接依赖，调度器只传递产物引用。
- 隔离 Edge 平台 API 503 场景：缓存工作流画布显示 2 节点、1 连线；本机运行成功，复跑节点命中缓存；报告 UI 显示 2 行、4 字段、2 类标签、0 问题，并标明非科研结果。无页面异常。
- 相关 14 项后端测试、Python `compileall`、`npm run build` 通过；18767 临时 runtime 已停，8767 用户 runtime 未操作。

## 2026-11-02 空白画布 CSV 实际搭建闭环

- 修复新 ArtifactHandle 源节点没有本机 CSV 文件选择器的问题；旧快捷预检与新源节点共用授权导入路径。
- 新增不重叠的两列默认节点位置，组件目录连续添加可直接拖线；历史中选择终态运行会清除旧的运行中按钮状态。
- 隔离 Edge 在平台 API 503 时从空画布完成 CSV 导入→添加两节点→拖线→本机运行→查看报告；2 节点均 SUCCEEDED，报告 2 行/非科研结果，按钮复位，pageerror 为空。
- 前端生产构建、相关 14 项后端测试、Python `compileall` 与 `git diff --check` 通过；Vite 保留 JS chunk >500 kB 提示。


## 2026-11-02 Ready Queue 增量依赖释放

- 将 `workflow_scheduler.py` 的每轮全图 WAITING 节点扫描替换为依赖计数与直接后继索引；同一父节点的多条端口连线只计一个调度依赖，队列按编译顺序稳定出队。失败节点将其后继标为 `BLOCKED/DEPENDENCY_FAILED` 并继续传播，独立分支及 `WAITING_EXTERNAL` 保持原行为。
- 新增依赖索引 RED→GREEN 与多父节点 join 等待用例；调度器 4 项、ExecutionPlan 1 项、CSV 预检 3 项测试通过，`compileall` 通过。变更后重新执行隔离 Edge 断网场景：画布内运行和工作台缓存入口运行均成功，完整报告可见，pageerror 为空。
- 专用 runtime 18767 已停止；未接触 runtime 8767。

## 2026-11-02 ComfyUI P0 适配范围对齐

- V4.0 将十项适配能力明确为 P0 架构目标，并按比赛节奏分为 B1 前五项、B2 本机 CSV 结构预检闭环、B3 缓存/ArtifactHandle/资源准入/执行路由/Worker 监督基础版。
- 根据现有源码修正 V4.0 中过期实现状态：本机 DAG、CSV 输入与预检、Input Signature 缓存、静态资源准入、后台任务监督和固定 Crossref 网络节点已接入；真实平台 Worker、更多本机执行组件、真实修订冲突验收及独立 Worker 进程故障边界仍待完成。
- 对照源码位置为 `comfy_execution/graph.py`、`comfy_execution/caching.py`、`comfy/comfy_types/node_typing.py`、`execution.py`、`main.py` 和模型资源管理实现。只采用可适配的架构模式，未复制源码；本机快照许可证为 GPL-3.0。
- 本轮只整理方案、任务和进度记录，未修改产品代码，未运行代码测试或访问服务。

## 2026-11-02 CSV 字段选择本机执行器

- 新增 `ict.data.csv_select_columns`，支持类型化 CSV ArtifactHandle 输入、按精确字段名选择与重排、行流式读取和本机派生 ArtifactHandle 输出，可连接到现有结构预检节点。
- 派生产物标记 `derived_from_confirmed_input`，来源记录包含工作流 Run、生产节点和父 Artifact ID；选择器校验输入授权与 SHA-256，并拒绝空/重复表头、字段缺失和行列数不一致。
- Input Signature 实现摘要现在包含 `local_artifacts.py`；便携包将该文件作为数据带入，以便冻结 runtime 计算同一实现摘要。
- 隔离 runtime API smoke 通过：三节点首跑均 SUCCEEDED，派生产物列与来源正确，报告可读取并标为非科研结果；第二次运行三个节点均 CACHED。此验证未触碰用户 runtime 8767。
- 隔离 Edge 电脑端空白画布验收已通过：在 5174 页面添加 CSV 来源、字段选择和连接输入预检节点，导入合成 CSV、填写字段、拖接两条强类型连线并本机运行；3 个节点成功，报告标注非科研结果且不含已过滤字段。

## 2026-11-02 CSV 字段选择本机执行器

- 新增 `ict.data.csv_select_columns`，支持本机 CSV 类型化 ArtifactHandle 输入、按逗号分隔的精确字段名选择与重排、CSV 行流式读取和本机派生 ArtifactHandle 输出；能直接连到现有结构预检节点。
- 派生产物标记 `derived_from_confirmed_input`，来源记录包含工作流 Run、生产节点和父 Artifact ID；运行时验证输入授权与 SHA-256，并检查空/重复表头、字段缺失和行列数不一致。
- Input Signature 实现摘要现在包含 `local_artifacts.py`；便携包将该文件作为数据带入，以便冻结 runtime 计算相同摘要。
- 代码已修改，隔离 runtime 运行和缓存复跑尚待验收；本轮不声称该新节点已通过运行验证。

## 2026-11-02 CSV 字段选择画布验收与 loopback 端口修复

- 浏览器验收暴露来源规则不一致：CORS regex 接受 loopback 动态端口，但 runtime 中间件仍只接受静态 `origins`；Vite 在 5173 被占用后切到 5174 时，本机目录不可用。
- 修复后中间件仅接受有效 HTTP `127.0.0.1`/`localhost` 来源（动态端口），拒绝外网域名及伪装 loopback 子域。手工 HTTP 核对：5174 来源返回 200，两个非 loopback 来源均返回 403。
- 隔离 Edge 使用合成缓存、模拟平台 API 503、Vite 5174 与临时 runtime 18768；从空白画布添加 CSV 源、字段选择、连接输入预检，导入临时 CSV，设置 `record_id,group_id,split,label`，拖接两条强类型连线并运行。三个节点均成功，产物已移除 `unused_column`，报告显示“非科研结果”，无 pageerror。
- Playwright `pageerror` 为空且截图无可视错误遮罩；Vite 开发服务器在加节点/拖线时记录 `ResizeObserver loop completed with undelivered notifications`，尚未定位根因，暂列待办。
- 截图：`C:/Users/lumen/AppData/Local/Temp/ict_csv_select_browser_acceptance.png`。本轮未接触用户 runtime 8767；该合成流程不能证明真实平台 Worker 或科研结果。


## 2026-11-04 继续推进 11/10 本机组件闭环

- 复核当前工作计划：电脑端优先，离线本机 CSV 基本闭环和用户显式同步是 11/10 范围；平台 Worker、云 GPU、真实科学结论和手机端不纳入本次目标。
- 最近离线项目打开修复已在最新便携包 v3 的隔离 Edge 中完成无令牌直开与连接失败后打开两种路径，结果记录在 `task.md`。项目摘要可以离线打开，下游未缓存目录显示明确状态。
- 当前下一项是用最新源码便携包再走一次空状态起步的本机项目→本机 CSV 模板→导入→运行→查看报告→重启恢复闭环。环境必须隔离，合成报告必须标记为非科研结果。
- 本条记录写入时主闭环验收尚未开始；未对用户项目目录做任何操作。

- 2026-11-04 当前包验收进度：从空隔离 runtime 创建本机项目成功；模板市场读取本机内置 CSV 模板并通过 `POST /api/v1/local/projects/{id}/workflows/from-template` 创建工作流，返回 201，编辑器路由为 `#workbench/projects/<project>/workflows/<workflow>`。尚未完成节点参数、导入、运行、报告与重启恢复。
- 验收脚本初次把 hash 路由当成整页导航等待而超时；已确认路由变化与服务端创建成功，下一步等待 hash/编辑器 DOM，不再创建同名流程。

- 最新便携包画布已实际渲染本机模板：4 个节点、3 条连线；组件目录显示 CSV 源、字段选择、结构预检和描述统计四个执行器均为本机可用。已选中 CSV 来源节点，参数检查栏出现本机文件选择入口与 Artifact ID 字段；截图 `02-local-csv-template-workflow.png` 留在隔离验收目录。

## 2026-11-04 最新便携包离线项目与 CSV 闭环复核

- 当前便携包 `desktop/dist/workflow-app-20261104-offline-project-open-v3/ICTWorkflowWorkbench.exe`（SHA-256 `DA1893AD9780AAE03E9BC44EDFF422447C4342CBB41F81128A1FDB796EF7FAE7`）在隔离临时目录及 loopback 端口 `18826` 中运行；health 为 `mode=local`、`platform_required=false`、`frontend_served=true`，平台项目服务未配置。
- 从空隔离状态创建本机项目“`ICT Offline CSV Acceptance`”，工作台卡片可打开项目；从本机模板市场实例化 CSV 结构预检与描述统计模板，形成 4 节点、3 连线 DAG，四个组件均报告“本机可用”。
- 首次本机校验提示源节点缺少 Artifact ID。重新通过源节点文件导入选择合成 CSV `synthetic-acceptance.csv`，将生成的 handle `dee25865-fc0f-4da0-ae46-5d87272f9ec7` 保存到草稿修订 3；字段选择参数为 `record_id,group_id,split,label`。保存后图结构与组件契约校验通过。
- 本机运行 `84906edd-00e0-463a-a520-32fe1b06c8cd` 成功，4 个节点全部成功，两个末端目标均执行；产生字段筛选 CSV、结构预检报告和描述统计摘要。结构报告为 4 行×4 字段、0 问题；报告及摘要分别明确标记“非科研结果”“非科研结论”，不代表真实科研分析。
- 以同一隔离 `LOCALAPPDATA` 和端口重启便携包后，返回工作台并重新打开项目成功；草稿修订 4、运行记录、4 个产物引用以及两份报告仍可读。验收后只停止了本轮路径匹配的两个便携包进程，端口 `18826` 已释放；未接触正式端口或用户数据。
- 本轮是未连接平台服务时的本机组件功能验收；loopback runtime 保持运行，不等于整机断网验收。没有调用平台 API、外网节点或真实科研数据，也未改产品代码、未运行自动化测试套件。
- 功能闭环通过，但 Codex 内嵌浏览器视口约 516 px，本轮不作为宽屏电脑端视觉签收。

## 2026-11-04 最新便携包复现状态与组件详情手工复核

- 最新包 v3 再次启动成功，使用上一条闭环保留的合成本机数据目录；health 为 local 且 `platform_required=false`，工作台显示平台项目服务未连接、本机项目仍可用。
- 在本机“论文复现 / 实验核验”页创建明确标注合成 CSV、非科研、无比较结论的任务。其独立任务工作流可以加入本机 CSV 快捷结构预检节点、保存、校验并运行；这证明任务工作流在本机项目服务未连接时可用。
- 运行 `b65ab913-6ea1-4679-a1ac-bd0c7d317b31` 成功后，复现任务状态 `awaiting_review` 在 UI 映射为“待复核”；运行状态为“成功”，事件状态为“排队中 / 运行中 / 就绪 / 运行中 / 成功 / 成功”。报告为“结构预检报告 · 非科研结果”，没有科研准确性、符合或差异结论。
- 组件详情真实显示 CSV 描述统计节点的本机执行位置、executor binding/version、依赖版本、权限及资源预算；这不是固定空态。屏幕截图宽度约 501 px，故只能确认交互和数据映射，不能代表宽屏电脑端视觉完成。
- 最新包 hash 为 `DA1893AD9780AAE03E9BC44EDFF422447C4342CBB41F81128A1FDB796EF7FAE7`。验收结束后关闭了精确隔离 profile 的 Edge 进程与包进程，18826 不再监听。

## 2026-11-04 离线项目导航修复

工作台离线打开路径现在会把平台项目 ID 解析到本机目录中关联的本机工作副本 ID；本机目录加载后，直接访问平台项目深链接也会切换到本机副本。详情请求检测到平台级不可用错误时，会更新全局连接状态并触发这条回退。已运行 `npm run typecheck` 并通过。尚未进行隔离桌面交互复核，本轮未运行自动化测试套件。

## 2026-11-04 离线路由修复包交付

前端生产构建通过，使用独立输出目录生成便携 EXE（SHA-256 `907DD3D6E27AC728DDCD332C26EF86B98F579A1DB7C21BF3EC7B2A46E7F63A8A`）。隔离包启动后 health 为本机模式且不依赖平台服务，首页和本次 JS bundle 返回 HTTP 200，平台 API 8765 保持关闭；smoke 后已停止进程并释放端口。浏览器路由脚本没完成点击断言，因此断连项目实际打开仍未验收。

## 2026-11-04 平台项目断连回退交互复核

使用临时本机 runtime、模拟项目目录和模拟 503 详情接口，实点工作台平台项目卡片后成功切入关联本机项目详情。关闭服务前确认没有触碰真实 API 或项目。此项补足此前仅构建、未跑实际路由的缺口；下一步继续 task_plan 记录的宽屏桌面签收。

## 2026-11-04 默认桌面包离线项目打开

正式输出路径的桌面 EXE 落后于源码两天，是“隔离包有修复、日常默认包仍打不开”的直接原因。已备份旧 EXE，并通过 `desktop/build_workflow_app.ps1` 重建 `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe`。新包在独立 LOCALAPPDATA 和 18832 端口运行，平台服务未连接时实点本机项目卡片，成功进入项目详情。测试数据只在隔离目录，真实平台 API 8765 未启动；相关进程已回收。自动化测试未运行。

## 2026-11-04 默认桌面包未连接服务时打开项目

当前正式默认便携包在平台令牌为空时，本机项目卡片可进入本机项目详情；含有 `platform_project_id` 映射的合成平台项目卡片会切换到匹配的本机副本。复核使用隔离 LOCALAPPDATA 和合成数据，项目详情与“工作流”入口均实际显示。缓存详情被标记后，关联复现与平台工作流组件不再请求远端数据。默认包 SHA-256：`541F4B6AD11BD0BE79A36ED29DD3F7681C6A06FE2DE1233FCC6C08D25B0CDA89`。未运行自动化测试；没有本机副本的远端项目仍无法离线还原未缓存数据。

## 2026-11-04 工作台断连项目卡片打开补正

用户反馈服务未连接时仍打不开工作台项目。定位到详情摘要兜底依赖 localStorage，未使用工作台当前内存中的项目目录项。现在工作台将已加载的平台/本机项目摘要传给对应详情页；服务不可用时进入只读部分项目页，未缓存的下属内容仍按真实状态显示。保留权限拒绝及 API JSON 404 行为。`npm run typecheck`、官方前端生产构建与 PyInstaller 打包通过；隔离默认包 health 为 local、平台非必需，首页和 JS 返回 200。便携 EXE SHA-256：`9B166A84967799E46B5F67C73603DEE32CAD25AC28D4879795C32C763CCA85F9`。没有运行自动化测试；CUA 状态读取超时，未实点工作台卡片，页面交互验收仍待补。

## 2026-11-04 离线项目工作流画布入口补正

在隔离合成项目页复现：项目详情和工作流目录缓存可见，但“打开画布”按钮因 `isCachedSnapshot` 被禁用。修复后按完整画布缓存与项目归属校验决定是否开放入口；`WorkflowEditor` 现有缓存读取可承接离线打开。没有完整图缓存时仍不可离线打开；本机 runtime 不可用时不能创建、运行或写入本机数据库。发现系统登记的 `E:\AAAAcom\icttest\ICTResearchWorkbench.exe` 停留在 2026-10-21，已备份并同步本次正式构建。前端/桌面打包成功，包和登记应用 hash 均为 `6898E6DE67577DD05637C3EAE68A325EFF85EEB29A890A4AC81FD9DEB611A9A6`。构建后浏览器点击复核未做：隔离启动被本机执行策略拦截；自动化测试未运行。

## 2026-11-04 断连项目打开复核

此前用户浏览器标签指向 `127.0.0.1:5173`，但该端口没有前端监听；重启 `npm.cmd run dev` 后 5173 返回 HTTP 200，本机运行时 8767 正常，平台服务保持未连接。工作台中合成缓存平台项目卡片实点后进入项目概览，工作流/数据未缓存时明确显示缺失。默认桌面包与登记入口仍为同一 SHA-256 `6898E6DE67577DD05637C3EAE68A325EFF85EEB29A890A4AC81FD9DEB611A9A6`。本轮未改源码、未跑自动化测试；用户真实项目尚未复现。

## 2026-11-04 未连接服务时工作台项目再次打不开

当前 Edge 工作台在 `127.0.0.1:5173/#workbench` 显示本机项目目录为空；平台服务未连接，且当前浏览器没有平台项目列表缓存，因此页面没有可点击的项目卡片。`127.0.0.1:8767` 本机 runtime 正在监听，平台 API `8765` 未监听。已有隔离合成项目路径曾通过，但用户实际项目未复现；先取得项目名/ID、项目来源和实际运行入口，再针对真实对象修复。未改源码或运行自动化测试。

## 2026-11-04 宽屏电脑端视觉签收

以隔离 Edge headless 在 1280×720、1440×900 查看当前源码的工作台断连空态和工作流布局预览。两档均无横向溢出；工作流组件目录、画布、属性检查栏和底部运行面板均可见，页面异常数为 0。截图归档于 `artifacts/ui/workbench-{1280x720,1440x900}-unconnected-20261104.png` 与 `artifacts/ui/workflow-editor-{1280x720,1440x900}-preview-20261104.png`。静态预览仅作为布局证据；本机组件运行仍以隔离便携包 E2E 为证。用户实际项目打开问题仍待明确对象后复现。

## 2026-11-04 项目数据目录核对补充

开发页 runtime 使用 `C:\Users\lumen\.ict\runtime\runtime.sqlite3`，只读计数为 0 个本机项目、0 个工作流；桌面包默认使用 `%LOCALAPPDATA%\ICT\WorkflowWorkbench\runtime`，该数据库当前没有本机项目表/记录。平台 API 未监听。两个环境的数据目录不同，暂不擅自合并；用户实际项目来源与启动入口仍待确认。

## 2026-11-04 用户澄清：没有项目时要能直接创建

用户没有现成项目；需要在工作台内、平台服务未连接时创建首个本机项目。确认“新建本机项目”入口独立于平台服务；创建提交走本机 runtime，成功后直接进入本机项目详情。使用隔离临时 runtime 和前端端口实际操作，创建后刷新仍能重新读取；页面错误数为 0。没有触碰真实项目目录或平台 API。当前源码已支持该闭环，不需要重复改业务逻辑；入口为“工作台 → 项目 → 本机项目 → 新建本机项目”。联网后同步仍由用户显式发起。

## 2026-11-04 默认桌面包当前版本 CSV 闭环复核

默认正式 EXE（SHA-256 `6898E6DE67577DD05637C3EAE68A325EFF85EEB29A890A4AC81FD9DEB611A9A6`）在隔离 `LOCALAPPDATA`、端口 18836 且平台 API 未连接时，完成创建本机项目、内置四节点 CSV 模板、合成 CSV 导入、明确保存、校验、双输出运行和报告读取。四节点均成功；结构报告和描述统计分别标记“非科研结果”和“非科研结论”。同一隔离目录重启后，经 local runtime API 复读项目、修订 4 工作流、run `e26ffa3e-8be8-4e1f-b279-4cceb9ac4cdf` 及两份报告，字段选择输出 4 列。所有请求均为 loopback，未访问平台或互联网。后端相关 30 项与前端相关 18 项定向验证通过；无产品源码改动。复核后关闭便携包，并恢复当前开发页 5173 与本机 runtime 8767。

## 2026-11-04 Crossref 网络节点验收补充

隔离 runtime 中 Crossref 组件准入和调度可用。一次用户授权的公开 DOI 请求进入 WAITING_EXTERNAL，但 HTTPS 建连在本机 WinINet 代理 127.0.0.1:6987 超时，节点记录 NETWORK_TIMEOUT；未重试，临时数据库已清理。随后用本地模拟响应验证成功产物仍带 research_result=false，429/503 分别落为 NETWORK_RATE_LIMITED / NETWORK_UPSTREAM_ERROR。模拟结果不计 live 查询成功。待网络条件恢复并再次获得授权后复测；本机 CSV 离线闭环不受影响。

复查 127.0.0.1:6987 监听仍由 Xiaobai 的 innercore-x64.exe（PID 33528）提供；平台 API 未连接，开发前端和本机 runtime 仍健康。没有更改系统代理，也没有重发 Crossref 请求。

## 2026-11-04 CSV 组件修复与默认包复验

字段选择和描述统计现已与结构预检采用相同表头规则：首尾空白会从表头去掉，修剪后重名会报错，数据单元格不改写。TDD 新增的 3 项回归与相关 CSV/产物库用例合计 10 项通过。默认 EXE 已重建（SHA-256 `AE5118C50C7CCABE5415BDB3CB6F7B8AA2F3D8D50BDDA20C7AE816C79C39728`），隔离包在平台 API 未连接时通过合成 CSV 工作流：校验有效，四节点成功，两份报告列名统一且 `research_result=false`。端口 18837 已释放；临时运行目录因删除操作被本机执行策略拦截而保留，内含合成数据。Crossref live 仍待网络恢复及重新授权后验收，不计入本机 CSV 离线闭环失败。

## 2026-11-04 11/10 基本组件闭环全量验收

完成当前工作计划范围核对：离线本机项目/工作流、四节点 CSV DAG、运行/产物追溯、重启持久化及显式同步确认/取消链路均有证据。当前正式包 hash `AE5118C50C7CCABE5415B5DB3CB6F7B8AA2F3D8D50BDDA20C7AE816C79C39728`；同一隔离目录重启后项目、revision 2 草稿、成功运行 `7e8176de-ac8b-476b-a8e1-165c9c233ca2`、四个 SUCCEEDED 节点及两份非科研报告均可读取，health 标记不依赖平台 API。

全量前端 56 项通过、1 项跳过，前端类型检查通过；全量后端 111 项通过。全量运行发现 `App.test.tsx` 两个测试夹具落后于断连优先本机项目 UI，更新断言和 Fetch 响应头夹具后定向与全量回归通过；没有改产品行为。Crossref live 请求此前受本机代理 TLS 超时阻断，未再次发送；平台 Worker、科研有效性、云 GPU 和移动端不属于 11/10 基本组件闭环。

## 2026-11-04 本机 CSV 文件夹批处理与隔离桌面包验收

- 在隔离便携包 `desktop/dist/workflow-app-20261104-csv-folder/ICTWorkflowWorkbench.exe` 完成电脑端真实 UI 路径：新建本机项目、添加两节点模板、递归导入合成目录、保存、校验、运行和查看报告。输入为 3 个 CSV（含子目录）及 1 个非 CSV；逐文件状态覆盖通过、警告、阻断。
- 报告 `research_result=false`，不保存 CSV 原始单元格。目录上限为 200 个 CSV、合计 100 MiB，单文件 100 MiB。工作流中只有相对路径、ArtifactHandle 和哈希。
- 同一 `%LOCALAPPDATA%` 和端口重启隔离包后，项目、修订 3 工作流、成功运行及 3 行报告均可复读。平台 API/外部主机请求为 0，页面错误为 0。包 SHA-256：`E5BFCEEFE41A06C7B62CF71CE228C094281A69D27AE625A7146E13C7943E677C`；原默认 EXE 未覆盖。
- 修复载入草稿时组件目录补入参数默认值造成的误报未保存：按同一组件注册表默认值比较当前图与已保存图。新增的 2 项 Vitest 回归通过；隔离 UI 验证参数编辑后变脏、恢复默认值后回到已保存状态。
- `npm run typecheck`、`npm run build` 和后端 `py_compile` 通过。构建仍提示主 JS bundle 约 785 KB，超过 500 KB 提示阈值；不影响本次打包验收。
- 验收截图：`%TEMP%\ict-csv-folder-package-20261104-report-table-bottom.png`。

## 2026-11-04 旧草稿兼容与最终便携包 v2 复核

- 扩展脏状态回归到旧草稿缺少组件默认参数、节点 category/title/description 和 edge type 的情况；第三项测试先失败再修复，最终 3/3 通过。
- 最终便携包 `desktop/dist/workflow-app-20261104-csv-folder-v2/ICTWorkflowWorkbench.exe` SHA-256：`B1D95BEB6468568BF5C1C0B3CB9AB66D6077E71C61A0DB9991AD800E9BC6DE65`。独立目录构建，未覆盖默认 EXE 或首个验收包。
- 用 v2 包复用隔离合成目录、项目和 ArtifactHandle；载入被刻意恢复为旧字段形态的草稿时仍显示已保存，校验通过并再次本机运行；运行完成后重启 v2 runtime，成功运行和 3 行逐文件报告可读。页面错误 0，平台/外网请求 0。
- 生产构建与便携包归档来自最终源码；主 JS 785.21 KB，构建工具给出超过 500 KB 的分包建议，本轮没有扩大到代码分包改造。

## 2026-11-04 ReproForge 工作流设计报告审阅

- 用户提供 ReproForge 节点化科研复现与证据审计设计报告，要求继续开发工作流；报告作为设计参考材料处理。
- 报告建议把 Workflow Definition 与 Workflow Run 分离，并以持久化 NodeRun、Artifact hash 和事件链支持失败隔离、断点续跑与局部重试。
- 当前本机 Runtime 有 ExecutionPlan 快照、节点状态事件、缓存和最终 NodeRun 记录；启动时会把未完成 run 标记为 `LOCAL_WORKER_RESTARTED`，没有用户显式恢复流程。
- 下一开发切片暂建议为“原运行冻结计划上的显式恢复与成功节点产物复用”；尚待用户确认方向，未改产品代码。
## 2026-11-04 本机运行显式恢复设计确认

- 用户选择先做显式恢复中断运行：来源运行保持不变，新建运行沿用其冻结计划，复用持久化成功节点，仅由用户动作启动未完成步骤。
- 已写设计规格 `docs/superpowers/specs/2026-11-04-local-workflow-recovery-design.md`，包含本机 API、Run 来源关系、节点结果事务保存、Artifact 校验、重复请求防重和兼容范围。
- 按 `brainstorming` 技能的规格审阅门槛，当前等待用户审阅该规格；尚未修改产品代码或创建实现计划。
## 2026-11-04 本机运行恢复进入实施

- 用户审阅并通过中断恢复设计规格。
- 已创建实施计划 `docs/superpowers/plans/2026-11-04-local-workflow-recovery.md`，分为持久化、DAG 恢复语义、本机 API、运行详情 UI 与交付记录。
- 计划按项目约束不委派代理、不创建提交；当前开发环境指令禁止未经请求运行测试/验证，计划已明确不执行测试或构建。
## 2026-11-04 本机工作流中断恢复源码实现

- 后端 SQLite 记录恢复来源；Runtime 启动仍只标记中断 run，不会自动调度。新增受本机认证保护的 `POST /api/v1/local/runs/{run_id}/recover`，只接受 `LOCAL_WORKER_RESTARTED`，冻结计划哈希沿用原值，并以事务防止同来源出现并发活动恢复任务。
- 节点成功/缓存命中后先在事务中持久化输出和终态事件，再释放下游；恢复前逐个验证来源 ArtifactHandle 的本机索引、文件大小与 SHA-256。未验证的旧输出不会被伪装成恢复结果。
- DAG 接受 `RESTORED` 节点输出并满足其下游依赖；复现任务详情与项目工作流编辑器运行历史均提供显式恢复入口、恢复来源、节点复用数及网络节点可能重新调度的提示。
- 项目工作流编辑器恢复后新增并选中新运行，保留来源记录；若新运行详情读取失败，仍保留 API 返回的恢复运行摘要与明确提示。
- 本轮修改尚未运行自动化测试、类型检查、构建或桌面包验收。正式 EXE 未重建，正在运行的本机服务未重启。

## 2026-11-05 电脑端工作流组件目录可读性优化

- 对照 V4.0 UI-5.3 与 ComfyUI 实际画布/侧栏截图，保留“组件目录—中央画布—属性检查—底部运行面板”的专用工作区结构；不把参考软件的深色品牌视觉复制到 ICT。
- 组件目录条目改成名称独立一行、执行能力与简述并列一行，类别仍可由筛选和条目提示识别；减少端口契约和长执行器说明在窄侧栏中的拥挤，完整契约继续由组件详情抽屉提供。
- 执行能力使用现有真实组件定义映射为本机、网络、平台、阻断或未知标签；依据 V4.0 语义色表达，不生成运行状态或组件数据。
- 在 1280×720 本机静态布局预览中目视复核，组件名称完整显示，状态/简述分层清楚；此页使用静态预览条目，不代表真实组件执行状态。
- 未运行测试、类型检查或构建；真实组件目录数据状态和便携桌面包仍待复核。

## 2026-11-05 电脑端运行历史节点状态可读性

- 对照 V4.0 UI-7.7 与 ComfyUI 截图说明，运行历史原先只呈现运行级摘要；节点状态散落在画布和日志，难以快速看出具体步骤进展。
- 在工作流运行历史详情中按冻结执行计划顺序列出节点，状态颜色直接来自本机持久化 NodeRun；同时显示组件/节点 ID、产物数量和错误码。
- 节点记录缺失时显示“无节点状态记录”，不从整体运行状态推断节点成功、排队或等待；找不到当前画布中相同 ID 和组件类型的步骤时保留只读状态。
- 点击可匹配的步骤会选中画布节点并打开右侧属性检查，方便就近查看节点上下文。
- 尚未运行测试、类型检查、构建或桌面运行历史界面复核。

## 2026-11-05 工作台平台断连状态收敛

- 用户确认将重复且高度较大的平台断连空态改为紧凑平台服务状态行。
- 工作台项目分区标题统一改为“平台项目”；未连接时显示“平台目录暂不可用”，说明平台目录/成员权限需连接后读取，并说明本机项目已在上方单独管理。
- 使用服务图标替代通用文件夹图标；1200px 以上电脑端改成左对齐三列状态行并降低最小高度，连接平台入口仍保留。
- 依据 V4.0 UI-6.1 与美吉生物云项目首页截图组织主区/辅助区；未创建项目示例或更改连接行为。
- 尚未运行时预览、测试、类型检查或构建；待目视确认不同宽度下文案和按钮排布。

## 2026-11-06 工作台电脑端平台断连状态复核

- 将平台项目区明确命名为“平台项目”；断连文案指向平台目录/成员权限，短句说明本机项目已在上方独立管理。
- 1200px 以上桌面布局调整为左对齐紧凑状态行；上方已有平台连接/配置入口时，最近工作流不再重复显示连接按钮；缓存项目列表没有该入口时仍保留原按钮。
- 在 1280×720 前端预览中目视确认两种区域的层级、状态文案与按钮数量；预览显示真实浏览器目录缓存和 Runtime 未连接状态，没有修改项目数据。
- 只启动独立 Vite 前端；本机 Runtime 与平台 API 未启动，临时端口 5173/5174 已停止并确认释放。未运行测试、类型检查或构建。

## 2026-11-06 模板市场电脑端结构复审
- 对照 V4.0 UI-8.3 与 ComfyUI 模板社区参考；当前实现将可离线实例化的本机模板与依赖平台服务的模板目录拆成上下两块。
- 候选方向：统一浏览区 + “本机内置 / 平台目录”切换；本机优先显示，平台标签保留真实服务状态。此交互结构需要用户确认后再实现。
- 现有模板截图早于本机模板区改造，5173 当前未运行，未将旧截图当作当前页面复核。Agent 页未发现需改问题，本轮没有源码变更。

## 2026-11-06 工作流运行详情电脑端预览复核
- 在独立 Vite 5174 和开发态 `#__preview/workflow-run-detail` 页面，以 1280×720 复核无运行实例布局；页面状态、禁用操作原因、执行图/日志/产物空态均明确，没有横向溢出。
- 本机 Runtime 和平台服务均未启动；Vite 对本机 Runtime 的读取失败属于本次隔离预览状态，没有读取或更改项目运行数据。
- 已停止预览服务并确认 5174 释放；未运行测试、类型检查或构建。实际运行历史与默认桌面包仍待复核。

## 2026-11-06 设置页偏好项宽屏布局
- V4.0 UI-13.1 规定设置页采用左侧分类目录与右侧表单；现有截图中“内容密度”选项落在说明下方，与右侧对齐的动效开关排布不一致。
- 仅在 ≥1200px 宽屏下改为说明在左、分段选项在右；窄屏保持纵向布局，偏好仍只保存在当前浏览器。
- 在隔离 Vite 页面 1280×720 目视确认排布；本机 Runtime 未启动，页面未操作设置。未运行测试、类型检查或构建；5174 已关闭。

## 2026-11-06 工作台平台断连状态行桌面适配
- 按用户确认的紧凑状态行方案，移除平台断连说明中重复提及上方本机项目的句子。
- 901–1199px 桌面采用左对齐的紧凑两行状态块，避免平台状态、说明和连接按钮挤在单行；≥1200px 维持单行；≤900px 规则不变。
- 浏览器无障碍树读到平台目录断连状态及连接入口。像素截图未能生成：Python 环境缺少 Playwright，Node 导入不兼容，Edge 截图调用未产生文件；本轮未完成像素级目视验收。
- 首次使用 `npm run dev` 时项目脚本同时拉起了本机 Runtime；已立即中止。随后只启动直接 Vite 预览；停止后确认 5173、5174、8767 均无监听。浏览器原有“隔离验收合成项目”目录缓存未修改或视为真实数据。
- 未运行测试、类型检查或构建。

## 2026-11-06 本机模板市场工作流缩略图
- V4.0 UI-8.3 要求模板卡片展示工作流缩略图。ComfyUI 模板社区截图仅作为卡片/画廊组织参考，ICT 保持现有浅色设计系统。
- 本机模板目录通过现有 `instantiate_local_workflow_template()` 图工厂派生预览，后端只回传稳定编号、节点名/类别/画布位置及连线；不回传实例 UUID 或节点参数。模板数据与缩略图拓扑保持同源。
- 前端校验可选 `workflow_preview`，旧 Runtime 兼容无该字段；DAG 分层绘制 SVG。成环或不可布局拓扑显示现有文字流程；窄屏继续使用文字流程。平台模板未提供拓扑，因此不伪造图预览。
- 静态审阅覆盖后端返回字段、前端解析/渲染、异常拓扑回退和窄屏 CSS；随后用隔离临时 Runtime 数据目录与 Vite 页面在 1280×720 目视复核，确认 CSV 分支、文件夹直连流程和方向箭头可辨。隔离库为空，卡片上的“先创建一个本机项目”只代表预览环境状态。
- 已停止预览 Runtime/Vite，并确认 18765、15173 端口释放。自动清理策略拒绝删除系统 Temp 中本次创建的隔离目录；目录仅含空库和日志，不含项目数据。
- 未运行测试、类型检查或构建。

## 2026-11-06 模板市场统一浏览区
- 用户选择在一个浏览区按来源筛选，而不是把本机模板和平台目录分成上下两块。
- 模板市场现以“全部来源 / 本机内置 / 平台目录”切换结果；“全部模板 / 已收藏”作为独立筛选。本机收藏和平台收藏沿用现有浏览器收藏状态。
- 本机与平台注册模板在同一结果容器渲染。本机卡片保留真实工作流缩略图、版本、用途说明和“添加到本机项目”；重复项目选择器使用不同 DOM ID。
- 本机搜索继续在平台断连时可用；数据版本与执行器筛选只在平台真实模板已加载时显示，只作用于平台结果。平台目录空态、错误态、配置与重试入口维持真实服务状态。
- 1280×720 隔离 Runtime/Vite 目视复核了默认全部来源、本机来源搜索和平台未连接空态；工作流图、结果区内滚动和左栏服务状态可见，浏览器控制台无错误。只使用空隔离库，没有打开或创建用户项目。
- 隔离进程已停止，确认 5173 与 18765 释放；复用的系统 Temp 隔离目录保留空数据库和日志。未运行测试、类型检查或构建；平台在线目录及默认桌面包未验证，手机端暂缓。

## 2026-11-06 质量报告未检查态精简
- 有真实报告时保留原有服务响应指标；无报告时改为单条当前状态和说明，不再显示记录数、拆分数、标签类别、警告类型、阻断类型的破折号占位。
- 桌面端拆分摘要无数据时去掉虚线框，改为轻量说明文字；真实数据与科研结论没有被补造。
- 隔离 Vite 在 `#__preview/quality-report` 通过无障碍树及 1280×720 屏幕观察；当前无令牌，运行按钮保持禁用，页面标明合成数据不是科研结果。未调用质量报告接口或读取令牌；应用尝试读取本机项目目录时因 Runtime 未启动而失败，随后回退浏览器缓存，没有读到项目数据。
- 已停止 Vite 并确认 15173 端口释放。真实报告返回后的页面、默认桌面包和手机端未复核；未运行测试、类型检查或构建。
