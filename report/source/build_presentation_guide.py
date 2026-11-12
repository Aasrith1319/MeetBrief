"""Build the MeetBrief AI presentation guide (slide content, speaker notes and viva answers for 4 presenters) as DOCX."""
import sys
from pathlib import Path

import model as M
from docx_writer import Docx
from model import Bullets, Figure, H1, H2, H3, P, PageBreak, Table

FIG = Path(__file__).parent / "fig"
OUT = Path(sys.argv[1] if len(sys.argv) > 1 else "..") / "MeetBrief_AI_Presentation_Guide.docx"
_t = [0]


def T(caption, header, rows, widths):
    _t[0] += 1
    return Table(str(_t[0]), caption, header, rows, widths, 9.5)


_f = [0]


def F(caption, name, width=15.5):
    _f[0] += 1
    return Figure(str(_f[0]), caption, str(FIG / name), width)


def slide(n, title, points, say, numbered=False):
    return [H3("", f"Slide {n}: {title}"), P("**On the slide**", space_after=2, keep_next=True), Bullets(points, numbered),
            P("**What to say**", space_after=2, keep_next=True), P(say)]


def qa(items):
    out = [H2("", "Questions you may be asked")]
    for q, a in items:
        out += [P(f"**Q: {q}**", space_after=2, keep_next=True, align="left"), P(f"A: {a}")]
    return out


FRONT = [
    P("**MeetBrief AI**", align="center", size=26, space_after=4),
    P("Presentation Guide", align="center", size=16, space_after=4),
    P("Slide content, speaker notes and viva answers, divided for 4 presenters", align="center", space_after=16),
    P("**One-line pitch:** MeetBrief AI is a Chrome extension and local backend that captures online meetings, then "
      "gives late joiners a catch-up, explains and translates what was said, and answers questions with evidence, "
      "using only free open models that run on a laptop."),
    H2("", "Who presents what"),
    T("Division of work (about 5 minutes each; change the timing to match your slot)",
      ["Presenter", "Part", "Slides", "Main topics"], [
          ["{{Member 1 name}}", "1. Problem and background", "1–5", "Problem statement, existing work and gap, objectives, scope, requirements"],
          ["{{Member 2 name}}", "2. System design and workflow", "6–10", "Architecture, tech stack, end-to-end workflow, hybrid capture, shared rooms"],
          ["{{Member 3 name}}", "3. NLP models and methodology", "11–14", "Models used, meeting memory, summaries and grounded Q&A, multilingual pipeline"],
          ["{{Member 4 name}}", "4. Results, demo and conclusion", "15–20", "Evaluation, model comparison, testing and security, live demo, limitations, future work"],
      ], [2.6, 3.6, 1.1, 7.2]),
    P("Text in red is for you to fill in. Everyone should read the **Key facts** page, because a viva question can go to any member."),
    H2("", "Read this before making slides"),
    Bullets([
        "**The speech accuracy figure (WER 0.0) was measured with Whisper *base*.** The system now uses Whisper *small*, "
        "and that figure has not been re-measured. Say which model it came from.",
        "**Evaluation numbers come from small synthetic datasets.** Call them a sanity check, not general accuracy.",
        "**The multilingual results use Mac text-to-speech voices,** not real speakers. In a real Meet call, one "
        "Telugu-labelled line has been captured so far; a full live test across all five languages has not been completed.",
        "**Never say \"all languages\" or \"100% accurate\".** The accurate claim is in the Key facts below.",
    ]),
    H2("", "Key facts everyone must know"),
    T("Key facts", ["Item", "Value"], [
        ["Project type", "Chrome Manifest V3 extension + Python FastAPI backend + SQLite"],
        ["AI models", "9 open models from Hugging Face, all run locally; no paid or external AI API"],
        ["Meeting platforms", "Google Meet tested live; Zoom web and Teams web are experimental"],
        ["Capture", "Meet captions + tab audio together (hybrid), also transcript and recording upload"],
        ["Languages", "Speech labelled as English, Telugu, Kannada, Hindi or Tamil by default (configurable; Whisper knows about 99). Translation to the 21 languages in the code table; 14 are offered in the panel"],
        ["Code size", "About 8,200 lines of Python (including tests) and 2,500 lines of extension JavaScript"],
        ["API", "52 HTTP routes (40 meeting routes, 12 room routes)"],
        ["Automated checks", "88 backend tests, 42 meeting-simulator checks, 12 rooms checks, 17 Meet-page checks, all passing at the last run"],
        ["Machine used", "Apple M2, 16 GB RAM, models on CPU"],
    ], [4.0, 10.5]),
]

P1 = [
    H1("", "Part 1: Problem and Background"),
    P("**Presenter:** {{Member 1 name}}", align="left"),
    *slide(1, "Title", ["MeetBrief AI: a multilingual, context-aware meeting assistant", "Team names, guide name, RV University, School of CSE"],
           "Good morning. We are presenting MeetBrief AI, a meeting assistant that helps people understand online meetings "
           "even if they join late, speak a different language, or miss a technical point. Everything runs locally on a laptop."),
    *slide(2, "Problem statement", [
        "Late joiners lose context and interrupt the meeting to ask what happened",
        "Decisions, owners and deadlines get lost in conversation",
        "Multilingual teams switch languages mid-meeting",
        "Cloud AI note-takers send private meetings to third parties, and may invent details",
    ], "Our problem statement: design a privacy-preserving, multilingual meeting assistant that captures online meetings "
       "without sending data to external AI services, extracts decisions and tasks with evidence, gives faithful summaries, "
       "refuses to guess when information is missing, and gives late joiners a personal catch-up, using only open models "
       "that run on a student laptop."),
    *slide(3, "Existing work and the gap", [
        "Early: HMM dialogue acts (Stolcke 2000), AMI and ICSI corpora, TextRank (2004)",
        "Structured outcomes: action items and decisions (Purver 2007), CALO assistant (Tur 2010)",
        "Transformers: BERT, SQuAD 2.0 (unanswerable questions), BART, Whisper, NLLB-200",
        "Known risk: abstractive models hallucinate (Maynez 2020)",
        "Gap: no surveyed system combines local models, evidence, abstention, Indian languages and late-joiner catch-up",
    ], "Research moved from hand-built features to pre-trained Transformers. Two findings shaped our design: meeting outcomes "
       "work better as structured records than as plain summaries, and abstractive models can invent facts. So we use models "
       "for fluency but link every claim back to the transcript. No system we surveyed brought all of these together."),
    *slide(4, "Objectives", [
        "Capture meetings from captions, tab audio, transcripts and recordings",
        "Build a structured meeting memory: decisions, tasks, owners, deadlines, questions",
        "Generate evidence-linked summaries; answer questions and abstain when unsure",
        "Explain and translate content for each person",
        "Support late joiners with shared rooms and \"What I missed\"",
        "Keep data private and measure every component",
    ], "We set eight objectives in the report, grouped here into six. Each maps to a working feature, and each was measured "
       "or tested, which my teammates will show."),
    *slide(5, "Scope and requirements", [
        "In scope: extension, local backend, shared rooms, 9 local models, evaluation",
        "Out of scope: recovering speech nobody captured, meeting bots, native mobile apps",
        "See the requirement tables below (pick the main rows for the slide)",
    ], "Here is what we built and what we deliberately left out. MeetBrief cannot recover speech from before anyone's browser "
       "joined. For that, a user can upload the host's recording or official transcript."),
    T("Functional requirements", ["ID", "Requirement"], [
        ["FR1", "Detect a meeting and capture captions and tab audio with user consent"],
        ["FR2", "Import transcripts (.txt, .vtt, .srt, .json, .docx) and recordings (.mp4, .m4a, .mp3, .wav, .webm)"],
        ["FR3", "Identify speakers from captions, or separate voices from audio"],
        ["FR4", "Extract decisions, tasks, owners, deadlines and unresolved questions with evidence"],
        ["FR5", "Generate catch-up, quick, detailed, chronological, topic and personalised summaries"],
        ["FR6", "Answer questions from the transcript and abstain when the answer is absent"],
        ["FR7", "Explain any statement by style and difficulty; translate per viewer"],
        ["FR8", "Share a room per meeting link: one capturer, automatic handover, per-member catch-up"],
        ["FR9", "Export results; allow task edits and speaker naming"],
    ], [1.4, 13.1]),
    T("Non-functional requirements", ["Type", "Requirement"], [
        ["Privacy", "Local models only; private in-memory mode; audio deleted right after transcription; 30-day default retention"],
        ["Faithfulness", "Outputs link to transcript segments; uncertain items are flagged"],
        ["Performance", "A 15 s audio chunk must finish in under 15 s to keep up live (measured about 9 s on average, 13.6 s at worst)"],
        ["Reliability", "Each model falls back to classical NLP if missing; capturer handover after 25 s without a heartbeat"],
        ["Security", "Token auth, restricted CORS, allow-listed member routes, upload size limits, escaped UI text"],
    ], [2.8, 11.7]),
    T("Hardware and software used", ["Category", "Details"], [
        ["Hardware", "Apple M2 laptop, 16 GB RAM, about 8–9 GB of disk for model files; a second laptop on the same Wi-Fi for rooms"],
        ["Browser", "Google Chrome 116 or later (Manifest V3, side panel, tabCapture, offscreen documents)"],
        ["Language/runtime", "Python 3.13, JavaScript"],
        ["Backend", "FastAPI, Uvicorn, Pydantic, SQLite"],
        ["ML libraries", "PyTorch, Transformers, sentence-transformers, faster-whisper, PyAV, scikit-learn, langdetect"],
        ["Export", "ReportLab, uharfbuzz (Telugu/Hindi text shaping in PDFs)"],
        ["Testing", "pytest, browser harnesses with the real background.js, StackHawk HawkScan (DAST)"],
    ], [3.2, 11.3]),
    *qa([
        ("How is this different from Otter or Google's own notes?", "Those run in the cloud. MeetBrief runs open models on your own "
         "laptop, links outputs to evidence, abstains when unsure, supports code-mixed Indian-language input, and gives each late joiner their own catch-up."),
        ("Why not use GPT or Claude?", "Meetings are private, and a paid API adds cost and sends data outside. Our aim was to show this works with free local models."),
        ("Can it capture what was said before anyone joined?", "No. No extension can. Users can upload the host's recording or official transcript instead."),
    ]),
]

P2 = [
    H1("", "Part 2: System Design and Workflow"),
    P("**Presenter:** {{Member 2 name}}", align="left"),
    *slide(6, "System architecture", ["Use the architecture figure below", "Three layers: browser extension, local API, NLP engine and storage"],
           "There are three layers. In the browser, content scripts read the meeting page, a service worker manages capture state, "
           "and an offscreen document records tab audio. The FastAPI backend receives everything and runs the NLP. SQLite stores "
           "meetings on disk, and private meetings stay in memory only. The side panel shows results and can also run as a web app."),
    F("System architecture", "architecture.png"),
    *slide(7, "Technology stack", [
        "Extension: Manifest V3 service worker, content scripts, offscreen document, side panel",
        "Backend: Python, FastAPI, Uvicorn, SQLite",
        "AI: PyTorch, Transformers, sentence-transformers, faster-whisper",
        "Platform adapters: Google Meet, Zoom web, Teams web",
    ], "Each meeting platform has a small adapter that outputs speaker and text. Everything after that uses one common Segment "
       "format, so the NLP does not depend on the platform."),
    *slide(8, "End-to-end workflow", [
        "Detect: the meeting code is found from the link and the user joins",
        "Room: the first person auto-shares; later people join automatically",
        "Capture: captions and tab audio are read by the elected capturer",
        "Normalise: text is cleaned, de-duplicated and stored as Segments",
        "Understand: speakers, language, decisions, tasks, questions, topics",
        "Serve: summary, Ask AI, Explain Again, Read in, export",
        "End: when the last member leaves, the final summary is built",
    ], "This is the full journey of a sentence. It is captured, cleaned, understood, and then available to every member in their "
       "own language. Results update live while the meeting continues.", numbered=True),
    F("Processing pipeline", "pipeline.png"),
    *slide(9, "Hybrid capture: captions and tab audio", [
        "Captions: real names, and they include the recording person's own voice",
        "Tab audio: 15-second WebM/Opus chunks, transcribed by Whisper, then deleted",
        "Merge: an audio sentence with 60% or more content-word overlap with one caption line is dropped",
        "If captions stop, tab audio carries the meeting",
        "Voice naming: after 2 agreeing matches, \"Speaker 2\" gets the caption's real name",
    ], "Neither source is enough alone. Captions have names but can miss speech. Tab audio works without captions but never "
       "contains your own voice, because Meet does not play you back to yourself. So we use both, and keep only what the captions missed."),
    *slide(10, "Shared rooms for late joiners", [
        "A room is keyed by the meeting link; no invitations needed",
        "One capturer is elected through 10 s heartbeats; others stand by, so no duplicates",
        "If the capturer leaves or crashes, a member takes over after about 25 s",
        "Each member's join time defines their \"What I missed\"",
        "Idle rooms expire after 15 minutes; the last person leaving triggers the final summary",
    ], "Rooms are what make this useful for late joiners. If I join 20 minutes late, the room already holds everything said, and "
       "I get a catch-up of exactly what I missed. Only one laptop records, so nothing is duplicated."),
    F("Shared room behaviour", "rooms.png", 14),
    *qa([
        ("Why does the user have to click the toolbar icon for tab audio?", "Chrome only allows tab capture after the user invokes the "
         "extension on that tab: the toolbar icon, a keyboard shortcut or a context menu. A click inside the side panel does not count. We found this during live testing."),
        ("Why an offscreen document?", "A Manifest V3 service worker has no access to media streams, so recording runs in an offscreen document."),
        ("How do you avoid duplicates?", "Three ways: only one capturer per room, redrawn captions are merged, and audio lines that match a caption are dropped."),
        ("What happens if the backend laptop goes off?", "That is the single point of failure in our setup. Members cannot reach the room until it returns. Stored meetings are safe in SQLite."),
    ]),
]

P3 = [
    H1("", "Part 3: NLP Models and Methodology"),
    P("**Presenter:** {{Member 3 name}}", align="left"),
    *slide(11, "Models used", ["Show the model table below", "All open models, downloaded once, run locally"],
           "We use nine open models, each for one job. Each can be replaced with a setting, and if one is missing that feature "
           "falls back to classical NLP such as TextRank and TF-IDF, and the interface says so."),
    T("Models and what each does (sizes are approximate)", ["Task", "Model", "Size", "Used for"], [
        ["Speech recognition", "Whisper small (faster-whisper, int8)", "244 M", "Speech to text and direct speech-to-English translation"],
        ["Speaker separation", "microsoft/wavlm-base-plus-sv", "95 M", "Voice embeddings, online clustering (cosine threshold 0.86)"],
        ["Summarization", "philschmid/bart-large-cnn-samsum", "400 M", "Abstractive dialogue overview"],
        ["Translation", "facebook/nllb-200-distilled-600M", "600 M", "Summaries and transcript lines in the viewer's language"],
        ["Explanation", "Qwen/Qwen2.5-1.5B-Instruct", "1.5 B", "Explain Again: simplify, example, steps, analogy"],
        ["Question answering", "deepset/roberta-base-squad2", "125 M", "Extractive answers with a \"no answer\" option"],
        ["Embeddings", "paraphrase-multilingual-MiniLM-L12-v2", "118 M", "Semantic search, topics, evidence alignment"],
        ["Zero-shot NLI", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "280 M", "Optional second opinion on dialogue acts"],
        ["Named entities", "dslim/bert-base-NER", "110 M", "People, organisations, places in memory"],
    ], [2.9, 5.6, 1.2, 4.8]),
    *slide(12, "Methodology: structured meeting memory", [
        "Normalise: one Segment schema (text, time, speaker, language, source, flags)",
        "Dialogue acts: decision, proposal, task, question, other",
        "Extract: tasks with owner and deadline; decisions with revision history",
        "Link: \"actually\" or \"instead\" marks the earlier decision as superseded",
        "User corrections are stored separately and always win",
    ], "Instead of only summarising, we build a structured memory of the meeting. Every item keeps the IDs of the transcript "
       "segments it came from. Decisions and tasks use transparent rules, because we measured rules at 93.8% accuracy against "
       "59.4% for zero-shot NLI on dialogue acts. The neural model could not tell deciding from suggesting."),
    *slide(13, "Summaries and grounded Q&A", [
        "Summary: BART writes the overview; each sentence is aligned to transcript evidence",
        "Unsupported sentences or unseen entities are flagged",
        "Q&A: hybrid sparse + dense retrieval, then a relevance gate, then SQuAD 2.0 reader",
        "Abstain when passages cover under half the question's content words",
        "\"Why\" questions need an explicit reason in the transcript",
    ], "This is where we control hallucination. A generated sentence must be supported by the transcript or it is flagged. For "
       "questions, if the transcript does not contain the answer, MeetBrief says so instead of guessing. In our evaluation it "
       "abstained correctly on all unanswerable questions."),
    *slide(14, "Multilingual pipeline", [
        "Split audio on pauses; detect language per utterance",
        "Guess limited to the meeting languages (default: en, te, kn, hi, ta)",
        "Non-English: Whisper translates speech straight to English",
        "Models read the English, so tasks spoken in any language reach the summary",
        "Each viewer picks \"Read in\"; lines show \"Translated from Telugu\" with the original below",
    ], "Our key finding: Whisper small writes Telugu and Kannada text badly, but understands the speech well enough to translate "
       "it. So we ask Whisper for English directly. Telugu then came out very well, for example: Ravi will be working on the "
       "database. Hindi and Tamil keep the original text beside the English. Telugu and Kannada show only the English, because "
       "their script output is unreliable. Each viewer can read in their own language through NLLB-200."),
    T("Five-language test (Mac text-to-speech voices, live-style 15 s chunks)", ["Spoken", "Language label", "English output example", "Quality"], [
        ["English", "Correct", "Ravi will handle the database work.", "Exact"],
        ["Telugu", "Correct", "We will meet again at 10 am tomorrow.", "Very good"],
        ["Hindi", "Correct", "We will talk about budget tomorrow. If you have any questions, ask.", "Good"],
        ["Tamil", "Correct", "We will meet tomorrow morning at 4 o'clock. (should be evening)", "Good, some errors"],
        ["Kannada", "Sometimes wrong", "If you have any doubts, ask me. (often loose)", "Weakest"],
    ], [2.0, 2.7, 7.4, 2.4]),
    *qa([
        ("Why rules for decisions when you have neural models?", "We measured both. Rules scored 0.938 and zero-shot NLI 0.594 on 32 labelled sentences. NLI recalled 0 of 8 decisions. So NLI is optional and only raises confidence."),
        ("Why Qwen2.5-1.5B?", "In our 9-item benchmark it gave 8 correct explanations against 2 for Qwen 0.5B and 0 for Flan-T5-large. This is a small human-rated sample."),
        ("What is abstention?", "Refusing to answer when evidence is missing. The reader scores a no-answer option, and a relevance gate rejects weak passages."),
        ("Why does Kannada perform worst?", "Whisper small has little Kannada ability, and Kannada sounds close to Telugu to the model. A larger model would help but is too slow live on our laptop."),
        ("What is diarization?", "Working out who spoke when. We embed each segment with WavLM and cluster online. It gives labels like Speaker 1, not names."),
    ]),
]

P4 = [
    H1("", "Part 4: Results, Demo and Conclusion"),
    P("**Presenter:** {{Member 4 name}}", align="left"),
    *slide(15, "Evaluation results", ["Show the results table below", "State clearly: small synthetic datasets"],
           "We evaluated each component. The held-out set was annotated before the first run, though two fixes were made after seeing "
           "failures, so we treat it as only partly unbiased. Action items scored F1 1.0, decisions 0.8, and Q&A was correct on all "
           "answerable questions and abstained on all unanswerable ones."),
    T("Measured results (held-out set unless stated; with models)", ["Metric", "Result"], [
        ["Decisions precision / recall / F1", "0.667 / 1.0 / 0.8"],
        ["Action items P / R / F1", "1.0 / 1.0 / 1.0"],
        ["Proposals P / R / F1", "1.0 / 0.333 / 0.5 (weakest extraction result)"],
        ["Task owner and deadline accuracy", "1.0 and 1.0"],
        ["Q&A answerable / unanswerable abstained", "4/4 and 2/2 (development set: 12/12 and 5/5)"],
        ["Overview ROUGE-1 / 2 / L", "0.55 / 0.367 / 0.43 (TextRank: 0.357 / 0.116 / 0.242)"],
        ["Abstractive sentences supported by evidence", "4/4"],
        ["Dialogue-act accuracy, 32 sentences", "Rules 0.938; zero-shot NLI 0.594"],
        ["ASR word error rate, 29.3 s synthetic audio", "0.0 with Whisper base (clean TTS; real speech will be worse; not re-measured on small)"],
        ["Diarization, same audio", "Speaker accuracy 1.0, 3 of 3 speakers found"],
        ["Translation round-trip chrF", "Hindi 0.835, Telugu 0.827; numbers preserved 6/6 each"],
    ], [7.5, 7.0]),
    *slide(16, "Rules versus models", [
        "Overview ROUGE-1 rose from 0.357 (TextRank) to 0.55 (BART) on held-out",
        "Dialogue acts: rules 0.938 beat NLI 0.594",
        "Explanation: Qwen 1.5B 8/9 correct, Flan-T5-large 0/9",
        "Latency cost: summary about 0.9 ms with rules, about 5.8 s with models",
    ], "Models did not win everywhere. They improved summary quality and explanations, but rules were better for dialogue acts. "
       "So we chose per task from evidence, rather than using a neural model everywhere."),
    F("ROUGE scores, rules versus models", "rouge.png", 12),
    *slide(17, "Testing and security", [
        "88 backend tests; 42 simulator, 12 rooms and 17 Meet-page checks",
        "Simulations use the real background.js, including crash handover",
        "HawkScan: first scan 1 High, 2 Medium, 3 Low; final scans 0 open findings",
        "Root cause of the High: a threading race, fixed with a database lock",
        "Live two-laptop testing found bugs that simulation could not",
    ], "Beyond unit tests, we simulated rooms with the real extension code. The security scan found a High issue, which turned out "
       "to be a database race rather than injection, and we fixed it. After later changes the scan subscription expired, so the "
       "latest changes are covered by tests, not a new scan. Live testing mattered most: it exposed Chrome's tab-capture permission rule."),
    *slide(18, "Live demo", ["Run the steps in the demo checklist below", "Keep a recorded backup"],
           "Now we will show it working in a real Google Meet call between two laptops."),
    H3("", "Demo checklist (practise this at least twice)"),
    Bullets([
        "Before: start the backend, reload the extension, connect both laptops to the same Wi-Fi.",
        "Second laptop settings: backend URL `http://<first laptop IP>:8000`, **API token empty**, name and email saved under Settings → Account.",
        "Sit in separate rooms or use earphones. **Unmute in Meet.**",
        "On the recording laptop: join first, **click the MeetBrief toolbar icon once**, and turn on CC.",
        "Speak a decision and a task in English, for example: Ravi will finish the database by Friday.",
        "The other person speaks in Telugu or Hindi. Open **Transcript** and show the *Translated from* tag.",
        "Show **Decisions**, **Action Items**, then **Ask AI**: one answerable question, and one unanswerable one to show abstention.",
        "Show **What I missed** on the second laptop.",
        "Backup: a screen recording, and `datasets/sample_transcripts/sprint_planning.txt` through Upload if Wi-Fi or Meet fails.",
    ], numbered=True),
    *slide(19, "Limitations and future work", [
        "Datasets are small and synthetic; no AMI/ICSI-scale evaluation yet",
        "Kannada is weak; Telugu and Kannada show English only",
        "With captions off, the recording person's own voice is not captured",
        "Meet captions follow one language at a time",
        "Real-speech accuracy not yet measured; Zoom and Teams experimental",
        "Future: microphone capture, larger or fine-tuned Indic ASR, real-meeting evaluation, hosted server",
    ], "We want to be honest about limits. The biggest are small evaluation data and weak Kannada. The next step is microphone "
       "capture for the recording person, and an Indic-focused speech model."),
    *slide(20, "Conclusion", [
        "A working local, multilingual meeting assistant using 9 open models",
        "Evidence-linked outputs and abstention reduce the risk of invented facts",
        "Shared rooms give each late joiner a personal catch-up",
        "Measured design choices: models where they help, rules where they win",
    ], "To conclude: MeetBrief shows a useful and private meeting assistant is possible on a laptop with free models. Thank you. "
       "We are happy to take questions."),
    *qa([
        ("Your F1 of 1.0 looks too good.", "Agreed, the dataset is small and synthetic. We say so in the report. It is a sanity check, not a general accuracy claim."),
        ("Why is ROUGE not enough?", "ROUGE measures word overlap, not truth. So we also check evidence support for generated sentences."),
        ("Is it secure to run with 0.0.0.0?", "Only on a trusted network for testing. Dev identities are for testing and must not be used on a public server. Real deployment needs Google sign-in and HTTPS."),
        ("Is it legal to record a meeting?", "MeetBrief asks for consent and shows a capture status, but participants should still be told. Audio is deleted after transcription."),
    ]),
]

REF = [
    H1("", "Common Slide Tips and Sources"),
    H2("", "Slide tips"),
    Bullets([
        "Keep to 4–5 short points per slide. The *What to say* text is for speaking, not for the slide.",
        "Figures are in `report/source/fig/`. Screenshots of the panel make good backup slides.",
        "Hand over by name: \"Now {{next member}} will explain...\"",
        "Rehearse together with a timer, including the demo.",
    ]),
    H2("", "Where these facts come from"),
    T("Sources in the project", ["Topic", "File"], [
        ["Measured results", "`research/evaluation_results.md`"],
        ["Explanation benchmark", "`research/explanation_benchmark.md`"],
        ["Architecture", "`docs/ARCHITECTURE.md`"],
        ["Rooms", "`docs/ROOMS.md`"],
        ["Security scan", "`docs/SECURITY_SCAN.md`"],
        ["Literature and full references", "`report/MeetBrief_AI_Project_Report.pdf`, Chapter 2 and References"],
    ], [6.0, 8.5]),
]

d = Docx(margins_cm=(2.2, 2.2, 2.2, 2.2), line=1.15, base_pt=11, font="Calibri", heading_sizes=(18, 14, 12),
         caps_h2=False, caps_h3=False)
for b in FRONT + P1 + P2 + P3 + P4 + REF:
    d.add(b)
d.save(str(OUT), title="MeetBrief AI Presentation Guide")
print("saved", OUT)
