"""Minimal, dependency-free .docx (Office Open XML) writer for the report and paper.

Supports: Times New Roman styles, headings that feed Word's TOC, sections with their own page-number format
(none / lower-roman / arabic) and column count, centred page-number footers, tables, PNG images, a TOC field
with pre-computed entries, and red placeholder runs.
"""
import zipfile
from pathlib import Path
from xml.sax.saxutils import escape

from PIL import Image

import model as M

CM = 567          # twips per cm
EMU_CM = 360000   # EMU per cm
RED = "C00000"

NS = ('xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main" '
      'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships" '
      'xmlns:wp="http://schemas.openxmlformats.org/drawingml/2006/wordprocessingDrawing" '
      'xmlns:a="http://schemas.openxmlformats.org/drawingml/2006/main" '
      'xmlns:pic="http://schemas.openxmlformats.org/drawingml/2006/picture"')


def _t(text):
    return f'<w:t xml:space="preserve">{escape(text)}</w:t>'


class Docx:
    def __init__(self, margins_cm=(2.54, 2.54, 2.54, 3.81), line=1.5, base_pt=12, font="Times New Roman",
                 heading_sizes=(16, 14, 12), heading_center=False, caps_h2=True, caps_h3=True):
        self.margins = margins_cm
        self.line = line
        self.base = base_pt
        self.font = font
        self.hs = heading_sizes
        self.h_center = heading_center
        self.caps_h2, self.caps_h3 = caps_h2, caps_h3
        self.body = []
        self.media = []  # (name, bytes)
        self.ids = 1
        self.sect = {"numbers": None, "start": 1, "cols": 1, "continuous": False}
        self.fresh_page = True  # at the top of a new page (no page break needed before a chapter)
        self.pending_break = False  # next paragraph starts a new page

    # ------------------------------------------------------------ runs & paragraphs
    def _run(self, text, style=(), size=None, bold=False, italic=False, underline=False, caps=False, color=None, font=None):
        pr = []
        f = font or ("Courier New" if "code" in style else None)
        if f:
            pr.append(f'<w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}"/>')
        if bold or "b" in style:
            pr.append("<w:b/><w:bCs/>")
        if italic or "i" in style:
            pr.append("<w:i/><w:iCs/>")
        if caps:
            pr.append("<w:caps/>")
        if underline:
            pr.append('<w:u w:val="single"/>')
        c = RED if "red" in style else color
        if c:
            pr.append(f'<w:color w:val="{c}"/>')
        sz = size or (self.base - 2 if "code" in style else None)
        if sz:
            pr.append(f'<w:sz w:val="{int(sz * 2)}"/><w:szCs w:val="{int(sz * 2)}"/>')
        parts = text.split("\n")
        inner = "<w:br/>".join(_t(p) for p in parts)
        return f"<w:r><w:rPr>{''.join(pr)}</w:rPr>{inner}</w:r>"

    def _ppr(self, style=None, align="justify", after=6, before=0, line=None, keep_next=False, indent=None, hanging=None,
             tabs=None, page_break_before=False):
        jc = {"justify": "both", "center": "center", "left": "left", "right": "right"}[align]
        ln = int(240 * (line or self.line))
        x = []
        if style:
            x.append(f'<w:pStyle w:val="{style}"/>')
        if keep_next:
            x.append("<w:keepNext/>")
        if page_break_before or self.pending_break:
            x.append("<w:pageBreakBefore/>")
            self.pending_break = False
        if tabs:
            x.append("<w:tabs>" + "".join(f'<w:tab w:val="{v}" w:leader="{ld}" w:pos="{pos}"/>' for v, ld, pos in tabs) + "</w:tabs>")
        x.append(f'<w:spacing w:before="{int(before * 20)}" w:after="{int(after * 20)}" w:line="{ln}" w:lineRule="auto"/>')
        if indent is not None or hanging is not None:
            x.append(f'<w:ind w:left="{int((indent or 0) * CM)}"' + (f' w:hanging="{int(hanging * CM)}"' if hanging else "") + "/>")
        x.append(f'<w:jc w:val="{jc}"/>')
        return "<w:pPr>" + "".join(x) + "</w:pPr>"

    def para(self, text, align="justify", size=None, bold=False, italic=False, underline=False, caps=False, after=6,
             before=0, line=None, keep_next=False, color=None, style=None, page_break_before=False):
        rs = "".join(self._run(t, st, size, bold, italic, underline, caps, color) for t, st in M.runs(text))
        self.body.append(f"<w:p>{self._ppr(style, align, after, before, line, keep_next, page_break_before=page_break_before)}{rs}</w:p>")

    def page_break(self):
        self.pending_break = True
        self.fresh_page = True

    # ------------------------------------------------------------ blocks
    def add(self, b):
        if not isinstance(b, M.H1):
            self.fresh_page = False
        if isinstance(b, M.H1):
            title = f"Chapter {b.num}: {b.title}" if b.num else b.title
            pb, self.fresh_page = not self.fresh_page, False
            self.body.append(f"<w:p>{self._ppr('Heading1', 'center' if self.h_center else 'left', after=12, before=0, keep_next=True, page_break_before=pb)}"
                             f"{self._run(title, (), self.hs[0], bold=True)}</w:p>")
        elif isinstance(b, M.H2):
            self.body.append(f"<w:p>{self._ppr('Heading2', 'left', after=6, before=12, keep_next=True)}"
                             f"{self._run(f'{b.num} {b.title}'.strip(), (), self.hs[1], bold=True, caps=self.caps_h2)}</w:p>")
        elif isinstance(b, M.H3):
            self.body.append(f"<w:p>{self._ppr('Heading3', 'left', after=4, before=8, keep_next=True)}"
                             f"{self._run(f'{b.num} {b.title}'.strip(), (), self.hs[2], bold=True, caps=self.caps_h3)}</w:p>")
        elif isinstance(b, M.P):
            self.para(b.text, b.align, b.size, b.bold, b.italic, after=b.space_after, keep_next=b.keep_next)
        elif isinstance(b, M.Bullets):
            for i, it in enumerate(b.items):
                mark = f"{i + 1}." if b.numbered else "•"
                rs = self._run(mark + "\t") + "".join(self._run(t, st) for t, st in M.runs(it))
                self.body.append(f"<w:p>{self._ppr(None, 'justify', after=3, indent=1.0, hanging=0.6, tabs=[('left', 'none', int(1.0 * CM))])}{rs}</w:p>")
            self.body.append(f"<w:p>{self._ppr(None, after=0, line=1)}</w:p>")
        elif isinstance(b, M.Table):
            self.table(b)
        elif isinstance(b, M.Figure):
            self.figure(b)
        elif isinstance(b, M.Code):
            for ln in b.text.split("\n"):
                self.body.append(f"<w:p>{self._ppr(None, 'left', after=0, line=1)}{self._run(ln or ' ', {'code'}, 9)}</w:p>")
            self.body.append(f"<w:p>{self._ppr(None, after=6, line=1)}</w:p>")
        elif isinstance(b, M.PageBreak):
            self.page_break()
        elif isinstance(b, M.Spacer):
            self.body.append(f"<w:p>{self._ppr(None, after=b.pt, line=1)}</w:p>")

    def caption(self, label, num, text, after=6, before=4, keep_next=False):
        self.body.append(f"<w:p>{self._ppr('Caption', 'center', after=after, before=before, line=1, keep_next=keep_next)}"
                         f"{self._run(f'{label} {num}: ', (), 10, bold=True)}{self._run(text, (), 10)}</w:p>")

    def table(self, b: M.Table, borders=True, caption=True, text_width_cm=None):
        tw = text_width_cm or self.text_width_cm()
        widths = b.widths or [1] * len(b.header or b.rows[0])
        total = sum(widths)
        cols = [int(tw * w / total * CM) for w in widths]
        if self.body and "<w:pageBreakBefore/>" in self.body[-1] and not (caption and b.caption):
            # Pages applies a heading's "page break before" to a table that follows it directly
            self.body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="0" w:line="40" w:lineRule="exact"/></w:pPr></w:p>')
        if caption and b.caption:
            self.caption("Table", b.num, b.caption, after=4, before=6, keep_next=True)
        bd = ('<w:tblBorders>' + "".join(f'<w:{s} w:val="single" w:sz="4" w:space="0" w:color="808080"/>'
                                         for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>') if borders else \
            '<w:tblBorders>' + "".join(f'<w:{s} w:val="nil"/>' for s in ("top", "left", "bottom", "right", "insideH", "insideV")) + '</w:tblBorders>'
        x = [f'<w:tbl><w:tblPr><w:tblW w:w="{sum(cols)}" w:type="dxa"/><w:jc w:val="center"/>{bd}<w:tblLayout w:type="fixed"/>'
             f'<w:tblCellMar><w:left w:w="80" w:type="dxa"/><w:right w:w="80" w:type="dxa"/></w:tblCellMar></w:tblPr><w:tblGrid>'
             + "".join(f'<w:gridCol w:w="{c}"/>' for c in cols) + "</w:tblGrid>"]

        def row(cells, header=False):
            r = ["<w:tr>" + ("<w:trPr><w:tblHeader/></w:trPr>" if header else "")]
            for c, wdt in zip(cells, cols):
                shade = '<w:shd w:val="clear" w:color="auto" w:fill="D9E2F3"/>' if header and borders else ""
                paras = []
                for line in str(c).replace("§TE§", "").split("\n"):
                    rs = "".join(self._run(t, st, b.size, bold=header) for t, st in M.runs(line))
                    paras.append(f"<w:p>{self._ppr(None, 'left', after=1, line=1.0)}{rs}</w:p>")
                r.append(f'<w:tc><w:tcPr><w:tcW w:w="{wdt}" w:type="dxa"/>{shade}</w:tcPr>{"".join(paras)}</w:tc>')
            r.append("</w:tr>")
            return "".join(r)
        if b.header:
            x.append(row(b.header, True))
        for rr in b.rows:
            x.append(row(rr))
        x.append("</w:tbl>")
        self.body.append("".join(x))
        self.body.append('<w:p><w:pPr><w:spacing w:before="0" w:after="120" w:line="40" w:lineRule="exact"/></w:pPr></w:p>')

    def image_run(self, path, width_cm):
        data = Path(path).read_bytes()
        w, h = Image.open(path).size
        cx = int(width_cm * EMU_CM)
        cy = int(cx * h / w)
        n = len(self.media) + 1
        name = f"image{n}.png"
        self.media.append((name, data))
        rid = f"rIdImg{n}"
        did = self.ids = self.ids + 1
        return (f'<w:r><w:drawing><wp:inline distT="0" distB="0" distL="0" distR="0"><wp:extent cx="{cx}" cy="{cy}"/>'
                f'<wp:docPr id="{did}" name="Picture {did}"/><wp:cNvGraphicFramePr><a:graphicFrameLocks noChangeAspect="1"/></wp:cNvGraphicFramePr>'
                f'<a:graphic><a:graphicData uri="http://schemas.openxmlformats.org/drawingml/2006/picture"><pic:pic>'
                f'<pic:nvPicPr><pic:cNvPr id="{did}" name="{name}"/><pic:cNvPicPr/></pic:nvPicPr>'
                f'<pic:blipFill><a:blip r:embed="{rid}"/><a:stretch><a:fillRect/></a:stretch></pic:blipFill>'
                f'<pic:spPr><a:xfrm><a:off x="0" y="0"/><a:ext cx="{cx}" cy="{cy}"/></a:xfrm><a:prstGeom prst="rect"><a:avLst/></a:prstGeom></pic:spPr>'
                f'</pic:pic></a:graphicData></a:graphic></wp:inline></w:drawing></w:r>')

    def image(self, path, width_cm, align="center", after=6, keep_next=False):
        self.body.append(f"<w:p>{self._ppr(None, align, after=after, line=1, keep_next=keep_next)}{self.image_run(path, width_cm)}</w:p>")

    def figure(self, b: M.Figure):
        self.image(b.path, min(b.width_cm, self.text_width_cm()), keep_next=True)
        self.caption("Figure", b.num, b.caption, after=10)

    def text_width_cm(self):
        t, r, bm, l = self.margins
        w = 21.0 - l - r
        cols = self.sect["cols"]
        return (w - 0.42 * (cols - 1)) / cols

    # ------------------------------------------------------------ TOC / lists
    def toc(self, entries, field=True):
        """entries: [(level, text, page)] — cached result shown until Word updates the field."""
        tw = int(self.text_width_cm() * CM) - 100
        if field:
            self.body.append('<w:p><w:r><w:fldChar w:fldCharType="begin" w:dirty="true"/></w:r>'
                             '<w:r><w:instrText xml:space="preserve"> TOC \\o "1-3" \\h \\z \\u </w:instrText></w:r>'
                             '<w:r><w:fldChar w:fldCharType="separate"/></w:r></w:p>')
        for level, text, page in entries:
            ind = 0.0 if level == 1 else (0.6 if level == 2 else 1.2)
            bold = level == 1
            rs = self._run(text, (), self.base if level == 1 else self.base - 1, bold=bold) + self._run("\t" + str(page), (), self.base if level == 1 else self.base - 1, bold=bold)
            self.body.append(f"<w:p>{self._ppr(f'TOC{level}', 'left', after=1, before=3 if level == 1 else 0, line=1.0, indent=ind, tabs=[('right', 'dot', tw)])}{rs}</w:p>")
        if field:
            self.body.append('<w:p><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p>')

    # ------------------------------------------------------------ sections
    def _sectpr(self, s):
        t, r, b, l = self.margins
        foot = '<w:footerReference w:type="default" r:id="rIdFooter"/>' if s["numbers"] else '<w:footerReference w:type="default" r:id="rIdFooterEmpty"/>'
        pg = ""
        if s["numbers"]:
            fmt = "lowerRoman" if s["numbers"] == "roman" else "decimal"
            pg = f'<w:pgNumType w:fmt="{fmt}"' + (f' w:start="{s["start"]}"' if s["start"] else "") + "/>"
        typ = '<w:type w:val="continuous"/>' if s["continuous"] else '<w:type w:val="nextPage"/>'
        cols = f'<w:cols w:num="{s["cols"]}" w:space="{int(0.42 * CM)}"/>' if s["cols"] > 1 else '<w:cols w:space="708"/>'
        return (f'<w:sectPr>{foot}{typ}<w:pgSz w:w="11906" w:h="16838"/>'
                f'<w:pgMar w:top="{int(t * CM)}" w:right="{int(r * CM)}" w:bottom="{int(b * CM)}" w:left="{int(l * CM)}" '
                f'w:header="708" w:footer="567" w:gutter="0"/>{pg}{cols}</w:sectPr>')

    def section(self, numbers=None, start=1, cols=1, continuous=False):
        """End the current section; following content uses the new settings."""
        self.pending_break = False  # a new section already starts on a new page
        self.body.append(f"<w:p><w:pPr><w:spacing w:before=\"0\" w:after=\"0\" w:line=\"240\" w:lineRule=\"auto\"/>{self._sectpr(self.sect)}</w:pPr></w:p>")
        self.sect = {"numbers": numbers, "start": start, "cols": cols, "continuous": continuous}
        self.fresh_page = not continuous

    # ------------------------------------------------------------ save
    def _styles(self):
        f, sz = self.font, int(self.base * 2)
        def st(sid, name, ppr="", rpr="", lvl=None, based="Normal"):
            ol = f'<w:outlineLvl w:val="{lvl}"/>' if lvl is not None else ""
            return (f'<w:style w:type="paragraph" w:styleId="{sid}"><w:name w:val="{name}"/><w:basedOn w:val="{based}"/>'
                    f'<w:next w:val="Normal"/><w:qFormat/><w:pPr>{ppr}{ol}</w:pPr><w:rPr>{rpr}</w:rPr></w:style>')
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:styles {NS}>'
                f'<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="{f}" w:hAnsi="{f}" w:cs="{f}" w:eastAsia="{f}"/>'
                f'<w:sz w:val="{sz}"/><w:szCs w:val="{sz}"/><w:lang w:val="en-IN"/></w:rPr></w:rPrDefault>'
                f'<w:pPrDefault><w:pPr><w:widowControl/><w:spacing w:after="120" w:line="{int(240 * self.line)}" w:lineRule="auto"/></w:pPr></w:pPrDefault></w:docDefaults>'
                f'<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/><w:qFormat/></w:style>'
                + st("Heading1", "heading 1", "<w:keepNext/>", f'<w:b/><w:sz w:val="{self.hs[0] * 2}"/>', 0)
                + st("Heading2", "heading 2", "<w:keepNext/>", f'<w:b/><w:sz w:val="{self.hs[1] * 2}"/>', 1)
                + st("Heading3", "heading 3", "<w:keepNext/>", f'<w:b/><w:sz w:val="{self.hs[2] * 2}"/>', 2)
                + st("Caption", "caption", "", '<w:sz w:val="20"/>')
                + st("TOC1", "toc 1") + st("TOC2", "toc 2") + st("TOC3", "toc 3")
                + '</w:styles>')

    def _footer(self, number=True):
        if not number:
            return f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p/></w:ftr>'
        return (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:ftr {NS}><w:p><w:pPr><w:jc w:val="center"/></w:pPr>'
                '<w:r><w:fldChar w:fldCharType="begin"/></w:r><w:r><w:instrText xml:space="preserve"> PAGE </w:instrText></w:r>'
                '<w:r><w:fldChar w:fldCharType="separate"/></w:r><w:r><w:t>1</w:t></w:r><w:r><w:fldChar w:fldCharType="end"/></w:r></w:p></w:ftr>')

    def save(self, path, title="Document", author=""):
        doc = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:document {NS}><w:body>'
               + "".join(self.body) + self._sectpr(self.sect) + "</w:body></w:document>")
        rels = ['<Relationship Id="rIdStyles" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>',
                '<Relationship Id="rIdSettings" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/settings" Target="settings.xml"/>',
                '<Relationship Id="rIdFooter" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer1.xml"/>',
                '<Relationship Id="rIdFooterEmpty" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/footer" Target="footer2.xml"/>']
        rels += [f'<Relationship Id="rIdImg{i + 1}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/image" Target="media/{n}"/>'
                 for i, (n, _) in enumerate(self.media)]
        ct = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
              '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
              '<Default Extension="xml" ContentType="application/xml"/><Default Extension="png" ContentType="image/png"/>'
              '<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
              '<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>'
              '<Override PartName="/word/settings.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.settings+xml"/>'
              '<Override PartName="/word/footer1.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
              '<Override PartName="/word/footer2.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.footer+xml"/>'
              '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
              '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/></Types>')
        settings = (f'<?xml version="1.0" encoding="UTF-8" standalone="yes"?><w:settings {NS}><w:updateFields w:val="true"/>'
                    '<w:defaultTabStop w:val="720"/><w:compat><w:compatSetting w:name="compatibilityMode" w:uri="http://schemas.microsoft.com/office/word" w:val="15"/></w:compat></w:settings>')
        core = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
                'xmlns:dc="http://purl.org/dc/elements/1.1/" xmlns:dcterms="http://purl.org/dc/terms/" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
                f'<dc:title>{escape(title)}</dc:title><dc:creator>{escape(author)}</dc:creator></cp:coreProperties>')
        app = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties">'
               '<Application>MeetBrief report builder</Application></Properties>')
        with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("[Content_Types].xml", ct)
            z.writestr("_rels/.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
                       '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>'
                       '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
                       '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/></Relationships>')
            z.writestr("word/document.xml", doc)
            z.writestr("word/styles.xml", self._styles())
            z.writestr("word/settings.xml", settings)
            z.writestr("word/footer1.xml", self._footer(True))
            z.writestr("word/footer2.xml", self._footer(False))
            z.writestr("word/_rels/document.xml.rels", '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">' + "".join(rels) + "</Relationships>")
            z.writestr("docProps/core.xml", core)
            z.writestr("docProps/app.xml", app)
            for n, data in self.media:
                z.writestr(f"word/media/{n}", data)
