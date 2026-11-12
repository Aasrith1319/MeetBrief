"""Unicode font handling for PDF export.

ReportLab's built-in fonts only cover Latin-1, and Indic scripts additionally
need OpenType shaping (conjuncts, vowel signs). We register system TrueType
fonts per script with ``shapable=True`` (HarfBuzz via ``uharfbuzz``) and wrap
each run of a script in ``<font name=...>`` so mixed English/Telugu/Hindi text
renders correctly. Paths cover macOS, Linux (Noto/DejaVu) and Windows.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Optional

BUNDLED = str(Path(__file__).resolve().parent / "fonts")  # OFL Noto fonts shipped with the project
SYS = "/System/Library/Fonts"
SUP = "/System/Library/Fonts/Supplemental"
LNX = "/usr/share/fonts"
WIN = "C:/Windows/Fonts"

CANDIDATES: dict[str, list[str]] = {
    "base": [f"{SUP}/Arial Unicode.ttf", "/Library/Fonts/Arial Unicode.ttf", f"{LNX}/truetype/dejavu/DejaVuSans.ttf",
             f"{LNX}/TTF/DejaVuSans.ttf", f"{WIN}/arialuni.ttf", f"{WIN}/arial.ttf"],
    "te": [f"{BUNDLED}/NotoSansTelugu-VF.ttf", f"{SYS}/KohinoorTelugu.ttc", f"{SUP}/Telugu Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansTelugu-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
    "hi": [f"{BUNDLED}/NotoSansDevanagari-VF.ttf", f"{SYS}/Kohinoor.ttc", f"{SUP}/Devanagari Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansDevanagari-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
    "ta": [f"{BUNDLED}/NotoSansTamil-VF.ttf", f"{SUP}/Tamil Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansTamil-Regular.ttf", f"{WIN}/Nirmala.ttf"],
    "kn": [f"{BUNDLED}/NotoSansKannada-VF.ttf", f"{SYS}/NotoSansKannada.ttc", f"{SUP}/Kannada Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansKannada-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
    "ml": [f"{BUNDLED}/NotoSansMalayalam-VF.ttf", f"{SUP}/Malayalam Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansMalayalam-Regular.ttf", f"{WIN}/Nirmala.ttf"],
    "bn": [f"{BUNDLED}/NotoSansBengali-VF.ttf", f"{SYS}/KohinoorBangla.ttc", f"{SUP}/Bangla Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansBengali-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
    "gu": [f"{BUNDLED}/NotoSansGujarati-Regular.ttf", f"{SYS}/KohinoorGujarati.ttc", f"{SUP}/Gujarati Sangam MN.ttc", f"{LNX}/truetype/noto/NotoSansGujarati-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
    "pa": [f"{BUNDLED}/NotoSansGurmukhi-VF.ttf", f"{SUP}/Gurmukhi Sangam MN.ttc", f"{SUP}/Gurmukhi.ttf", f"{LNX}/truetype/noto/NotoSansGurmukhi-Regular.ttf",
           f"{WIN}/Nirmala.ttf"],
}
RANGES = {"te": "\u0C00-\u0C7F", "hi": "\u0900-\u097F", "ta": "\u0B80-\u0BFF", "kn": "\u0C80-\u0CFF",
          "ml": "\u0D00-\u0D7F", "bn": "\u0980-\u09FF", "gu": "\u0A80-\u0AFF", "pa": "\u0A00-\u0A7F"}
# a run = script characters plus spaces/punctuation between them (ZWJ/ZWNJ included)
RUN_RE = {k: re.compile(f"[{r}](?:[{r}\u200c\u200d\\s,.!?।॥:;'\"()-]*[{r}])?") for k, r in RANGES.items()}


@lru_cache(maxsize=1)
def registered() -> dict[str, str]:
    """Register available fonts; returns {script: fontName}."""
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont

    out: dict[str, str] = {}
    for script, paths in CANDIDATES.items():
        for p in paths:
            if not Path(p).exists():
                continue
            name = f"MM-{script}"
            try:
                pdfmetrics.registerFont(TTFont(name, p, subfontIndex=0, shapable=True))
                out[script] = name
                break
            except Exception:
                continue
    return out


def base_font() -> str:
    return registered().get("base", "Helvetica")


def wrap_scripts(markup: str) -> str:
    """Wrap each Indic-script run in <font name=...> so ReportLab picks a font that has the glyphs."""
    fonts = registered()
    for script, rx in RUN_RE.items():
        name: Optional[str] = fonts.get(script)
        if name:
            markup = rx.sub(lambda m: f'<font name="{name}">{m.group(0)}</font>', markup)
    return markup


def shaping_available() -> bool:
    try:
        import uharfbuzz  # noqa: F401
        return True
    except ImportError:
        return False
