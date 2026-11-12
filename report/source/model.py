"""Tiny document model shared by the DOCX and PDF writers.

Inline markup in text: **bold**, *italic*, {{placeholder}} (red, to be filled in by the student), `code`.
"""
import re
from dataclasses import dataclass, field
from typing import Optional

TOKEN = re.compile(r"(\*\*.+?\*\*(?!\*)|\*[^*\s][^*]*?\*|\{\{.+?\}\}|`[^`]+`)")


def runs(text: str):
    """Split inline markup into (text, style) pairs; style ⊂ {'b','i','red','code'}."""
    out = []
    for part in TOKEN.split(text):
        if not part:
            continue
        if part.startswith("**") and part.endswith("**"):
            out += [(t, st | {"b"}) for t, st in runs(part[2:-2])]  # nested placeholders / italics keep their style
        elif part.startswith("{{") and part.endswith("}}"):
            out.append((part[2:-2], {"red"}))
        elif part.startswith("`") and part.endswith("`"):
            out.append((part[1:-1], {"code"}))
        elif part.startswith("*") and part.endswith("*") and len(part) > 2:
            out += [(t, st | {"i"}) for t, st in runs(part[1:-1])]
        else:
            out.append((part, set()))
    return out


def plain(text: str) -> str:
    return "".join(t for t, _ in runs(text))


@dataclass
class H1:  # chapter
    num: str
    title: str


@dataclass
class H2:
    num: str
    title: str


@dataclass
class H3:
    num: str
    title: str


@dataclass
class P:
    text: str
    align: str = "justify"  # justify | center | left | right
    size: Optional[float] = None
    bold: bool = False
    italic: bool = False
    space_after: float = 6
    keep_next: bool = False


@dataclass
class Bullets:
    items: list
    numbered: bool = False


@dataclass
class Table:
    num: str
    caption: str
    header: list
    rows: list
    widths: list = field(default_factory=list)  # relative widths
    size: float = 10


@dataclass
class Figure:
    num: str
    caption: str
    path: str
    width_cm: float = 15.0


@dataclass
class Code:
    text: str


@dataclass
class PageBreak:
    pass


@dataclass
class Spacer:
    pt: float = 12
