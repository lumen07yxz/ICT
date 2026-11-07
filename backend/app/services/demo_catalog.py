"""W0 通用合成演示目录；领域模块确定后由版本化仓储替换。"""

from pydantic import BaseModel, ConfigDict


class DemoProjectNotAllowed(Exception):
    """请求的项目不在公开演示白名单中。"""


class DemoProjectOverview(BaseModel):
    model_config = ConfigDict(frozen=True)

    project_id: str
    purpose: str
    data_status: str
    research_ready: bool
    dataset_versions: list[str]
    pipeline_templates: list[str]
    recent_public_runs: list[str]


def get_demo_project_overview(project_id: str) -> DemoProjectOverview:
    """仅返回固定合成项目，避免工具调用探测私有项目。"""
    if project_id != "demo-research":
        raise DemoProjectNotAllowed

    return DemoProjectOverview(
        project_id="demo-research",
        purpose="用于科研软件接口联调的合成样例；不代表真实数据或研究结论。",
        data_status="synthetic_only",
        research_ready=False,
        dataset_versions=["dataset-synthetic-v1"],
        pipeline_templates=["research-smoke-v1"],
        recent_public_runs=[],
    )
