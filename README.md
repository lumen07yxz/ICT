# ICT 模块化智能科研软件项目

本仓库保存 ICT 创新赛赛题二项目资料和正在实现的软件。当前 UI 开发主线为 React、TypeScript 与 Vite，产品导航、页面和功能边界以 [模块化智能科研平台开发统一方案 V4.0](<./人工文档方案/模块化智能科研平台_开发统一方案_V4.0.md>) 为准。项目工作流已支持草稿持久化、版本化组件契约、独立执行计划、按输出裁剪依赖图和 DAG 调度；本机已接入 CSV 清单结构预检，网络目标接入固定 Crossref DOI 公共元数据读取。运行记录与 ArtifactHandle 保存在独立本机 runtime；Crossref 结果明确不是科研结果，且每次运行前需要确认。完整科研检验证据链、平台 Worker 执行器及 Agent 审批执行仍未接入。Tkinter/ttk 桌面端代码保留为旧版实现，不再作为 V4.0 的 UI 主线。后端由 FastAPI/MCP、PostgreSQL/Alembic 和 Celery/Redis Worker 组成，目前同时包含合成演示数据与项目 API；合成数据不代表真实科研数据或研究结论。

## 从这里开始

先读[文档索引](<./文档索引.md>)了解资料顺序和维护边界，再按需要查看以下核心材料：

- [ICT 大赛规则](<./ict大赛规则.md>)：赛题要求、赛程、提交材料与评审标准。
- [科研现状分析](<./科研现状分析.md>)：科研流程痛点与项目背景。
- [模块化智能科研平台开发统一方案 V4.0](<./人工文档方案/模块化智能科研平台_开发统一方案_V4.0.md>)：当前产品、UI 和工程设计的统一开发准绳。
- [模块化智能科研软件项目方案（初步构思）](<./模块化智能科研软件项目方案（初步构思）.md>)：早期方案，供历史追溯；与 V4.0 冲突时以 V4.0 为准。
- [团队成员分工与阶段执行清单](<./团队成员分工与阶段执行清单.md>)：角色分工、周计划、交付物与验收门。
- [AgentArts 赛题二使用与接入指南](<./AgentArts赛题二使用与接入指南.md>)：平台配置、接入、评测和演示步骤。

## 本地启动

### Python 环境

后端 API、MCP 与 Worker 使用 Python 3.12。在项目根目录执行：

```powershell
py -3.12 -m venv .venv
.\.venv\Scripts\python.exe -m pip install --require-hashes -r backend\requirements.lock
.\.venv\Scripts\python.exe -m unittest discover -s backend\tests -p "test_*.py" -v
```

这些测试使用内存或临时 SQLite，不需要云账号、Docker、正式数据或数据库密码。

### PostgreSQL 与 API

安装并启动 Docker Compose 后，在项目根目录执行：

```powershell
.\scripts\init-local.ps1
docker compose up --build -d
docker compose logs -f api
```

初始化脚本在本机 `.env` 中生成互不相同的随机数据库密码、演示令牌、AgentArts MCP 密钥和服务间内部密钥；它不会覆盖已有 `.env`。`.env` 已被 Git 忽略，不要上传或发送。Compose 会等待 PostgreSQL 和 Redis 就绪，运行 Alembic 迁移、写入通用合成演示项目，再启动 API、MCP 和单并发 Worker。MCP 与 Worker 均不对外暴露端口；MCP 通过 `ICT_INTERNAL_API_KEY` 请求 API 创建提案并读取运行状态，AgentArts 使用的 `AGENTARTS_MCP_API_KEY` 与内部密钥不同。数据库端口不映射到主机；API 和 MCP 分别只绑定本机 `127.0.0.1:8765`、`127.0.0.1:8766`。

访问 `http://127.0.0.1:8765/health`、`http://127.0.0.1:8765/docs`。只读合成概览接口为 `GET /api/v1/demo/projects/demo-research/overview`。项目 API 为 `GET /api/v1/projects`、`GET /api/v1/projects/{project_id}` 和 `POST /api/v1/projects`；这些接口要求 `Authorization: Bearer <演示令牌>`。操作者令牌可创建项目，查看者令牌只有读取权限。演示令牌从本机 `.env` 读取，在 Swagger 页面点击 **Authorize** 后手动粘贴；不要把令牌写入仓库或聊天。

`demo-research` 和 `dataset-synthetic-v1` 都是合成占位数据，`research_ready=false`。它们不代表真实数据、正式许可、科研流程或研究结论。API 健康接口只表示 API 进程存活；MCP 健康接口为 `http://127.0.0.1:8766/health`。本地 MCP 地址是 `http://127.0.0.1:8766/mcp/`，请求需携带 `X-AgentArts-Key`，密钥从本机 `.env` 读取。

MCP 暴露三个固定工具：`get_demo_project_overview` 读取合成概览；`create_run_proposal` 只为 `demo-research`、`dataset-synthetic-v1` 和 `research-smoke-v1` 创建 15 分钟有效的 `pending_approval` 提案；`get_run_status` 只读查询已批准运行。AgentArts/MCP 没有审批或启动任务权限。旧版 Tk 客户端（仅兼容）的“智能体提案”页允许项目 `operator` 复核并批准，后端重新校验成员角色、提案有效期和配置摘要后只创建一个 queued run；`viewer` 只能读取。这不代表当前 React/V4.0 页面已经具备提案审批入口；该 UI 与 Agent 对话服务尚未接入。Celery Worker 执行固定的合成短任务，并记录 queued/running/succeeded/failed 四态及合成结果。对 AgentArts 填写 HTTPS MCP 地址并将 `AGENTARTS_MCP_API_KEY` 配置为 `X-AgentArts-Key` 请求头凭据；`ICT_INTERNAL_API_KEY` 只供 MCP 与 API 服务内部通信，不配置给 AgentArts。不要把任何密钥放进系统提示词、普通聊天或仓库。公网部署及 AgentArts 平台 Trace 尚未完成。

### 不使用 Docker 时

可直接运行不依赖数据库的健康和合成概览接口：

```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8765 --no-access-log
```

此模式下数据库项目接口会返回 `DATABASE_NOT_CONFIGURED`。要验证项目、身份和数据版本 API，请使用上面的 Compose 环境。

### React 主 UI 与本机工作流运行时

在项目根目录启动 React 主 UI：

```powershell
Set-Location frontend
npm install
npm run dev
```

比赛演示若需预览生产构建，可在 `npm run build` 后运行 `npm run preview:local`；该命令将生产静态页面与本机工作流 runtime 一起启动，默认页面地址为 `http://127.0.0.1:4173`。这仍依赖本机 Python 环境。Windows 便携版位于 `desktop/dist/workflow-app/ICTWorkflowWorkbench.exe`，其中包含 React 页面与 loopback runtime；当前交付为便携 EXE，未构建安装器。

`npm run dev` 会先启动独立的本机工作流运行时（127.0.0.1:8767），再启动 Vite；若检测到已有本机运行时，会复用它。该端口与 MCP 的 8766 分开。退出 Vite 时会一并关闭此脚本启动的运行时。运行时不依赖 8765 平台 API，默认将 SQLite 记录和本机 ArtifactHandle 文件保存在 `%USERPROFILE%\.ict\runtime`。已缓存的项目/工作流副本可离线打开；CSV 结构预检在本机运行。Crossref 网络节点只在用户确认并点击运行后访问固定 `api.crossref.org` 端点读取 DOI 公开元数据，不上传本机文件；平台云执行器尚未接入。当前首版已启用确定性 Input Signature 缓存、保守的单节点资源需求检查、每个运行最多两个并发节点和两个活动运行；重启后会将未完成任务记为 Worker 中断。资源检查是准入策略，不是操作系统级资源硬限制。

Vite 的 `/api` 请求仍代理到本机平台 API `127.0.0.1:8765`。连接平台后可读取和同步平台项目工作流；离线编辑保存在本机，恢复连接后需通过编辑器“同步到平台”。登录令牌只保存在当前页面会话内。本轮已接入工作流编译、选定输出目标、依赖闭包、就绪队列、本机 CSV 结构预检、固定 Crossref DOI 网络节点、运行历史/日志/产物引用展示及报告摘要。CSV 结构预检与 Crossref 书目元数据都明确标为“非科研结果”。模板市场和 Agent 对话继续按各自服务状态展示。

### 旧版 Windows 桌面客户端（兼容保留）

`desktop/` 中的 Tkinter/ttk 客户端仅为既有流程和历史演示保留，不属于 V4.0 当前 UI 主线。其旧导航、页面、配色和功能描述不作为当前产品要求；新功能以 V4.0 与 `frontend/README.md` 为准。

仅在运行或维护旧版客户端时，才需要额外安装 `desktop\requirements.lock` 中的依赖；它们不属于当前 React/V4.0 的后端启动依赖。

## 当前开发边界（React/V4.0）

- `frontend/` 是当前 React/Vite UI 主线；产品结构、导航与交互边界以 V4.0 为准，代码实际能力以 `frontend/README.md` 和当前源码为准。
- 当前前端已接入项目工作流草稿、图/组件契约校验、不可变版本、独立本机 DAG 运行和运行追溯；本机 CSV 与固定 Crossref DOI network executor 已接入。平台 Worker、完整科研检验和 Agent 审批执行尚未接入。模板市场读取独立的全局模板注册接口 `GET /api/v1/templates`，当前注册项仅用于合成数据联调；论文复现、Agent 对话及账号服务仍按实际状态显示。
- API 返回的合成数据必须保留其合成范围标识，不代表真实科研数据、研究结果或结论。
- `desktop/` 是兼容保留的旧 Tk 客户端，不定义 React 页面、当前产品导航或未来功能。

## 日志

API 请求日志记录请求 ID、路由模板、状态、耗时和稳定错误码，不记录 Authorization 头、请求正文或访问令牌。Uvicorn 使用 `--no-access-log` 避免默认日志输出未经脱敏的 URL。
