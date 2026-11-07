"""MCP contract and access-control tests use only the synthetic demo project."""

import asyncio
import sys
import unittest
from pathlib import Path

import httpx
from mcp import Client


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


class MCPServiceTests(unittest.TestCase):
    def setUp(self) -> None:
        try:
            from app.mcp_service import create_mcp_app
        except ModuleNotFoundError as exc:
            self.fail(f"Remote read-only MCP service is not implemented yet: {exc}")

        self.api_key = "mcp-test-key-that-must-not-be-logged"
        self.app = create_mcp_app(
            api_key=self.api_key,
            allowed_hosts=["testserver", "testserver:*"]
        )
        self.server = self.app.state.mcp_server

    def request(
        self,
        method: str,
        path: str,
        *,
        start_lifespan: bool = True,
        **kwargs,
    ) -> httpx.Response:
        async def send() -> httpx.Response:
            async def send_request() -> httpx.Response:
                transport = httpx.ASGITransport(app=self.app)
                async with httpx.AsyncClient(
                    transport=transport,
                    base_url="http://testserver",
                ) as client:
                    return await client.request(method, path, **kwargs)

            if start_lifespan:
                async with self.app.router.lifespan_context(self.app):
                    return await send_request()
            return await send_request()

        return asyncio.run(send())

    def test_valid_mcp_key_allows_discovery_without_logging_key(self) -> None:
        rpc_request = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/list",
            "params": {
                "_meta": {
                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                    "io.modelcontextprotocol/clientInfo": {
                        "name": "ict-test-client",
                        "version": "1.0.0",
                    },
                    "io.modelcontextprotocol/clientCapabilities": {},
                }
            },
        }
        with self.assertLogs("ict.mcp", level="INFO") as captured:
            response = self.request(
                "POST",
                "/mcp/",
                headers={
                    "Accept": "application/json",
                    "Mcp-Method": "tools/list",
                    "MCP-Protocol-Version": "2026-07-28",
                    "X-AgentArts-Key": self.api_key,
                },
                json=rpc_request,
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(
            [tool["name"] for tool in response.json()["result"]["tools"]],
            ["get_demo_project_overview", "create_run_proposal", "get_run_status"],
        )
        logged = "\n".join(captured.output)
        self.assertIn("request_id=", logged)
        self.assertNotIn(self.api_key, response.text)
        self.assertNotIn(self.api_key, logged)

    def test_authenticated_http_tool_call_returns_synthetic_overview(self) -> None:
        response = self.request(
            "POST",
            "/mcp/",
            headers={
                "Accept": "application/json",
                "Mcp-Method": "tools/call",
                "Mcp-Name": "get_demo_project_overview",
                "MCP-Protocol-Version": "2026-07-28",
                "X-AgentArts-Key": self.api_key,
            },
            json={
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {
                    "name": "get_demo_project_overview",
                    "arguments": {"project_id": "demo-research"},
                    "_meta": {
                        "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                        "io.modelcontextprotocol/clientInfo": {
                            "name": "ict-test-client",
                            "version": "1.0.0",
                        },
                        "io.modelcontextprotocol/clientCapabilities": {},
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["project_id"], "demo-research")
        self.assertEqual(result["structuredContent"]["data_status"], "synthetic_only")
        self.assertFalse(result["structuredContent"]["research_ready"])

    def test_missing_or_invalid_mcp_key_is_rejected(self) -> None:
        missing = self.request("POST", "/mcp/", start_lifespan=False, json={})
        invalid = self.request(
            "POST",
            "/mcp/",
            start_lifespan=False,
            headers={"X-AgentArts-Key": "wrong-secret"},
            json={},
        )

        self.assertEqual(missing.status_code, 401)
        self.assertEqual(invalid.status_code, 401)
        self.assertEqual(invalid.json()["error"]["code"], "MCP_UNAUTHORIZED")
        self.assertNotIn("wrong-secret", invalid.text)

    def test_mcp_auth_fails_closed_when_key_is_not_configured(self) -> None:
        from app.mcp_service import create_mcp_app

        unconfigured_app = create_mcp_app(
            api_key="",
            allowed_hosts=["testserver", "testserver:*"],
        )

        async def send_request() -> httpx.Response:
            transport = httpx.ASGITransport(app=unconfigured_app)
            async with httpx.AsyncClient(
                transport=transport,
                base_url="http://testserver",
            ) as client:
                return await client.post("/mcp/", json={})

        response = asyncio.run(send_request())

        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.json()["error"]["code"], "MCP_AUTH_NOT_CONFIGURED")

    def test_mcp_host_allowlist_rejects_unapproved_hostnames(self) -> None:
        response = self.request(
            "POST",
            "/mcp/",
            headers={
                "Host": "attacker.example",
                "X-AgentArts-Key": self.api_key,
            },
            json={},
        )

        self.assertEqual(response.status_code, 421)

    def test_discovery_exposes_fixed_tools_and_synthetic_read_result(self) -> None:
        async def call_tool() -> tuple[list, object]:
            async with Client(self.server) as client:
                tools = await client.list_tools()
                result = await client.call_tool(
                    "get_demo_project_overview",
                    {"project_id": "demo-research"},
                )
                return tools.tools, result

        tools, result = asyncio.run(call_tool())

        self.assertEqual(
            [tool.name for tool in tools],
            ["get_demo_project_overview", "create_run_proposal", "get_run_status"],
        )
        self.assertTrue(tools[0].annotations.read_only_hint)
        self.assertFalse(tools[0].annotations.destructive_hint)
        self.assertFalse(tools[1].annotations.read_only_hint)
        self.assertFalse(tools[1].annotations.destructive_hint)
        self.assertTrue(tools[2].annotations.read_only_hint)
        self.assertTrue(tools[2].annotations.idempotent_hint)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["data_status"], "synthetic_only")
        self.assertFalse(result.structured_content["research_ready"])

    def test_unknown_project_fails_without_echoing_the_requested_id(self) -> None:
        private_id = "private-project-123"

        async def call_tool() -> object:
            async with Client(self.server) as client:
                return await client.call_tool(
                    "get_demo_project_overview",
                    {"project_id": private_id},
                )

        result = asyncio.run(call_tool())
        error_text = "\n".join(block.text for block in result.content if hasattr(block, "text"))

        self.assertTrue(result.is_error)
        self.assertIn("项目不可用", error_text)
        self.assertNotIn(private_id, error_text)


if __name__ == "__main__":
    unittest.main()
