"""Render a self-contained, synthetic-only HTML report for a finished run."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import escape
from html.parser import HTMLParser
from io import BytesIO

from .api import Run, RunEvent


REPORT_TEMPLATE_VERSION = "synthetic-run-report-v3"
_STATUS_LABELS = {"succeeded": "已完成", "failed": "运行失败"}
_EVENT_STATUS_LABELS = {
    "queued": "排队中",
    "running": "运行中",
    "succeeded": "已完成",
    "failed": "运行失败",
}
_EVENT_ERROR_CODES = {"QUEUE_UNAVAILABLE", "WORKER_EXECUTION_FAILED"}


@dataclass(frozen=True)
class _PdfBlock:
    """A small semantic block parsed from the canonical HTML report."""

    kind: str
    text: str = ""
    class_name: str | None = None
    rows: tuple[tuple[tuple[str, str], ...], ...] = ()


class _ReportPdfParser(HTMLParser):
    """Convert the report's fixed HTML structure into safe text/table blocks."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.blocks: list[_PdfBlock] = []
        self._ignored_depth = 0
        self._capture_tag: str | None = None
        self._capture_class: str | None = None
        self._capture_text: list[str] = []
        self._table_rows: list[tuple[tuple[str, str], ...]] | None = None
        self._current_row: list[tuple[str, str]] | None = None
        self._cell_tag: str | None = None
        self._cell_text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in ("style", "script"):
            self._ignored_depth += 1
            return
        if self._ignored_depth:
            return
        if tag == "table":
            self._table_rows = []
        elif tag == "tr" and self._table_rows is not None:
            self._current_row = []
        elif tag in ("th", "td") and self._current_row is not None:
            self._cell_tag = tag
            self._cell_text = []
        elif tag in ("h1", "h2", "p", "li", "footer"):
            self._capture_tag = tag
            self._capture_class = dict(attrs).get("class")
            self._capture_text = []

    def handle_data(self, data: str) -> None:
        if self._ignored_depth:
            return
        if self._cell_tag is not None:
            self._cell_text.append(data)
        elif self._capture_tag is not None:
            self._capture_text.append(data)

    def handle_endtag(self, tag: str) -> None:
        if self._ignored_depth:
            if tag in ("style", "script"):
                self._ignored_depth -= 1
            return
        if tag in ("th", "td") and self._cell_tag == tag and self._current_row is not None:
            self._current_row.append((tag, "".join(self._cell_text).strip()))
            self._cell_tag = None
            self._cell_text = []
        elif tag == "tr" and self._current_row is not None and self._table_rows is not None:
            self._table_rows.append(tuple(self._current_row))
            self._current_row = None
        elif tag == "table" and self._table_rows is not None:
            self.blocks.append(_PdfBlock(kind="table", rows=tuple(self._table_rows)))
            self._table_rows = None
        elif tag == self._capture_tag and self._capture_tag is not None:
            kind = {
                "h1": "title",
                "h2": "heading",
                "p": "paragraph",
                "li": "list_item",
                "footer": "footer",
            }[tag]
            self.blocks.append(
                _PdfBlock(
                    kind=kind,
                    text="".join(self._capture_text).strip(),
                    class_name=self._capture_class,
                )
            )
            self._capture_tag = None
            self._capture_class = None
            self._capture_text = []


def _text(value: object | None) -> str:
    """Escape every value from a run before placing it in an HTML text node."""
    if value is None or value == "":
        return "未登记"
    return escape(str(value), quote=True)


def _row(label: str, value: object | None) -> str:
    return f"<tr><th scope=\"row\">{_text(label)}</th><td>{_text(value)}</td></tr>"


def _render_status_events(events: list[RunEvent] | None) -> str:
    """Render validated lifecycle events or an explicit unavailable state."""
    if events is None:
        return '<p class="muted">导出时未能取得运行状态事件，报告未包含事件记录。</p>'
    if not events:
        return '<p class="muted">服务端未提供状态事件记录。</p>'
    if len(events) > 3:
        raise ValueError("运行状态事件数量超出固定状态机范围。")

    expected_statuses = {1: "queued", 2: "running"}
    previous_sequence = 0
    rows: list[str] = []
    for event in events:
        if not isinstance(event, RunEvent):
            raise ValueError("运行状态事件格式无效。")
        sequence = event.sequence
        if type(sequence) is not int or sequence not in (1, 2, 3):
            raise ValueError("运行状态事件格式无效。")
        expected_status = expected_statuses.get(sequence)
        if sequence == 3 and event.status in ("succeeded", "failed"):
            expected_status = event.status
        if (
            sequence <= previous_sequence
            or event.status != expected_status
            or (
                event.error_code is not None
                and (
                    not isinstance(event.error_code, str)
                    or event.error_code not in _EVENT_ERROR_CODES
                )
            )
            or (event.status != "failed" and event.error_code is not None)
            or not isinstance(event.occurred_at, str)
            or not event.occurred_at
        ):
            raise ValueError("运行状态事件格式无效。")
        try:
            occurred_at = datetime.fromisoformat(event.occurred_at.replace("Z", "+00:00"))
        except ValueError as exc:
            raise ValueError("运行状态事件时间格式无效。") from exc
        if occurred_at.tzinfo is None or occurred_at.utcoffset() is None:
            raise ValueError("运行状态事件时间必须包含时区。")

        rows.append(
            "<tr>"
            f"<td>{_text(sequence)}</td>"
            f"<td>{_text(_EVENT_STATUS_LABELS[event.status])}</td>"
            f"<td>{_text(event.occurred_at)}</td>"
            f"<td>{_text(event.error_code)}</td>"
            "</tr>"
        )
        previous_sequence = sequence

    return (
        "<table><thead><tr><th scope=\"col\">序号</th><th scope=\"col\">状态</th>"
        "<th scope=\"col\">发生时间（UTC）</th><th scope=\"col\">安全错误码</th></tr></thead>"
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def render_run_report(
    run: Run,
    generated_at: datetime | None = None,
    events: list[RunEvent] | None = None,
) -> str:
    """Render only allowlisted run fields; never infer absent research evidence."""
    if run.status not in _STATUS_LABELS:
        raise ValueError("仅能为已结束的运行生成报告。")

    created = generated_at or datetime.now(timezone.utc)
    if created.tzinfo is None or created.utcoffset() is None:
        raise ValueError("报告生成时间必须包含时区。")
    generated = created.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")

    if run.quality_status is None:
        quality_status = "未记录"
        quality_rule_set = "未登记"
        quality_digest = "未登记"
    else:
        quality_status = run.quality_status
        quality_rule_set = run.quality_rule_set_version
        quality_digest = run.quality_report_sha256

    if run.status == "succeeded":
        expected_result_fields = {
            "task",
            "processed_count",
            "synthetic_only",
            "research_ready",
            "message",
        }
        result = run.result
        if (
            not isinstance(result, dict)
            or set(result) != expected_result_fields
            or result.get("task") != "synthetic_smoke"
            or type(result.get("processed_count")) is not int
            or result["processed_count"] != run.parameters.get("sample_limit")
            or result.get("synthetic_only") is not True
            or result.get("research_ready") is not False
            or not isinstance(result.get("message"), str)
        ):
            raise ValueError("成功运行缺少有效的固定合成结果快照。")
        result_summary = (
            "<ul>"
            f"<li>处理合成样例数：{_text(result.get('processed_count'))}</li>"
            f"<li>任务信息：{_text(result.get('message'))}</li>"
            "</ul>"
        )
    else:
        result_summary = (
            "<p>任务未成功完成，没有可报告的处理数量或评价指标。</p>"
            f"<p>安全错误码：{_text(run.error_code)}</p>"
        )

    rows = "".join(
        (
            _row("运行 ID", run.run_id),
            _row("提案 ID", run.proposal_id),
            _row("项目 ID", run.project_id),
            _row("服务 Trace ID（非 AgentArts 平台 Trace）", run.trace_id),
            _row("运行状态", _STATUS_LABELS[run.status]),
            _row("创建时间", run.created_at),
            _row("开始时间", run.started_at),
            _row("结束时间", run.finished_at),
            _row("配置 SHA-256", run.config_sha256),
            _row("报告模板版本", REPORT_TEMPLATE_VERSION),
        )
    )
    event_timeline = _render_status_events(events)

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'">
  <meta name="report-template-version" content="{_text(REPORT_TEMPLATE_VERSION)}">
  <title>ICT 研究工作台 · 合成运行报告</title>
  <style>
    :root {{ color-scheme: light; font-family: "Microsoft YaHei UI", "Segoe UI", sans-serif; color: #243b39; background: #f4f2eb; }}
    body {{ margin: 0; padding: 32px 18px; }}
    main {{ max-width: 900px; margin: 0 auto; padding: 36px; background: #fffefa; border: 1px solid #dedfd5; border-radius: 14px; }}
    h1 {{ margin: 4px 0 12px; font-size: 30px; }}
    h2 {{ margin: 28px 0 10px; font-size: 18px; }}
    .eyebrow, .muted {{ color: #747a72; }}
    .notice {{ padding: 14px 16px; background: #f2eee2; border-left: 4px solid #a45f42; }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{ padding: 10px 12px; border-bottom: 1px solid #dedfd5; text-align: left; vertical-align: top; overflow-wrap: anywhere; }}
    th {{ width: 220px; color: #59645b; font-weight: 600; }}
    .result {{ padding: 14px 16px; background: #f8f6f0; border-radius: 8px; }}
    footer {{ margin-top: 32px; padding-top: 16px; border-top: 1px solid #dedfd5; font-size: 13px; color: #747a72; }}
    @media print {{ body {{ padding: 0; background: white; }} main {{ max-width: none; border: 0; border-radius: 0; padding: 18mm; }} }}
  </style>
</head>
<body>
  <main>
    <header>
      <p class="eyebrow">ICT 研究工作台 · 本地报告导出</p>
      <h1>合成冒烟运行报告</h1>
      <p class="notice">本报告只记录固定合成集成冒烟任务，不代表科研结论、模型性能或医学结论。</p>
    </header>
    <section>
      <h2>运行溯源</h2>
      <table><tbody>{rows}</tbody></table>
    </section>
    <section>
      <h2>方法与数据</h2>
      <table><tbody>
        {_row("研究目标", "未登记；当前仅验证固定冒烟模板的受控运行与状态回传")}
        {_row("数据来源", "本地固定合成演示样例")}
        {_row("数据版本", run.dataset_version)}
        {_row("数据拆分方案", "未登记；合成冒烟任务不执行科研数据拆分")}
        {_row("研究就绪状态", "research_ready=false")}
        {_row("固定模板", run.pipeline_template)}
        {_row("模板参数", f"sample_limit={run.parameters.get('sample_limit', '未登记')}")}
        {_row("组件/模型版本", "未登记；本任务不加载或训练模型")}
      </tbody></table>
    </section>
    <section>
      <h2>质量检查快照</h2>
      <table><tbody>
        {_row("质量状态", quality_status)}
        {_row("质量规则版本", quality_rule_set)}
        {_row("质量报告 SHA-256", quality_digest)}
      </tbody></table>
    </section>
    <section>
      <h2>运行状态时间线</h2>
      {event_timeline}
    </section>
    <section>
      <h2>运行结果与证据</h2>
      <div class="result">{result_summary}</div>
      <table><tbody>
        {_row("科研评价指标", "未生成；此冒烟任务不执行模型评价")}
        {_row("论文主张/证据来源", "未登记")}
      </tbody></table>
    </section>
    <section>
      <h2>限制</h2>
      <ul>
        <li>数据为合成演示样例，不包含 NCCCU 或其他真实医学数据。</li>
        <li>运行不执行模型推理、训练、Study 聚合或正式评价。</li>
        <li>报告只反映本次运行记录中的字段；缺失信息明确标记为未登记或未生成。</li>
      </ul>
    </section>
    <footer>生成时间（UTC）：{_text(generated)} · 报告模板：{_text(REPORT_TEMPLATE_VERSION)}</footer>
  </main>
</body>
</html>
"""


def render_run_pdf(
    run: Run,
    generated_at: datetime | None = None,
    events: list[RunEvent] | None = None,
) -> bytes:
    """Render the canonical synthetic-only report as a local PDF."""
    report_html = render_run_report(run, generated_at=generated_at, events=events)
    try:
        from reportlab.lib import colors
        from reportlab.lib.enums import TA_LEFT
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import ParagraphStyle
        from reportlab.lib.units import mm
        from reportlab.pdfbase import pdfmetrics
        from reportlab.pdfbase.cidfonts import UnicodeCIDFont
        from reportlab.platypus import (
            Paragraph,
            SimpleDocTemplate,
            Spacer,
            Table,
            TableStyle,
        )
    except ImportError as exc:
        raise RuntimeError("PDF 导出依赖缺失，请重新安装桌面客户端。") from exc

    font_name = "STSong-Light"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        pdfmetrics.registerFont(UnicodeCIDFont(font_name))

    parser = _ReportPdfParser()
    parser.feed(report_html)
    parser.close()
    footer_text = next((block.text for block in parser.blocks if block.kind == "footer"), None)
    if not footer_text:
        raise ValueError("报告缺少生成时间页脚。")

    ink = colors.HexColor("#243b39")
    muted = colors.HexColor("#747a72")
    clay = colors.HexColor("#a45f42")
    line = colors.HexColor("#dedfd5")
    pale = colors.HexColor("#f2eee2")
    styles = {
        "title": ParagraphStyle(
            "ICTReportTitle",
            fontName=font_name,
            fontSize=21,
            leading=29,
            textColor=ink,
            alignment=TA_LEFT,
            spaceAfter=8,
            wordWrap="CJK",
        ),
        "eyebrow": ParagraphStyle(
            "ICTReportEyebrow",
            fontName=font_name,
            fontSize=8,
            leading=12,
            textColor=muted,
            spaceAfter=4,
            wordWrap="CJK",
        ),
        "body": ParagraphStyle(
            "ICTReportBody",
            fontName=font_name,
            fontSize=9,
            leading=14,
            textColor=ink,
            spaceAfter=5,
            wordWrap="CJK",
        ),
        "muted": ParagraphStyle(
            "ICTReportMuted",
            fontName=font_name,
            fontSize=8.5,
            leading=13,
            textColor=muted,
            spaceAfter=5,
            wordWrap="CJK",
        ),
        "notice": ParagraphStyle(
            "ICTReportNotice",
            fontName=font_name,
            fontSize=9,
            leading=15,
            textColor=ink,
            backColor=pale,
            borderColor=clay,
            borderWidth=2,
            borderPadding=9,
            spaceAfter=12,
            wordWrap="CJK",
        ),
        "heading": ParagraphStyle(
            "ICTReportHeading",
            fontName=font_name,
            fontSize=12,
            leading=18,
            textColor=ink,
            spaceBefore=10,
            spaceAfter=5,
            keepWithNext=True,
            wordWrap="CJK",
        ),
        "cell": ParagraphStyle(
            "ICTReportCell",
            fontName=font_name,
            fontSize=8.2,
            leading=12,
            textColor=ink,
            wordWrap="CJK",
        ),
        "label": ParagraphStyle(
            "ICTReportLabel",
            fontName=font_name,
            fontSize=8.2,
            leading=12,
            textColor=colors.HexColor("#59645b"),
            wordWrap="CJK",
        ),
        "table_header": ParagraphStyle(
            "ICTReportTableHeader",
            fontName=font_name,
            fontSize=8,
            leading=11,
            textColor=colors.HexColor("#59645b"),
            wordWrap="CJK",
        ),
    }

    def paragraph(text: str, style: ParagraphStyle) -> Paragraph:
        # HTML entities are decoded by HTMLParser, so escape again before ReportLab parses markup.
        return Paragraph(escape(text, quote=True), style)

    def table_flowable(block: _PdfBlock) -> Table:
        rows = [list(row) for row in block.rows]
        event_table = bool(rows and len(rows[0]) == 4 and all(cell[0] == "th" for cell in rows[0]))
        if event_table:
            data = [
                [paragraph(value, styles["table_header"]) for _tag, value in row]
                if row_index == 0
                else [paragraph(value, styles["cell"]) for _tag, value in row]
                for row_index, row in enumerate(rows)
            ]
            column_widths = [12 * mm, 28 * mm, 84 * mm, 50 * mm]
        else:
            data = [
                [paragraph(row[0][1], styles["label"]), paragraph(row[1][1], styles["cell"])]
                for row in rows
                if len(row) >= 2
            ]
            column_widths = [45 * mm, 129 * mm]

        table = Table(
            data,
            colWidths=column_widths,
            hAlign="LEFT",
            repeatRows=1 if event_table else 0,
        )
        table_commands = [
            ("GRID", (0, 0), (-1, -1), 0.35, line),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LEFTPADDING", (0, 0), (-1, -1), 7),
            ("RIGHTPADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]
        if event_table:
            table_commands.extend(
                [
                    ("BACKGROUND", (0, 0), (-1, 0), pale),
                    ("LINEBELOW", (0, 0), (-1, 0), 0.7, line),
                ]
            )
        else:
            table_commands.append(("BACKGROUND", (0, 0), (0, -1), pale))
        table.setStyle(TableStyle(table_commands))
        return table

    story: list[object] = []
    for block in parser.blocks:
        if block.kind == "footer":
            continue
        if block.kind == "table":
            story.extend((table_flowable(block), Spacer(1, 5)))
            continue
        if block.kind == "title":
            story.extend((paragraph(block.text, styles["title"]), Spacer(1, 2)))
        elif block.kind == "heading":
            story.append(paragraph(block.text, styles["heading"]))
        elif block.kind == "list_item":
            story.append(paragraph(f"- {block.text}", styles["body"]))
        elif block.kind == "paragraph":
            if block.class_name == "eyebrow":
                style_name = "eyebrow"
            elif block.class_name == "notice":
                style_name = "notice"
            elif block.class_name == "muted":
                style_name = "muted"
            else:
                style_name = "body"
            story.append(paragraph(block.text, styles[style_name]))
            if block.class_name == "notice":
                story.append(Spacer(1, 2))

    output = BytesIO()

    def draw_footer(canvas: object, document: object) -> None:
        canvas.saveState()
        canvas.setStrokeColor(line)
        canvas.setLineWidth(0.5)
        canvas.line(document.leftMargin, 17 * mm, A4[0] - document.rightMargin, 17 * mm)
        canvas.setFillColor(muted)
        canvas.setFont(font_name, 6.7)
        canvas.drawString(document.leftMargin, 10 * mm, footer_text)
        canvas.drawRightString(A4[0] - document.rightMargin, 10 * mm, f"第 {document.page} 页")
        canvas.restoreState()

    document = SimpleDocTemplate(
        output,
        pagesize=A4,
        leftMargin=18 * mm,
        rightMargin=18 * mm,
        topMargin=16 * mm,
        bottomMargin=23 * mm,
        title="ICT 研究工作台 - 合成冒烟运行报告",
        author="ICT Research Workbench",
        subject=f"Synthetic run report; template {REPORT_TEMPLATE_VERSION}",
    )
    document.build(story, onFirstPage=draw_footer, onLaterPages=draw_footer)
    return output.getvalue()
