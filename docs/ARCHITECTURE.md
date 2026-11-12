# Architecture

```
 Meeting tab (Meet / Zoom web / Teams web)
   │  content scripts: meeting_detector.js → platform adapter → caption_capture.js (stabilise + de-dup)
   ▼
 Service worker (background.js) ── capture state machine, REC/ROOM badge, context menu,
   │                                  room join/share/heartbeat, Early Join alarms, lib/identity.js (Google sign-in)
   │        └─ offscreen document (audio/tab_capture.js): tabCapture stream → 15 s WebM/Opus chunks
   ▼ HTTP (127.0.0.1, X-MeetBrief-Token)
 FastAPI backend (backend/main.py, api/routes.py, api/rooms.py; auth.py resolves admin token / Google / dev identity)
   ├─ capture/transcript_normalizer   → common Segment schema (text, times, speaker, language, source, flags)
   ├─ speech/  Whisper ASR → WavLM speaker embeddings + online clustering (diarization)
   ├─ nlp/     language ID · decisions (rules; optional zero-shot NLI) · action items · questions · topics · speakers
   │           contradictions · summarization (TextRank + BART-SAMSum) · evidence alignment
   │           Explain Again (glossary + Qwen2.5-1.5B-Instruct) · translation (NLLB-200)
   ├─ memory/  meeting_state (structured memory + NER + user corrections) · rolling_summary · decision_history
   ├─ rag/     hybrid sparse+dense retrieval → relevance gate → intents → SQuAD2 extractive QA / abstention
   ├─ hf/      local Hugging Face model registry (lazy loading, per-task fallback, offline download script)
   ├─ connectors/ Google Meet REST · Zoom cloud recording · Microsoft Graph transcripts (WebVTT → Segment)
   └─ database/ SQLite on disk + in-memory DB for private mode; rooms + room_members; retention purge
   ▼
 Side panel UI (sidepanel/*) — also served standalone at /app/
```

## Key design decisions

* **Platform-independent core** (spec 5.3): adapters emit `{speaker, text}`; everything downstream uses `Segment`.
* **Everything local.** All neural components are open Hugging Face models executed on the user's machine
  (`backend/hf/models.py`). Each task degrades independently: if a model is missing or fails to load, that feature
  falls back to the classical pipeline and the UI says so.
* **Precise structure, generative prose, verified.** Decisions, tasks, owners, deadlines and questions come from
  transparent rules with evidence ids. A zero-shot NLI second opinion was measured (0.59 vs 0.94 accuracy on dialogue
  acts, and it added false-positive decisions), so it is optional and only raises confidence when it agrees. Abstractive summaries (BART-SAMSum) and explanations (Qwen2.5-Instruct) are
  aligned back to transcript segments; unsupported sentences or entities that never occur in the transcript are flagged.
* **QA with abstention.** The SQuAD 2.0 reader scores a "no answer" option; together with the retrieval relevance gate
  and "why needs a stated reason" rule this lets MeetBrief say "not in the transcript" instead of guessing.
* **Memory is recomputed, corrections persist.** The memory is rebuilt from the stored transcript (cheap, consistent)
  and cached by a fingerprint; user edits (task status/owner/deadline, speaker mappings) are stored separately and
  always override extracted values.
* **Decision revisions** are linked, not overwritten: a later confirmed decision with an explicit revision cue
  ("actually", "instead", "postpone") on the same subject marks the earlier one `superseded`.
* **Abstention.** Retrieved passages must cover at least half the question's content words; "why" questions require
  an explicit reason cue; questions that were asked but not answered in the meeting are reported as such.
* **Caption de-duplication** happens twice: in the content script (stable-text emission with word-prefix deltas) and
  in the backend (growing/duplicate caption updates merge into the last segment).
* **Security.** Local token auth (constant-time compare), CORS restricted to `chrome-extension://` and localhost,
  no secrets in the extension, transcript wrapped in tags + sanitised for LLM prompts, all UI text HTML-escaped,
  upload size limits, temporary audio deleted in `finally`.

* **Shared rooms** (see [ROOMS.md](ROOMS.md)). Requests carry a *principal*: the admin token (the owner's own
  extension and tools), a Google token verified against `MEETBRIEF_GOOGLE_CLIENT_ID`, or a dev identity. The middleware
  is fail-closed: there is no principal by default, members may only call an allow-list of read/ask routes, and
  `require_meeting` returns 404 for meetings outside their rooms. A room is keyed by the meeting link; exactly one
  member is the capturer (elected by heartbeats with a 25 s timeout). Each member's `joined_at` defines their
  "what you missed" window, and the last member leaving ends the room with a final summary.
* **Concurrency.** All database methods are serialised with a re-entrant lock; heavy model jobs are limited by a
  semaphore (`MEETBRIEF_MAX_MODEL_JOBS`).

## Data model

See `backend/models.py`: `Segment` (7.1), `Decision` (7.2), `ActionItem` (7.3), `MeetingMemory` (7.4), plus
`OpenQuestion`, `Topic`, `Contradiction`.
