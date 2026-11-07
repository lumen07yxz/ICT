"""Typed literature workflow nodes and the fixed Crossref search adapter."""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from html.parser import HTMLParser
from typing import Any
from urllib.parse import quote, urlsplit

from pydantic import BaseModel, TypeAdapter, ValidationError

from app.services.network_crossref_executor import (
    CROSSREF_API_BASE,
    _field_text,
    _first_text,
    _published_date,
    fetch_crossref_message,
)
from app.services.workflow_scheduler import ExternalWait, WorkflowNodeFailure


logger = logging.getLogger("ict.local_runtime.api.literature")
LITERATURE_SEARCH_COMPONENT = "ict.paper.literature_search"
RESULT_OUTPUT_COMPONENT = "ict.paper.result_output"
LITERATURE_SEARCH_BINDING = "ict.network.literature_search"
RESULT_OUTPUT_BINDING = "ict.local.literature_result_output"
LITERATURE_SEARCH_PERMISSION = "network:crossref:search:read"
RESULT_OUTPUT_PERMISSION = "local:workflow:result:write"
DEFAULT_LIMIT = 20
MAX_LIMIT = 100
MAX_QUERY_LENGTH = 500


class Paper(BaseModel):
    """A normalized scholarly record; absent publisher fields stay absent."""

    title: str
    authors: list[str]
    publication_year: int | None
    journal_or_venue: str | None
    abstract: str | None
    doi: str | None
    url: str | None
    source: str


_PAPERS = TypeAdapter(list[Paper])


@dataclass(frozen=True)
class SearchOptions:
    query: str
    source: str
    start_year: int | None
    end_year: int | None
    limit: int
    sort: str


def parse_search_options(parameters: dict[str, Any]) -> SearchOptions:
    """Validate the editor's string parameters for both compilation and execution."""

    def number(key: str, low: int, high: int, code: str, label: str) -> int | None:
        raw = parameters.get(key)
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            return None
        value = raw.strip() if isinstance(raw, str) else ""
        if value.isascii() and value.isdecimal() and len(value) <= len(str(high)):
            parsed = int(value)
            if low <= parsed <= high:
                return parsed
        raise WorkflowNodeFailure(code, f"{label}必须是 {low} 至 {high} 的整数。")

    raw_query = parameters.get("query")
    query = raw_query.strip() if isinstance(raw_query, str) else ""
    if not query:
        raise WorkflowNodeFailure("PARAMETER_REQUIRED", "请填写参数“检索主题”。")
    if len(query) > MAX_QUERY_LENGTH:
        raise WorkflowNodeFailure("PARAMETER_MAX_LENGTH_EXCEEDED", f"检索主题最多 {MAX_QUERY_LENGTH} 个字符。")

    source = parameters.get("source", "Crossref")
    if source != "Crossref":
        raise WorkflowNodeFailure("LITERATURE_SOURCE_INVALID", "请选择已接入的检索数据源 Crossref。")
    sort = parameters.get("sort", "relevance")
    if sort not in ("relevance", "published"):
        raise WorkflowNodeFailure("LITERATURE_SORT_INVALID", "请选择按相关性或发表时间排序。")
    start = number("start_year", 1000, 9999, "LITERATURE_YEAR_INVALID", "起始年份")
    end = number("end_year", 1000, 9999, "LITERATURE_YEAR_INVALID", "结束年份")
    if start is not None and end is not None and start > end:
        raise WorkflowNodeFailure("LITERATURE_YEAR_RANGE_INVALID", "起始年份不能晚于结束年份。")
    limit = number("limit", 1, MAX_LIMIT, "LITERATURE_LIMIT_INVALID", "最大返回数量")
    return SearchOptions(query, source, start, end, limit or DEFAULT_LIMIT, sort)


class _AbstractText(HTMLParser):
    """Read the text of deposited JATS markup without rendering external HTML."""

    def __init__(self) -> None:
        super().__init__()
        self.parts: list[str] = []

    def handle_endtag(self, tag: str) -> None:
        if tag.rsplit(":", 1)[-1] in {"p", "title", "sec"}:
            self.parts.append(" ")

    def handle_data(self, data: str) -> None:
        self.parts.append(data)


def _author_name(author: dict[str, Any]) -> str:
    return _field_text(author.get("name")) or " ".join(
        part for field in ("given", "family") if (part := _field_text(author.get(field)))
    )


def _normalize_crossref_paper(item: dict[str, Any], title: str) -> Paper:
    abstract = _AbstractText()
    if isinstance(item.get("abstract"), str):
        abstract.feed(item["abstract"])
        abstract.close()
    authors = item.get("author")
    published = {field: item.get(field) for field in ("published", "issued")}
    publication_date = _published_date(published)
    event = item.get("event")
    doi = _field_text(item.get("DOI"))
    url = _field_text(item.get("URL"), limit=4000)
    if url:
        try:
            parts = urlsplit(url)
            if parts.scheme not in ("https", "http") or not parts.hostname or parts.username or parts.password:
                url = None
        except ValueError:
            url = None
    return Paper(
        title=title,
        authors=[name for author in authors if isinstance(author, dict) and (name := _author_name(author))]
        if isinstance(authors, list) else [],
        publication_year=int(publication_date[:4]) if publication_date else None,
        journal_or_venue=_first_text(item.get("container-title")) or (
            _field_text(event.get("name")) if isinstance(event, dict) else None
        ),
        abstract=" ".join("".join(abstract.parts).split()) or None,
        doi=doi,
        url=url or ("https://doi.org/" + quote(doi, safe="/") if doi else None),
        source="Crossref",
    )


async def _search_crossref(options: SearchOptions, node_id: str) -> list[Paper]:
    filters = ["type:journal-article", "type:proceedings-article", "type:posted-content"]
    if options.start_year is not None:
        filters.append(f"from-pub-date:{options.start_year}-01-01")
    if options.end_year is not None:
        filters.append(f"until-pub-date:{options.end_year}-12-31")
    params = {
        "query.bibliographic": options.query,
        "rows": options.limit,
        "sort": "score" if options.sort == "relevance" else "published",
        "order": "desc",
        "filter": ",".join(filters),
        "select": "title,DOI,URL,author,container-title,event,published,issued,abstract",
    }
    message = await fetch_crossref_message(CROSSREF_API_BASE.rstrip("/"), node_id, params=params)
    items = message.get("items")
    if not isinstance(items, list) or any(not isinstance(item, dict) for item in items):
        raise WorkflowNodeFailure("NETWORK_RESPONSE_INVALID", "Crossref 未返回有效的文献列表。")
    papers = [
        _normalize_crossref_paper(item, title)
        for item in items[:options.limit]
        if (title := _first_text(item.get("title"))) is not None
    ]
    logger.info("literature_search_completed node_id=%s source=%s received=%s returned=%s", node_id, options.source, len(items), len(papers))
    return papers


def _persistable_result(node: dict[str, Any], inputs: dict[str, Any]) -> dict[str, Any]:
    # The scheduler commits this node's output to the run record before marking it succeeded.
    try:
        papers = _PAPERS.validate_python(inputs.get("items"), strict=True)
    except ValidationError as error:
        raise WorkflowNodeFailure("LITERATURE_INPUT_INVALID", "结果输出未收到有效的上游文献列表。") from error
    logger.info("literature_result_received run_id=%s node_id=%s paper_count=%s", node.get("_runtime_run_id"), node.get("id"), len(papers))
    return {"papers": _PAPERS.dump_python(papers, mode="json")}


def build_literature_executors(request_semaphore: asyncio.Semaphore) -> dict[str, Any]:
    async def search(node: dict[str, Any]) -> dict[str, Any]:
        options = parse_search_options(node["parameters"])
        async with request_semaphore:
            papers = await _search_crossref(options, node["id"])
        return {"papers": _PAPERS.dump_python(papers, mode="json")}

    def dispatch_search(node: dict[str, Any], _inputs: dict[str, Any]) -> ExternalWait:
        return ExternalWait(search(node), operation_code="CROSSREF_LITERATURE_SEARCH")

    return {LITERATURE_SEARCH_BINDING: dispatch_search, RESULT_OUTPUT_BINDING: _persistable_result}
