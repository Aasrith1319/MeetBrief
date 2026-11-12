# MeetBrief AI

A multilingual, context-aware meeting assistant: a **Chrome extension (Manifest V3)** with a side panel, plus a
**Python FastAPI backend** for NLP. All NLP runs **locally with open Hugging Face models** — no paid or external AI API. It helps late joiners catch up, re-explains concepts, answers questions with
transcript evidence, attributes statements to speakers, and extracts decisions and action items.

**Design rule:** MeetBrief helps you understand the meeting without pretending to know what it hasn't captured or
can't verify. Every important output links to transcript segments, uncertain owners/deadlines/speakers are flagged,
and Q&A abstains when the transcript doesn't contain the answer.

## Quick start

```bash
./run.sh
```

This creates `.venv`, installs `requirements.txt` + `requirements-ml.txt` (PyTorch, Transformers) +
`requirements-audio.txt` (Whisper) and starts the backend on `http://127.0.0.1:8000`. The console prints an **API token**.

Download all models once (≈ 8 GB, then works offline — set `HF_HUB_OFFLINE=1`):

```bash
.venv/bin/python -m backend.hf.download
```

* **Web app (no extension needed):** open http://127.0.0.1:8000/app/ and upload a transcript from
  `datasets/sample_transcripts/` (try `sprint_planning.txt`).
* **Chrome extension:** `chrome://extensions` → enable *Developer mode* → *Load unpacked* → choose `chrome-extension/`.
  Click the MeetBrief toolbar icon to open the side panel → *Settings* → paste the backend URL and token → *Save & test*.
* **API docs:** http://127.0.0.1:8000/docs

### Models (all local, from the Hugging Face Hub)

| Task | Model |
|---|---|
| Abstractive dialogue summarization | `philschmid/bart-large-cnn-samsum` |
| Translation (Hindi, Telugu, Tamil, … 200 languages) | `facebook/nllb-200-distilled-600M` |
| Explain Again (simplify / example / steps / analogy) | `Qwen/Qwen2.5-1.5B-Instruct` (chosen over Flan-T5 by a [benchmark](research/explanation_benchmark.md)) |
| Extractive question answering with "no answer" | `deepset/roberta-base-squad2` |
| Multilingual sentence embeddings (search, topics, evidence alignment) | `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2` |
| Zero-shot dialogue acts (decision / proposal / task / question) | `MoritzLaurer/mDeBERTa-v3-base-mnli-xnli` |
| Named entity recognition | `dslim/bert-base-NER` |
| Speaker embeddings for diarization | `microsoft/wavlm-base-plus-sv` |
| Speech recognition | Whisper `small` via `faster-whisper` (speech → English translation for non-English lines) |

Every model can be swapped with an environment variable (see `backend/hf/models.py`). Without the ML packages, or with
`MEETBRIEF_MODELS=off`, MeetBrief still works using its classical NLP pipeline (TextRank, TF-IDF retrieval, rules).
The side-panel badge and *Settings → NLP models* show what is loaded. See [docs/NLP_CONCEPTS.md](docs/NLP_CONCEPTS.md).

## Live capture (Google Meet)

1. Join a Google Meet call and **turn on captions** (CC).
2. Open the MeetBrief side panel on that tab → **Start captions**. Confirm the consent prompt.
3. The capture bar shows *Capturing captions* and the toolbar icon shows **REC**. Pause/Stop at any time.

**Automatic mode** (Settings → *Automatic meeting mode*, or say yes after the first consent prompt): when you join a
Meet call MeetBrief starts capturing on its own (switching Meet captions on if needed), keeps a live catch-up running,
and when you leave or close the tab it stops and builds a **final summary** (notification "Meeting ended — summary
ready"). Chrome does not let extensions open the side panel by themselves, so click the REC icon or the notification.

**Joined late? Import what you missed.** No extension can capture speech from before your browser joined the call. If
the host recorded the meeting or enabled Google Meet *Transcripts*, use **Upload** with the recording
(`.mp4/.m4a/.mp3/.wav/.webm/…` — transcribed with Whisper and speaker-separated in the background) or the transcript
document (`.docx`, `.txt`, `.vtt`, `.srt`, `.json`).

**Hybrid capture (default):** captions and the tab's audio are captured together. Captions stay the primary transcript (real speaker names, and they include your own voice, which a tab's audio never contains); Whisper transcribes the audio and the server keeps only lines the captions missed, so nothing is duplicated and nothing is lost when captions drop out. Chrome only allows tab capture after you invoke MeetBrief on the tab, so click the MeetBrief toolbar icon once on the meeting tab (or press Alt+Shift+A, or right-click the page → *Add tab audio to MeetBrief*); the panel's single **Start capture (captions + tab audio)** button then starts both. Switch it off in Settings (*Also record the meeting tab's audio as a backup*).

**Multilingual meetings:** each sentence's language is detected on its own (limited to `MEETBRIEF_LANGUAGES`: English, Telugu, Kannada, Hindi, Tamil by default), so speakers may switch languages mid-meeting. Whisper also translates non-English speech straight into English; summaries, Q&A, decisions and tasks read that English. In the **Transcript** tab every viewer picks **Read in** (remembered per browser): lines spoken in another language are shown translated and tagged *Translated from Telugu* etc., with the original underneath (Telugu and Kannada show only the English with the small model, as its Telugu/Kannada script is unreliable). Short phrases Whisper invents on silence ("Thank you.", "Participants") are filtered out.

**When captions aren't available** (CC off, unsupported language) the tab audio carries the meeting on its own. Only the meeting tab is captured (no microphone
permission); audio stays audible, is sent in 15 s chunks to the local backend, transcribed with Whisper
(`faster-whisper`), and deleted immediately. Speakers are separated with WavLM voice embeddings + online clustering
(labels *Speaker 1, Speaker 2…*; map them to names in *Who Said What?*). Real names are never guessed.

Zoom and Teams web adapters are included but **experimental** (untested against live calls; selectors may need updating).

## Late joiners: shared rooms, Early Join, imports, desktop recorder

* **Shared rooms:** the first member in a meeting clicks *Share* (or shares automatically). Everyone else with the
  extension in the same meeting joins the room automatically and gets a personalised **"What you missed"** catch-up
  plus the live recap. One member captures at a time, and capturing hands over automatically when that member leaves.
  Members sign in with Google (verified by the server), or with dev identities in test mode.
* **Early Join:** *Schedule* tab → MeetBrief opens Meet, Zoom or Teams one minute early and joins with mic and camera off.
* **Official transcripts:** import from Google Meet (REST API), Zoom cloud recordings or Microsoft Teams (Graph).
* **Desktop apps:** `tools/desktop_recorder.py` records a loopback or microphone device into MeetBrief.

Setup (Google OAuth client, shared server, scopes) is in [docs/ROOMS.md](docs/ROOMS.md).

## Features

| Area | Highlights |
|---|---|
| Catch Me Up | catch-up recap (optionally "last N minutes"), quick, detailed, chronological, by-topic and personalized summaries; live update; summaries in the selected language |
| Explain Again | simplify / examples / step-by-step / detailed / analogy, 4 difficulty levels, any language; separates *what the meeting said* from *general explanation*; "explain another way"; right-click selected text → *Explain with MeetBrief* |
| Ask AI | hybrid semantic retrieval + grounded answers with clickable evidence; follow-ups; speaker filter; abstains when evidence is missing ("the reason was not explicitly stated") |
| Who Said What? | per-speaker key points, suggestions, decisions, tasks, questions; generic labels stay generic until you map them |
| Decisions | confirmed vs proposed vs superseded; decision-change history; unresolved questions; potential contradictions |
| Action Items | task, owner, deadline, status, evidence; mark complete; correct owner/deadline (user edits persist) |
| Timeline | topics (TextTiling + transition cues), decisions, tasks and questions in order |
| Transcript | full transcript, semantic search, side-by-side translation, jump-to-evidence |
| Notes & export | personal notes kept separate from AI output; export Markdown / PDF / TXT / JSON; search across retained meetings |
| Privacy | private mode (in-memory only), configurable retention, delete transcript / meeting / all data, consent guidance, capture indicator, local API token |

See [docs/FEATURES.md](docs/FEATURES.md) for the status of every feature F01–F72.

## Project structure

```
chrome-extension/      MV3 extension (side panel UI, service worker, platform adapters, tab-audio offscreen doc)
backend/               FastAPI app
  api/                 routes + service layer        capture/   transcript normalisation & caption de-dup
  nlp/                 language ID, summarization, simplification, translation, topics, decisions, actions, questions, speakers
  rag/                 hybrid embeddings, retrieval, grounded answer generation
  memory/              meeting state, rolling summary, decision history
  speech/              Whisper ASR, diarization, alignment
  database/            SQLite (disk) + in-memory (private mode)
  export/ evaluation/ tests/ llm/
  api/rooms.py         shared rooms     connectors/  Google Meet / Zoom / Teams transcript import
tools/                 desktop_recorder.py (desktop meeting apps)
datasets/              sample transcripts (txt/vtt/srt/json, English + Hinglish + Telugu-English) and evaluation annotations
research/              measured evaluation results
docs/                  architecture, API, user guide, evaluation
```

## Tests and evaluation

```bash
.venv/bin/pip install -r requirements-dev.txt
.venv/bin/python -m pytest backend/tests -q
.venv/bin/python -m backend.evaluation.run_eval     # writes research/evaluation_results.md
```

`backend/tests/test_models.py` exercises every Hugging Face model (skipped automatically if a model isn't downloaded).

Measured results ([research/evaluation_results.md](research/evaluation_results.md)) — small synthetic data, read the
caveats in the report:

| Component | Result |
|---|---|
| Abstractive overview vs TextRank (held-out, ROUGE-1) | **0.55** vs 0.36 |
| Abstractive sentences supported by transcript evidence | 16/16 |
| Summarizer benchmark (ROUGE-1) | BART-SAMSum 0.554 vs MEETING_SUMMARY 0.514 → BART-SAMSum chosen |
| Explanation model benchmark | Qwen2.5-1.5B 8/9 correct vs Flan-T5-large 0/9 → Qwen chosen ([details](research/explanation_benchmark.md)) |
| Dialogue acts: rules vs zero-shot NLI | 0.94 vs 0.59 accuracy → rules primary |
| Held-out decisions / action items F1 | 0.80 / 1.0 |
| Q&A: answerable correct / unanswerable abstained | 16/16 / 7/7 |
| ASR WER / diarization speaker accuracy (synthetic 3-voice TTS) | 0.0 / 1.0 |
| Translation round-trip chrF (Hindi / Telugu) | 0.84 / 0.83 |

## Configuration

| Variable | Default | Purpose |
|---|---|---|
| `MEETBRIEF_MODELS` | `on` | `off` = classical pipeline only |
| `MEETBRIEF_DISABLE` | – | disable single model tasks, e.g. `nli,ner` |
| `MEETBRIEF_DEVICE` | `cpu` | `auto` / `mps` / `cuda` |
| `MEETBRIEF_SUMMARY_MODEL`, `MEETBRIEF_MT_MODEL`, `MEETBRIEF_GEN_MODEL`, `MEETBRIEF_QA_MODEL`, `MEETBRIEF_EMBEDDING_MODEL`, `MEETBRIEF_NLI_MODEL`, `MEETBRIEF_NER_MODEL`, `MEETBRIEF_SPEAKER_MODEL` | see table above | swap Hugging Face models |
| `MEETBRIEF_DIALOGUE_ACTS` | `rules` | `hybrid` = add the zero-shot NLI second opinion (slower; see evaluation) |
| `MEETBRIEF_WHISPER_MODEL` | `small` | faster-whisper size (`tiny` … `large-v3`); `base` garbles Telugu/Kannada |
| `MEETBRIEF_LANGUAGES` | `en,te,kn,hi,ta` | languages speech may be labelled as (`all` = any of Whisper's ~99) |
| `MEETBRIEF_NATIVE_TEXT` | — | `all` also writes Telugu/Kannada speech in its own script (needs `medium` or larger to be readable) |
| `MEETBRIEF_SPEAKER_THRESHOLD` | `0.86` | cosine threshold for "same speaker" |
| `MEETBRIEF_HOST` / `MEETBRIEF_PORT` | `127.0.0.1` / `8000` | bind address |
| `MEETBRIEF_API_TOKEN` | random, saved in `data/api_token.txt` | pin the API token |
| `MEETBRIEF_AUTH` | `1` | set `0` to disable token auth (development only) |
| `MEETBRIEF_RETENTION_DAYS` | `30` | default retention |
| `MEETBRIEF_GOOGLE_CLIENT_ID` | – | Google OAuth client ID for shared-room sign-in ([docs/ROOMS.md](docs/ROOMS.md)) |
| `MEETBRIEF_ROOMS_DEV_AUTH` | `0` | `1` = trust `X-MeetBrief-Dev-User` identities (local testing only) |
| `MEETBRIEF_MAX_MODEL_JOBS` | `2` | concurrent heavy model jobs |

## Limitations

* MeetBrief can only recap what it captured or what you upload; it cannot reconstruct earlier conversation.
* Small local models are weaker than large hosted LLMs: abstractive summaries can be generic or wrong, which is why every
  generated sentence is aligned to the transcript and flagged ⚠ when unsupported. LLM explanations are labelled as
  general knowledge. Extraction of decisions/tasks/owners/deadlines stays rule-based (precise, explainable); zero-shot
  NLI was benchmarked and is optional.
* Romanised Hinglish/Tenglish is only partly translated (NLLB has no Latin-script Hindi/Telugu); native-script text is fine.
* The QA model (SQuAD 2.0) is English-only; Hindi/Telugu questions use retrieval + rules, and answers can be translated.
* Diarization works segment-by-segment: overlapping speech or speaker changes inside one Whisper segment are not split.
* Live capture was verified against a simulated Google Meet caption DOM, not a live call; Zoom/Teams adapters are
  experimental. See [docs/TESTING_CHECKLIST.md](docs/TESTING_CHECKLIST.md).
* First requests after start-up are slow while models load (a few seconds each); CPU inference is used by default.
