"""reportlab renderer for the shared document model (report: 1 column; paper: IEEE 2 columns)."""
from xml.sax.saxutils import escape

from PIL import Image as PILImage
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import (BaseDocTemplate, CondPageBreak, Flowable, Frame, FrameBreak, Image, KeepTogether,
                                NextPageTemplate, PageBreak, PageTemplate, Paragraph, Spacer, Table, TableStyle)

import model as M

FD = "/System/Library/Fonts/Supplemental/"
pdfmetrics.registerFont(TTFont("TNR", FD + "Times New Roman.ttf"))
pdfmetrics.registerFont(TTFont("TNR-B", FD + "Times New Roman Bold.ttf"))
pdfmetrics.registerFont(TTFont("TNR-I", FD + "Times New Roman Italic.ttf"))
pdfmetrics.registerFont(TTFont("TNR-BI", FD + "Times New Roman Bold Italic.ttf"))
pdfmetrics.registerFont(TTFont("Mono", FD + "Courier New.ttf"))
from reportlab.lib.fonts import addMapping
addMapping("TNR", 0, 0, "TNR"); addMapping("TNR", 1, 0, "TNR-B"); addMapping("TNR", 0, 1, "TNR-I"); addMapping("TNR", 1, 1, "TNR-BI")

ALIGN = {"justify": TA_JUSTIFY, "center": TA_CENTER, "left": TA_LEFT, "right": TA_RIGHT}
RED = "#C00000"


def markup(text):
    out = []
    for t, st in M.runs(text):
        s = escape(t).replace("\n", "<br/>")
        if "code" in st:
            s = f'<font face="Mono" size="-1">{s}</font>'
        if "b" in st:
            s = f"<b>{s}</b>"
        if "i" in st:
            s = f"<i>{s}</i>"
        if "red" in st:
            s = f'<font color="{RED}">{s}</font>'
        out.append(s)
    return "".join(out)


def roman(n):
    vals = [(1000, "m"), (900, "cm"), (500, "d"), (400, "cd"), (100, "c"), (90, "xc"), (50, "l"), (40, "xl"), (10, "x"), (9, "ix"), (5, "v"), (4, "iv"), (1, "i")]
    s = ""
    for v, r in vals:
        while n >= v:
            s += r
            n -= v
    return s


class Mark(Flowable):
    """Zero-size flowable that records (kind, level, text) at the page where it lands."""
    def __init__(self, kind, level, text):
        super().__init__()
        self.kind, self.level, self.text = kind, level, text
        self.width = self.height = 0

    def draw(self):
        pass


class Doc(BaseDocTemplate):
    def __init__(self, path, margins_cm, base=12, line=1.5, two_col=False, title_frame_cm=0, **kw):
        t, r, b, l = margins_cm
        super().__init__(path, pagesize=(21 * cm, 29.7 * cm), topMargin=t * cm, bottomMargin=b * cm, leftMargin=l * cm,
                         rightMargin=r * cm, **kw)
        self.base, self.line = base, line
        self.entries = []
        self.starts = {}
        W, H = self.pagesize
        fw, fh = W - (l + r) * cm, H - (t + b) * cm
        if two_col:
            gap = 0.42 * cm
            cw = (fw - gap) / 2
            first = [Frame(l * cm, H - t * cm - title_frame_cm * cm, fw, title_frame_cm * cm, id="title", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                     Frame(l * cm, b * cm, cw, fh - title_frame_cm * cm, id="c1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                     Frame(l * cm + cw + gap, b * cm, cw, fh - title_frame_cm * cm, id="c2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]
            later = [Frame(l * cm, b * cm, cw, fh, id="d1", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0),
                     Frame(l * cm + cw + gap, b * cm, cw, fh, id="d2", leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)]
            self.col_width = cw
            self.addPageTemplates([PageTemplate("first", first, onPage=self._num("paper")),
                                   PageTemplate("cols", later, onPage=self._num("paper"))])
        else:
            frame = lambda: Frame(l * cm, b * cm, fw, fh, leftPadding=0, rightPadding=0, topPadding=0, bottomPadding=0)
            self.col_width = fw
            self.addPageTemplates([PageTemplate("plain", [frame()], onPage=self._num(None)),
                                   PageTemplate("roman", [frame()], onPage=self._num("roman")),
                                   PageTemplate("arabic", [frame()], onPage=self._num("arabic"))])

    def _num(self, kind):
        def draw(canv, doc):
            if kind is None:
                return
            start = doc.starts.setdefault(kind, doc.page)
            n = doc.page - start + 1
            label = roman(n) if kind == "roman" else str(n)
            canv.setFont("TNR", 10 if kind == "paper" else 12)
            canv.drawCentredString(doc.pagesize[0] / 2, 1.3 * cm, label)
        return draw

    def display_page(self):
        tmpl = self.pageTemplate.id
        kind = {"roman": "roman", "arabic": "arabic", "first": "paper", "cols": "paper"}.get(tmpl)
        if kind is None:
            return ""
        start = self.starts.setdefault(kind, self.page)
        n = self.page - start + 1
        return roman(n) if kind == "roman" else str(n)

    def afterFlowable(self, fl):
        if isinstance(fl, Mark):
            self.entries.append((fl.kind, fl.level, fl.text, self.display_page()))


class Renderer:
    def __init__(self, base=12, line=1.5, h_sizes=(16, 14, 12), paper=False):
        self.paper = paper
        lead = base * line * (1.15 if not paper else 1.0)  # Word's '1.5 lines' uses the font's line height
        S = ParagraphStyle
        self.body = S("body", fontName="TNR", fontSize=base, leading=lead, alignment=TA_JUSTIFY, spaceAfter=6 if not paper else 2,
                      firstLineIndent=0.35 * cm if paper else 0)
        self.h1 = S("h1", fontName="TNR-B", fontSize=h_sizes[0], leading=h_sizes[0] * 1.3, spaceAfter=12, alignment=TA_LEFT, keepWithNext=1)
        self.h2 = S("h2", fontName="TNR-B", fontSize=h_sizes[1], leading=h_sizes[1] * 1.3, spaceBefore=10, spaceAfter=6,
                    alignment=TA_CENTER if paper else TA_LEFT, keepWithNext=1)
        self.h3 = S("h3", fontName="TNR-BI" if paper else "TNR-B", fontSize=h_sizes[2], leading=h_sizes[2] * 1.3,
                    spaceBefore=6, spaceAfter=3, alignment=TA_LEFT, keepWithNext=1)
        self.cap = S("cap", fontName="TNR", fontSize=10 if not paper else 8, leading=12 if not paper else 9.5, alignment=TA_CENTER, spaceBefore=3, spaceAfter=8)
        self.cell = S("cell", fontName="TNR", fontSize=10 if not paper else 7.5, leading=12 if not paper else 9)
        self.cellb = S("cellb", parent=self.cell, fontName="TNR-B")
        self.code = S("code", fontName="Mono", fontSize=8 if not paper else 7, leading=10 if not paper else 8.5)
        self.bullet = S("bullet", parent=self.body, leftIndent=0.9 * cm, bulletIndent=0.3 * cm, firstLineIndent=0, spaceAfter=3 if not paper else 1)

    def para(self, text, size=None, align="justify", bold=False, italic=False, after=None, before=0, leading=None, keep=False, font=None):
        st = ParagraphStyle("x", parent=self.body, fontSize=size or self.body.fontSize,
                            leading=leading or (size or self.body.fontSize) * (self.body.leading / self.body.fontSize),
                            alignment=ALIGN[align], spaceAfter=self.body.spaceAfter if after is None else after, spaceBefore=before,
                            fontName=font or ("TNR-BI" if bold and italic else "TNR-B" if bold else "TNR-I" if italic else "TNR"),
                            firstLineIndent=self.body.firstLineIndent if align == "justify" else 0, keepWithNext=keep)
        return Paragraph(markup(text), st)

    def flow(self, blocks, col_width):
        """Render blocks; every heading is bundled with the flowable that follows it (no stranded headings)."""
        raw = self._flow(blocks, col_width)
        out, i = [], 0
        while i < len(raw):
            f = raw[i]
            if isinstance(f, Paragraph) and f.style.name in ("h2", "h3") and i + 1 < len(raw):
                group, j = [f], i + 1
                while j < len(raw) and isinstance(raw[j], (Mark, CondPageBreak)):  # invisible items
                    if isinstance(raw[j], Mark):
                        group.append(raw[j])
                    j += 1
                if j < len(raw):
                    nxt = raw[j]
                    group += list(nxt._content) if isinstance(nxt, KeepTogether) else [nxt]
                    # a table caption travels with its table
                    if isinstance(nxt, Paragraph) and nxt.style.name == "capk" and j + 1 < len(raw):
                        group.append(raw[j + 1])
                        j += 1
                    j += 1
                out.append(KeepTogether(group))
                i = j
                continue
            out.append(f)
            i += 1
        return out

    def _flow(self, blocks, col_width):
        out = []
        for b in blocks:
            if isinstance(b, M.H1):
                title = f"Chapter {b.num}: {b.title}" if b.num else b.title
                out += [PageBreak(), Mark("toc", 1, title), Paragraph(escape(title), self.h1)]
            elif isinstance(b, M.H2):
                t = f"{b.num} {b.title.upper()}".strip()
                out += [CondPageBreak(3 * cm), Mark("toc", 2, f"{b.num} {b.title.upper()}".strip()), Paragraph(escape(t), self.h2)]
            elif isinstance(b, M.H3):
                t = f"{b.num} {b.title}".strip() if self.paper else f"{b.num} {b.title.upper()}".strip()
                out += [CondPageBreak(2 * cm), Mark("toc", 3, f"{b.num} {b.title.upper()}".strip()), Paragraph(escape(t), self.h3)]
            elif isinstance(b, M.P):
                out.append(self.para(b.text, b.size, b.align, b.bold, b.italic, after=b.space_after, keep=b.keep_next))
            elif isinstance(b, M.Bullets):
                for i, it in enumerate(b.items):
                    out.append(Paragraph(markup(it), self.bullet, bulletText=f"{i + 1}." if b.numbered else "•"))
                out.append(Spacer(1, 4))
            elif isinstance(b, M.Table):
                t = self.table(b, col_width)
                out += t if isinstance(t, list) else [t]
            elif isinstance(b, M.Figure):
                out.append(self.figure(b, col_width))
            elif isinstance(b, M.Code):
                out.append(Paragraph(escape(b.text).replace("\n", "<br/>").replace(" ", "&nbsp;"), self.code))
                out.append(Spacer(1, 6))
            elif isinstance(b, M.PageBreak):
                out.append(PageBreak())
            elif isinstance(b, M.Spacer):
                out.append(Spacer(1, b.pt))
        return out

    def table(self, b: M.Table, col_width, borders=True, caption=True):
        widths = b.widths or [1] * len(b.header or b.rows[0])
        tot = sum(widths)
        cw = [col_width * w / tot for w in widths]
        cell = ParagraphStyle("c", parent=self.cell, fontSize=b.size if not self.paper else min(b.size, 7.5),
                              leading=(b.size if not self.paper else min(b.size, 7.5)) * 1.2)
        cellb = ParagraphStyle("cb", parent=cell, fontName="TNR-B")
        data = []
        if b.header:
            data.append([Paragraph(markup(str(h)), cellb) for h in b.header])
        for r in b.rows:
            data.append([script_image(str(c)[4:], cw[i] - 6, cell.fontSize) if str(c).startswith("§TE§")
                         else Paragraph(markup(str(c)), cell) for i, c in enumerate(r)])
        t = Table(data, colWidths=cw, repeatRows=1 if b.header else 0)
        style = [("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 3), ("RIGHTPADDING", (0, 0), (-1, -1), 3),
                 ("TOPPADDING", (0, 0), (-1, -1), 2), ("BOTTOMPADDING", (0, 0), (-1, -1), 2)]
        if borders:
            style += [("GRID", (0, 0), (-1, -1), 0.5, colors.HexColor("#808080"))]
            if b.header:
                style += [("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9E2F3"))]
        t.setStyle(TableStyle(style))
        if not caption or not b.caption:
            return t
        label = f"TABLE {b.num}" if self.paper else f"Table {b.num}:"
        cap = Paragraph(f"<b>{label}</b> {markup(b.caption)}", ParagraphStyle("capk", parent=self.cap, keepWithNext=1))
        if len(b.rows) <= 4 or self.paper:  # short tables move as one block; long ones may continue on the next page (header repeats)
            return KeepTogether([Mark("lot", 1, f"{b.num} {b.caption}"), cap, t, Spacer(1, 8)])
        return [Mark("lot", 1, f"{b.num} {b.caption}"), CondPageBreak(4 * cm), cap, t, Spacer(1, 8)]

    def figure(self, b: M.Figure, col_width):
        w, h = PILImage.open(b.path).size
        width = min(b.width_cm * cm, col_width)
        img = Image(b.path, width=width, height=width * h / w)
        label = f"Fig. {b.num}." if self.paper else f"Figure {b.num}:"
        return KeepTogether([Mark("lof", 1, f"{b.num} {b.caption}"), img, Paragraph(f"<b>{label}</b> {markup(b.caption)}", self.cap)])


def script_image(text, width_pt, size_pt):
    """Telugu (or other complex-script) text as an image: reportlab cannot shape Indic scripts, PIL + raqm can."""
    from PIL import Image as PI, ImageDraw, ImageFont
    import hashlib, tempfile, os
    scale = 4
    font = ImageFont.truetype("/Users/venkatsashank/nlp/backend/export/fonts/NotoSansTelugu-VF.ttf", int(size_pt * scale * 1.05),
                              layout_engine=ImageFont.Layout.RAQM)
    maxw = int(width_pt * scale)
    words, lines, cur = text.split(" "), [], ""
    for w in words:
        trial = (cur + " " + w).strip()
        if font.getlength(trial) <= maxw or not cur:
            cur = trial
        else:
            lines.append(cur); cur = w
    lines.append(cur)
    lh = int(size_pt * scale * 1.7)
    img = PI.new("RGB", (maxw, lh * len(lines) + int(size_pt * scale * 0.3)), "white")
    d = ImageDraw.Draw(img)
    for i, ln in enumerate(lines):
        d.text((0, i * lh), ln, font=font, fill="black")
    path = os.path.join(tempfile.gettempdir(), "mb_te_" + hashlib.md5(text.encode()).hexdigest() + ".png")
    img.save(path)
    return Image(path, width=img.width / scale, height=img.height / scale)


def flatten(items):
    out = []
    for x in items:
        if isinstance(x, list):
            out += flatten(x)
        else:
            out.append(x)
    return out


def toc_table(entries, col_width, size=12, indent_levels=True):
    """Static TOC/LoF/LoT table: text ... page."""
    rows = []
    st1 = ParagraphStyle("t1", fontName="TNR-B", fontSize=size, leading=size * 1.25)
    st2 = ParagraphStyle("t2", fontName="TNR", fontSize=size - 1, leading=(size - 1) * 1.25)
    for level, text, page in entries:
        st = st1 if level == 1 else st2
        ind = "" if not indent_levels or level == 1 else ("&nbsp;" * (4 if level == 2 else 8))
        rows.append([Paragraph(ind + escape(text), st), Paragraph(str(page), ParagraphStyle("p", parent=st, alignment=TA_RIGHT))])
    t = Table(rows, colWidths=[col_width - 1.6 * cm, 1.6 * cm])
    t.setStyle(TableStyle([("VALIGN", (0, 0), (-1, -1), "TOP"), ("LEFTPADDING", (0, 0), (-1, -1), 0), ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                           ("TOPPADDING", (0, 0), (-1, -1), 1), ("BOTTOMPADDING", (0, 0), (-1, -1), 1)]))
    return t


__all__ = ["Doc", "Renderer", "Mark", "toc_table", "flatten", "markup", "NextPageTemplate", "PageBreak", "Spacer", "Image",
           "Paragraph", "ParagraphStyle", "Table", "TableStyle", "FrameBreak", "cm", "TA_CENTER", "TA_LEFT", "colors", "KeepTogether"]
