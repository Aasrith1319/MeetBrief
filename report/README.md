# MeetBrief AI — project report and research paper

| File | What it is |
|---|---|
| `MeetBrief_AI_Project_Report.pdf` | Project report in the RV University format (A4; margins L 3.81 / R, T, B 2.54 cm; Times New Roman 12, 1.5 spacing; roman front-matter and arabic chapter page numbers). Print/submit this one. |
| `MeetBrief_AI_Project_Report.docx` | The same report, editable in Word or Pages (same 50-page layout). |
| `MeetBrief_AI_Research_Paper_IEEE.pdf` / `.docx` | 4-page IEEE conference paper (A4, two columns). |
| `MeetBrief_AI_Presentation_Guide.docx` | Slide content, speaker notes and viva answers for 4 presenters. Rebuild: `build_presentation_guide.py ..` |
| `MeetBrief_AI_Research_Paper_IEEE_v2.pdf` / `.docx` | Extended paper following the Team 4 reference structure (research gaps, questions, threats to validity, contributions). Rebuild: `build_paper_v2.py ..` |
| `source/` | Scripts, figures and text used to generate all four files. |

## Fill in before submitting (shown in red)
Month/Year, name of the degree, candidate name, USN, guide name and designation, mentor name, program `[B.Tech(H)]`,
author names and e-mails in the paper, and personalise section 7.1 (Personal Learning Experience).
Red text marks every place; change it to black after filling in.

## Regenerate after editing the text
Edit `source/report_content.py`, `source/report_content2.py` or `source/paper_content.py`, then:

    cd ~/nlp/report/source
    ../../.venv/bin/python figures.py
    ../../.venv/bin/python build_report.py ..
    ../../.venv/bin/python build_paper.py ..

If you edit the .docx directly and pages shift, update the page numbers in the Contents / List of Figures / List of
Tables by hand (or insert Word's automatic table of contents: References → Table of Contents; chapter and section
headings use Word's Heading 1/2/3 styles).
