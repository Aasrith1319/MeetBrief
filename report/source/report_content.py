"""Content of the MeetBrief AI project report (RV University format). {{…}} = red placeholder for the student."""
from pathlib import Path

from model import H1, H2, H3, P, Bullets, Table, Figure, Code

FIG = Path(__file__).parent / "fig"

TITLE = "MEETBRIEF AI: A PRIVACY-PRESERVING MULTILINGUAL MEETING ASSISTANT WITH SHARED ROOMS FOR LATE JOINERS"
TITLE_SHORT = "MeetBrief AI: A Privacy-Preserving Multilingual Meeting Assistant with Shared Rooms for Late Joiners"
MONTH_YEAR = "{{Month, Year}}"
DEGREE = "{{Name of the degree}}"
NAME = "{{NAME OF THE CANDIDATE}}"
USN = "{{(USN)}}"
GUIDE = "{{GUIDE NAME}}"

ABSTRACT = [
    "Online meetings on Google Meet, Zoom and Microsoft Teams are now the default way that classes and project teams "
    "work, yet a participant who joins late, loses the connection, or does not follow a technical term has no reliable way "
    "to recover what was said. Existing assistants are cloud services that send meeting content to external servers, are "
    "mostly English-first, and serve only the person who started them.",
    "This project presents **MeetBrief AI**, a Chrome extension with a local Python backend that turns a live meeting into "
    "a structured, searchable and explainable record. Captions are read from the meeting page together with the tab audio "
    "(hybrid capture), and audio is transcribed with Whisper and separated by speaker with WavLM embeddings. A hybrid pipeline of transparent rules and "
    "open Hugging Face models running entirely on the user's machine extracts decisions, revisions, tasks, owners and "
    "deadlines; produces TextRank and BART-SAMSum summaries whose every sentence is aligned to transcript evidence; answers "
    "questions with hybrid retrieval and RoBERTa-SQuAD2 while abstaining when the answer is absent; explains statements "
    "with Qwen2.5-1.5B; and lets every viewer read the transcript in their own language, using Whisper speech translation and NLLB-200. *Shared rooms* keyed by the meeting link give "
    "every participant with the extension a personalised \"what you missed\" catch-up, with one elected capturer and "
    "automatic handover.",
    "On annotated evaluation meetings the system reaches an action-item F1 of 1.0 and a held-out decision F1 of 0.80, "
    "answers 16 of 16 answerable questions while abstaining on 7 of 7 unanswerable ones, and raises overview ROUGE-1 from "
    "0.36 to 0.55 with all generated sentences evidence-supported. Cue-phrase rules (accuracy 0.94) outperformed zero-shot "
    "NLI (0.59) for dialogue acts, and Qwen2.5-1.5B gave 8 of 9 correct explanations versus 0 of 9 for Flan-T5-large. "
    "Seventy-three automated tests, browser harnesses, a security scan and a live two-laptop Google Meet trial validated the "
    "system. The results show that a fully local, evidence-grounded meeting assistant is practical on a student laptop.",
    "**Keywords:** meeting summarization, question answering, dialogue acts, speaker diarization, multilingual NLP, "
    "privacy-preserving AI.",
]

ACK = [
    "It is my pleasure to express with deep sense of gratitude to {{[Internal Guide name]}}, {{[Designation, School of "
    "Computer Science and Engineering, RV University]}}, for his/her constant guidance, continual encouragement, "
    "understanding; more than all, he/she taught me patience in my endeavor. My association with him/her is not confined to "
    "academics only, but it is a great opportunity on my part of work with an intellectual and expert in the field of "
    "Natural Language Processing.",
    "I would like to express my gratitude to Prof Dr Ram Kumar Kakani, Vice Chancellor RV University, and Prof Dr Shobha G, "
    "Dean SoCSE, RV University, for providing with an environment to work in and for his inspiration during the tenure of "
    "the course.",
    "In jubilant mood I express ingeniously my whole-hearted thanks to Dr. Rashmi S, Program Director, {{[B.Tech(H)]}} SoCSE, "
    "RV University, all teaching staff and members working as limbs of our university for their not-self-centered "
    "enthusiasm coupled with timely encouragements showered on me with zeal, which prompted the acquirement of the "
    "requisite knowledge to finalize my course study successfully. I would like to thank my parents for their support.",
    "I would like to extend my sincere thanks to my mentor, {{[Mentor Name]}}, {{[Designation, School of Computer Science and "
    "Engineering, RV University]}}, for their unwavering support, thoughtful guidance, and motivational presence throughout "
    "the course of this project. Their mentorship not only enriched my learning but also inspired me to approach challenges "
    "with confidence and clarity. Working with them has been a meaningful experience, and I am truly grateful for the "
    "valuable time and insights shared with me during this journey.",
    "It is indeed a pleasure to thank my friends who persuaded and encouraged me to take up and complete this task, and who "
    "joined the live test meetings of MeetBrief. At last but not least, I express my gratitude and appreciation to all "
    "those who have helped me directly or indirectly toward the successful completion of this project.",
]

ACRONYMS = [
    ("AMI", "Augmented Multi-party Interaction corpus"), ("API", "Application Programming Interface"),
    ("ASR", "Automatic Speech Recognition"), ("BART", "Bidirectional Auto-Regressive Transformer"),
    ("BERT", "Bidirectional Encoder Repr. from Transformers"), ("BOLA", "Broken Object-Level Authorization"),
    ("chrF", "Character n-gram F-score"), ("CORS", "Cross-Origin Resource Sharing"), ("CSP", "Content Security Policy"),
    ("DAST", "Dynamic App. Security Testing"), ("DER", "Diarization Error Rate"), ("DOM", "Document Object Model"),
    ("F1", "Harmonic mean of precision, recall"), ("HF", "Hugging Face"), ("JSON", "JavaScript Object Notation"),
    ("LLM", "Large Language Model"), ("MMR", "Maximal Marginal Relevance"), ("MPS", "Metal Performance Shaders (GPU)"),
    ("MV3", "Chrome Manifest Version 3"), ("NER", "Named Entity Recognition"), ("NLI", "Natural Language Inference"),
    ("NLLB", "No Language Left Behind (MT)"), ("NLP", "Natural Language Processing"),
    ("OAuth", "Open Authorization"), ("QA", "Question Answering"), ("RAG", "Retrieval-Augmented Generation"),
    ("REST", "Representational State Transfer"), ("ROUGE", "Recall-Oriented Understudy for Gisting Eval."),
    ("SAMSum", "Samsung dialogue summary corpus"), ("SQuAD", "Stanford Question Answering Dataset"),
    ("TF-IDF", "Term Freq.–Inverse Document Freq."), ("TTS", "Text-to-Speech"), ("UI", "User Interface"),
    ("URL", "Uniform Resource Locator"), ("VAD", "Voice Activity Detection"), ("VTT", "Web Video Text Tracks"),
    ("WER", "Word Error Rate"), ("WavLM", "Wave Language Model (speech)"),
]

# =========================================================================================== CHAPTERS
CH1 = [
    H1("1", "Introduction"),
    H2("1.1", "Introduction"),
    P("Meetings are where most decisions in teams are made and most tasks are assigned. Since 2020, a large share of these "
      "meetings moved to video platforms such as Google Meet, Zoom and Microsoft Teams. The amount of spoken information "
      "exchanged in a one-hour call is large, it is rarely written down completely, and the people who most need a recap — "
      "participants who joined late, dropped out because of a weak connection, or attended a meeting in a language they "
      "are less comfortable with — are exactly the ones who cannot ask the others to repeat everything."),
    P("Natural Language Processing (NLP) offers the building blocks to solve this: speech recognition, summarization, "
      "information extraction, question answering, machine translation and text simplification. Large commercial "
      "assistants combine these as cloud services. However, for students and many organisations three limitations remain: "
      "(i) meeting content is sent to third-party servers, which raises privacy and consent concerns; (ii) the tools are "
      "mostly English-first and do not handle Indian code-switched speech such as Hinglish or Telugu–English well; and "
      "(iii) the assistant usually serves only the person who started it, so a participant who joins late gets nothing for "
      "the minutes they missed."),
    P("This project, **MeetBrief AI**, is a Chrome extension with a local backend that addresses these limitations. It "
      "captures what is said in a meeting, builds a structured *meeting memory* (decisions, action items, owners, "
      "deadlines, open questions and topics), and lets the user catch up, ask questions, request an easier explanation of "
      "any statement, translate the recap into Hindi or Telugu, and export the result. All neural models run locally from "
      "the Hugging Face Hub, and every generated sentence is linked to the transcript lines that support it."),
    H3("1.1.1", "Motivation"),
    P("The idea came from a common experience in college project meetings: someone joins ten minutes late and asks "
      "\"what did I miss?\", interrupting the meeting, or silently stays confused. A recap that is generated automatically, "
      "personalised to the moment each person joined, and grounded in the actual words spoken would remove this friction. "
      "Because the project is part of an NLP course, a second motivation was to study how far *small, open* models can go "
      "when they are combined carefully with classical, explainable techniques instead of relying on a paid API."),
    H3("1.1.2", "The late-joiner problem"),
    P("No software can recover speech that was never captured. A late joiner can only receive a recap if (a) some other "
      "participant's device was capturing the meeting from the start, or (b) the meeting platform itself recorded a "
      "transcript. MeetBrief solves case (a) with *shared rooms*: the first participant with the extension registers the "
      "meeting link, captures it, and every later participant with the extension automatically joins the same room and "
      "receives everything said before they arrived. Case (b) is handled by importing the official transcript of Google "
      "Meet, Zoom or Microsoft Teams, or a recording file. Meetings held in desktop applications are covered by a desktop "
      "recorder that sends system audio to the same pipeline."),
    H2("1.2", "Problem Statement"),
    P("To design and implement a privacy-preserving, multilingual meeting assistant that (1) captures online meetings from "
      "captions or audio without sending data to external AI services, (2) extracts decisions, action items, owners, "
      "deadlines and unresolved questions with traceable evidence, (3) produces faithful summaries and answers questions "
      "about the meeting while refusing to guess when the information is absent, (4) explains and translates meeting "
      "content for participants with different backgrounds and languages, and (5) gives participants who join late a "
      "personalised catch-up of what they missed, using only open models that run on a student laptop."),
    H2("1.3", "Objectives"),
    Bullets([
        "**O1 – Capture:** read live captions from Google Meet (and experimentally Zoom and Teams web), transcribe tab or "
        "desktop audio with speaker separation, and import transcripts or recordings.",
        "**O2 – Understanding:** build a structured meeting memory: dialogue acts, decisions with revision history, tasks "
        "with owners and deadlines, open questions, topics, entities and potential contradictions.",
        "**O3 – Faithful summaries:** generate catch-up, quick, detailed, chronological, topic-wise and personalised "
        "summaries in which every sentence is aligned to supporting transcript segments.",
        "**O4 – Grounded Q&A:** answer natural-language questions about the meeting with quoted evidence and abstain when "
        "the transcript does not contain the answer.",
        "**O5 – Explain and translate:** explain any statement at four difficulty levels in five styles, and translate "
        "outputs into each viewer's language, with English, Telugu, Kannada, Hindi and Tamil as the meeting languages.",
        "**O6 – Late joiners:** implement shared rooms with per-member \"what you missed\" catch-up, a single elected "
        "capturer and automatic handover, plus Early Join and official-transcript import.",
        "**O7 – Privacy and security:** run all models locally, support private (in-memory) mode, retention and deletion, "
        "and validate the API with automated security testing.",
        "**O8 – Evaluation:** measure every component (ROUGE, precision/recall/F1, QA accuracy and abstention, WER, "
        "speaker accuracy, chrF, latency) and compare rule-based and model-based variants.",
    ], numbered=False),
    H2("1.4", "Scope of the Project"),
    P("**In scope.** A Chrome Manifest V3 extension (side panel, service worker, content scripts, offscreen audio "
      "recorder), a FastAPI backend with SQLite storage, local Hugging Face models for summarization, translation, "
      "explanation, question answering, embeddings, NER, zero-shot NLI and speaker embeddings, Whisper ASR, shared rooms "
      "for multi-participant use on a common server, connectors for official transcripts, a desktop recorder, an "
      "evaluation framework and a test suite. English, Telugu, Kannada, Hindi, Tamil and code-switched input are supported, with "
      "Kannada the weakest (Section 3.1.8)."),
    P("**Out of scope.** Recovering speech that nobody captured; a server-side meeting bot that joins calls without any "
      "participant's browser; native desktop or mobile apps; and large-scale evaluation on real recorded corpora such as "
      "AMI or ICSI (the framework supports QMSum, but the reported numbers come from small annotated synthetic meetings)."),
    H2("1.5", "Organisation of the Report"),
    P("Chapter 2 reviews prior work on meeting understanding year by year and lists the tools used. Chapter 3 describes the "
      "proposed methodology and architecture. Chapter 4 covers datasets, implementation and the experimental setup. "
      "Chapter 5 reports quantitative results and compares the approach with existing methods. Chapter 6 discusses key "
      "findings and how the objectives were met, Chapter 7 is the impression report, and Chapter 8 concludes with future "
      "work. References and appendices follow."),
]

CH2 = [
    H1("2", "Background"),
    H2("2.1", "Literature Survey"),
    P("Research on automatic meeting understanding spans speech processing, dialogue analysis, summarization and question "
      "answering. The survey below is organised chronologically to show how methods moved from hand-crafted features to "
      "pre-trained Transformers, and which gaps remain for a local, multilingual assistant."),
    H3("2.1.1", "Early work (2000–2007): dialogue acts, corpora and extractive summaries"),
    P("Stolcke et al. (2000) modelled dialogue acts — statements, questions, agreements — with hidden Markov models over "
      "word and prosodic features on Switchboard, showing that the function of an utterance can be recognised "
      "automatically. The ICSI Meeting Corpus (Janin et al., 2003) and the AMI Meeting Corpus (Carletta et al., 2005) "
      "provided the first large multi-party meeting recordings with transcripts and annotations, and they remain the main "
      "benchmarks. Mihalcea and Tarau (2004) introduced TextRank, a graph-based ranking of sentences derived from PageRank "
      "(Page et al., 1999), which became a strong unsupervised extractive baseline. Hearst (1997) had earlier proposed "
      "TextTiling for segmenting text into topical units using lexical cohesion. Murray, Renals and Carletta (2005) "
      "compared extractive summarization techniques on meeting recordings and found that meeting speech, with "
      "disfluencies and overlapping turns, is much harder than news text."),
    H3("2.1.2", "Decisions and action items (2007–2010)"),
    P("Purver et al. (2007) detected and summarised action items in multi-party dialogue by first classifying the "
      "utterances that describe a task, an owner, a timeframe or an agreement, and Hsueh and Moore (2007) detected "
      "decision-related dialogue acts in AMI meetings. The CALO Meeting Assistant (Tur et al., 2010) integrated speech "
      "recognition, topic segmentation, action-item and decision detection into one system. These works established that "
      "meeting outcomes are better represented as structured records than as plain summaries — an idea MeetBrief adopts "
      "for its meeting memory — but they relied on corpus-specific supervised classifiers and server-side processing."),
    H3("2.1.3", "Transformers and pre-training (2017–2019)"),
    P("The Transformer (Vaswani et al., 2017) and pre-trained encoders such as BERT (Devlin et al., 2019) and RoBERTa "
      "(Liu et al., 2019) changed nearly every NLP task. For question answering, SQuAD 2.0 (Rajpurkar, Jia and Liang, "
      "2018) added unanswerable questions, so that models learn to output *no answer* — the property MeetBrief uses for "
      "abstention. Sentence-BERT (Reimers and Gurevych, 2019) made dense sentence embeddings efficient for semantic search, "
      "and its multilingual distillation (Reimers and Gurevych, 2020) extended this to 50+ languages. Yin, Hay and Roth "
      "(2019) showed that NLI models can perform zero-shot text classification by treating labels as hypotheses. In speech, "
      "x-vector embeddings (Snyder et al., 2018) became the standard representation for speaker recognition and "
      "diarization. The SAMSum corpus (Gliwa et al., 2019) provided human-written summaries of chat dialogues."),
    H3("2.1.4", "Abstractive and retrieval-augmented methods (2020–2021)"),
    P("BART (Lewis et al., 2020a), a denoising sequence-to-sequence model, achieved strong abstractive summarization "
      "results; fine-tuned on SAMSum it summarises dialogues rather than news. HMNet (Zhu et al., 2020) designed a "
      "hierarchical network with cross-domain pre-training specifically for meeting summarization. QMSum (Zhong et al., "
      "2021) introduced query-based meeting summarization over AMI, ICSI and parliamentary meetings. At the same time, "
      "Maynez et al. (2020) showed that abstractive summarizers frequently hallucinate content not supported by the source, "
      "and Retrieval-Augmented Generation (Lewis et al., 2020b) proposed grounding generation in retrieved passages. "
      "Together these results motivate MeetBrief's design: use abstractive models for fluency, but retrieve and align "
      "evidence for every generated claim."),
    H3("2.1.5", "Large multilingual and speech foundation models (2022–2024)"),
    P("WavLM (Chen et al., 2022) learned speech representations that work well for speaker verification and diarization, "
      "and Park et al. (2022) surveyed deep-learning diarization. NLLB-200 (NLLB Team, 2022) covered 200 languages "
      "including Hindi and Telugu with a single translation model. Whisper (Radford et al., 2023) trained on 680,000 hours of "
      "weakly supervised audio and became a robust multilingual ASR model. Small instruction-tuned language models such as "
      "Qwen2.5 (Qwen Team, 2024) can now run on a laptop and follow concise prompts for explanation and simplification. "
      "These advances make a fully local assistant feasible, but no surveyed system combines them with structured meeting "
      "memory, evidence alignment, abstention, Indian-language support and multi-participant catch-up."),
    Table("2.1", "Summary of the literature survey", ["Year", "Work", "Method", "Relevance / gap for this project"], [
        ["2000", "Stolcke et al.", "HMM dialogue-act tagging", "Utterance function is learnable; needs labelled data"],
        ["2003–05", "ICSI / AMI corpora", "Annotated meeting recordings", "Standard benchmarks; English only"],
        ["2004", "Mihalcea & Tarau", "TextRank (graph ranking)", "Unsupervised extractive baseline (used)"],
        ["2005", "Murray et al.", "Extractive meeting summaries", "Speech disfluencies make meetings hard"],
        ["2007", "Purver et al.; Hsueh & Moore", "Action-item / decision detection", "Structured outcomes; corpus-specific"],
        ["2010", "Tur et al. (CALO)", "Integrated meeting assistant", "Server-side, no late-joiner support"],
        ["2018", "Rajpurkar et al.", "SQuAD 2.0 unanswerable questions", "Enables abstention (used)"],
        ["2019", "Devlin et al.; Reimers & Gurevych", "BERT; Sentence-BERT", "Encoders and semantic search (used)"],
        ["2019", "Yin et al.", "Zero-shot NLI classification", "Tested; weaker than rules here"],
        ["2020", "Lewis et al.; Maynez et al.", "BART; hallucination study", "Abstractive + need for grounding"],
        ["2021", "Zhong et al.", "QMSum query-based summaries", "Supported by the evaluation tool"],
        ["2022", "Chen et al.; NLLB Team", "WavLM; NLLB-200", "Diarization and Hindi/Telugu MT (used)"],
        ["2023", "Radford et al.", "Whisper ASR", "Local multilingual ASR (used)"],
        ["2024", "Qwen Team", "Qwen2.5 small LLMs", "Local explanations (used)"],
    ], widths=[1.1, 2.4, 2.6, 3.4]),
    H3("2.1.6", "Research gap"),
    P("Prior research systems treat the meeting as a single recording processed after the fact, usually on a server, "
      "and evaluate summarization quality in English. Commercial assistants add live capture but are cloud-based and "
      "single-user. The gap addressed by this project is an assistant that is (1) live and multi-participant, giving each "
      "late joiner their own catch-up; (2) local and privacy-preserving; (3) evidence-grounded with explicit abstention; "
      "and (4) usable in Indian multilingual settings, while remaining explainable enough for an academic evaluation of "
      "each NLP component."),
    H2("2.2", "Tools and Techniques"),
    P("Table 2.2 lists the main tools used. All of them are open source and free; no paid API is used anywhere in the "
      "system."),
    Table("2.2", "Tools, libraries and models used", ["Category", "Tool / model", "Purpose in MeetBrief"], [
        ["Language / runtime", "Python 3.13, JavaScript (ES2022)", "Backend and Chrome extension"],
        ["Web framework", "FastAPI, Uvicorn, Pydantic", "REST API, validation, auth middleware"],
        ["Storage", "SQLite (disk + in-memory)", "Meetings, segments, rooms, notes; private mode"],
        ["Browser platform", "Chrome Manifest V3", "Side panel, service worker, content scripts, offscreen audio, identity, alarms"],
        ["Model hub", "Hugging Face Transformers, Sentence-Transformers", "Local model loading and inference (CPU / Apple MPS)"],
        ["Summarization", "philschmid/bart-large-cnn-samsum", "Abstractive dialogue summaries"],
        ["Question answering", "deepset/roberta-base-squad2", "Extractive QA with no-answer score"],
        ["Embeddings", "paraphrase-multilingual-MiniLM-L12-v2", "Dense retrieval, topic labels, evidence alignment"],
        ["Explanation", "Qwen/Qwen2.5-1.5B-Instruct", "Explain Again (simplify, example, analogy, …)"],
        ["Translation", "facebook/nllb-200-distilled-600M", "English ↔ Hindi / Telugu and 200 languages"],
        ["NER", "dslim/bert-base-NER", "Entities; verifying task owners"],
        ["Zero-shot NLI", "MoritzLaurer/mDeBERTa-v3-base-mnli-xnli", "Optional dialogue-act second opinion"],
        ["Speech", "faster-whisper (Whisper small), microsoft/wavlm-base-plus-sv", "ASR and speaker embeddings"],
        ["Classical NLP", "TF-IDF, TextRank, TextTiling, MMR, langdetect", "Fallbacks and explainable components"],
        ["Export", "ReportLab (PDF), Markdown", "Meeting minutes export"],
        ["Testing / security", "pytest, browser harnesses, StackHawk HawkScan", "Unit, integration and DAST testing"],
    ], widths=[2.2, 3.6, 4.2]),
    P("**Techniques.** The system combines classical techniques — regular-expression and cue-phrase rules, TF-IDF, graph "
      "ranking, lexical cohesion and online clustering — with neural ones: encoder–decoder Transformers for summarization "
      "and translation, an encoder for extractive QA, a decoder-only LLM for explanations, bi-encoders for embeddings and "
      "self-supervised speech models. The guiding principle is *hybrid*: precise structured facts come from transparent "
      "rules with evidence, fluent text comes from models, and every model output is verified against the transcript."),
]

CH3 = [
    H1("3", "Methodology"),
    H2("3.1", "Proposed Methodology"),
    P("MeetBrief is organised in four layers (Figure 3.1): a **capture layer** in the meeting tab, a **coordination layer** "
      "in the extension's service worker, a **local backend** that runs the NLP pipeline and stores the meeting memory, and "
      "a **presentation layer** in Chrome's side panel. The design follows four principles."),
    Bullets([
        "**Local first.** Every model runs on the user's machine; raw audio is deleted as soon as it is transcribed.",
        "**Evidence over fluency.** Every summary sentence, answer and extracted item carries the ids of the transcript "
        "segments that support it, and unsupported generated sentences are flagged.",
        "**Graceful degradation.** Each neural component has a classical fallback, so the system still works if a model is "
        "missing or the laptop is slow.",
        "**Abstain rather than guess.** When the transcript does not contain an answer, the system says so.",
    ]),
    Figure("3.1", "System architecture of MeetBrief AI", str(FIG / "architecture.png"), 15.5),
    H3("3.1.1", "Capture layer"),
    P("A platform adapter for each meeting app reads the accessible caption region of the page. Captions are updated "
      "progressively (\"We need\" → \"We need to\" → \"We need to improve…\"), so the capture module emits a block only "
      "after its text has been stable for 1.8 s, sends only the new words beyond what was already emitted, and filters out "
      "text that belongs to the platform's own buttons and icons. The adapter also detects when the user joins and leaves "
      "the call (using the call controls and participant tiles, with a 6-second debounce because Meet hides its toolbar "
      "when the mouse is idle), and shows a small on-page status label. When captions are unavailable, the user can capture "
      "the tab's audio: an offscreen document records 15-second WebM/Opus chunks that the backend transcribes. For meetings "
      "in desktop apps, a command-line recorder streams a loopback or microphone device to the same endpoint. Official "
      "transcripts can be imported from Google Meet, Zoom cloud recordings and Microsoft Teams."),
    H3("3.1.2", "Text normalisation and language identification"),
    P("All sources are converted into a common *segment* schema (text, start and end time, speaker, language, source and "
      "flags). The normaliser parses VTT, SRT, JSON, DOCX and plain-text transcripts, attaches timestamps, removes fillers "
      "and merges fragments. Language is identified per segment by combining Unicode script ranges (Telugu, Devanagari, …), "
      "a lexicon of romanised Hindi and Telugu words for code-switched text, and a character n-gram naive-Bayes detector."),
    Figure("3.2", "Processing pipeline from captured input to user-facing features", str(FIG / "pipeline.png"), 15.5),
    H3("3.1.3", "Dialogue acts and information extraction"),
    P("Each sentence is classified into *decision*, *proposal*, *task*, *question* or *other* using cue-phrase rules (for "
      "example \"let's go with\", \"we decided\", \"please … by Friday\", \"I will …\"). An optional second opinion from a "
      "zero-shot NLI model (hypotheses such as \"The speaker makes a decision\") can raise the confidence of a rule-based "
      "item but never adds items on its own, because evaluation showed that it confuses deciding with suggesting. Tasks are "
      "extracted with their owner (an addressee such as \"Karthik, please…\", or a self-commitment \"I will…\") and "
      "deadline; owners are verified with BERT-based NER. A simple coreference step merges vague confirmations such as "
      "\"Sure, I can do that by Friday\" into the request they answer. A later confirmed decision that contains a revision "
      "cue (\"actually\", \"instead\", \"postpone\") on the same subject marks the earlier decision as *superseded*, so the "
      "memory keeps the history instead of overwriting it. Questions are paired with later replies, and unanswered ones are "
      "reported."),
    H3("3.1.4", "Topic segmentation and meeting memory"),
    P("Topics are found with TextTiling: a depth score is computed over the cosine similarity of TF-IDF windows, combined "
      "with transition cues (\"moving on to…\"); each topic receives a KeyBERT-style label chosen by embedding similarity "
      "and Maximal Marginal Relevance. The meeting memory stores topics, decisions with revisions, tasks, questions, "
      "entities and potential contradictions (high-similarity sentence pairs that differ in polarity or numbers). It is "
      "recomputed from the stored transcript and cached by a fingerprint, while user corrections (task status, owner, "
      "deadline, speaker names) are stored separately and always override extracted values."),
    H3("3.1.5", "Summarization with evidence alignment"),
    P("Two summarizers are combined. TextRank ranks sentences by PageRank over a TF-IDF cosine-similarity graph with "
      "boosts for problem and reason statements; it provides *key moments* that are quoted verbatim. BART fine-tuned on "
      "SAMSum generates an abstractive *overview*; long meetings are processed hierarchically in chunks under the "
      "1,024-token limit. Each generated sentence is then aligned to its most similar transcript segment with dense "
      "embeddings; sentences with low similarity, or with entities that never occur in the transcript, are flagged with a warning marker. "
      "The summary also lists options discussed, confirmed and superseded decisions, action items and the current topic. "
      "Summary modes include catch-up, quick, detailed, chronological, by-topic, personalised (for one speaker), "
      "\"last N minutes\" and a final summary built automatically when the meeting ends."),
    H3("3.1.6", "Retrieval-augmented question answering with abstention"),
    P("A question is first rewritten using the chat history for follow-ups (\"and who will do it?\"). Retrieval combines "
      "word-level TF-IDF, character 3–5-gram TF-IDF (robust to spelling and romanisation) and dense multilingual "
      "embeddings, with optional speaker and time filters. A relevance gate requires the retrieved passages to cover at "
      "least half of the question's content words; \"why\" questions additionally need an explicit reason cue. Questions "
      "about owners, deadlines or decisions are answered from the structured memory; others go to RoBERTa fine-tuned on "
      "SQuAD 2.0, whose span is accepted only if it beats the *no-answer* score. If an answer comes from a decision that "
      "was later revised, the reader is re-run on the revision so that the current state leads (for example \"Tuesday — "
      "earlier plan: Friday\"). Otherwise the system replies that the information is not in the captured transcript."),
    H3("3.1.7", "Explain Again and translation"),
    P("*Explain Again* shows what the meeting itself said about a selected term (retrieved segments) and then an "
      "explanation in one of five styles (simplify, example, step-by-step, detailed, analogy) at four levels. A curated "
      "glossary is used first; otherwise Qwen2.5-1.5B-Instruct generates a short explanation that is clearly labelled as "
      "general knowledge to verify. Outputs can be translated with NLLB-200 while preserving Markdown, segment citations "
      "and numbers (a post-check confirms that every number in the source appears in the translation)."),
    H3("3.1.8", "Speech recognition and speaker diarization"),
    P("Audio chunks are transcribed by Whisper (faster-whisper, small model) with voice-activity filtering and word "
      "timestamps. Audio is split on pauses and the language of each utterance is detected, limited to the configured "
      "meeting languages (by default English, Telugu, Kannada, Hindi and Tamil), so a speaker may switch language inside a "
      "chunk. For non-English speech Whisper also translates the speech directly into English; the rule and model "
      "components read this English, while the original words are kept for display. This was chosen after testing: Whisper "
      "small writes Telugu and Kannada text unreliably but translates the speech far better, so those two languages are "
      "shown in English only, tagged with the language they were translated from. Each viewer picks a reading language, and "
      "other targets are produced with NLLB-200. Short phrases Whisper invents on silence are filtered. On a text-to-speech "
      "test track, English, Telugu, Hindi and Tamil were usable and Kannada was the weakest; this is an informal check, not "
      "a measured accuracy."),
    P("Captions and tab audio are captured together. Captions give real names and include the capturing user's own voice, "
      "which tab audio never contains. An audio sentence with at least 60% content-word overlap with one recent caption "
      "line is dropped as a duplicate; the rest is kept, so nothing is lost when captions stop. Two agreeing matches also "
      "map a voice label to the caption's name. Chrome grants tab capture only after the user invokes the extension on the "
      "tab, through its toolbar icon, shortcut or context menu."),
    P("For each recognised segment a WavLM-Base-Plus x-vector is computed, and an *online* agglomerative "
      "clustering assigns it to the most similar existing speaker centroid if the cosine similarity exceeds a threshold "
      "(0.86), otherwise a new speaker is created; centroids persist across chunks so labels stay consistent through the "
      "meeting. Generic labels (Speaker 1, Speaker 2…) are never replaced by guessed real names; the user maps them."),
    H3("3.1.9", "Shared rooms for late joiners"),
    P("The key used to identify a meeting is derived from its link (for example *google_meet:abc-defg-hij*, handling both "
      "*meet.google.com/abc-defg-hij* and *meet.google.com/meet/abc-defg-hij*). When a signed-in user joins a call, the "
      "extension asks the server whether a room exists for that key. If not, it offers to *share* the meeting; the sharer "
      "becomes the room's capturer. Every other member who joins the same call is admitted automatically (optionally only "
      "for the sharer's email domain or after approval), stands by, and receives a catch-up computed up to *their own* "
      "join time (Figure 3.3). Members send a heartbeat every 10 s; the server keeps one capturer, prefers a member whose "
      "captions are visible if the capturer reports captions off, and hands over capturing when the capturer leaves or "
      "misses heartbeats for 25 s. Rooms idle for 15 minutes are closed so that a reused meeting link starts a new room, "
      "and when the last member leaves, the room ends with a final summary."),
    Figure("3.3", "Shared-room protocol: late joiner catch-up and capturer handover", str(FIG / "rooms.png"), 15.5),
    H3("3.1.10", "Privacy and security design"),
    P("The backend binds to localhost by default and requires an API token compared in constant time. Room members are "
      "identified by a Google token verified by the server (audience = the project's OAuth client) or, in test mode, by a "
      "typed identity. Access control is principal-based and fail-closed: members may call only an allow-list of read and "
      "ask routes, may read only meetings of rooms they belong to (other ids return 404 to prevent probing), may not delete "
      "or modify meetings, and only the current capturer may push transcript segments. Other members' email addresses are "
      "visible only to the sharer. Private mode keeps a meeting in an in-memory database that is never written to disk, "
      "retention is configurable, and the web app uses a nonce-based Content Security Policy."),
]

CH4 = [
    H1("4", "Implementation"),
    H2("4.1", "Datasets"),
    P("Because public meeting corpora are English-only and large, the project created small, fully annotated synthetic "
      "meetings that exercise every feature, including Indian code-switching. Two annotation files separate a "
      "*development* set (used while writing the rules, so its scores are optimistic) from a *held-out* set annotated "
      "before the first evaluation run. Table 4.1 summarises the data."),
    Table("4.1", "Datasets used for development and evaluation", ["Dataset", "Content", "Annotations / use"], [
        ["sprint_planning.txt", "Product sprint planning (5 speakers, ~6 min)", "Decisions incl. one revision, tasks, owners, deadlines, Q&A"],
        ["demo_indexing.txt", "Database performance discussion", "Decisions, proposals, tasks, Q&A"],
        ["mixed_hinglish.txt", "Hindi–English code-switched meeting", "Language ID, translation, extraction"],
        ["telugu_english.txt", "Telugu–English code-switched meeting", "Language ID, translation, extraction"],
        ["unlabeled_speakers.vtt, sample.srt, sample.json", "Same content in caption formats", "Parser and normaliser tests"],
        ["heldout_design_review.txt", "Notification-system design review", "Held-out decisions, tasks, questions, Q&A"],
        ["dialogue_acts.json", "32 hand-labelled sentences", "Rules vs zero-shot NLI comparison"],
        ["three_speakers.wav", "29.3 s synthetic meeting, 3 TTS voices", "WER and speaker-accuracy evaluation"],
        ["QMSum (optional, not bundled)", "Query-based summaries of AMI/ICSI meetings", "Supported via --qmsum for larger studies"],
    ], widths=[3.0, 3.4, 3.6]),
    H2("4.2", "Implementation"),
    P("The implementation consists of about 7,600 lines of Python in the backend and tools and about 2,700 lines of "
      "JavaScript, HTML and CSS in the extension. The backend exposes 50 REST endpoints."),
    H3("4.2.1", "Chrome extension"),
    Bullets([
        "**Content scripts** (`meeting_detector.js`, `caption_capture.js`, platform adapters for Google Meet, Zoom web and "
        "Teams web): call detection, caption stabilisation, on-page status label (Figure 4.2), Early Join (opens a scheduled "
        "meeting one minute early and joins with microphone and camera off).",
        "**Service worker** (`background.js`): per-tab capture state machine serialised through a single queue, REC/ROOM "
        "badge, notifications with Share/Not-now buttons, room join/share/heartbeat, routing of transcript segments to the "
        "meeting or room, alarms for Early Join, and re-injection into meeting tabs that were open before an update.",
        "**Side panel** (Figure 4.1): tabs for Catch Me Up, Explain Again, Ask AI, Who Said What, Decisions, Action Items, "
        "Timeline, Transcript, Notes, Schedule, Upload and Settings, built with strict-CSP-safe JavaScript.",
        "**Offscreen document**: records only the meeting tab's audio after the user explicitly starts it (no microphone "
        "permission is requested).",
    ]),
    Figure("4.1", "MeetBrief side panel during a live Google Meet capture", str(FIG / "ui_sidepanel.png"), 9.0),
    Figure("4.2", "On-page status label shown inside the meeting page", str(FIG / "ui_status_label.png"), 12.0),
    H3("4.2.2", "Backend"),
    Bullets([
        "`api/` – routes, rooms and service layer; `auth.py` – principals (owner token, Google identity, test identity) and "
        "the fail-closed access middleware.",
        "`capture/` – transcript normaliser and caption de-duplication; `speech/` – Whisper ASR, WavLM diarization, alignment.",
        "`nlp/` – language identification, dialogue acts, decisions, actions, questions, topics, summarization, evidence "
        "alignment, simplification, glossary, translation, speakers, contradictions.",
        "`rag/` – hybrid embeddings, retrieval and answer generation; `memory/` – meeting state, rolling summary, decision "
        "history.",
        "`hf/` – local model registry with lazy loading, per-task fallback, device selection (CPU, CUDA or Apple MPS) and a "
        "semaphore that limits concurrent heavy jobs; `database/` – SQLite with a re-entrant lock serialising access; "
        "`connectors/` – Google Meet REST API, Zoom cloud recording and Microsoft Graph transcript import.",
        "`evaluation/` – metrics implemented from scratch (ROUGE, P/R/F1, WER, chrF, speaker accuracy) and the benchmark "
        "scripts; `export/` – Markdown, PDF (with bundled Noto fonts for Telugu and Hindi), TXT and JSON.",
    ]),
    H3("4.2.3", "Key algorithms"),
    P("**Caption stabilisation.** For each caption block the module remembers the text already emitted; when the block "
      "has not changed for 1.8 s, disappears, or grows beyond 600 characters, only the words after the longest common word "
      "prefix are sent. The backend merges growing duplicate updates into the last segment, so de-duplication happens "
      "twice."),
    P("**Hybrid retrieval score.** For a query q and segment s, the score is a weighted combination of word TF-IDF cosine, "
      "character n-gram TF-IDF cosine and dense embedding cosine, followed by the relevance gate on content-word coverage. "
      "Character n-grams make retrieval robust to romanised Hindi and Telugu spellings."),
    P("**Capturer election.** On each heartbeat the server records the member's last-seen time and caption visibility. "
      "If the current capturer is alive (in the call and seen within 25 s) it stays; otherwise the first member in the "
      "call whose heartbeat arrives becomes the capturer. A member with visible captions takes over a capturer that "
      "explicitly reports captions off. Transcript segments are accepted only from the current capturer and are placed on "
      "the room's shared clock, so the transcript has neither gaps nor duplicates."),
    H3("4.2.4", "Sample output"),
    P("Running the system on the sprint-planning meeting produced the following (real, unedited) results:"),
    Table("4.2", "Excerpt of MeetBrief output for the sprint-planning meeting", ["Feature", "Output"], [
        ["Overview (BART)", "\"The payment page needs to be lazy loaded only when the user selects a payment method and the "
                            "address validation should be moved to the backend. [S3] … The mobile app release for 2.4 will be "
                            "postponed to next Tuesday. [S13]\""],
        ["Decisions", "Confirmed: go with lazy loading the payment scripts first (Meera) [S5]; postpone the 2.4 release to "
                      "next Tuesday (Meera) [S13], superseding \"release version 2.4 on Friday\" [S10]"],
        ["Action items", "Implement the lazy loading — Karthik, Wednesday; Investigate the Android crash reports — David, "
                         "today; Write the rollback plan — Sana, next Monday; Update the release notes — owner unknown (flagged)"],
        ["Ask AI", "Q: When is the 2.4 release now? A: \"Tuesday\" — Meera (04:12) [S13] (earlier plan: Friday, revised)\n"
                   "Q: What is the marketing budget? A: \"I couldn't find anything about this in the captured transcript.\""],
        ["Explain Again", "\"Lazy loading is a technique … where resources or data are loaded only when they are needed, "
                          "rather than all at once …\" — labelled as general knowledge (Qwen2.5-1.5B)"],
        ["Translation (te)", "§TE§మొబైల్ అప్లికేషన్ 2.4 విడుదల వచ్చే మంగళవారం వరకు వాయిదా పడింది."],
    ], widths=[2.2, 7.8]),
    H3("4.2.5", "Testing and quality assurance"),
    P("The project has 73 automated pytest tests: unit and API tests (concurrency, error handling, uploads, recordings, "
      "privacy, retention), 14 room tests (late joiner, access rules, approval, broken object-level authorization, "
      "capturer handover, idle-room expiry), connector tests with mocked provider APIs, desktop-recorder tests, and model "
      "tests that run every Hugging Face model. Browser harnesses run the real extension code against a simulated Meet "
      "page (17 checks: join, auto-captions, caption emission, toolbar flicker, leave, Early Join) and against two simulated "
      "members on a test server (12 checks: share, late-join catch-up, duplicate refusal, handover, room end). A dynamic "
      "security scan (StackHawk HawkScan) was run on a throwaway instance; it found a race condition that produced HTTP "
      "500 errors (fixed by serialising database access), a permissive CSP (replaced with a nonce-based policy) and member "
      "email exposure in room views (restricted to the sharer); the final scan reported zero open findings."),
    H2("4.3", "Experimental Setup"),
    Table("4.3", "Experimental setup", ["Item", "Configuration"], [
        ["Hardware", "Apple MacBook Air, Apple M2, 8-core CPU, MPS GPU (generation); other models on CPU"],
        ["Software", "macOS, Python 3.13, PyTorch, Transformers, Sentence-Transformers, faster-whisper, FastAPI, Chrome"],
        ["Models", "BART-large-CNN-SAMSum, RoBERTa-base-SQuAD2, MiniLM-L12 multilingual, Qwen2.5-1.5B-Instruct, "
                   "NLLB-200-distilled-600M, BERT-base-NER, mDeBERTa-v3-base-XNLI, WavLM-base-plus-sv, Whisper small (ASR evaluation below used base)"],
        ["Decoding", "Greedy decoding for generation; NLLB beam size 4; summary chunks ≤ 1,024 tokens"],
        ["Thresholds", "Speaker cosine 0.86; QA minimum span score 0.15 and positive margin over no-answer; caption stability 1.8 s"],
        ["Configurations", "(a) rules only (MEETBRIEF_MODELS=off) and (b) with Hugging Face models; optional hybrid NLI"],
        ["Live trial", "Two laptops on the same Wi-Fi, Google Meet call, backend on one laptop (MEETBRIEF_HOST=0.0.0.0)"],
    ], widths=[2.2, 7.8]),
    P("Every text component was measured twice, rules only versus with the Hugging Face models, so that the evaluation "
      "doubles as a model-selection benchmark. Summaries were compared with author-written references using ROUGE-1/2/L "
      "F1. Extraction was evaluated with precision, recall and F1 against hand annotations, owners and deadlines with "
      "accuracy on matched tasks, and Q&A with answer accuracy on answerable questions and correct abstention on "
      "unanswerable ones. Speech used word error rate and speaker accuracy after optimal label mapping, and translation "
      "used round-trip chrF with a number-preservation check. Latency was measured end to end on the backend."),
]
