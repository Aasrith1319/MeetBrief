"""Meeting exports (F61): Markdown, JSON, plain text and PDF.

Personal notes are exported in their own section, separate from AI-generated content.
"""
from __future__ import annotations

import io
import json
import re
from datetime import datetime

from backend.models import MeetingMemory, Segment
from backend.nlp.text_utils import format_time


def to_markdown(meeting: dict, segments: list[Segment], memory: MeetingMemory, summary: str, notes: list[dict],
                include_transcript: bool = True) -> str:
    created = datetime.fromtimestamp(meeting["created_at"]).strftime("%Y-%m-%d %H:%M")
    lines = [f"# {meeting['title']}", "", f"*Exported from MeetBrief AI — meeting created {created}; "
             f"source: {meeting.get('source_type')}; {len(segments)} transcript segments.*", "",
             "> AI-generated content below is linked to transcript segments [S…]. Verify important items against the transcript.", "",
             "## Summary (AI-generated)", "", summary, ""]
    lines += ["## Decisions", ""]
    for d in memory.decisions:
        lines.append(f"- **{d.status}** — {d.summary} (by {d.speaker or 'unknown'}, {format_time(d.timestamp)}) "
                     f"[{', '.join(d.evidence_segments)}]" + (f" — supersedes {d.supersedes}" if d.supersedes else ""))
    if not memory.decisions:
        lines.append("- None identified")
    lines += ["", "## Action items", "", "| Task | Owner | Deadline | Status | Evidence |", "|---|---|---|---|---|"]
    for t in memory.action_items:
        lines.append(f"| {t.task_text} | {t.owner} | {t.deadline} | {t.status} | {', '.join(t.evidence_segments)} |")
    lines += ["", "## Open questions", ""]
    for q in memory.open_questions:
        if q.status != "answered":
            lines.append(f"- {q.text} (asked by {q.asked_by or 'unknown'}) [{q.evidence_segments[0]}]")
    lines += ["", "## Timeline", ""]
    for tp in memory.topics:
        lines.append(f"- {format_time(tp.start_time)} — **{tp.label}**: {tp.summary}")
    if notes:
        lines += ["", "## Personal notes (user-written)", ""]
        lines += [f"- {n['text']}" + (f" [{n['segment_id']}]" if n.get("segment_id") else "") for n in notes]
    if include_transcript:
        lines += ["", "## Transcript", ""]
        for s in segments:
            said = f"{s.original_text} _(English: {s.text})_" if s.original_text else s.text
            lines.append(f"- `{s.segment_id}` {format_time(s.start_time)} **{s.speaker_label}**: {said}")
    return "\n".join(lines) + "\n"


def to_json(meeting: dict, segments: list[Segment], memory: MeetingMemory, summary: str, notes: list[dict]) -> str:
    return json.dumps({"meeting": meeting, "summary": summary, "memory": memory.model_dump(), "notes": notes,
                       "segments": [s.model_dump() for s in segments]}, ensure_ascii=False, indent=2)


def to_text(markdown: str) -> str:
    text = re.sub(r"[*`#>]", "", markdown)
    text = re.sub(r"~~(.*?)~~", r"\1", text)
    return text


def to_pdf(markdown: str) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet
    from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer
    from xml.sax.saxutils import escape

    from backend.export import fonts

    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, title="MeetBrief AI export")
    styles = getSampleStyleSheet()
    base = fonts.base_font()
    for st in ("Title", "Heading2", "BodyText", "Bullet"):
        styles[st].fontName = base  # Unicode font (punctuation, arrows, ⚠)
    story = []
    for line in markdown.split("\n"):
        if not line.strip():
            story.append(Spacer(1, 6))
            continue
        if line.startswith("|---"):
            continue
        safe = escape(line)
        safe = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", safe)
        safe = re.sub(r"~~(.+?)~~", r"<strike>\1</strike>", safe)
        safe = re.sub(r"(?<!\*)\*(?!\*)(.+?)\*", r"<i>\1</i>", safe).replace("`", "")
        if base != "Helvetica":
            safe = re.sub(r"</?(?:b|i)>", "", safe)  # TTF families have no registered bold/italic variants
        safe = fonts.wrap_scripts(safe.replace("⚠️", "[!]").replace("⚠", "[!]").replace("✅", "[ok]"))
        if line.startswith("# "):
            story.append(Paragraph(safe[2:], styles["Title"]))
        elif line.startswith("## "):
            story.append(Paragraph(safe[3:], styles["Heading2"]))
        elif line.startswith("|"):
            story.append(Paragraph(" · ".join(c.strip() for c in safe.strip("|").split("|")), styles["BodyText"]))
        else:
            story.append(Paragraph(safe.lstrip("-> ").strip() if line.startswith(("- ", "> ")) else safe,
                                   styles["Bullet"] if line.startswith("- ") else styles["BodyText"]))
    doc.build(story)
    return buf.getvalue()
