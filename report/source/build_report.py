"""Build the MeetBrief AI project report (RV University format) as PDF and DOCX."""
import sys
from pathlib import Path

import model as M
import pdf_writer as PW
from docx_writer import Docx
from report_content import (ABSTRACT, ACK, ACRONYMS, CH1, CH2, CH3, CH4, DEGREE, FIG, GUIDE, MONTH_YEAR, NAME, TITLE,
                            TITLE_SHORT, USN)
from report_content2 import APPENDIX, CH5, CH6, CH7, CH8, REFERENCES

OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "out")
OUT.mkdir(parents=True, exist_ok=True)
MARGINS = (2.54, 2.54, 2.54, 3.81)  # top, right, bottom, left (cm)
CHAPTERS = CH1 + CH2 + CH3 + CH4 + CH5 + CH6 + CH7 + CH8
LOGO = str(FIG / "rv_logo.png")

CERT = (f"This is to certify that the project work titled “{{{{{TITLE}}}}}” is performed by {NAME} {USN}, a bonafide "
        f"student of {DEGREE} at the School of Computer Science and Engineering, RV University, Bengaluru in partial "
        f"fulfillment for the award of degree {DEGREE} in Computer Science & Engineering, during the Academic year "
        f"**2026-2027**.")
DECL = [f"I hereby declare that the thesis entitled “{TITLE_SHORT}” submitted by me, for the award of the degree "
        f"{DEGREE} in RV University is a record of bonafide work carried out by me under the supervision of {{{{<Guide Name>}}}}.",
        "I further declare that the work reported in this thesis has not been submitted and will not be submitted, either "
        "in part or in full, for the award of any other degree or diploma in this institute or any other institute or university."]
SIGN = [["{{[Guide Name]}}", "Dr. Rashmi S", "Dr. G Shobha"], ["**Guide**", "{{[B.Tech(H)]}}", ""],
        ["{{[Assistant Professor]}}", "Program Director", "Dean"], ["SoCSE", "SoCSE", "SoCSE"],
        ["RV University", "RV University", "RV University"], ["Date:", "Date:", "Date:"]]


def acro_rows():
    """Acronyms in two side-by-side column pairs (fits one page in Word, Pages and the PDF)."""
    half = (len(ACRONYMS) + 1) // 2
    left, right = ACRONYMS[:half], ACRONYMS[half:] + [("", "")] * (2 * half - len(ACRONYMS))
    return [[f"**{a}**", b, f"**{c}**" if c else "", e] for (a, b), (c, e) in zip(left, right)]


def front_entries(blocks):
    """Contents / figures / tables entries in document order (texts only)."""
    toc, lof, lot = [], [], []
    for b in blocks:
        if isinstance(b, M.H1):
            toc.append((1, f"Chapter {b.num}: {b.title}" if b.num else b.title))
        elif isinstance(b, M.H2):
            toc.append((2, f"{b.num} {b.title.upper()}".strip()))
        elif isinstance(b, M.Figure):
            lof.append(f"{b.num} {b.caption}")
        elif isinstance(b, M.Table):
            lot.append(f"{b.num} {b.caption}")
    return toc, lof, lot


# ============================================================================================ PDF
def pdf_story(R, pages, col_width):
    P = PW.Paragraph
    S = PW.ParagraphStyle
    story = []
    for _ in range(2):  # cover page and title page carry identical text (format rule)
        story += [PW.Spacer(1, 1.2 * PW.cm), PW.Image(LOGO, width=6.5 * PW.cm, height=6.5 * PW.cm * 509 / 1012), PW.Spacer(1, 1.0 * PW.cm),
                  R.para("**School of Computer Science and Engineering**", 16, "center", after=10),
                  R.para(MONTH_YEAR, 14, "center", after=22),
                  R.para(f"**{TITLE}**", 20, "center", after=22, leading=26),
                  R.para("*Submitted in partial fulfillment for the award of the degree of*", 14, "center", after=12),
                  R.para(f"**{DEGREE}**", 22, "center", after=26, leading=28),
                  R.para("*by*", 14, "center", after=12),
                  R.para(f"**{NAME}**", 16, "center", after=4), R.para(f"**{USN}**", 16, "center", after=22),
                  R.para("*Guided by*", 14, "center", after=10), R.para(f"**{GUIDE}**", 16, "center", after=0),
                  PW.PageBreak()]
    # certificate
    story += [PW.Spacer(1, 0.4 * PW.cm), PW.Image(LOGO, width=6 * PW.cm, height=6 * PW.cm * 509 / 1012), PW.Spacer(1, 0.6 * PW.cm),
              R.para("**School of Computer Science and Engineering**", 16, "center", after=4),
              R.para("RV University", 12, "center", after=2),
              R.para("RV Vidyaniketan, 8th Mile, Mysore Road, Bengaluru, Karnataka, India - 560059", 12, "center", after=18),
              R.para("**CERTIFICATE**", 16, "center", after=14), R.para(CERT, 12, "justify", after=18)]
    sig = M.Table("", "", None, SIGN, [1, 1, 1], size=12)
    st = R.table(sig, col_width, borders=False, caption=False)
    story += [st, PW.Spacer(1, 0.8 * PW.cm)]
    rows = [["Signature of the Mentor", "Signature of the Guide"], ["", ""], ["Name of the Examiner", "Signature of Examiner"],
            ["1.", "1."], ["", ""], ["2.", "2."]]
    story += [R.table(M.Table("", "", None, rows, [1, 1], size=12), col_width, borders=False, caption=False), PW.PageBreak()]
    # declaration
    story += [PW.Spacer(1, 1 * PW.cm), u(R, "DECLARATION")]
    story += [R.para(t, 12, "justify", after=10) for t in DECL]
    story += [PW.Spacer(1, 2 * PW.cm), R.para("**Place: Bangalore**", 12, "left", after=4),
              PW.Table([[R.para("**Date:**", 12, "left"), R.para("**Signature of the Candidate**", 12, "right")]], colWidths=[col_width / 2] * 2),
              PW.NextPageTemplate("roman"), PW.PageBreak()]
    # abstract, acknowledgement
    story += [PW.Mark("toc", 1, "ABSTRACT"), u(R, "ABSTRACT")] + [R.para(t, 12, "justify", after=8) for t in ABSTRACT] + [PW.PageBreak()]
    story += [PW.Mark("toc", 1, "ACKNOWLEDGEMENT"), u(R, "ACKNOWLEDGEMENT")] + [R.para(t, 12, "justify", after=4) for t in ACK]
    story += [PW.Spacer(1, 0.6 * PW.cm), PW.Table([[R.para("**Place: Bangalore**", 12, "left"), R.para(f"**{NAME}**", 12, "right")],
                                                  [R.para("**Date:**", 12, "left"), ""]], colWidths=[col_width / 2] * 2), PW.PageBreak()]
    # contents / figures / tables / acronyms
    toc, lof, lot = front_entries(CHAPTERS + [M.H1("", "References")] + APPENDIX)
    fm = [(1, "CONTENTS"), (1, "LIST OF FIGURES"), (1, "LIST OF TABLES"), (1, "LIST OF ACRONYMS")]
    toc_rows = [(lv, t, pages.get(("toc", t), "")) for lv, t in [(1, "ABSTRACT"), (1, "ACKNOWLEDGEMENT")] + fm + toc]
    story += [PW.Mark("toc", 1, "CONTENTS"), u(R, "CONTENTS", underline=False), PW.toc_table(toc_rows, col_width), PW.PageBreak()]
    story += [PW.Mark("toc", 1, "LIST OF FIGURES"), u(R, "LIST OF FIGURES", underline=False),
              PW.toc_table([(2, f"Figure {t}", pages.get(("lof", t), "")) for t in lof], col_width, size=12, indent_levels=False), PW.PageBreak()]
    story += [PW.Mark("toc", 1, "LIST OF TABLES"), u(R, "LIST OF TABLES", underline=False),
              PW.toc_table([(2, f"Table {t}", pages.get(("lot", t), "")) for t in lot], col_width, size=12, indent_levels=False), PW.PageBreak()]
    story += [PW.Mark("toc", 1, "LIST OF ACRONYMS"), u(R, "LIST OF ACRONYMS", underline=False),
              R.table(M.Table("", "", None, acro_rows(), [1.3, 3.0, 1.3, 3.0], size=10.5), col_width, borders=False, caption=False),
              PW.NextPageTemplate("arabic")]
    # chapters, references, appendix
    story += R.flow(CHAPTERS, col_width)
    story += [PW.PageBreak(), PW.Mark("toc", 1, "References"), PW.Paragraph("REFERENCES", R.h1)]
    ref = S("ref", parent=R.body, leftIndent=0.8 * PW.cm, firstLineIndent=-0.8 * PW.cm, spaceAfter=6, alignment=PW.TA_LEFT)
    story += [PW.Paragraph(PW.markup(r), ref) for r in REFERENCES]
    story += R.flow(APPENDIX, col_width)
    return PW.flatten(story)


def u(R, text, underline=True):
    st = PW.ParagraphStyle("fh", parent=R.h1, fontSize=14, leading=18, alignment=PW.TA_CENTER, spaceAfter=16)
    return PW.Paragraph(f"<u>{text}</u>" if underline else text, st)


def build_pdf(path):
    pages = {}
    for _ in range(2):  # pass 1 collects page numbers, pass 2 prints them in the contents/lists
        doc = PW.Doc(str(path), MARGINS, title=TITLE_SHORT, author="")
        R = PW.Renderer()
        doc.build(pdf_story(R, pages, doc.col_width))
        pages = {(k, t): p for k, lv, t, p in doc.entries}
    return pages


# ============================================================================================ DOCX
def build_docx(path, pages):
    d = Docx(MARGINS)
    for i in range(2):
        d.image(LOGO, 6.5, after=18)
        d.para("**School of Computer Science and Engineering**", "center", 16, after=10)
        d.para(MONTH_YEAR, "center", 14, after=22)
        d.para(f"**{TITLE}**", "center", 20, after=22, line=1.15)
        d.para("*Submitted in partial fulfillment for the award of the degree of*", "center", 14, after=12)
        d.para(f"**{DEGREE}**", "center", 22, after=26, line=1.15)
        d.para("*by*", "center", 14, after=12)
        d.para(f"**{NAME}**", "center", 16, after=4)
        d.para(f"**{USN}**", "center", 16, after=22)
        d.para("*Guided by*", "center", 14, after=10)
        d.para(f"**{GUIDE}**", "center", 16, after=0)
        d.page_break()
    d.image(LOGO, 5.2, after=8)
    d.para("**School of Computer Science and Engineering**", "center", 16, after=2)
    d.para("RV University", "center", 12, after=0)
    d.para("RV Vidyaniketan, 8th Mile, Mysore Road, Bengaluru, Karnataka, India - 560059", "center", 12, after=12)
    d.para("**CERTIFICATE**", "center", 16, after=10)
    d.para(CERT, "justify", 12, after=18)
    d.table(M.Table("", "", None, SIGN, [1, 1, 1], size=12), borders=False, caption=False)
    d.para("", after=6, line=1)
    d.table(M.Table("", "", None, [["Signature of the Mentor", "Signature of the Guide"], ["Name of the Examiner", "Signature of Examiner"],
                                   ["1.", "1."], ["2.", "2."]], [1, 1], size=12), borders=False, caption=False)
    d.page_break()
    d.para("**DECLARATION**", "center", 14, underline=True, after=18, before=24)
    for t in DECL:
        d.para(t, "justify", 12, after=10)
    d.para("", after=40)
    d.para("**Place: Bangalore**", "left", 12, after=4)
    d.table(M.Table("", "", None, [["**Date:**", "**Signature of the Candidate**"]], [1, 1], size=12), borders=False, caption=False)
    d.section(numbers="roman", start=1)
    d.para("**ABSTRACT**", "center", 14, underline=True, after=16)
    for t in ABSTRACT:
        d.para(t, "justify", 12, after=8)
    d.page_break()
    d.para("**ACKNOWLEDGEMENT**", "center", 14, underline=True, after=16)
    for t in ACK:
        d.para(t, "justify", 12, after=4)
    d.table(M.Table("", "", None, [["**Place: Bangalore**", f"**{NAME}**"], ["**Date:**", ""]], [1, 1], size=12), borders=False, caption=False)
    d.page_break()
    toc, lof, lot = front_entries(CHAPTERS + [M.H1("", "References")] + APPENDIX)
    def listing(title, rows):
        d.para(f"**{title}**", "center", 14, after=12)
        d.toc([(lv, t, pg) for lv, t, pg in rows], field=False)
        d.page_break()
    fm = [(1, "ABSTRACT"), (1, "ACKNOWLEDGEMENT"), (1, "CONTENTS"), (1, "LIST OF FIGURES"), (1, "LIST OF TABLES"), (1, "LIST OF ACRONYMS")]
    d.para("**CONTENTS**", "center", 14, after=12)
    d.toc([(lv, t, pages.get(("toc", t), "")) for lv, t in fm], field=False)
    d.toc([(lv, t, pages.get(("toc", t), "")) for lv, t in toc], field=False)
    d.page_break()
    listing("LIST OF FIGURES", [(2, f"Figure {t}", pages.get(("lof", t), "")) for t in lof])
    listing("LIST OF TABLES", [(2, f"Table {t}", pages.get(("lot", t), "")) for t in lot])
    d.para("**LIST OF ACRONYMS**", "center", 14, after=12)
    d.table(M.Table("", "", None, acro_rows(), [1.3, 3.0, 1.3, 3.0], size=10.5), borders=False, caption=False)
    d.section(numbers="arabic", start=1)
    for b in CHAPTERS:
        d.add(b)
    d.add(M.H1("", "References"))
    for r in REFERENCES:
        d.body.append(f"<w:p>{d._ppr(None, 'left', after=6, indent=0.8, hanging=0.8)}" + "".join(d._run(t, st) for t, st in M.runs(r)) + "</w:p>")
    for b in APPENDIX:
        d.add(b)
    d.save(str(path), title=TITLE_SHORT)


if __name__ == "__main__":
    pdf = OUT / "MeetBrief_AI_Project_Report.pdf"
    pages = build_pdf(pdf)
    build_docx(OUT / "MeetBrief_AI_Project_Report.docx", pages)
    n = max(int(p) for (k, t), p in pages.items() if k == "toc" and str(p).isdigit())
    print("built", pdf, "chapters start at arabic 1; last toc page", n)
