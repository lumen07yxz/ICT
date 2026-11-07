# ICT 工作流运行时实现记忆

- 用户要求比赛版优先完成 V4.0 的 P0 前五项，再接一个本机 CSV 结构预检闭环；缓存和资源准入先做基础版，ArtifactHandle、授权和故障状态限于支撑该闭环的最小能力。
- ComfyUI `comfy_execution/graph.py` 的 ready/block 计数和 `caching.py` 的输入签名已按源码细节适配到 ICT 自有实现。ICT 使用自己的 `EditorDocument`、`ict.execution.v1` 和组件 Schema，不把 ComfyUI Prompt JSON/扩展导入机制直接复制进产品。
- 2026-11-02 已新增 `backend/app/services/workflow_execution.py`：选择输出后裁剪祖先图、解析当前登记的组件契约、生成稳定拓扑序与不含布局的 SHA-256 计划哈希。
- 2026-11-02 `backend/app/services/workflow_scheduler.py` 使用依赖计数的增量 Ready Queue：完成节点只检查直接后继，同一父节点多条端口连线只计一个调度依赖；失败沿后继依赖子图传播 BLOCKED。保留有界并发、事件、`WAITING_EXTERNAL` 和 SQLite 持久化。
- ICT 自有 `desktop/ict_desktop/manifest_quality.py::inspect_manifest()` 已经由受控本机 ArtifactHandle 输入执行；报告明确“结构预检，非科研结果”。
- 用户允许直接参考并复用 ComfyUI 源码中适合的内容。源码核对后，`graph.py` ready/block 与 external block、`caching.py` 祖先输入签名已按 ICT 的静态 ExecutionPlan、ArtifactHandle 和持久化缓存接口适配；对应 ICT 代码已存在，因此不替换成 Comfy Prompt 类或复制冗余源码。ComfyUI 仓库标 GPL-3.0，ICT 根目录无 LICENSE/COPYING；若后续确需复制/修改其源码并随 ICT 分发，先确定许可/分发方式并履行相应义务。
- 当前交付目标：2026-11-10 前完成电脑端基本组件闭环：本机项目/工作流、CSV 来源/字段选择/结构预检/探索性描述统计、离线运行、产物追溯及显式同步；手机端暂缓。
- 当前实现边界：`npm run dev` 会启动/复用独立本机 runtime，默认 8767；隔离 Edge mock API 已验证画布中途 503 仍可运行、断开后可从工作台缓存副本重开运行。冲突 UI 与版本历史经过模拟平台路由验收，真实平台 revision 冲突服务仍待验收。
- 2026-11-02 后续接入 B3 基础版：SQLite Input Signature 缓存使用产物内容哈希、组件/实现版本、参数、依赖和 Python/平台环境；资源请求与并发准入有保守上限；task 异常由 supervisor 落失败状态，runtime 重启时将遗留运行标为 `LOCAL_WORKER_RESTARTED`。不是 OS 级硬资源隔离或独立 worker 进程池。
- 更新时曾待浏览器断网端到端验收；该项已于 2026-11-02 通过 Edge 隔离浏览器完成。Windows 便携 EXE 已封装 UI 与本机 runtime；安装器和正常 Edge app 窗口交互验收仍未完成。
- 执行目标边界：当前注册本机 CSV executor 和固定 Crossref DOI 元数据 `network` executor；通用联网组件和真实平台云 Worker 尚未接入。不要把 Schema 中的执行目标分类误说成执行器已普遍可用。
- 开发与生产预览启动器都通过同一脚本管理本机 runtime；`npm run preview:local` 预览 `dist` 并启动 8767 runtime。Uvicorn factory 已提供默认本机数据目录，loopback 动态端口由 CORS regex 与中间件共同限制为有效 HTTP 127.0.0.1/localhost 来源；隔离 Edge 的 5174 来源已验收。
- 2026-11-02 已实际启动默认 runtime：Uvicorn startup、health 200、5173 CORS preflight 通过；隔离 API 纵向切片导入 CSV 后首跑 `SUCCEEDED`、复跑 `CACHED`，Run/NodeRun history 和报告 ArtifactHandle 来源完整。后续隔离 Edge 画布验收记录见文末 2026-11-02 CSV 字段选择条目。
- 当前“产物”面板会从本机 runtime 请求经 SHA-256/类型/大小校验的 CSV 结构预检报告摘要；未提供任意路径读取或 CSV 原始内容下载接口。
- 2026-11-02 已把独立本机 FastAPI runtime（默认 8767）、React 离线草稿/缓存入口、CSV Artifact 导入与本机预检运行、运行历史/节点事件/产物面板及 `npm run dev` 自动启动接通。平台 API 8765 与 MCP 8766 不受影响。
- 编辑器运行请求提交 ICT 自有 `ExecutionPlan`，可按输出目标裁剪上游节点；本机未同步草稿若平台 revision 前进则保留本机版本并提示冲突，不能静默用新 revision 覆盖。
- 本机 CSV 报告仅是结构预检且明确“非科研结果”。B3 基础缓存、准入和 task/重启恢复监督已接入；Windows 便携 EXE 已包含 UI 与本机 runtime，未构建安装器，也未完成正常 Edge app 窗口的视觉验收。独立 Worker 进程池仍未实现。
- 2026-11-02 对照 ComfyUI v0.43.0 源码确认：`ExecutionList` ready/block 计数和 `CacheKeySetInputSignature` 祖先输入签名已映射到 ICT 自有 `ExecutionPlan`、静态队列和内容哈希缓存，不复用 ComfyUI Prompt/执行类。
- 许可证与复用：源码快照 `LICENSE` 为 GPL-3.0；ICT 根目录无 `LICENSE`/`COPYING`。用户允许直接参考适用源码；当前直接复用 ICT 自有组件 Schema、CSV 检查器和执行器，并将 ComfyUI 机制按 ICT 契约适配。若需复制 ComfyUI 源文件并随 ICT 分发，先确认许可/分发方式并履行相应义务。
- 2026-11-02 已补逐节点本机准入：执行器能力清单限制组件权限声明，依赖通过自身声明版本与组件精确要求匹配；ArtifactHandle 输入检查确认授权状态。组件选择器显示稳定 blocker code。混合图遇到无 executor 的 network/platform 节点时只阻断对应节点/下游，独立本机分支仍可继续。
- 手工隔离 API 验收：CSV 首跑 `SUCCEEDED`、复跑 `CACHED`；混合 local/platform 图为 `PARTIALLY_SUCCEEDED`；依赖版本不匹配拒绝为 `COMPONENT_DEPENDENCY_UNAVAILABLE`，权限超范围拒绝为 `LOCAL_PERMISSION_UNAVAILABLE`。依赖安装态目前限 ICT 捆绑的自有 CSV 检查器，不会动态安装第三方包。
- 本轮 `npm run build`、相关 Python `py_compile`、`git diff --check` 通过；未运行测试套件。真实平台 Worker 和更多本机科研 executor 仍待完成。ComfyUI 源码细节用于算法适配，没有复制原文件。
- 2026-11-02 已补真实 Edge 离线流程验收：从浏览器缓存恢复项目/工作流，平台 API 不可用，仍通过本机 CSV 导入、草稿保存、运行成功和报告面板展示；ASGI runtime、SQLite 与产物目录均隔离在临时目录，未污染用户 runtime。中途断网状态和平台 revision 冲突保护仍待浏览器验收。
- 2026-11-02 按用户给定 P0 范围更新 V4.0：`local / network / platform` 最小逐节点路由与显式同步/冲突保护纳入 B3 验收；独立 Worker 进程池、动态显存调度和多层共享缓存后置。
- 平台 revision 冲突浏览器验收仍待完成。本轮隔离脚本未通过浏览器导航控件定位，未触达产品逻辑，因此不据此判断冲突保护行为通过或失败。
- 2026-11-02 冲突保护 UI 已实现：冲突时把本机画布和平台当前快照并列呈现，并链接到平台版本历史；不自动覆盖。真实平台 revision 冲突浏览器验收仍需完成。前端构建通过，但 jsdom 集成验收未能越过缺少 `window.matchMedia` 的测试环境问题。
- 2026-11-02 编辑器本机运行路径先将当前画布存入本机 runtime，再以所选输出目标提交 run，不调用平台 run API。混合目标预告应由目标依赖闭包与本机执行器可用性计算，只提示当前所选闭包中无法本机执行的节点；该提示不会使 `network/platform` executor 变为可用。
- 2026-11-02 已加入 Windows 便携工作流桌面包：`desktop/workflow_shell.py` 在 loopback 同源提供 React `frontend/dist` 与 FastAPI runtime，用户数据/SQLite/产物/日志/Edge profile 均放 `%LOCALAPPDATA%\\ICT\\WorkflowWorkbench`。PyInstaller onefile 输出在 `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe`。
- 便携 EXE 隔离 smoke 已通过 health、首页/JS/CSS、本机会话和 CSV executor availability；没有打开 Edge app 窗口，也没有构建 Inno 安装器。生产包现已能启动本机 UI/runtime，但目前只有 CSV 本机 executor，`network/platform` 执行端仍未接入。
- onefile 诊断启动测试若强杀外层 bootloader，会留下解包子进程；关闭 smoke 时需核对可执行路径再回收对应子进程。本产品正常关闭路径等待 Edge app 窗口退出后会有序停止 runtime。
- 2026-11-02 已接入首个受控 network executor：Crossref DOI 公开元数据。节点固定访问 `api.crossref.org`，使用 `httpx==0.28.1`、并发 1、20 秒超时、2 MiB 响应上限、不重定向/重试；画布每次运行前明确确认，禁止工作流指定 URL/代码或上传本机文件。
- Crossref 产物使用 `public_metadata` ArtifactHandle；专用读取接口校验存档哈希、JSON 类型、大小、固定域名和 DOI，并仅暴露白名单书目字段/非科研结果免责声明。`ICTWorkflowWorkbench.spec` 需带 adapter 源文件、httpx hidden import 与 dist-info 元数据，以使冻结包可核验实现摘要和精确依赖。
- 当前本机 runtime 可同时调度本地 CSV 与固定 Crossref 网络节点；平台执行器仍未接入。EXE health/UI/组件目录隔离 smoke 通过且未发 live DOI 请求；不可把该 smoke 描述成 Crossref 在线调用成功或平台 Worker 已完成。
- 2026-11-02 已将本机 CSV 预检从参数直传扩展为类型化两节点 DAG：只读 ArtifactHandle 源输出 `CsvArtifactRef`，连接输入版检查组件消费；运行前/执行器内均核对权限与媒体类型，画布可离线运行，产物报告标明非科研结果。隔离 Edge 通过 503 离线运行与缓存命中验收；本机 runtime 默认 8767 未写入。
- 2026-11-02 电脑端从空白画布实操发现并修复三处边界：新 ArtifactHandle 源缺少 CSV 文件选择器、组件默认坐标重叠、历史选择终态运行未清除 `runBusy`。现在可以在平台 API 503 时导入、添加两节点、拖线、本机运行并查看报告；Edge pageerror 为空。

- 2026-11-02 scheduler 增量队列改动经 `test_workflow_scheduler.py`、`test_workflow_execution.py`、`test_local_csv_preflight.py` 共 8 项测试（含多父节点 join 等待）和隔离 Edge 断网 E2E 验收；平台路由由 mock 提供，不代表真实平台服务已测。
- 2026-11-02 用户确认的比赛演示顺序为 B1 前五项、B2 单一本机 CSV 离线闭环、B3 基础缓存/资源准入；ArtifactHandle、授权和错误状态只做到该闭环所需程度。用户允许直接参考适用源码；ComfyUI v0.43.0 的依赖计数、external block 和祖先签名已按 ICT 自有格式适配，本轮未复制原文件。
- 2026-11-02 V4.0 状态说明已与代码对齐：固定 Crossref `network` executor 已接入；真实 `platform` Worker、更多本机科研执行器、真实平台 revision 冲突验收和独立 Worker 进程故障边界仍未完成。不得把 mock/合成运行描述为真实平台 Worker。
- 2026-11-02 `ict.data.csv_select_columns` 本机 runtime API smoke 已通过：三节点 CSV 源→字段选择→结构预检首跑 SUCCEEDED，派生 ArtifactHandle 保留确认授权及父 artifact/run/node 来源，报告仍是结构预检非科研结果；相同计划复跑三个节点均 CACHED。隔离 Edge 空白画布链路现已通过验收。
- 2026-11-02 新增 CSV 字段选择组件 `ict.data.csv_select_columns`：静态逗号分隔字段参数，输入输出均为 `CsvArtifactRef`，本机流式读取并生成带父 Artifact、producer node/run lineage 的派生 CSV。实现摘要必须涵盖 `local_csv_executor.py`、`local_artifacts.py` 与既有 checker；PyInstaller spec 需同时打包 `local_artifacts.py` 源文件，否则冻结版不能算出同一摘要。API smoke 和隔离 Edge 空白画布验收均通过。
- 2026-11-02 CSV 字段选择画布 E2E：隔离 Edge 在 Vite 5174、runtime 18768、平台 API 模拟 503 下完成三节点导入/筛选/预检，三节点成功、派生列与报告正确。Playwright `pageerror` 为空；随后在独立复现中捕获 ResizeObserver window 错误事件，并已按下方记录修复。非真实平台 Worker/非科研结果。
- 2026-11-02 ResizeObserver 根因与修复：隔离 Edge 记录到新增节点后，React Flow 完成节点测量，因 `useNodesInitialized` false/true 导致 ICT 画布观察器反复卸载/重建；重新观察 `.canvas` 时触发 window loop 错误事件。移除该状态门控后连续添加 3 个节点的错误数从 3 降到 0，完整 CSV 离线流程仍成功且保留两条连线；React Flow 尺寸回调未过滤。节点新增遮挡策略已由用户确认并实现：目录“＋”新增后仅在超出可视边界时轻微平移，保留缩放和已有节点坐标，拖拽放置不触发；隔离 Edge 验收通过。
- 2026-11-02 调度器现对 `ExternalWait` 按节点 `resource_limits.timeout_seconds` 限时；缺省兜底为 600 秒。超时取消 awaitable，记为 `EXTERNAL_WAIT_TIMEOUT` 并只阻断其后继，独立分支继续；普通执行器抛出的 `TimeoutError` 记为 `NODE_EXECUTION_TIMEOUT`。Crossref 的 20 秒契约与 CSV 节点的本机时限会由调度器执行。六个相关模块共 21 项测试通过；未请求 live Crossref，未验证平台 Worker 超时。

- 2026-11-02 运行错误本地化：前端 `workflowRunErrors.ts` 将已登记的外部超时、执行器/依赖/目标、Crossref、CSV 常见错误映射为原因/影响/下一步；未知码有安全说明。运行历史、节点事件和选中节点最近运行显示说明并保留原始码。隔离 Edge 重复 CSV 字段产生 `CSV_COLUMNS_DUPLICATE`，可见说明完整且无堆栈；状态为“部分完成”，因为独立 CSV 来源分支成功、字段选择分支失败。
- 2026-11-02 目录新增节点可见性：用户确认仅被遮挡时轻微平移。`workflowViewport.ts` 计算最小像素位移，`WorkflowCanvas` 只调整 viewport x/y、不改 zoom 或 node positions；目录按钮和组件抽屉加节点启用此行为，画布拖拽放置不启用。1600×1000 Edge 验收 scale=1、已有节点相对位置相同，新节点完整落入画布。
- 2026-11-02 隔离浏览器闭环复验：CSV 来源→重复字段选择→结构预检，正向有效输入跑完且报告标“非科研结果”；反向重复字段显示本地化失败原因、影响、建议和错误码，`pageerror=[]`。平台 API 503 是模拟断连；本机 draft 首次读取 404 属于尚未建档的预期响应；未调用真实 Crossref 或平台 Worker。
- 2026-11-02 前端 `npm run build` 通过（180 modules）；保留既有 JS chunk 超 500 kB 提示。相关定向单元测试 7 项此前通过。隔离浏览器使用 Vite 5174 / runtime 18771，未访问用户运行时 8767。

- 2026-11-02 V4.0 B2 离线验收加固：隔离 runtime 由临时 `sitecustomize.py` 在 socket 层阻断非 loopback DNS/connect；Python guard 自检确认 `example.com` 解析在 guard 内失败，未发出网络请求。Edge 端路由只放行本机 Vite/runtime，其他地址全部 abort；平台 `/api` 模拟 503。CSV 源→字段选择→结构预检和报告读取成功，浏览器外网请求列表为空，runtime 非 loopback 拦截日志为空。运行数据、SQLite 和文件均在临时目录，端口 5174/18771 完成后已关闭；用户端口 5173/5175/8767 保持原状。

- 2026-11-03 错误码覆盖审计：发现 `inspect_manifest()` 的 `manifest_unreadable`、`manifest_header_missing`、`manifest_header_duplicate`、`missing_required_columns`、`invalid_encoding`、`invalid_csv`、`manifest_changed` 以前都会落到通用提示，现已逐项映射。还补齐 CSV 字段不存在/行宽错误、产物哈希/授权/存储错误、Crossref HTTP/重定向/响应解析/超限/落盘错误，以及报告读取类型/大小/损坏错误。CSV/Crossref 报告读取失败保留 `LocalRuntimeApiError.code` 并在产物面板展示本地化说明。隔离 Edge 用模拟 `ARTIFACT_REPORT_UNREADABLE` 实测可见完整说明；相关 23 项前端定向测试和构建通过。
- 2026-11-03 revision 冲突恢复：`workflowConflictSync.ts` 负责读取并复核平台 revision、先为平台当前草稿创建不可变版本，再以复核过的 revision 同步本机内容；复核期间变更或同步期间再次 409 时重新读取平台状态并终止覆盖。`App.tsx` 在首次 409 后缓存本机名称/说明/画布、展示双方版本并要求显式确认。辅助逻辑 6 项测试覆盖复核和竞态；隔离 Edge mock API E2E 验证冲突、取消、确认、快照、同步均符合预期，`pageerror=[]`、非 loopback 请求为空。真实平台 revision 冲突仍未验收。
- 2026-11-03 已连接会话断连恢复：隔离 Edge 在同一编辑页先 mock 项目 API 正常，再把草稿 PATCH 改为 503；修改后的名称写入浏览器缓存，并向 mock 本机 runtime 草稿接口保存成功；恢复 mock API 后无需重开页面即可显式同步，平台 revision 1→2、mock runtime 返回草稿 revision 3，`pageerror=[]` 且非 loopback 请求为空。与之前使用隔离真实 runtime 的“平台 503 时已打开画布仍可本机运行”E2E 共同覆盖会话中断保存、离线执行和恢复同步；真实平台 TCP/鉴权行为仍待验收。
- 2026-11-03 真实隔离 runtime 组合 E2E：Vite 5177 + `backend/app/local_runtime.py` 18772 + 独立临时数据目录，项目/工作流 API 使用 mock。已连接页面导入合成 CSV，平台 PATCH 503 后浏览器缓存和 SQLite 草稿写入成功；平台保持不可用时本机 CSV 源与结构预检两节点均 `SUCCEEDED`，真实报告 API 返回 `research_result=false`、“结构预检，非科研结果”、2 行 4 列 0 问题。恢复 mock 平台后无需重载页面即可同步至 revision 2；UI 显示运行成功并恢复运行按钮，`pageerror=[]`、非 loopback 请求为空。截图 `ict_mid_session_real_runtime_recovery_20261103.png` 位于系统 Temp。真实平台服务与鉴权行为未覆盖。
- 2026-11-03 工作流版本快照完整性：新不可变版本记录名称、说明和 graph，SHA-256 覆盖三者；恢复时还原完整新快照。迁移为旧版本新增 nullable 元数据列，历史 null 不推断，旧图恢复时保留当前草稿元数据。冲突同步在保存本机内容前核对快照元数据与已复核平台修订。V4.0 版本实体行及桌面版本/冲突 UI 已相应更新；`npm run typecheck`、后端 Python AST 检查、Alembic 全量升级至 0008 的临时 SQLite 检查、内存 SQLite service round-trip 和隔离 SQLite 上实际 FastAPI create/list/detail/update/restore API 往返均通过。Dockerfile/Compose 启动时先应用 Alembic migrations。未运行测试套件；真实部署服务 UI 冲突仍待联调。
- 2026-11-03 本机 CSV 描述统计：新增 `ict.data.csv_descriptive_summary` 本机执行器及 `CsvDescriptiveSummaryRef` 端口。流式输出缺失率、数值列 min/mean/max 与类别频数，有限列数/类别空间/报告大小；报告经 SHA-256、授权和字段白名单检查后才能由本机令牌 API 读取。桌面产物栏加入字段摘要表，明确“探索性描述统计摘要，非科研结论”。隔离 FastAPI ASGI runtime 使用合成 CSV 验证两节点运行成功，4 行/4 列结果准确；报告 `research_result=false`，没有网络/平台调用。`npm run typecheck`、`npm run build` 和四个后端模块 AST 解析通过；未跑测试套件。Vite 保留大于 500 kB 的既有 chunk 警告。隔离 Edge 1440×900 中从组件目录/画布进入后由 UI 发起运行，来源与统计节点均 SUCCEEDED，产物摘要表可见；浏览器无 pageerror/console error，外部网络请求为 0。截图为 `artifacts/ui/workflow-descriptive-summary-20261103.png`；项目 API 使用 loopback mock，runtime 为真实隔离实例。
- 2026-11-03 CSV 描述统计限额复核：2,001 列合成输入只让来源节点成功，描述统计节点精确返回 `CSV_COLUMN_LIMIT_EXCEEDED`，整体 run 按独立节点部分成功状态记为 `PARTIALLY_SUCCEEDED`；列上限检查位于摘要解析路径，不影响字段选择组件。
- 2026-11-03 工作流端口验收：保存的 typed edge handle 必须包含 React Flow 端口前缀 `out:<port-id>` 和 `in:<port-id>`。首轮验收 fixture 误用裸 `csv`，编译器正确拒绝并返回 `SOURCE_PORT_UNKNOWN`；改正临时验收图后闭环成功，无产品代码变更。
- 2026-11-03 组件 Schema 编译校验：`validate_workflow_component_contracts()` 之前只检查字符串参数是否必填/类型正确，未执行 Schema 的 `maxLength`。现编译时统一执行字符串 `minLength`/`maxLength`，错误消息只显示参数标题和边界，不回显参数内容。Crossref DOI 300/301 字符边界用例按 TDD 先红后绿；该校验位于执行计划编译阶段，未调用网络执行器。
- 2026-11-03 组件长度错误的 UI 验证说明：`workflows.py` 的验证 issue 映射需为 `PARAMETER_MIN_LENGTH_UNSATISFIED` 与 `PARAMETER_MAX_LENGTH_EXCEEDED` 提供专属 title/impact/guidance，避免落入通用兜底。隔离 SQLite + ASGI 覆盖建项目→建工作流→保存超长 DOI→调用 validations；300 上限在 reason 显示、guidance 可操作且原输入不回显。两个新 API 用例先因通用映射失败，补映射后通过。
- 2026-11-03 前端组件 Schema 长度传递：`parseWorkflowComponent()` 原来只解析 `minLength`，会丢弃服务端 `maxLength`。现接口类型和解析器保留并校验非负整数 `maxLength`；工作流检查器输入使用 `limitWorkflowParameterValue()` 按 Unicode code point 截断，字段帮助文字显示限制与当前计数，组件详情也显示最大值。3 个 Vitest 定向用例先红后绿，前端 typecheck/build 通过。浏览器验收起初受 Python 环境缺少 Playwright 阻断，随后按下一条记录完成隔离 Edge 验收。
- 2026-11-03 前端参数上限桌面 E2E：临时目录安装 Playwright，不改前端依赖；用现有 Edge、隔离缓存工作流和本机 API fixture 在 1440×900 画布验证 301→300 字符截断、最大值提示及实时计数。`pageerror=[]`、console errors/HTTP 错误/外部请求均为空，截图在 `artifacts/ui/workflow-parameter-max-length-desktop-20261103.png`。`with_server.py` 返回后曾残留 `vite preview --port 5181` 的 Node 进程；以命令行确认归属后结束，并复核端口已释放。后续隔离预览应跟踪自己启动的 PID，不能只依赖 helper 的“stopped”输出。
- 2026-11-03 便携 EXE 默认启动验收：`desktop/dist/workflow-app/ICTWorkflowWorkbench.exe` 已创建 Edge 窗口并在 `127.0.0.1:8768` 启动 runtime；health 为 `mode=local`、`platform_required=false`、`frontend_served=true`，`/` 返回 200 和 ICT 标题。Computer Use 截图因无法可靠确认当前浏览器 URL 而被策略阻止，所以不能记录视觉/交互通过；本次未导入项目数据或访问平台 API。应用进程与 8768 listener 在记录时仍运行，日志在 `%LOCALAPPDATA%\ICT\WorkflowWorkbench\logs\workflow-runtime.log`。
- 2026-11-03 便携 runtime 冷启动页面：以隔离 Edge context 打开 `http://127.0.0.1:8768/`，1440×900、HTTP 200，`pageerror`/console error/failed request/非 loopback 请求均为 0，截图 `artifacts/ui/workflow-package-cold-start-desktop-20261103.png`。首屏没有缓存项目，提示连接项目服务后查看/创建项目；当前 local runtime 只有组件目录、Artifact、workflow draft/run 等 API，没有本机项目目录或创建本机 workflow 的入口。冷启动离线创建是否属于 11/8 范围待用户确认；已有缓存项目离线运行的承诺仍单独成立。此截图来自隔离浏览器，不是产品 app window。
- 2026-11-03 重建当前源码便携包：PyInstaller 6.22.3 输出 `desktop/dist/workflow-app-20261103/ICTWorkflowWorkbench.exe`（SHA-256 `BEB8CC1E0749FCCEC08AB78AA3B5280648802180F8D6966D73C117AA9FBFD6D6`），旧包未覆盖。新 EXE 启动 health/static runtime 后，root HTML 与现有 `frontend/dist/index.html` 完全一致，JS/CSS 均 200；经本机 session 读取的 10 项组件中 CSV 结构预检与描述统计 executor 均可用。1440×900 隔离 Edge 页面无 pageerror、console error、失败请求或非 loopback 请求，截图 `artifacts/ui/workflow-package-current-source-desktop-20261103.png`。这不是 app-mode 窗口交互验收；正常 app 窗口仍在运行，端口 8768。
- 2026-11-03 离线运行认证修复与便携包闭环：浏览器同源 GET 不带 Origin，旧 session 校验造成本机组件/草稿/运行 API 401；现仅在 Sec-Fetch-Site=same-origin 且 request URL origin 与 session origin 精确匹配时允许缺少 Origin，缺少 Fetch Metadata 与跨端口仍拒绝，回归 4/4。隔离 Edge、平台 API 503 与正确 typed-edge CSV 源→结构预检图运行成功（2 节点、2 行×4 列、0 issues、research_result=false、pageerror=[]、无非 loopback 请求）。正式 EXE 新建于 `desktop/dist/workflow-app-20261103-authfix/ICTWorkflowWorkbench.exe`，SHA-256 `79A179C9B6F52C7DABA5244D2B840DFBE457C7EC6A5EA1979A57AB4195EEDBD9`，原包未覆盖。由于旧版仍占用单实例锁，打包 runtime 验收用只改 mutex 名称的隔离副本、临时 LOCALAPPDATA 和端口 18781；health local/无平台依赖，10 组件可用，草稿修订 1，两个节点 SUCCEEDED，CSV 报告明确非科研结果；临时进程已关闭。冷启动离线新建项目/工作流未验证。
- 2026-11-03 用户确认画布新增节点视口规则：组件目录“＋”添加后，仅当节点被画布有效可视边界（含底部运行面板占用的空间）遮挡时才执行最小平移；不改变缩放或其他节点位置，拖拽放置和手动视口保持原样。实现已有 `pendingNodeRevealId` 与 `minimalViewportPanForNode`，桌面验收需确认运行面板打开/收起时均只在遮挡后调整。
- 2026-11-03 离线本机项目/工作流冷启动闭环验收完成：全新临时 runtime 和浏览器无项目缓存，平台 API 模拟 503；工作台创建仅本机项目与空白工作流，导入合成 CSV，连接 typed `out:csv`→`in:csv` 并成功运行。runtime 重启后仍可读取项目、工作流、run 和报告，报告 2 行×4 列、0 问题且 `research_result=false`/“非科研结果”；报告读取无失败请求或页面错误。截图在 `artifacts/ui/local-workspace-run-report-desktop-20261103.png`。
- 2026-11-03 目录新增节点视口验收：运行面板折叠时遮挡触发 `translateY -20px`，展开时触发 `translateY -103px`；两种情况下 zoom 保持 1、已有节点 `translate(x,y)` 不变，新节点在 `.canvas` 内可见。展开态截图 `artifacts/ui/local-workspace-node-reveal-expanded-dock-desktop-20261103.png`；拖拽组件到画布边缘的释放点误差 0px，viewport 前后完全相同。手动 zoom 到 `0.578704` 后，目录新增的节点原本可见，viewport 变换在添加前后完全一致。无 pageerror/console error/failed request。
- 2026-11-03 离线工作区便携包重建到 `desktop/dist/workflow-app-20261103-localworkspace/ICTWorkflowWorkbench.exe`，SHA-256 `D336535DEFF981EDBEAE378174CB31B025B9E6AB19FA3810C3E3C8345C8C7D2B`；PyInstaller 归档含当前 `frontend/dist` 和本机 runtime。未启动该 EXE，因为用户产品实例仍占用单实例锁/8768。平台接口行为来自 503 mock；真实平台同步和云端 Worker 仍未验收。
- 2026-11-03 便携 runtime 冒烟随后通过：同一 spec 和资源输入临时重建 onefile 测试 EXE，仅将 mutex 名称改为隔离值；`--serve-only`、临时 `LOCALAPPDATA`、18783 端口启动成功。Edge 冷启动后在平台 API 模拟 503 时创建本机项目/工作流、添加 CSV 源与结构预检节点、导入 CSV、类型化连线并运行，产物页显示 2 行、2 类标签、0 问题且“非科研结果”。health 为 local/`platform_required=false`/`frontend_served=true`；平台 mock 503×2，本机 API 16 次，无非 loopback 请求、failed request 或 pageerror；仅有两条预期 503 console error。截图 `artifacts/ui/workflow-package-offline-workspace-e2e-20261103.png`。测试父进程退出后发现 onefile child 仍持有端口；按已核对的临时 EXE 完整路径停止后，18783 确认释放。正式 mutex 名称 EXE 未直接启动。

## 2026-11-03 本机离线项目同步偏好

- 用户确认：断网时新建的项目和工作流先保存在本机；恢复联网后仍由用户显式发起同步，不允许因服务恢复、登录或后台刷新自动上传。
- 显式同步应让用户看到来源、目标和字段边界；当前 ICT 设计为创建新的私有平台副本，仅将项目元数据与工作流定义放进同步正文，不放本机文件、ArtifactHandle 实体、运行/报告/日志或凭据。本机 API 凭据仅按既有 Authorization 方式用于请求鉴权，不写入 outbox；本机原件保留。
- 同步要本机持久保存 outbox、远端对象 ID 和修订映射；远端修订变化时停止覆盖，并呈现冲突/部分失败。含本机文件引用的图可保留定义，但云端可能无法读取该引用。
- 创建响应不确定时必须避免盲目重试造成重复；提供已有平台项目/工作流 ID 的人工关联，或要求用户先核对并确认没有已创建对象。

## 2026-11-03 显式同步与 11/10 基本组件闭环

- 用户最新目标：11 月 10 日前完成电脑端基本组件可用闭环；本轮按离线本机项目/工作流和四类主 CSV 组件收敛，并保留一个兼容性快捷预检节点，不将真实平台 Worker、云 GPU 或科研有效性宣称为已完成。
- 新增 `frontend/src/api/localProjectSync.test.ts`：6 项同步编排测试覆盖创建、部分失败续传、远端修订冲突和不确定创建确认。
- 新增 `backend/tests/test_local_project_sync_outbox.py`：2 项真实 runtime/SQLite API 测试覆盖 outbox 持久化、pending 排他及本机草稿修改后的待同步标记；与本机目录测试合计 4 项通过。
- 新增 `frontend/src/api/localProjectSync.runtime.test.ts`：通过 `VITE_LOCAL_SYNC_E2E=1`、`VITE_LOCAL_RUNTIME_URL` 连接隔离 runtime 和 mock 平台；本机 CSV 来源运行成功，显式调用同步后只传元数据/工作流定义，文件内容和 run ID 不发送，outbox 保存且本机 run 可读。此测试不覆盖项目页确认框的实际鼠标交互。
- 2026-11-03 验收：前端 typecheck 通过，定向 Vitest 同步编排 6 项和 App UI 取消/确认用例 1 项通过，真实 runtime 集成 1 项通过，Python 4 项通过。App UI 测试在 jsdom 环境，不代表打包 app 的浏览器视觉验收。端口 18791 已释放；临时目录 `%TEMP%\ict-local-sync-e2e-20261103125808369` 留存，因为环境策略拒绝了清理命令。

## 2026-11-03 当前源码便携包冒烟与同步策略确认

- 用户确认离线新建/修改的项目和工作流先保存在本机；联网恢复、登录或后台刷新都不触发自动上传，只有用户显式发起同步。当前同步正文仅含项目元数据和工作流定义；文件、运行、报告与日志留在本机。
- 当前源码重建的便携 EXE 位于 `desktop/dist/workflow-app-20261103-nov10/ICTWorkflowWorkbench.exe`，SHA-256 `8C602E86B108C3D175BAA6DA5F0CF6B1DB984120633B9020373B7F2D390CF75A`。隔离 `LOCALAPPDATA`、`--serve-only`、端口 18792 启动后，health 报告 local/无需平台服务，首页 HTTP 200；本机会话认证后 10 个登记组件中 5 个 CSV 本机节点可执行。未连接真实平台或外网，onefile 相关进程已按核验路径停止、端口已释放。
- 当前 CSV 闭环的四个主组件是本机 CSV 来源、字段选择、输入版结构预检、描述统计；另有一个快捷结构预检兼容组件。结构预检标“非科研结果”，描述统计标“探索性摘要”。
- 完整同步与本机执行前端测试、runtime 集成测试、Python 测试结果及尚未验收的真实平台行为见 `task.md` 与 `docs/superpowers/plans/2026-11-03-offline-local-workspace.md`。便携包已完成隔离浏览器功能和持久化验收；真实平台联调与完整视觉签收仍未完成。
- 2026-11-03 当前源码便携包 UI 与重启持久化验收：EXE `desktop/dist/workflow-app-20261103-nov10/ICTWorkflowWorkbench.exe`（SHA-256 `8C602E86B108C3D175BAA6DA5F0CF6B1DB984120633B9020373B7F2D390CF75A`）在隔离 `LOCALAPPDATA`/18792 中从实际 UI 打开本机项目，运行 CSV 来源→字段选择→输入版结构预检与描述统计的 4 节点、3 连线工作流。成功 run `ebc92954-1130-401b-abb3-47053c466dcf` 产出派生 CSV 与两份报告；重启同一 EXE 并复用同一数据目录后，项目、revision 5 草稿、运行历史、4 个 ArtifactHandle 和报告内容仍可读取。控制台错误为 0；未连接平台或外网。合成清单额外 `score` 列产生 `unvalidated_extra_columns` 提示，结构报告仍标“非科研结果”，描述统计标“探索性/非科研结论”。此记录覆盖功能与本机持久化，不代表真实平台同步/鉴权或完整视觉签收。
- 2026-11-03 Alembic 0007 存量回填验收与测试夹具修正：原 `test_upgrade_backfills_only_statuses_supported_by_historical_timestamps` 在升级到 0004 后调用最新 ORM `seed_demo_project()`，因旧 schema 没有 `projects.workspace_id` 而失败；根因在测试夹具版本不匹配，不是已证实的 migration 缺陷。将历史项目/成员/数据集/提案/run fixture 改为按 0004 schema 的原始 SQL，并新增 0006→head 的存量工作区/项目工作流回填测试，覆盖多成员角色、跨项目共享 viewer、无成员孤立项目和 workflow owner。`backend/.venv/Scripts/python.exe -m unittest tests.test_migrations -v` 4 项通过。后续 `build_engine()` 对 SQLite 启用 `PRAGMA foreign_keys=ON` 后，实际验证了缺 owner 与跨 workspace owner 均被拒绝。
- 2026-11-03 后端全回归：更新两个 `test_run_proposals.py` 私有项目 fixture，为其创建 workspace；定向运行提案 API 20 项、Worker/派发 6 项通过。全量后端 104 项在根目录 `.venv` 通过。`backend/.venv` 缺少 requirements 中已声明的 `celery[redis]==5.6.3`，因此该环境直接运行全套会有两项导入错误；不要把这两项记为实现失败。
- 用户确认断网新建的项目和工作流落在本机；联网后需用户显式同步，不自动上传。该规则适用于本机项目/工作流同步。

## 2026-11-03 本机复现任务执行链

- SQLite runtime 增加 `local_reproduction_tasks` 与 `local_reproduction_workflows`。工作流继续使用统一的 workflow draft/ExecutionPlan/scheduler/run/artifact 管线，按 `owner_type=reproduction`、`owner_id=task_id` 区分所属对象，不另建一套执行引擎。
- 成功运行只将任务状态转为 `awaiting_review`，`assessment_state` 固定为 `not_assessed`；运行成功不自动认定论文复现或实验准确。CSV 结构预检/探索性描述摘要使用已有报告边界，均不是科研结论。
- 2026-11-03 后端临时目录集成验收：创建实验任务和所属工作流，导入合成 CSV，执行预检，关闭并重开同一 runtime 后仍可读取任务、草稿修订、运行状态/事件和报告。基准 JSON 上限 64 KB；空标题、未知对象和越限基准均被拒绝。
- 电脑端复现任务列表支持本机新建；详情按 task owner 读取 workflow 和最近运行，展示 ExecutionPlan 哈希、节点状态/事件、ArtifactHandle 和本机报告。新增 UI 测试覆盖离线创建、待复核状态、无符合/差异结论、报告的非科研标签及请求只发往 loopback。
- 2026-11-03 回归：前端 54 passed / 1 skipped，生产构建 182 modules 成功（JS bundle 约 755.77 kB，仍有 >500 kB 提示）；后端全量 108 tests passed。
- 便携 EXE 独立产物：`desktop/dist/workflow-app-20261103-local-reproduction/ICTWorkflowWorkbench.exe`，SHA-256 `CA7952D817530E5E1360BFFE15EA5AE070B2B6EB02485CAF995142412309A438`。端口 18794 隔离 smoke 完成 health/home、创建本机复现任务/工作流、CSV 预检执行与报告读取；任务 `awaiting_review`，报告 `research_result=false`。只访问 loopback，smoke 进程停止且端口释放，临时数据目录保留。
- 复现任务的显式同步入口尚未实现；必须保持本机数据不自动上传，后续需要独立的用户确认/冲突恢复同步设计。真实指标提取、实际论文方法复现、比较/证据审查及科研有效性均未完成或验证。UI 测试为 jsdom；新增复现详情页尚未做真实浏览器视觉签收。

## 2026-11-03 复现详情状态显示

- 后端事件使用大写状态枚举；前端 `runStatusLabel()` 需兼容大写/小写，复现详情节点状态也必须调用该映射，避免直接显示 `QUEUED`/`SUCCEEDED`。
- 回归测试使用大写事件 fixture 并检查中文状态；前端全量 56 passed / 1 skipped、typecheck 与生产构建通过。修正后包在 `desktop/dist/workflow-app-20261103-reproduction-statuses/ICTWorkflowWorkbench.exe`，SHA-256 `A4494F148B45988F9B26AAA82A59DA51B98D1B2FE045349509E7751C8D96B6AC`；归档包含当前前端 JS、HTML 和 CSV 执行器。
- 隔离包启动命令被执行策略拦截，未做新版包浏览器复核；既有 18795 实例保持运行。修正前截图不代表修正后视觉签收。

## 2026-11-03 组件详情依赖与运行环境

- V4.0 UI-8.2 要求组件详情列出依赖与运行环境。原 UI 将这一栏硬编码为“未提供环境清单”，尽管注册契约已含执行目标、executor 绑定/版本、精确依赖和 blocker。
- 当前抽屉改为读取这些契约值；无依赖显示“无额外依赖”，可用性仍使用运行时 `execution_available`/`execution_blockers`。ComfyUI 参考侧栏用分区说明节点包、模型和缺失输入；ICT 仅借鉴状态分区，展示本系统真实字段。
- `npm run typecheck` 与生产构建通过，未运行自动化测试。便携包 `desktop/dist/workflow-app-20261103-component-environment/ICTWorkflowWorkbench.exe` SHA-256 `CBB7AAFD917553875F827FF9889A955972328DAF0CD7D643A1A745C21D80C8E4`，归档含最新前端资源和本机 CSV 执行器；受执行策略限制，未启动该包或做修正后浏览器视觉复核。

## 2026-11-03 本机离线 CSV 工作流模板

- 本机模板 `ict.local.csv_quality_exploration@1.0.0` 复用已登记的 CSV 来源、字段选择、连接输入结构预检与描述统计四个本机组件，形成一个输入和两个报告输出分支；空白必填参数由用户在画布补齐。
- 模板目录/实例化由本机运行时提供，图由服务端内置定义解析；模板创建把完整 revision 1 图和工作流记录写入 SQLite 单个事务。没有模板自动同步；联网后仍需用户在项目页明确确认显式同步。
- 模板市场在平台注册目录状态之外展示本机内置条目，项目选择器只列本机项目；创建成功后导航至现有画布。无项目时转到工作台创建本机项目。
- 前端 typecheck/build、三个后端模块 Python 语法编译通过。临时 SQLite runtime API 烟测创建并运行完整四节点图，所有节点 SUCCEEDED；结构预检 2 行、`research_result=false`、状态 warning（额外 `score` 列不在通用检查范围），描述统计 2 行×5 列；重开 SQLite 后 revision 2 可读。烟测没有访问平台或外网。未运行自动化测试，未做浏览器视觉验收。
- Windows 便携包独立构建于 `desktop/dist/workflow-app-20261103-offline-template/ICTWorkflowWorkbench.exe`，SHA-256 `8B9500540381C7C6EB8B299798434A1843D97B2C2AEF5FCAE842FC189B0D7733`。PyInstaller 分析图纳入本机模板模块，EXE 归档输入包含新前端静态资源；未启动该 EXE，因此不代表 runtime/API/视觉验收。

## 2026-11-03 组件目录桌面样式便携包

- 电脑端组件目录改为固定搜索/筛选和底部提示，组件列表在自身区域滚动；长描述在列表中截为一行，详情抽屉仍提供完整说明。仅作用于 `min-width:901px`，手机端样式未改。
- 便携 EXE 独立构建于 `desktop/dist/workflow-app-20261103-component-catalog/ICTWorkflowWorkbench.exe`，SHA-256 `F843C10100D1FD84AFC4C162F9272A5BBCC325EDF3A92288C0B08673182EDB24`。PyInstaller 归档包含当前 HTML/CSS/JS 与 local runtime / CSV / Crossref 模块；内嵌 CSS 与 `frontend/dist` 字节一致。
- 新 EXE 未启动，当前证据仅覆盖构建与归档内容；不代表该包 runtime 或组件闭环已重新验收。

## 2026-11-03 工作台离线项目入口修复

- `disconnect()` 曾将平台项目状态直接清为 `idle`，而无令牌刷新会保留 `cachedProjectList()`；断开后因此无法从工作台重新打开浏览器已缓存的项目列表。现在断开时恢复这份真实缓存，并标记为 `cached`。
- 平台列表处于未连接、错误或缓存状态时，本机项目目录优先展示；文案明确本机项目仍可打开。平台正常连接时仍先展示平台项目。
- 本次 `npm run build` 通过；1440×900 隔离页面确认离线目录在连接提示之前。检查使用临时本机 runtime 空目录，未创建演示项目；原 8767 runtime 检查时已停止，未访问用户项目。
- 离线可以打开本机项目和有浏览器详情缓存的平台项目；从未缓存到本机的远端详情与工作流仍需要平台服务先载入。后续若要求这些远端对象完整离线使用，需要定义显式本机副本/缓存策略。
- 当前源码便携包已独立构建至 `desktop/dist/workflow-app-20261103-offline-project-open/ICTWorkflowWorkbench.exe`，24,295,826 bytes，SHA-256 `E3D56C2B3ED06F2B4D07AA40ADC6B8F18910DD3D26E2B630774646E524A67E82`；归档含本次 JS/CSS/HTML、本机 runtime、模板模块与 CSV executor。包未启动。

## 2026-11-03 本机项目详情离线缓存

- 根因：离线工作台虽然展示本机项目，但项目目录、详情和工作流目录都直接请求本机 runtime；runtime 不可用时先前没有本机缓存回退。
- runtime 成功返回后，浏览器缓存本机项目目录，并异步缓存项目详情/工作流目录；本机项目创建和在线打开项目时也刷新缓存。runtime 失败时读取最后一次真实缓存，项目详情/目录可只读查看，创建/编辑/运行入口明确要求 runtime 恢复。
- 缓存数据是当前浏览器的 localStorage 快照，不自动上传；未缓存过的对象无法离线补造。平台远端项目仍依赖各自已有的真实浏览器缓存，后续若要求完整离线副本需另做显式本机副本流程。
- 缓存仅在网络异常或 5xx 时回退；runtime 返回 4xx（如项目不存在/拒绝访问）时显示真实错误，避免用旧快照掩盖服务器状态。
- 前端生产构建通过；未执行自动化测试或真实用户项目运行时验收。
- 便携 EXE 独立构建于 `desktop/dist/workflow-app-20261103-offline-local-project-cache/ICTWorkflowWorkbench.exe`，24,294,749 bytes，SHA-256 `283DC6D18F689511E4B154DDC219E5F8126684C51A5F68497D4DADDFCE67D877`；PyInstaller 归档确认含本次前端 JS/CSS/HTML，EXE 未启动。
- 含 4xx 缓存边界修正的最新 EXE 位于 `desktop/dist/workflow-app-20261103-offline-local-project-cache-v2/ICTWorkflowWorkbench.exe`，24,294,541 bytes，SHA-256 `6908A7F5B3ED53DE07C2E4B888DD0EC7639A8A9CD3D7D306D1B2AFB9CB117DA9`；归档确认含最新前端 JS/CSS/HTML，未启动。

## 2026-11-03 画布节点执行能力状态

- 组件目录/详情已展示 `execution_available`，但画布节点只显示 executor binding，保存的图会剥离运行时契约字段。`hydrateWorkflowNodes()` 在注册表加载后重新填充执行能力；节点现在就地显示本机可用、需网络、需平台服务、执行受阻或状态待读取，并通过 title 呈现契约原因。
- 仅新增显示层，不改变 ICT 运行准入、目标裁剪、调度或持久化图格式。
- `npm run build` 通过；未运行自动化测试/实页视觉检查。便携 EXE 独立构建于 `desktop/dist/workflow-app-20261103-node-execution-status/ICTWorkflowWorkbench.exe`，24,296,734 bytes，SHA-256 `25F48765F519ECC36C8904CE0D274562E345876A7557F2CABBF84F910885F8D1`；归档已核对，未启动。

## 2026-11-04 工作台断开平台后打开项目的回退边界

- 仅有工作台项目目录缓存时，也要允许打开项目详情页：目录字段足以展示项目摘要，但不能声称其中包含工作流或数据详情。
- 无平台令牌时跳过远程详情请求；网络/5xx 才允许从完整详情缓存降级到目录摘要，401/403/404 等权威 4xx 继续显示错误。
- 本机项目 runtime 不可用时，同样可从本机目录缓存打开摘要；页面提示本机 runtime 恢复后读取未缓存内容。打开项目摘要不代表工作流可编辑或可运行。
- 摘要缓存不带数据集明细；概览与数据页必须标“目录未缓存”，不能显示成项目没有数据。

## 2026-11-04 离线打开项目的状态提示

- 本机项目详情从缓存首屏打开时，同时读取本机 runtime。等待期间应显示“正在检查本机运行时”，不要把缓存快照提前标成 runtime 故障；请求失败并确认 runtime 不可用后再切换到缓存只读说明。
- 工作台在平台未连接、本机 runtime 停止时仍可点击已缓存本机项目进入详情。缓存详情可读；没有 runtime 时不能创建/编辑/运行工作流。未缓存项目数据不能离线补造。

## 2026-11-04 本机工作流校验路由

- 工作流编辑器校验不得固定依赖平台服务。本机 runtime 可用时，优先把当前已保存图和修订号发到 loopback `/api/v1/local/workflows/{workflow_id}/validations`；本机与平台复用同一 `workflow_catalog` 图结构和组件契约校验规则。
- 本机校验请求体使用 `revision` 与 `graph`，图 schema 约束版本、字段、最大 500 节点/2000 连线、2 MB 序列化大小。端点只校验、不写入草稿、不启动运行、不接触平台凭据。
- 前端应复用 `parseWorkflowValidation`，保证本机/平台响应进入同一报告面板；本机失败提示保留组件问题、节点/连线定位信息。
- 便携 EXE 验收时使用单独 `LOCALAPPDATA` 和 loopback 端口，平台 `platform_required=false`。合成 CSV 的结构报告与描述摘要均必须保留 `research_result=false`；隔离重启应保留项目、工作流、运行记录和 ArtifactHandle。

## 2026-11-04 工作台项目缓存回退

- 平台项目连接失败时，工作台会保留上次真实项目目录；项目详情 API 若返回 404，必须区分 API JSON 与前端静态宿主 HTML。静态宿主 HTML 404 表示 API 路由不可达，可展示本机缓存；401/403 与 API JSON 404 仍禁止用旧缓存覆盖。
- `connect()` 失败时保留输入令牌，因此详情页不能只以“令牌是否为空”判断服务可用性；项目 API 错误应携带响应 Content-Type，供缓存回退按响应来源分类。
- 缓存回退日志可以记录项目 ID 和错误对象，不能记录 Bearer 令牌。

## 2026-11-04 离线项目详情的下游目录状态

- 平台连接失败后，`platformUnavailable` 需要从工作台传到平台项目详情页、项目工作流目录和关联论文复现目录。仅阻断子资源请求还不够；目录没有本机缓存时应以中性状态说明“未缓存/服务未连接”，不能把连接失败呈现为 404 对象错误。
- 缓存的项目目录摘要可以打开项目详情壳层；摘要不代表工作流和数据集目录已缓存。工作流、数据和关联复现目录各自显示真实缓存状态，不虚构空列表或可运行内容。
- 2026-11-04 对独立便携包进行 Edge 桌面验收：用隔离合成项目目录分别验证无令牌直开和连接失败后打开。两次都可从工作台进入详情；未缓存的工作流/复现目录呈现中性状态，不误报对象不存在或无权访问。连接失败场景只有项目目录探测 404，没有详情/子资源请求；无令牌场景没有平台项目 API 请求；两次 `pageerror` 均为 0。合成项目不是科研数据或结果。验收端口 18825 与临时 `LOCALAPPDATA` 均隔离，结束后进程和端口已释放。
- 最新验收包：`desktop/dist/workflow-app-20261104-offline-project-open-v3/ICTWorkflowWorkbench.exe`，SHA-256 `DA1893AD9780AAE03E9BC44EDFF422447C4342CBB41F81128A1FDB796EF7FAE7`。

## 2026-11-04 便携包本机 CSV 工作流的持久化验收

- 最新包 `workflow-app-20261104-offline-project-open-v3` 使用隔离 `LOCALAPPDATA` 时，本机项目、模板工作流、ArtifactHandle、运行记录和派生产物都写入该目录下的 runtime 数据库/对象存储；保留同一目录重启后 UI 能从工作台重新进入项目并读取报告。
- `ict.data.csv_artifact_source` 必须携带本机导入生成的 `parameters.artifact_id`。模板实例初次校验会正确阻断缺失 handle；用节点属性里的“选择本机 CSV”导入并显式保存草稿后，校验与本机运行通过。若模板运行前发现缺失，先核对源节点参数和草稿修订，不要把“文件已导入产物库”误当成“工作流参数已持久化”。
- 只选择两个报告末端时，Ready Queue 依赖闭包包含四个节点；CSV 结构预检摘要和描述统计摘要均从运行产物句柄加载。结构报告标记非科研结果，描述摘要标记非科研结论。
- 本机验收的 health `mode=local`、`platform_required=false` 说明平台服务未依赖；loopback runtime 本身仍须运行。用户没有本机副本的项目不能据此推断可离线恢复。

## 2026-11-04 本机复现状态与组件详情 UI 证据

- 复现任务从 `awaiting_review` 显示“待复核”；运行状态映射“成功”，事件状态映射“排队中 / 运行中 / 就绪 / 成功”。使用运行和事件实际 UI 内容确认，不只依赖代码映射表。
- 复现任务可拥有独立本机工作流；当前小闭环使用快捷 CSV 结构预检节点，任务运行后保留 ArtifactHandle 与报告；报告仍为非科研结果。任务详情明确说明复现结论依赖真实工作流、比较规则和证据，任务/运行不会自动同步。
- CSV 描述统计组件详情从注册契约展示实际执行环境：`local`、`ict.local.csv_descriptive_summary@1.0.0`、无额外依赖、资源预算及 `local:artifact:read/write` 权限。平台服务断开不会隐藏本机节点的安装状态。
- 此轮浏览器视口约 501 px；后续电脑端视觉工作须在宽屏完整桌面窗口验收。

## 2026-11-04 离线打开关联平台项目

用户明确把“平台服务不可用时仍能继续用本机项目”作为优先要求，且项目/工作流的同步必须由用户显式发起。平台与本机项目 ID 不同时，断连导航应通过本机项目的 `platform_project_id` 映射到本机工作副本；项目详情请求发现平台级不可用时也要更新全局连接状态并触发映射。连接成功时继续走平台项目。没有本机副本时不能声称可离线恢复远端数据，只展示已缓存摘要和未缓存范围。

## 2026-11-04 再次反馈工作台断连项目无法打开

- 在隔离临时数据库和无平台 API 环境中，`npm run dev` 启动独立 local runtime 后，创建本机项目并从工作台本机目录点击，成功进入 `local-project-*` 项目详情。前端路由与后端 ID 前缀一致。
- 这不能证明平台项目映射路径已经验收，也不能证明无本机副本的远端项目可以完整离线使用。排查时须先分清用户点的是“本机项目”还是“我的项目”平台项目，并确认运行的是开发态/便携包；远端数据没有本机副本时不应假报缓存可用。

## 2026-11-04 平台项目卡片断连映射实测

- 独立 UI + runtime 中，模拟平台项目卡片的详情请求返回 503 后，工作台确实将 route 从平台项目 ID 切换到本机目录中 `platform_project_id` 匹配的 `local-project-*` 项目，并渲染本机详情。
- 该证据覆盖已有本机副本的映射路径；未下载/未映射的平台项目不能离线恢复其工作流或数据。未触碰真实平台服务和用户项目。

## 2026-11-04 用户继续反馈离线项目打不开：先核对正式启动产物

本次定位到源码已有离线路由，但默认桌面 EXE 仍是较早版本；之前只生成了独立命名的验收包，用户日常启动路径没有更新。以后修复桌面端问题时，除了验证源码和隔离包，还要检查 `desktop/build_workflow_app.ps1` 指定的正式输出路径是否已重建，并在该默认包上完成最短真实 UI 路径。用户已明确希望工作台在平台服务不可用时仍能打开本机项目；同步继续保持显式操作。对没有本机副本的远端项目，离线能力受本机缓存数据范围限制。

## 2026-11-04 默认包无平台连接打开项目复核

默认便携包在平台服务未连接、平台令牌为空时，本机项目卡片可以进入项目详情；已关联 `platform_project_id` 的平台卡片也会切换到本机 `local-project-*` 副本。缓存项目详情必须被视为只读/部分可用快照，阻断平台专属复现和工作流目录请求。复核时使用隔离数据和合成项目，不读取用户项目。没有本机副本且没有缓存的远端对象不能离线恢复完整内容。出问题先核对用户运行的 EXE 路径与 hash，再区分平台服务和本机 runtime。

## 2026-11-04 离线项目详情应复用工作台当前目录对象

平台/本机项目卡片有时已在工作台内存列表中可见，但详情页若只从 localStorage 重读摘要，存储被禁用、清理或写入失败时仍会打不开。详情页应接收当前列表中 ID 精确匹配的项目摘要，平台或本机服务不可用时可显示只读部分项目壳层，并明确未缓存的工作流/数据内容。该回退只用于服务断连/网络失败，不覆盖平台 401/403 或 API JSON 404。构建后要更新默认桌面 EXE；API health 与静态资源可用不等同实际工作台卡片点击通过。

## 2026-11-04 离线项目工作流画布入口

若本机项目详情是缓存快照，不能一概禁用工作流入口：先用 `cachedWorkflowDetail(workflowId)` 验证完整图缓存及 `owner_id`，仅对归属匹配的缓存画布开放离线编辑器路由。工作流目录摘要不能代替画布图；没有完整图就说明需要本机 runtime 恢复。画布打开和执行能力要区分：运行、创建及写入本机数据库需要 local runtime。重复反馈时先查用户启动的注册 EXE 路径和 SHA-256；本项目在 2026-11-04 发现系统登记路径仍是 2026-10-21 旧包，已备份并替换为当前构建。构建后仍须实点新包确认，不以打包成功代替 UI 验收。

## 2026-11-04 用户工作台端口恢复

隔离验收结束后确认原浏览器标签仍在 `127.0.0.1:5173`，但 Vite 已被停止；旧页面仍在标签内，不代表服务可用。用户继续使用该开发页时，应将 `frontend` 的 `npm run dev` 保持运行；本地开发脚本同时启动独立 runtime（默认 8767），平台 API 仍可保持断开。结束验收环境时只停止自己创建的 Vite/runtime 会话，先核对端口 PID，避免把用户正在使用的 5173 一并结束。平台项目列表缓存只支持项目摘要壳层；没有本机副本时不包含工作流、数据等服务端内容。

## 2026-11-04 再次反馈工作台离线项目打不开

收到重复反馈后先检查用户当前 Edge 页面。当前标签最初是 `#__preview/workflow-editor` 静态布局预览；从其“工作台”入口返回后，真实工作台为 `#workbench`，显示本机项目 0 个、平台服务未连接、没有平台项目列表缓存。runtime 8767 正在监听，平台 API 8765 未监听。之前合成项目的隔离交互通过不等于用户对象通过。后续先确认项目 ID/来源及用户实际启动的浏览器页或桌面 EXE，再做对象级复现；不要重复修改已经验证通过的合成路由，也不要虚构离线项目数据。

## 2026-11-04 宽屏复核环境

项目 `.venv` 安装了 Python Playwright，但其配套 Chromium 二进制不存在；无需下载新浏览器，使用 Playwright 的 `channel="msedge"` 在 headless 隔离上下文查看本机页面即可得到 1280×720 与 1440×900 截图。截图归档在 `artifacts/ui/`。工作流页若位于 `#__preview/workflow-editor`，是不能保存或运行的静态布局预览；宽屏签收只证明排版，不证明项目数据或运行状态。

## 2026-11-04 开发页与桌面包数据目录

开发态 `create_local_runtime_app()` 未传入 `root` 时默认写入 `Path.home()/.ict/runtime`；Windows 桌面 shell 显式使用 `%LOCALAPPDATA%/ICT/WorkflowWorkbench/runtime`。两者是独立数据库，不应把 Vite 空列表当作桌面包数据状态，也不要未经确认合并目录。当前开发数据库只读计数为 0 个项目/0 个工作流；桌面默认数据库当前未见 `local_projects` 表。平台 API 未运行时，没有本机副本或浏览器缓存的远端项目不可读取。先确认用户实际启动入口和项目来源，再判断路由还是数据可用性问题。

## 2026-11-04 无项目时从工作台创建本机项目

用户澄清当前没有现成项目，期望在软件使用过程中、平台服务未连接时直接创建首个本机项目。源码中工作台“本机项目”目录的“新建本机项目”入口走独立 local runtime，提交后进入详情页；联网不自动同步。用临时隔离 runtime 和临时 Vite 端口实点创建并刷新，项目仍可读取且没有页面脚本异常。此流程已在当前源码验证，无需索要项目 ID，也不应向用户真实 runtime 填入测试项目。用户可从“工作台 → 项目 → 本机项目 → 新建本机项目”开始。

## 2026-11-04 默认便携包 CSV 闭环验证

当前正式默认 EXE 的 SHA-256 为 `6898E6DE67577DD05637C3EAE68A325EFF85EEB29A890A4AC81FD9DEB611A9A6`。在隔离 `LOCALAPPDATA`、平台 API 关闭时，用包内工作台新建项目并实例化 CSV 模板；导入文件后必须点“保存到本机”才把源节点 ArtifactHandle 和参数一并落到工作流草稿，刷新后 artifact ID 可复读。校验与运行四节点成功，产出结构预检和描述统计两个非科研报告；停止并重启相同 EXE 后项目、revision 4 workflow、run 和报告仍在本机 SQLite/Artifact Store 中。本轮发现画布上的“产物”切换不是普通 button；用受认证本机 run/artifact API 核实内容，不以错误 locator 判定功能失败。隔离目录在 `%TEMP%/ict-default-package-audit-d4163bcb220d4d94a461c0ca6c935610`；开发入口恢复于 5173/8767。

## 2026-11-04 Crossref 网络验收环境记录

Windows 环境中 HTTPX 会从 WinINet 读取系统代理，即使 HTTP_PROXY/HTTPS_PROXY 环境变量未设置且 WinHTTP 显示 Direct。本机配置为 127.0.0.1:6987；本地 TCP 可连接，但 Crossref HTTPS 建连超时。节点正确把异常记为 NETWORK_TIMEOUT 并保留 WAITING_EXTERNAL 事件。不要为了通过验收绕过用户代理或盲目延长超时；live 请求失败后停止重试，等网络条件变化并重新取得授权。通过本地模拟响应可安全验证调度、报告写入与 429/503 错误码，不应把模拟结果当作真实 Crossref 查询。

- Crossref 超时复查：WinINet 的 127.0.0.1:6987 listener 属于 Xiaobai 的 innercore-x64.exe（当前 PID 33528）。本地 TCP 可达不代表代理上游 HTTPS 正常；没有检查或修改该应用的代理规则，live 请求失败后不重试。

## 2026-11-04 CSV 表头规范化与便携包验收

`manifest_quality.inspect_manifest` 已对 CSV 表头去首尾空白。下游 `local_csv_executor.py` 的字段选择与描述统计必须共用这一约定；统一后的空表头或重复列名应稳定失败，但不得修改单元格内容。回归文件 `backend/tests/test_local_csv_components.py` 覆盖带空格表头、摘要列名和修剪后重复列。当前便携包已重建并在隔离数据目录完成四节点运行；平台 API 断开时本机 CSV 链路可执行，两个输出均标记 `research_result=false`。本机草稿保存使用严格递增修订号：模板初始修订 1，首次改稿应提交 2；重复提交当前修订会按设计返回 409。

## 2026-11-04 断连工作台测试契约

`App.test.tsx` 应反映断连时“本机项目仍可使用”的当前产品契约，并给本机 runtime mock 返回有效 session 与项目列表；不可继续断言已经移除的“连接服务空页”。项目 API 假响应需实现 `headers.get('content-type')`，因为错误分类依赖 JSON 与 HTML 404 的区分。当前更新只修正测试夹具/断言，产品逻辑没有回退。修订后的全量前端 56 项通过、1 项跳过，后端全量 111 项通过，类型检查通过。

## 2026-11-04 CSV 文件夹批处理与默认参数脏状态

- 目录工作流契约：`ict.data.csv_folder_source@1.0.0` 输出强类型 `CsvFileCollectionRef`，`ict.data.quality_check@2.0.0` 输入该集合并输出逐文件 `CsvFolderQualityReportRef`。本机导入采用浏览器 `webkitdirectory`，递归处理 CSV，忽略非 CSV；工作流只保存目录相对路径和经授权 ArtifactHandle/哈希，不保存绝对路径或原始单元格。
- 当前限制：最多 200 个 CSV、合计 100 MiB，单文件沿用 100 MiB 导入上限。报告只含结构计数和状态，`research_result=false`。
- 工作流编辑器的脏状态比较要同时归一化当前图和保存图中的注册组件默认参数；只归一化当前图会把组件后来增加的默认值误判为用户修改。实现位于 `frontend/src/workflowDraft.ts`，`App.tsx` 用 `workflowState.data.graph` 作为持久化基线。
- 2026-11-04 隔离便携包已完成目录导入、保存、校验、运行、报告读取及同一数据目录重启复读；合成数据覆盖 3 个 CSV（含嵌套目录）和 1 个非 CSV。平台/外网请求 0、页面错误 0。新包输出位于 `desktop/dist/workflow-app-20261104-csv-folder/`，SHA-256 `E5BFCEEFE41A06C7B62CF71CE228C094281A69D27AE625A7146E13C7943E677C`；未覆盖默认包。

## 2026-11-04 最终包 v2 与旧草稿归一化补充

- `workflowDraftSnapshot` 还需复刻编辑器读取时对节点 category/title/description 和缺失 edge type 的默认值（`科研组件`、`未命名节点`、空描述、`smoothstep`）；只归一化组件参数仍会把历史草稿误报为已修改。
- 对旧图缺少上述字段的集成页面复核：最终 v2 包加载后状态为已保存，校验和再次运行成功；同一隔离 `%LOCALAPPDATA%` 重启后读取运行和三行报告成功，平台/外网请求和页面错误均为 0。
- 最终当前便携包在 `desktop/dist/workflow-app-20261104-csv-folder-v2/ICTWorkflowWorkbench.exe`，SHA-256 `B1D95BEB6468568BF5C1C0B3CB9AB66D6077E71C61A0DB9991AD800E9BC6DE65`。首次完整目录导入验收包仍保存在 `desktop/dist/workflow-app-20261104-csv-folder/`；二者均未覆盖默认 EXE。
