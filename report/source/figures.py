"""Figures for the MeetBrief report and paper (PIL only, no extra installs)."""
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

OUT = Path(__file__).parent / "fig"
OUT.mkdir(exist_ok=True)
SHOTS = Path(__file__).parent.parent.parent / "images"
FONT = "/System/Library/Fonts/Supplemental/Arial.ttf"
BOLD = "/System/Library/Fonts/Supplemental/Arial Bold.ttf"
S = 2  # supersampling for crisp output


def f(size, bold=False):
    return ImageFont.truetype(BOLD if bold else FONT, size * S)


INK, MUTED, LINE = (25, 30, 45), (90, 98, 115), (70, 80, 100)
FILLS = {"ext": (225, 235, 255), "api": (232, 245, 233), "nlp": (255, 243, 224), "db": (243, 229, 245),
         "user": (236, 239, 241), "model": (255, 249, 196)}


def canvas(w, h):
    img = Image.new("RGB", (w * S, h * S), "white")
    return img, ImageDraw.Draw(img)


def box(d, x, y, w, h, title, lines=(), fill="api", tsize=15, lsize=12):
    d.rounded_rectangle([x * S, y * S, (x + w) * S, (y + h) * S], radius=10 * S, fill=FILLS[fill], outline=LINE, width=2 * S)
    d.text(((x + w / 2) * S, (y + 14) * S), title, font=f(tsize, True), fill=INK, anchor="mt")
    for i, ln in enumerate(lines):
        d.text(((x + w / 2) * S, (y + 38 + i * (lsize + 6)) * S), ln, font=f(lsize), fill=MUTED, anchor="mt")


def arrow(d, x1, y1, x2, y2, label=None, both=False, lsize=11):
    d.line([x1 * S, y1 * S, x2 * S, y2 * S], fill=LINE, width=2 * S)
    import math
    def head(xa, ya, xb, yb):
        ang = math.atan2(yb - ya, xb - xa)
        for s in (-1, 1):
            d.line([xb * S, yb * S, (xb - 10 * math.cos(ang + s * 0.45)) * S, (yb - 10 * math.sin(ang + s * 0.45)) * S], fill=LINE, width=2 * S)
    head(x1, y1, x2, y2)
    if both:
        head(x2, y2, x1, y1)
    if label:
        d.text((((x1 + x2) / 2 + 6) * S, ((y1 + y2) / 2 - 8) * S), label, font=f(lsize), fill=MUTED, anchor="lm")


def save(img, name):
    img = img.resize((img.width // S, img.height // S), Image.LANCZOS)
    img.save(OUT / name, dpi=(200, 200))
    return OUT / name


# ------------------------------------------------------------------ Fig: architecture
def architecture():
    img, d = canvas(1000, 690)
    d.text((500 * S, 18 * S), "MeetBrief AI — system architecture", font=f(18, True), fill=INK, anchor="mt")
    box(d, 30, 60, 290, 150, "Meeting tab (Meet / Zoom / Teams web)", ["platform adapter (DOM captions)", "caption stabiliser + de-dup",
        "join / leave detector, status label", "Early Join (mic/camera off)"], "ext", 14)
    box(d, 355, 60, 290, 150, "Chrome MV3 service worker", ["capture state machine, REC badge", "shared rooms: share / join / heartbeat",
        "Google or test identity", "offscreen tab-audio recorder"], "ext", 14)
    box(d, 680, 60, 290, 150, "Side panel UI", ["Catch Me Up · Explain Again · Ask AI", "Who Said What · Decisions · Tasks",
        "Timeline · Transcript · Notes · Export", "Schedule · Upload · Settings"], "ext", 14)
    arrow(d, 320, 135, 355, 135, both=True)
    arrow(d, 645, 135, 680, 135, both=True)
    box(d, 30, 265, 940, 70, "FastAPI backend (local, token / identity auth, rooms, connectors)",
        ["REST API (50 endpoints) · principal-based access control · capturer election · transcript import (Meet / Zoom / Teams)"], "api", 15)
    arrow(d, 500, 210, 500, 265, "HTTP JSON: segments, audio chunks, questions")
    nl = [("Speech", ["Whisper ASR", "WavLM diarization"]), ("Understanding", ["dialogue acts, tasks", "decisions, questions, NER"]),
          ("Summaries", ["TextRank + BART-SAMSum", "evidence alignment"]), ("RAG Q&A", ["hybrid retrieval", "RoBERTa-SQuAD2 + abstain"]),
          ("Explain / Translate", ["Qwen2.5-1.5B + glossary", "NLLB-200 (hi, te, ...)"])]
    for i, (t, ls) in enumerate(nl):
        box(d, 30 + i * 190, 380, 175, 105, t, ls, "nlp", 14, 11)
        arrow(d, 117 + i * 190, 335, 117 + i * 190, 380)
    box(d, 30, 530, 450, 120, "Meeting memory", ["structured state: decisions, tasks, owners, deadlines", "topics (TextTiling), rolling summary",
        "user corrections always override extraction"], "db", 14)
    box(d, 520, 530, 450, 120, "Storage", ["SQLite (meetings, segments, rooms, members, notes)", "in-memory DB for private mode",
        "retention purge · raw audio deleted after ASR"], "db", 14)
    arrow(d, 255, 485, 255, 530)
    arrow(d, 745, 485, 745, 530)
    d.text((500 * S, 670 * S), "All neural models run locally from the Hugging Face Hub; every model has a classical fallback.",
           font=f(12), fill=MUTED, anchor="mt")
    return save(img, "architecture.png")


# ------------------------------------------------------------------ Fig: NLP pipeline
def pipeline():
    img, d = canvas(1000, 420)
    d.text((500 * S, 16 * S), "Processing pipeline for one meeting", font=f(18, True), fill=INK, anchor="mt")
    steps = [("Input", ["live captions", "tab / desktop audio", "transcript files"], "user"),
             ("Normalise", ["timestamps, speakers", "filler removal", "caption de-dup"], "api"),
             ("Language ID", ["script ranges", "code-switch lexicon", "langdetect"], "api"),
             ("Analyse", ["dialogue acts", "tasks / owners", "decisions, questions"], "nlp"),
             ("Memory", ["topics, NER", "revisions", "contradictions"], "db")]
    for i, (t, ls, c) in enumerate(steps):
        box(d, 20 + i * 196, 60, 170, 120, t, ls, c, 15, 12)
        if i:
            arrow(d, 20 + i * 196 - 26, 120, 20 + i * 196, 120)
    outs = [("Catch Me Up", ["TextRank / BART", "evidence-aligned"]), ("Ask AI", ["hybrid retrieval", "extractive QA, abstain"]),
            ("Explain Again", ["glossary + LLM", "4 levels, 5 styles"]), ("Translate", ["NLLB-200", "number check"]),
            ("Export", ["MD / PDF / TXT", "JSON"])]
    for i, (t, ls) in enumerate(outs):
        box(d, 20 + i * 196, 260, 170, 100, t, ls, "model", 15, 12)
    d.line([105 * S, 220 * S, 889 * S, 220 * S], fill=LINE, width=2 * S)
    arrow(d, 889, 180, 889, 220)
    for i in range(5):
        arrow(d, 105 + i * 196, 220, 105 + i * 196, 260)
    d.text((500 * S, 385 * S), "Every generated sentence is linked to transcript segment ids [S…] so the user can verify it.",
           font=f(12), fill=MUTED, anchor="mt")
    return save(img, "pipeline.png")


# ------------------------------------------------------------------ Fig: shared room sequence
def rooms():
    img, d = canvas(1000, 560)
    d.text((500 * S, 16 * S), "Shared room: late joiner and capturer handover", font=f(18, True), fill=INK, anchor="mt")
    cols = [(150, "Priya's extension"), (500, "MeetBrief server"), (850, "Rahul's extension (late)")]
    for x, t in cols:
        d.rounded_rectangle([(x - 110) * S, 50 * S, (x + 110) * S, 85 * S], radius=8 * S, fill=FILLS["ext" if x != 500 else "api"], outline=LINE, width=2 * S)
        d.text((x * S, 67 * S), t, font=f(14, True), fill=INK, anchor="mm")
        d.line([x * S, 85 * S, x * S, 540 * S], fill=(180, 186, 198), width=2 * S)
    msgs = [(110, 150, 500, "joins call → lookup(meeting key): none"), (150, 150, 500, "Share → room created, Priya = capturer"),
            (190, 150, 500, "captions → /rooms/{id}/segments (room clock)"),
            (240, 850, 500, "joins 10 min later → lookup → join"), (280, 500, 850, "role = standby, missed = 600 s"),
            (320, 850, 500, "GET /catchup → 'What you missed'"), (370, 150, 500, "Priya leaves → capturer released"),
            (410, 850, 500, "heartbeat (10 s) → elected capturer"), (450, 850, 500, "captions continue → same transcript"),
            (500, 850, 500, "last member leaves → room ends + final summary")]
    for y, x1, x2, t in msgs:
        arrow(d, x1, y, x2, y)
        d.text((((x1 + x2) / 2) * S, (y - 6) * S), t, font=f(12), fill=INK, anchor="mb")
    return save(img, "rooms.png")


# ------------------------------------------------------------------ charts
def bars(name, title, groups, series, ylabel, ymax=1.0, colors=((79, 70, 229), (245, 158, 11), (16, 150, 72)), w=900, h=440, fmt="{:.2f}"):
    img, d = canvas(w, h)
    d.text((w / 2 * S, 14 * S), title, font=f(17, True), fill=INK, anchor="mt")
    left, right, top, bottom = 80, w - 30, 60, h - 80
    for k in range(6):
        v = ymax * k / 5
        y = bottom - (bottom - top) * k / 5
        d.line([left * S, y * S, right * S, y * S], fill=(225, 228, 234), width=1 * S)
        d.text(((left - 8) * S, y * S), fmt.format(v) if ymax <= 1 else f"{v:.0f}", font=f(11), fill=MUTED, anchor="rm")
    d.text((22 * S, ((top + bottom) / 2) * S), ylabel, font=f(12), fill=MUTED, anchor="mm")
    gw = (right - left) / len(groups)
    bw = gw * 0.7 / len(series)
    for gi, g in enumerate(groups):
        for si, (sname, vals) in enumerate(series):
            v = vals[gi]
            x0 = left + gi * gw + gw * 0.15 + si * bw
            y0 = bottom - (bottom - top) * v / ymax
            d.rectangle([x0 * S, y0 * S, (x0 + bw - 4) * S, bottom * S], fill=colors[si])
            d.text(((x0 + (bw - 4) / 2) * S, (y0 - 4) * S), fmt.format(v) if ymax <= 1 else f"{v:g}", font=f(10), fill=INK, anchor="mb")
        d.text(((left + gi * gw + gw / 2) * S, (bottom + 10) * S), g, font=f(12), fill=INK, anchor="mt")
    lx = left
    for si, (sname, _) in enumerate(series):
        d.rectangle([lx * S, (h - 34) * S, (lx + 14) * S, (h - 20) * S], fill=colors[si])
        d.text(((lx + 20) * S, (h - 27) * S), sname, font=f(12), fill=INK, anchor="lm")
        lx += 30 + len(sname) * 7.5
    return save(img, name)


def screenshots():
    out = {}
    src = SHOTS / "2.webp"
    if src.exists():
        im = Image.open(src).convert("RGB")
        im.crop((1474, 170, 1962, 540)).save(OUT / "ui_sidepanel.png")
        im.crop((22, 1012, 580, 1056)).resize((1116, 88), Image.LANCZOS).save(OUT / "ui_status_label.png")
        out = {"sidepanel": OUT / "ui_sidepanel.png", "label": OUT / "ui_status_label.png"}
    return out


if __name__ == "__main__":
    architecture(); pipeline(); rooms()
    bars("rouge.png", "Overview summary quality (ROUGE-1 F1)", ["Development set", "Held-out set"],
         [("TextRank (extractive)", [0.449, 0.357]), ("BART-SAMSum (abstractive)", [0.555, 0.55])], "ROUGE-1", fmt="{:.2f}")
    bars("dialogue_acts.png", "Dialogue-act recall: cue-phrase rules vs zero-shot NLI (32 sentences)",
         ["decision", "proposal", "task", "question", "other"],
         [("Rules (acc. 0.94)", [8 / 8, 4 / 6, 6 / 6, 5 / 5, 7 / 7]), ("Zero-shot NLI (acc. 0.59)", [0 / 8, 5 / 6, 2 / 6, 5 / 5, 7 / 7])], "recall")
    bars("explain.png", "Explanation model benchmark (9 items, human-rated correct)", ["Flan-T5-large", "Qwen2.5-0.5B", "Qwen2.5-1.5B"],
         [("correct", [0, 2, 8]), ("partly", [2, 4, 1]), ("wrong", [7, 3, 0])], "items", ymax=9,
         colors=((16, 150, 72), (245, 158, 11), (220, 38, 38)))
    bars("latency.png", "Latency on the held-out meeting (ms, CPU)", ["Analyse", "Summary", "Q&A"],
         [("Rules only", [27.0, 0.9, 4.2]), ("With HF models", [1071.0, 5798.4, 54.1])], "milliseconds", ymax=7000)
    print(screenshots())
    print(sorted(p.name for p in OUT.iterdir()))
