# 本机工作流中断恢复实现计划

> 按项目规则由当前 Agent 顺序实施；不委派子代理、不创建 Git 提交。每项仅修改完成该恢复切片所需的文件。

**目标：** 在本机 Runtime 重启后，允许用户显式从原运行创建新运行，复用持久化成功节点输出，并沿原冻结 ExecutionPlan 调度未完成节点。

**架构：** SQLite 为每个恢复运行保存来源 run ID、冻结计划、恢复的节点输出和事件。调度器接受经过本机 Artifact Store 验证的恢复输出，把这些节点作为已完成依赖，成功节点在继续释放下游前原子保存输出和状态事件。API 只允许恢复 `LOCAL_WORKER_RESTARTED` 运行，并防止同一来源并发恢复；UI 在运行详情中提供明确的恢复动作。

**技术栈：** Python/FastAPI/SQLite asyncio，React/TypeScript，现有本机 Artifact Store 与 ExecutionPlan/cache。

---

## 文件职责

- `backend/app/services/local_runtime_store.py`：SQLite 增量兼容、来源运行关系、恢复运行创建、节点输出/事件事务写入。
- `backend/app/services/workflow_scheduler.py`：恢复输出注入、`RESTORED` 节点状态、成功输出持久化回调。
- `backend/app/local_runtime.py`：恢复路由、运行准入、防重复提交、复用现有后台运行监督。
- `backend/app/services/local_artifacts.py`：使用现有接口校验恢复输出中的 ArtifactHandle 和摘要。
- `frontend/src/api/localRuntime.ts`：恢复请求、来源 run 字段和 NodeRun 状态类型。
- `frontend/src/App.tsx` 与工作流运行详情样式：恢复条件、确认说明、恢复来源显示、失败反馈。
- `task.md`、`progress.md`：跟踪实现阶段和未验证项。

## 任务 1：持久化运行来源和节点结果

- [x] 以幂等 SQLite 增量方式为 `local_workflow_runs` 增加可空 `recovered_from_run_id`，不改写既有运行。
- [x] 添加同一 SQLite 连接事务内的节点完成写入：输出 JSON、节点状态、事件一次提交。
- [x] 增加恢复准备读取，返回来源运行冻结计划、来源错误码、成功节点输出和恢复来源标识。
- [x] 输出或事件写入失败时向调度器抛错；不让依赖节点消费一个未持久化成功的结果。

## 任务 2：支持恢复节点状态的 DAG 调度

- [x] 添加 `RESTORED` 节点状态，并将其作为依赖已满足状态。
- [x] 调度入口接受经验证的 `node_id -> output` 恢复映射；恢复节点从 ready queue 中排除，上游输出可供其下游使用。
- [x] `SUCCEEDED` 与 `CACHED` 的节点在下游可调度前调用持久化结果接口；避免普通事件回调和结果事务重复写完成事件。
- [x] 不在 scheduler 内自动重跑；恢复外部节点只能由 API 的显式恢复请求启动。

## 任务 3：增加本机恢复 API

- [x] 新增 `POST /api/v1/local/runs/{run_id}/recover`，仅允许来源状态为 `failed` 且错误码为 `LOCAL_WORKER_RESTARTED`。
- [x] 从原运行复制冻结的 `execution_plan_json`，重新执行本机准入，不使用当前工作流草稿；子运行有新 ID 但保持相同 `plan_hash`。
- [x] 验证恢复节点所引用 Artifact 的本机存在性与 SHA-256；不完整输出不标为 `RESTORED`，交由显式恢复运行重算/缓存命中。
- [x] 原子检查同一来源是否已有 queued/running/waiting_external 恢复子运行，重复请求不得启动并发副本。
- [x] 将恢复运行放入现有 `active_runs` 监督路径；只在收到该请求后启动。

## 任务 4：接入运行详情 UI

- [x] 在 `LocalWorkflowRun` 类型中加入恢复来源字段和 `RESTORED` 状态。
- [x] 仅对 `LOCAL_WORKER_RESTARTED` 的失败运行显示“恢复运行”；显示确认说明，指出会创建新运行且可能继续未完成的网络节点。
- [x] 成功恢复后刷新运行详情/列表，展示恢复来源、恢复节点数及需要重新调度的节点。
- [x] 复用现有运行事件、状态标签、错误提示和视觉样式，不创建新的一级导航。

## 任务 5：更新交付记录

- [x] 更新 `task.md` / `progress.md`，列明已实现范围及尚未运行的自动化测试/验收项。
- [x] 做源码差异与关键路径静态审阅，确认 API 不会在启动时自动执行、来源运行不可变、所有本地路径保持本机。
- [x] 不运行自动化测试或构建命令；本轮执行环境指令未授权测试/验证运行。若后续需要完整验收，由用户明确要求后再执行。

## 完成定义

代码覆盖用户显式恢复、计划快照、成功节点原子持久化、Artifact 校验、运行来源追踪、重复请求防重和 UI 状态说明。没有实现运行时暂停、自动重试、人工审批、平台 Worker 或跨设备恢复。自动化回归、构建和桌面包重建在用户授权验收前保持未执行。