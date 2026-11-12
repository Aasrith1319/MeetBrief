"""Build the MeetBrief AI research paper (IEEE conference style, A4, two columns) as PDF and DOCX."""
import sys
from pathlib import Path

import model as M
import pdf_writer as PW
from docx_writer import Docx, CM
from paper_content import ABSTRACT, AUTHORS, BODY, KEYWORDS, REFS, TITLE

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
MARGINS = (1.9, 1.432, 4.3, 1.432)  # IEEE A4: top, right, bottom, left (cm)
TITLE_CM = 6.6


# ============================================================================================ PDF
def build_pdf(path):
    doc = PW.Doc(str(path), MARGINS, two_col=True, title_frame_cm=TITLE_CM, title=TITLE, author="")
    for t in doc.pageTemplates:  # IEEE papers carry no page numbers
        t.onPage = lambda c, d: None
    R = PW.Renderer(base=10, line=1.2, h_sizes=(24, 10, 10), paper=True)
    R.h2.fontName = "TNR"
    S = PW.ParagraphStyle
    story = [PW.NextPageTemplate("cols"),
             PW.Paragraph(PW.markup(TITLE), S("t", fontName="TNR", fontSize=22, leading=26, alignment=PW.TA_CENTER, spaceAfter=14))]
    cells = []
    for name, dept, uni, mail in AUTHORS:
        cells.append(PW.Paragraph(f"{PW.markup(name)}<br/><i>{dept}</i><br/><i>{uni}</i><br/>{PW.markup(mail)}",
                                  S("a", fontName="TNR", fontSize=10, leading=12.5, alignment=PW.TA_CENTER)))
    W = 21 * PW.cm - (MARGINS[1] + MARGINS[3]) * PW.cm
    story += [PW.Table([cells], colWidths=[W / len(cells)] * len(cells)), PW.FrameBreak()]
    ab = S("ab", fontName="TNR-B", fontSize=9, leading=10.5, alignment=4, spaceAfter=6)
    story += [PW.Paragraph(f"<i>Abstract</i>—{PW.markup(ABSTRACT)}", ab),
              PW.Paragraph(f"<i>Index Terms</i>—{PW.markup(KEYWORDS)}", ab)]
    story += R.flow(BODY, doc.col_width)
    story += [PW.Paragraph("REFERENCES", R.h2)]
    rs = S("r", fontName="TNR", fontSize=8, leading=9.5, leftIndent=0.55 * PW.cm, firstLineIndent=-0.55 * PW.cm, spaceAfter=2, alignment=0)
    story += [PW.Paragraph(f"[{i + 1}]&nbsp;&nbsp;{PW.markup(r)}", rs) for i, r in enumerate(REFS)]
    doc.build(PW.flatten(story))


# ============================================================================================ DOCX
class PaperDocx(Docx):
    def add(self, b):
        if isinstance(b, M.H2):
            self.body.append(f"<w:p>{self._ppr(None, 'center', after=4, before=8, line=1.0, keep_next=True)}"
                             f"{self._run(f'{b.num} {b.title}', (), 10, caps=True)}</w:p>")
        elif isinstance(b, M.H3):
            self.body.append(f"<w:p>{self._ppr(None, 'left', after=2, before=4, line=1.0, keep_next=True)}"
                             f"{self._run(f'{b.num} {b.title}', (), 10, italic=True)}</w:p>")
        elif isinstance(b, M.P):
            ppr = self._ppr(None, "justify", after=0, line=1.0).replace("<w:jc ", f'<w:ind w:firstLine="{int(0.35 * CM)}"/><w:jc ')
            self.body.append(f"<w:p>{ppr}" + "".join(self._run(t, st) for t, st in M.runs(b.text)) + "</w:p>")
        elif isinstance(b, M.Figure):
            self.image(b.path, self.text_width_cm(), keep_next=True, after=2)
            self.body.append(f"<w:p>{self._ppr(None, 'center', after=8, line=1.0)}{self._run(f'Fig. {b.num}. ', (), 8)}{self._run(b.caption, (), 8)}</w:p>")
        elif isinstance(b, M.Table):
            self.body.append(f"<w:p>{self._ppr(None, 'center', after=2, before=6, line=1.0, keep_next=True)}{self._run(f'TABLE {b.num}', (), 8)}</w:p>")
            self.body.append(f"<w:p>{self._ppr(None, 'center', after=3, line=1.0, keep_next=True)}{self._run(b.caption, (), 8, caps=True)}</w:p>")
            self.table(b, caption=False)
        else:
            super().add(b)


def build_docx(path):
    d = PaperDocx(MARGINS, line=1.0, base_pt=10)
    d.para(TITLE, "center", 22, after=12, line=1.0)
    cells = [[f"{n}\n*{dep}*\n*{u}*\n{m}" for n, dep, u, m in AUTHORS]]
    d.table(M.Table("", "", None, cells, [1, 1], size=10), borders=False, caption=False)
    d.section(cols=2, continuous=True)
    d.body.append(f"<w:p>{d._ppr(None, 'justify', after=4, line=1.0)}{d._run('Abstract', (), 9, bold=True, italic=True)}"
                  f"{d._run('—' + ABSTRACT, (), 9, bold=True)}</w:p>")
    d.body.append(f"<w:p>{d._ppr(None, 'justify', after=6, line=1.0)}{d._run('Index Terms', (), 9, bold=True, italic=True)}"
                  f"{d._run('—' + KEYWORDS, (), 9, bold=True)}</w:p>")
    for b in BODY:
        d.add(b)
    d.add(M.H2("", "References"))
    for i, r in enumerate(REFS):
        d.body.append(f"<w:p>{d._ppr(None, 'left', after=2, line=1.0, indent=0.55, hanging=0.55)}"
                      + d._run(f"[{i + 1}]\t", (), 8) + "".join(d._run(t, st, 8) for t, st in M.runs(r)) + "</w:p>")
    d.save(str(path), title=TITLE)


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    build_pdf(OUT / "MeetBrief_AI_Research_Paper_IEEE.pdf")
    build_docx(OUT / "MeetBrief_AI_Research_Paper_IEEE.docx")
    print("built paper")
