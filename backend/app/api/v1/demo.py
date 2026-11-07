"""只读演示接口；MCP wrapper 以后调用同一个服务函数。"""

from fastapi import APIRouter

from app.services.demo_catalog import DemoProjectOverview, get_demo_project_overview


router = APIRouter(prefix="/api/v1/demo", tags=["demo"])


@router.get("/projects/{project_id}/overview", response_model=DemoProjectOverview)
def read_demo_project_overview(project_id: str) -> DemoProjectOverview:
    return get_demo_project_overview(project_id)
