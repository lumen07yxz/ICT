export interface WorkflowRunErrorDetails {
  reason: string
  impact: string
  nextStep: string
}

const ERROR_DETAILS: Readonly<Record<string, WorkflowRunErrorDetails>> = {
  EXTERNAL_WAIT_TIMEOUT: {
    reason: '外部操作等待超时',
    impact: '此节点已失败；依赖它的下游已阻断，独立分支仍可继续。',
    nextStep: '检查网络或外部服务后重试。',
  },
  NODE_EXECUTION_TIMEOUT: {
    reason: '节点执行器报告超时',
    impact: '此节点未完成；依赖它的下游已阻断，独立分支仍可继续。',
    nextStep: '检查组件日志、输入规模和资源设置后重试。',
  },
  DEPENDENCY_FAILED: {
    reason: '上游节点未成功',
    impact: '当前节点未运行；不依赖该分支的节点不受影响。',
    nextStep: '查看失败节点的错误说明，修复后重新运行。',
  },
  EXECUTION_TARGET_UNAVAILABLE: {
    reason: '执行目标不可用',
    impact: '此节点未执行；依赖它的下游已阻断，独立分支仍可继续。',
    nextStep: '连接所需执行端，或选择当前可用的执行目标。',
  },
  EXECUTOR_UNAVAILABLE: {
    reason: '本机执行器不可用',
    impact: '此节点未运行；依赖它的下游已阻断。',
    nextStep: '安装或启用匹配版本的组件执行器后重试。',
  },
  NODE_EXECUTION_FAILED: {
    reason: '节点执行失败',
    impact: '此节点没有生成可用结果；依赖它的下游已阻断。',
    nextStep: '查看节点事件和本机运行时日志后重试。',
  },
  SCHEDULER_TASK_FAILED: {
    reason: '调度任务异常',
    impact: '尚未完成的相关节点已停止调度。',
    nextStep: '检查本机运行时日志，确认运行时可用后重试。',
  },
  RUN_CANCELLED: {
    reason: '运行已取消',
    impact: '未完成节点已停止调度；已完成节点和产物记录保留。',
    nextStep: '调整工作流后可重新运行。',
  },
  LOCAL_WORKER_TASK_CRASHED: {
    reason: '本机运行任务异常退出',
    impact: '本次运行未完成。',
    nextStep: '查看本机运行时日志；运行时恢复后重新运行。',
  },
  LOCAL_WORKER_RESTARTED: {
    reason: '本机运行时在执行期间重启',
    impact: '尚未完成的节点已标记失败。',
    nextStep: '确认本机运行时正常后重新运行。',
  },
  LOCAL_RUNTIME_EXECUTION_FAILED: {
    reason: '本机工作流执行失败',
    impact: '本次运行未完成。',
    nextStep: '查看本机运行时日志后重试。',
  },
  LOCAL_RUN_PERSISTENCE_FAILED: {
    reason: '运行记录保存失败',
    impact: '运行状态或产物溯源可能不完整。',
    nextStep: '检查本机存储空间和运行时日志后再运行。',
  },
  ARTIFACT_AUTHORIZATION_REQUIRED: {
    reason: '本机产物没有有效授权',
    impact: '此节点没有读取该文件，也没有生成派生产物。',
    nextStep: '重新导入文件，并确认你有权在本机处理。',
  },
  ARTIFACT_CONTENT_HASH_MISMATCH: {
    reason: '本机产物内容校验失败',
    impact: '文件内容与登记时的 SHA-256 不一致，节点没有使用该产物。',
    nextStep: '从原始文件重新导入，并重新运行。',
  },
  ARTIFACT_CSV_REQUIRED: {
    reason: '输入产物不是 CSV 文件',
    impact: 'CSV 节点无法读取该输入，后续依赖节点会阻断。',
    nextStep: '连接已授权的本机 CSV 产物。',
  },
  ARTIFACT_EMPTY: {
    reason: '本机 CSV 产物为空',
    impact: '节点没有可处理的数据或可用派生产物。',
    nextStep: '确认输入文件包含内容后重新导入。',
  },
  ARTIFACT_FILE_MISSING: {
    reason: '本机产物文件不可用',
    impact: '节点无法读取登记的文件，依赖它的下游已阻断。',
    nextStep: '重新导入原始文件后重跑。',
  },
  ARTIFACT_FILE_NAME_INVALID: {
    reason: '本机文件名不符合要求',
    impact: '文件没有导入或派生产物没有保存。',
    nextStep: '为文件使用有效的 CSV 文件名后重新选择。',
  },
  ARTIFACT_NOT_FOUND: {
    reason: '本机产物不存在或已移除',
    impact: '节点无法读取输入，依赖它的下游已阻断。',
    nextStep: '重新导入文件并更新节点引用。',
  },
  ARTIFACT_PRODUCER_INVALID: {
    reason: '本机产物缺少有效来源节点',
    impact: '系统无法为派生产物建立完整来源记录。',
    nextStep: '检查本机运行时日志后重新运行。',
  },
  ARTIFACT_RUN_INVALID: {
    reason: '本机产物的运行来源无效',
    impact: '系统无法确认产物对应的运行记录。',
    nextStep: '检查本机运行时日志后重新运行。',
  },
  ARTIFACT_SIZE_MISMATCH: {
    reason: '本机产物大小与记录不一致',
    impact: '系统无法确认文件完整性，因此不会继续处理。',
    nextStep: '重新导入原始文件后重跑。',
  },
  ARTIFACT_SOURCE_REQUIRED: {
    reason: '派生产物缺少来源 CSV',
    impact: '节点无法建立数据溯源，也没有保存输出。',
    nextStep: '为节点连接一个有效的本机 CSV 输入。',
  },
  ARTIFACT_STORAGE_KEY_INVALID: {
    reason: '本机产物索引无效',
    impact: '系统拒绝访问该存储位置，节点没有读取或保存文件。',
    nextStep: '检查本机运行时存储状态和日志。',
  },
  ARTIFACT_STREAM_INVALID: {
    reason: '本机文件读取流无效',
    impact: '节点没有完成文件读取或保存派生产物。',
    nextStep: '重新选择本机文件；若仍失败，检查运行时日志。',
  },
  ARTIFACT_TOO_LARGE: {
    reason: '本机产物超过大小上限',
    impact: '文件没有导入或派生产物没有保存。',
    nextStep: '缩小或拆分文件后重试。',
  },
  LOCAL_CHECKER_UNAVAILABLE: {
    reason: '本机 CSV 结构检查器不可用',
    impact: '结构预检报告没有生成。',
    nextStep: '确认本机安装包完整并重启运行时。',
  },
  LOCAL_STORE_UNAVAILABLE: {
    reason: '本机产物存储不可用',
    impact: '节点无法读取输入或持久化输出。',
    nextStep: '检查本机存储空间、目录权限和运行时日志。',
  },
  LOCAL_ARTIFACT_WRITE_FAILED: {
    reason: '本机产物写入失败',
    impact: '派生文件或结构报告没有保存。',
    nextStep: '检查本机存储空间和目录权限后重跑。',
  },
  REPORT_NOT_SERIALIZABLE: {
    reason: '结构报告无法安全保存',
    impact: '本次运行没有生成可追溯的报告产物。',
    nextStep: '检查组件输出和本机运行时日志。',
  },
  REPORT_EMPTY: {
    reason: '结构报告内容为空',
    impact: '本次运行没有生成可查看的报告。',
    nextStep: '检查输入数据和报告生成节点后重跑。',
  },
  REPORT_TOO_LARGE: {
    reason: '结构报告超过本机保存上限',
    impact: '本次运行没有保存报告产物。',
    nextStep: '缩减报告内容后重跑。',
  },
  REPORT_PRODUCER_INVALID: {
    reason: '结构报告缺少来源节点',
    impact: '本机没有保存该报告，来源无法追溯。',
    nextStep: '检查本机运行时日志后重新运行。',
  },
  REPORT_RUN_INVALID: {
    reason: '结构报告的运行来源无效',
    impact: '本机没有保存无法关联运行记录的报告。',
    nextStep: '检查本机运行时日志后重新运行。',
  },
  REPORT_FILE_NAME_INVALID: {
    reason: '结构报告文件名不受支持',
    impact: '本次运行没有保存报告。',
    nextStep: '使用内置报告节点重新生成报告。',
  },
  REPORT_AUTHORIZATION_INVALID: {
    reason: '结构报告授权状态无效',
    impact: '本机拒绝保存此报告。',
    nextStep: '使用有效的本机授权输入重新运行。',
  },
  ARTIFACT_REPORT_TOO_LARGE: {
    reason: '本机报告超过查看上限',
    impact: '产物面板没有读取报告内容。',
    nextStep: '缩减报告内容后重新生成，或查看本机运行时日志。',
  },
  ARTIFACT_REPORT_TYPE_UNSUPPORTED: {
    reason: '产物类型不受支持',
    impact: '产物面板没有显示该文件内容。',
    nextStep: '选择与此报告类型匹配的内置查看入口。',
  },
  ARTIFACT_REPORT_UNREADABLE: {
    reason: '本机报告文件无法读取',
    impact: '产物面板没有显示报告内容。',
    nextStep: '重新运行对应节点；若仍失败，检查本机运行时日志。',
  },
  NETWORK_TIMEOUT: {
    reason: 'Crossref 请求超时',
    impact: '文献元数据节点失败；依赖它的下游已阻断。',
    nextStep: '检查网络后重试。',
  },
  NETWORK_UNAVAILABLE: {
    reason: '无法连接 Crossref',
    impact: '文献元数据节点失败；依赖它的下游已阻断。',
    nextStep: '检查网络连接后重试。',
  },
  NETWORK_RATE_LIMITED: {
    reason: 'Crossref 暂时限流',
    impact: '文献元数据节点未完成。',
    nextStep: '等待一段时间后重试。',
  },
  NETWORK_ACCESS_DENIED: {
    reason: 'Crossref 拒绝了请求',
    impact: '文献元数据节点未完成。',
    nextStep: '稍后重试，或核对当前网络是否允许访问 Crossref。',
  },
  NETWORK_UPSTREAM_ERROR: {
    reason: 'Crossref 服务暂时异常',
    impact: '文献元数据节点未完成。',
    nextStep: '稍后重试。',
  },
  NETWORK_HTTP_ERROR: {
    reason: 'Crossref 返回了无法处理的状态',
    impact: '文献元数据没有生成。',
    nextStep: '核对 DOI；确认无误后稍后重试。',
  },
  NETWORK_REDIRECT_REJECTED: {
    reason: 'Crossref 返回的重定向已被拒绝',
    impact: '请求没有跟随跳转，文献元数据没有生成。',
    nextStep: '稍后重试；运行时只允许访问固定的 Crossref 地址。',
  },
  NETWORK_RESPONSE_INVALID: {
    reason: 'Crossref 返回的元数据无效',
    impact: '系统无法解析此响应，文献元数据没有生成。',
    nextStep: '核对 DOI，稍后重新查询。',
  },
  NETWORK_RESPONSE_TOO_LARGE: {
    reason: 'Crossref 响应超过读取上限',
    impact: '系统已停止读取，文献元数据没有生成。',
    nextStep: '核对 DOI；若仍超限，请查看本机运行时日志。',
  },
  NETWORK_RESULT_PERSIST_FAILED: {
    reason: '文献元数据已读取但保存失败',
    impact: '本机没有留下可追溯的元数据产物。',
    nextStep: '检查本机存储空间和目录权限后重新运行。',
  },
  NETWORK_DEPENDENCY_UNAVAILABLE: {
    reason: '本机缺少网络组件依赖',
    impact: '文献元数据节点未运行。',
    nextStep: '安装组件声明的网络依赖后重试。',
  },
  CROSSREF_DOI_REQUIRED: {
    reason: '尚未填写 DOI',
    impact: '文献元数据节点未运行。',
    nextStep: '填写有效 DOI 后重新运行。',
  },
  CROSSREF_DOI_INVALID: {
    reason: 'DOI 格式无效',
    impact: '文献元数据节点未运行。',
    nextStep: '检查 DOI 前缀和字符后重新运行。',
  },
  CROSSREF_DOI_NOT_FOUND: {
    reason: 'Crossref 中没有找到此 DOI',
    impact: '没有生成文献元数据产物。',
    nextStep: '核对 DOI 是否正确，或在出版方页面确认文献记录。',
  },
  CSV_COLUMNS_REQUIRED: {
    reason: '尚未填写要保留的 CSV 字段',
    impact: '字段选择节点未生成派生文件。',
    nextStep: '填写一个或多个字段名后重新运行。',
  },
  CSV_COLUMNS_DUPLICATE: {
    reason: 'CSV 字段列表包含重复名称',
    impact: '字段选择节点未生成派生文件。',
    nextStep: '移除重复字段名后重新运行。',
  },
  CSV_ARTIFACT_REQUIRED: {
    reason: '尚未选择本机 CSV 产物',
    impact: 'CSV 节点没有输入，依赖它的下游未运行。',
    nextStep: '导入 CSV 并将产物连接到此节点。',
  },
  CSV_COLUMNS_INVALID: {
    reason: '保留字段列表格式无效',
    impact: '字段选择节点未生成派生文件。',
    nextStep: '移除空字段名，并用英文逗号分隔字段。',
  },
  CSV_COLUMNS_NOT_FOUND: {
    reason: 'CSV 中找不到指定字段',
    impact: '字段选择节点未生成派生文件。',
    nextStep: '对照 CSV 表头检查字段拼写和空格。',
  },
  CSV_ROW_WIDTH_MISMATCH: {
    reason: 'CSV 数据行字段数量不一致',
    impact: '字段选择节点没有生成派生产物。',
    nextStep: '修正列数不一致的数据行后重新导入。',
  },
  manifest_unreadable: {
    reason: '清单文件无法读取',
    impact: '本机结构预检未生成报告。',
    nextStep: '确认文件仍可读取后重新导入；若仍失败，检查文件权限。',
  },
  manifest_header_missing: {
    reason: 'CSV 清单缺少表头',
    impact: '本机结构预检无法识别字段，也没有生成报告。',
    nextStep: '在第一行补齐 CSV 表头和必需列后重新导入。',
  },
  manifest_header_duplicate: {
    reason: 'CSV 清单表头有重复或空白列名',
    impact: '本机结构预检无法可靠定位字段，也没有生成报告。',
    nextStep: '修改表头，确保每个列名非空且唯一。',
  },
  missing_required_columns: {
    reason: 'CSV 清单缺少必需列',
    impact: '结构预检无法按通用清单格式检查数据。',
    nextStep: '按通用清单格式补齐必需列后重新导入。',
  },
  invalid_encoding: {
    reason: 'CSV 清单编码无法识别',
    impact: '本机结构预检没有生成报告。',
    nextStep: '将清单另存为 UTF-8 CSV 后重新导入。',
  },
  invalid_csv: {
    reason: 'CSV 清单格式无法解析',
    impact: '本机结构预检没有生成报告。',
    nextStep: '检查分隔符和引号是否成对，修正后重新导入。',
  },
  manifest_changed: {
    reason: '检查过程中清单文件发生变化',
    impact: '本次预检结果无效，没有生成报告。',
    nextStep: '重新导入一份稳定的文件副本后再次运行。',
  },
  CSV_HEADER_EMPTY: {
    reason: 'CSV 文件没有字段行',
    impact: '本机结构预检无法读取数据表结构。',
    nextStep: '提供包含字段名的 CSV 文件后重试。',
  },
  CSV_HEADER_INVALID: {
    reason: 'CSV 字段行包含空字段名',
    impact: '本机结构预检无法可靠识别各列。',
    nextStep: '补齐字段名后重新导入。',
  },
  CSV_COLUMN_LIMIT_EXCEEDED: {
    reason: 'CSV 字段数量超过本机摘要上限',
    impact: '描述统计节点没有读取整张表或生成部分报告。',
    nextStep: '仅保留当前分析需要的字段后再运行摘要。',
  },
  CSV_HEADER_DUPLICATE: {
    reason: 'CSV 文件包含重复字段名',
    impact: '字段选择和后续结构检查可能无法准确定位列。',
    nextStep: '修改 CSV 表头使字段名唯一后重新导入。',
  },
  CSV_ENCODING_INVALID: {
    reason: 'CSV 文件不是 UTF-8 编码',
    impact: '本机无法安全读取文件内容。',
    nextStep: '将文件另存为 UTF-8 编码后重新导入。',
  },
  CSV_PARSE_FAILED: {
    reason: 'CSV 格式无法解析',
    impact: '本机节点未生成可用产物。',
    nextStep: '检查分隔符、引号和每行字段数后重新导入。',
  },
  CSV_READ_FAILED: {
    reason: '本机 CSV 无法读取',
    impact: '本机节点未生成可用产物。',
    nextStep: '确认文件仍在本机授权产物库中，再重新导入。',
  },
  CSV_WRITE_FAILED: {
    reason: '本机派生 CSV 写入失败',
    impact: '字段选择节点没有生成派生文件。',
    nextStep: '检查本机存储空间和目录权限后重试。',
  },
}

const UNKNOWN_ERROR: WorkflowRunErrorDetails = {
  reason: '运行未能完成',
  impact: '节点没有生成成功结果；依赖它的下游可能未运行。',
  nextStep: '查看错误代码和本机运行时日志后重试。',
}

export function workflowRunErrorDetails(code: string): WorkflowRunErrorDetails {
  return ERROR_DETAILS[code] ?? UNKNOWN_ERROR
}
