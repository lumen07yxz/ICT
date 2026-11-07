"""MCP proposal tests verify the public tool forwards only a fixed pending proposal."""

import asyncio
import json
import re
import sys
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import httpx
from mcp import Client


BACKEND_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(BACKEND_DIR))


class InternalProposalHandler(BaseHTTPRequestHandler):
    received_headers: dict[str, str] = {}
    received_body: dict[str, object] = {}
    response_payload = {
        "id": "123e4567-e89b-12d3-a456-426614174000",
        "project_id": "123e4567-e89b-12d3-a456-426614174001",
        "dataset_version": "dataset-synthetic-v1",
        "pipeline_template": "research-smoke-v1",
        "parameters": {"sample_limit": 7},
        "config_sha256": "a" * 64,
        "trace_id": "123e4567-e89b-12d3-a456-426614174030",
        "status": "pending_approval",
        "approved_by": None,
        "approved_at": None,
        "run_id": None,
        "created_at": "2026-10-17T12:00:00Z",
        "expires_at": "2026-10-17T12:15:00Z",
    }
    response_status = 201
    delay_seconds = 0
    received_get_path = None
    run_status_payload = {
        "id": "123e4567-e89b-12d3-a456-426614174020",
        "proposal_id": "123e4567-e89b-12d3-a456-426614174010",
        "project_id": "123e4567-e89b-12d3-a456-426614174001",
        "dataset_version": "dataset-synthetic-v1",
        "pipeline_template": "research-smoke-v1",
        "parameters": {"sample_limit": 7},
        "config_sha256": "a" * 64,
        "quality_status": "success",
        "quality_rule_set_version": "generic-manifest-v1",
        "quality_report_sha256": "b" * 64,
        "trace_id": "123e4567-e89b-12d3-a456-426614174030",
        "status": "succeeded",
        "result": {
            "task": "synthetic_smoke",
            "processed_count": 7,
            "synthetic_only": True,
            "research_ready": False,
            "message": "集成冒烟任务完成。",
        },
        "error_code": None,
        "created_at": "2026-10-17T12:00:00Z",
        "started_at": "2026-10-17T12:00:01Z",
        "finished_at": "2026-10-17T12:00:02Z",
    }

    def do_POST(self):
        if type(self).delay_seconds:
            time.sleep(type(self).delay_seconds)
        type(self).received_headers = dict(self.headers.items())
        body = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        type(self).received_body = json.loads(body.decode("utf-8"))
        encoded = json.dumps(type(self).response_payload).encode("utf-8")
        self.send_response(type(self).response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        try:
            self.wfile.write(encoded)
        except BrokenPipeError:
            # A timeout test deliberately closes the client side before this response.
            pass

    def do_GET(self):
        type(self).received_get_path = self.path
        encoded = json.dumps(type(self).run_status_payload).encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, _format, *_args):
        return


class McpRunProposalTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.http_server = ThreadingHTTPServer(("127.0.0.1", 0), InternalProposalHandler)
        cls.http_thread = threading.Thread(target=cls.http_server.serve_forever, daemon=True)
        cls.http_thread.start()
        cls.api_url = f"http://127.0.0.1:{cls.http_server.server_port}/internal/v1/run-proposals"

    @classmethod
    def tearDownClass(cls):
        cls.http_server.shutdown()
        cls.http_server.server_close()
        cls.http_thread.join(timeout=2)

    def setUp(self):
        InternalProposalHandler.received_headers = {}
        InternalProposalHandler.received_body = {}
        InternalProposalHandler.response_status = 201
        InternalProposalHandler.delay_seconds = 0
        InternalProposalHandler.received_get_path = None

    def test_idempotency_scope_is_stable_for_retries_and_separates_sessions_and_arguments(self):
        from app.mcp_service import _proposal_idempotency_key

        payload = {
            "project_id": "demo-research",
            "dataset_version": "dataset-synthetic-v1",
            "pipeline_template": "research-smoke-v1",
            "sample_limit": 7,
        }
        retry = _proposal_idempotency_key("request-1", payload, "session-a")

        self.assertEqual(retry, _proposal_idempotency_key("request-1", payload, "session-a"))
        self.assertNotEqual(retry, _proposal_idempotency_key("request-2", payload, "session-a"))
        self.assertNotEqual(retry, _proposal_idempotency_key("request-1", payload, "session-b"))
        self.assertNotEqual(
            retry,
            _proposal_idempotency_key("request-1", {**payload, "sample_limit": 8}, "session-a"),
        )
        self.assertRegex(retry, re.compile(r"^[a-f0-9]{64}$"))

    def create_app(
        self,
        *,
        internal_key: str | None = "internal-only-key",
        timeout: float = 5.0,
    ):
        from app.mcp_service import create_mcp_app

        return create_mcp_app(
            api_key="agentarts-public-key",
            internal_api_key=internal_key,
            backend_api_url=self.api_url,
            backend_timeout_seconds=timeout,
            allowed_hosts=["testserver", "testserver:*"],
        )

    def test_create_tool_has_strict_fixed_schema_and_calls_internal_api_with_separate_key(self):
        app = self.create_app()

        async def inspect_tools_and_call():
            async with Client(app.state.mcp_server) as client:
                tool_list = await client.list_tools()
                result = await client.call_tool(
                    "create_run_proposal",
                    {
                        "project_id": "demo-research",
                        "dataset_version": "dataset-synthetic-v1",
                        "pipeline_template": "research-smoke-v1",
                        "sample_limit": 7,
                    },
                )
                return tool_list.tools, result

        tools, result = asyncio.run(inspect_tools_and_call())
        proposal_tool = next(tool for tool in tools if tool.name == "create_run_proposal")

        self.assertIn("get_demo_project_overview", [tool.name for tool in tools])
        self.assertFalse(proposal_tool.annotations.read_only_hint)
        self.assertFalse(proposal_tool.annotations.destructive_hint)
        self.assertEqual(proposal_tool.input_schema["additionalProperties"], False)
        self.assertEqual(
            set(proposal_tool.input_schema["required"]),
            {"project_id", "dataset_version", "pipeline_template", "sample_limit"},
        )
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "pending_approval")
        self.assertEqual(InternalProposalHandler.received_body["sample_limit"], 7)
        self.assertEqual(InternalProposalHandler.received_headers["X-Ict-Internal-Key"], "internal-only-key")
        self.assertNotEqual(InternalProposalHandler.received_headers["X-Ict-Internal-Key"], "agentarts-public-key")
        idempotency_key = InternalProposalHandler.received_headers["Idempotency-Key"]
        self.assertRegex(idempotency_key, re.compile(r"^[a-f0-9]{64}$"))

    def test_run_status_tool_is_strict_read_only_and_uses_private_api_key(self):
        app = self.create_app()

        async def list_and_read():
            async with Client(app.state.mcp_server) as client:
                tools = await client.list_tools()
                result = await client.call_tool(
                    "get_run_status",
                    {"run_id": "123e4567-e89b-12d3-a456-426614174020"},
                )
                invalid = await client.call_tool("get_run_status", {"run_id": "not-a-uuid"})
                return tools.tools, result, invalid

        tools, result, invalid = asyncio.run(list_and_read())
        tool = next(item for item in tools if item.name == "get_run_status")
        self.assertNotIn("approve_run_proposal", [item.name for item in tools])
        self.assertTrue(tool.annotations.read_only_hint)
        self.assertTrue(tool.annotations.idempotent_hint)
        self.assertEqual(tool.input_schema["additionalProperties"], False)
        self.assertEqual(set(tool.input_schema["required"]), {"run_id"})
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["status"], "succeeded")
        self.assertTrue(result.structured_content["result"]["synthetic_only"])
        self.assertEqual(
            InternalProposalHandler.received_get_path,
            "/internal/v1/runs/123e4567-e89b-12d3-a456-426614174020",
        )
        self.assertTrue(invalid.is_error)

    def test_authenticated_streamable_http_call_reaches_the_internal_api(self):
        app = self.create_app()

        async def send_request():
            async with app.router.lifespan_context(app):
                transport = httpx.ASGITransport(app=app)
                async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
                    return await client.post(
                        "/mcp/",
                        headers={
                            "Accept": "application/json",
                            "Mcp-Method": "tools/call",
                            "Mcp-Name": "create_run_proposal",
                            "MCP-Protocol-Version": "2026-07-28",
                            "X-AgentArts-Key": "agentarts-public-key",
                        },
                        json={
                            "jsonrpc": "2.0",
                            "id": "agentarts-request-1",
                            "method": "tools/call",
                            "params": {
                                "name": "create_run_proposal",
                                "arguments": {
                                    "project_id": "demo-research",
                                    "dataset_version": "dataset-synthetic-v1",
                                    "pipeline_template": "research-smoke-v1",
                                    "sample_limit": 11,
                                },
                                "_meta": {
                                    "io.modelcontextprotocol/protocolVersion": "2026-07-28",
                                    "io.modelcontextprotocol/clientInfo": {
                                        "name": "agentarts-contract-test",
                                        "version": "1.0.0",
                                    },
                                    "io.modelcontextprotocol/clientCapabilities": {},
                                },
                            },
                        },
                    )

        response = asyncio.run(send_request())

        self.assertEqual(response.status_code, 200, response.text)
        result = response.json()["result"]
        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"]["status"], "pending_approval")
        self.assertEqual(InternalProposalHandler.received_body["sample_limit"], 11)
        self.assertEqual(
            InternalProposalHandler.received_headers["X-Ict-Internal-Key"],
            "internal-only-key",
        )

    def test_invalid_tool_arguments_are_rejected_before_the_backend_request(self):
        app = self.create_app()

        async def call_invalid():
            async with Client(app.state.mcp_server) as client:
                invalid_id = await client.call_tool(
                    "create_run_proposal",
                    {
                        "project_id": "private-project",
                        "dataset_version": "dataset-synthetic-v1",
                        "pipeline_template": "research-smoke-v1",
                        "sample_limit": 7,
                    },
                )
                extra_field = await client.call_tool(
                    "create_run_proposal",
                    {
                        "project_id": "demo-research",
                        "dataset_version": "dataset-synthetic-v1",
                        "pipeline_template": "research-smoke-v1",
                        "sample_limit": 7,
                        "unexpected": "not allowed",
                    },
                )
                return invalid_id, extra_field

        results = asyncio.run(call_invalid())
        self.assertTrue(all(result.is_error for result in results))
        self.assertEqual(InternalProposalHandler.received_body, {})

    def test_missing_internal_key_fails_closed_without_exposing_service_details(self):
        app = self.create_app(internal_key=None)

        async def call_tool():
            async with Client(app.state.mcp_server) as client:
                return await client.call_tool(
                    "create_run_proposal",
                    {
                        "project_id": "demo-research",
                        "dataset_version": "dataset-synthetic-v1",
                        "pipeline_template": "research-smoke-v1",
                        "sample_limit": 7,
                    },
                )

        result = asyncio.run(call_tool())
        error_text = " ".join(block.text for block in result.content if hasattr(block, "text"))
        self.assertTrue(result.is_error)
        self.assertIn("提案服务尚未配置", error_text)
        self.assertNotIn("internal-only-key", error_text)
        self.assertEqual(InternalProposalHandler.received_body, {})

    def test_internal_api_timeout_returns_a_safe_tool_error(self):
        app = self.create_app(timeout=0.03)
        InternalProposalHandler.delay_seconds = 0.2

        async def call_tool():
            async with Client(app.state.mcp_server) as client:
                return await client.call_tool(
                    "create_run_proposal",
                    {
                        "project_id": "demo-research",
                        "dataset_version": "dataset-synthetic-v1",
                        "pipeline_template": "research-smoke-v1",
                        "sample_limit": 7,
                    },
                )

        result = asyncio.run(call_tool())
        error_text = " ".join(block.text for block in result.content if hasattr(block, "text"))

        self.assertTrue(result.is_error)
        self.assertIn("提案服务响应超时", error_text)
        self.assertNotIn(self.api_url, error_text)
        self.assertNotIn("internal-only-key", error_text)


if __name__ == "__main__":
    unittest.main()
