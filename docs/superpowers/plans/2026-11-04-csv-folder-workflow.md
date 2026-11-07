# 本机 CSV 文件夹工作流实施计划

> **执行方式：**当前会话内分步实施。项目说明要求未经明确请求不派发子代理、不执行 git commit。

**目标：**在电脑端工作流画布中选择一个本机目录，把其中的 CSV 逐文件交给本机质量检查节点处理，并查看每个文件的结果及汇总报告。

**架构：**文件选择只通过桌面浏览器的目录选择器发生；CSV 内容逐个复制到本机内容寻址 Artifact Store，工作流源节点把文件相对路径和 ArtifactHandle 列表保存为节点参数。类型化 `CsvFileCollectionRef` 由目录来源节点输出，质量检查节点流式处理集合并生成本机 JSON 报告；不读取任意绝对路径、不访问平台 API、不上传数据。

**技术栈：**React/TypeScript、现有 loopback FastAPI runtime、SQLite/本机 Artifact Store、Python 标准库 `csv`/`sqlite3`。

**工作流数据契约：**

```json
{
  "folder_name": "dataset",
  "files": [
    {
      "relative_path": "dataset/train.csv",
      "artifact_id": "本机产物 ID",
      "sha256": "64 位文件哈希",
      "size_bytes": 128
    }
  ]
}
```

集合只保存相对路径和已授权产物引用；文件内容仍存放在本机 Artifact Store。首版限制为最多 200 个 CSV、合计不超过 100 MiB、单文件服从现有 100 MiB 导入限制。目录内非 CSV 文件在选择后展示跳过数量；目录选择递归包含子目录。

**质量报告契约：**报告包含 `report_type=csv_folder_quality_v1`、`research_result=false`、规则配置、每个文件的相对路径/哈希/行列数/缺失统计/重复键数/状态，以及整体通过/警告/阻断计数；不保存任何原始单元格值。指定唯一键时用临时 SQLite 保存键的 SHA-256，单文件完成后关闭并清理临时库。

---

### 任务 1：注册文件夹集合节点与质量检查契约

**文件：**
- 修改：`backend/app/services/workflow_components.py`
- 修改：`backend/app/services/local_csv_executor.py`
- 修改：`backend/app/services/local_execution_cache.py`
- 修改：`backend/app/services/local_resource_admission.py`

- [x] 新增 `ict.data.csv_folder_source`：必填参数 `files_json`，输出 `CsvFileCollectionRef`，执行器校验文件数量、相对路径、产物存在性、内容哈希、授权状态和总大小。
- [x] 将不可运行的 `ict.data.quality_check` 更新为版本 `2.0.0`：输入 `CsvFileCollectionRef`，输出 `CsvFolderQualityReportRef`，参数为可选必需列、唯一键列和 `max_missing_rate`。
- [x] 注册本机 executor binding；缓存签名和资源准入在解析 `files_json` 后逐个纳入 ArtifactHandle 哈希与大小。

### 任务 2：实现逐文件质量检查与持久报告读取

**文件：**
- 修改：`backend/app/services/local_csv_executor.py`
- 修改：`backend/app/services/local_artifacts.py`
- 修改：`backend/app/local_runtime.py`

- [x] 使用流式 CSV 读取检查编码/解析、空或重复列名、行宽、配置必需列、缺失率和唯一键；一个文件失败时记录该文件错误并继续处理其他文件。
- [x] 仅把输入哈希、相对路径、计数、状态和规则写入报告；报告 ArtifactHandle 绑定来源运行/节点。
- [x] 为 `csv-folder-quality-report.json` 增加受限读取 API，校验媒体类型、文件名、授权、哈希和报告类型。

### 任务 3：接入桌面目录选择、进度、模板与报告界面

**文件：**
- 修改：`frontend/src/api/localRuntime.ts`
- 修改：`frontend/src/App.tsx`
- 修改：`backend/app/services/local_workflow_templates.py`

- [x] 在文件夹来源节点检查栏使用 `webkitdirectory` 目录选择器；递归筛选 CSV，显示数量/体积/跳过文件数，逐个导入并显示进度。
- [x] 将目录名、相对路径与 ArtifactHandle 信息保存进来源节点参数；导入失败时给出失败文件名和错误码，不创建不完整集合。
- [x] 新增两节点本机模板“CSV 文件夹逐文件质量检查”：文件夹来源 → 质量检查。
- [x] 运行产物栏可读取汇总报告，并按通过/警告/阻断展示逐文件结果。

### 任务 4：本机闭环验收和记录

**文件：**
- 更新：`task.md`
- 更新：`task_plan.md`
- 更新：`progress.md`
- 更新：`memory/ict/workflow-runtime.md`

- [x] `npm run typecheck` 与 `npm run build` 通过；新增默认参数/旧草稿归一化回归 3 项通过；后端变更模块通过 `py_compile`。
- [x] 在隔离 runtime 和合成目录上手工走通：递归选择 3 个 CSV（含子目录）及 1 个非 CSV → 导入 → 保存工作流 → 校验 → 运行 → 查看逐文件/汇总报告 → 重启后重读工作流、运行和报告。
- [x] 确认平台 API/外部主机请求为 0、页面错误为 0、工作流报告明确 `research_result=false`；大小上限为最多 200 个 CSV、合计 100 MiB、单文件 100 MiB。
- [x] 在隔离新输出目录构建便携包，不覆盖原 EXE；首个包完成文件夹 UI 全路径，最终 v2 包位于 `desktop/dist/workflow-app-20261104-csv-folder-v2/ICTWorkflowWorkbench.exe`，在同一隔离数据目录复读旧草稿、再次运行并经 runtime 重启复读报告。最终包 SHA-256：`B1D95BEB6468568BF5C1C0B3CB9AB66D6077E71C61A0DB9991AD800E9BC6DE65`。
