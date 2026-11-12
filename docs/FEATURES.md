# Feature status (F01–F72)

Legend: ✅ implemented and covered by tests or manual verification · 🧪 implemented, needs live-platform testing ·
⚙️ implemented, requires an optional dependency · ➖ partial (limitation noted)

All features run locally. "HF" = uses a local Hugging Face model (falls back to the classical pipeline if missing).

## Meeting capture
| ID | Feature | Status | Where |
|---|---|---|---|
| F01 | Meeting detection | 🧪 | `content/meeting_detector.js`, adapters `matches()` |
| F02 | Caption capture | ✅ Meet adapter verified against a simulated Meet caption DOM (`chrome-extension/dev/caption_harness.html`); 🧪 on live calls | `content/caption_capture.js` |
| F03 | Transcript processing | ✅ | `backend/capture/transcript_normalizer.py` |
| F04 | Meeting-tab audio capture | ✅ backend Whisper ASR verified with WebM/Opus and a 3-voice test meeting; 🧪 extension recording on live calls | `audio/tab_capture.js`, `backend/speech/` |
| F05 | Transcript upload (.txt/.vtt/.srt/.json/.docx incl. Google Meet transcript docs) and **recording upload** (.mp4/.m4a/.mp3/.wav/…, background Whisper + diarization) | ✅ | `POST /api/upload`, `POST /api/upload-recording` |
| F06 | Platform adapters | ✅ Meet · 🧪 Zoom/Teams (experimental) | `content/platform_adapters/` |
| F07 | Capture status | ✅ | side-panel capture bar, toolbar `REC` badge |
| F08 | Capture controls (start/pause/resume/stop) + **automatic mode**: join detected → capture starts (captions switched on), leave/tab close → stop + final summary (`/finalize`) + notification | ✅ verified in `dev/meeting_harness.html`; 🧪 live | `background.js`, `meeting_detector.js` |

## Summarization
| F09 Automatic catch-up (incl. "last N minutes") | ✅ HF abstractive overview (BART-SAMSum, evidence-aligned) + extractive/structured sections | `mode=catchup`, `from_time` |
|---|---|---|
| F10 Quick summary | ✅ | |
| F11 Detailed summary (incl. stated reasoning) | ✅ | |
| F12 Complete (chronological) context | ✅ | |
| F13 Live summary | ✅ | "Live update" toggle (15 s) |
| F14 Topic-based summary | ✅ | |
| F15 Personalized catch-up | ✅ | focus: decisions/tasks/technical/general |

## Explain Again
| F16–F20 Explain / simplify / examples / step-by-step / detailed | ✅ curated glossary + HF Qwen2.5-1.5B-Instruct for any term/sentence (labelled as general knowledge) + rule-based simplification |
|---|---|
| F21 Difficulty controls | ✅ |
| F22 Context-aware dictionary | ✅ (meeting context is retrieved and shown separately) |
| F23 Analogies | ✅ |
| F24 Repeat explanation | ✅ "Explain another way" |

## Multilingual
| F25 Multilingual summaries | ✅ HF NLLB-200 (markdown + citations preserved) |
|---|---|
| F26 Language identification | ✅ script ranges + langdetect + romanised markers |
| F27 Multilingual explanations | ✅ HF NLLB-200 (markdown + citations preserved) |
| F28 Multilingual Q&A | ✅ HF NLLB-200 (markdown + citations preserved) |
| F29 Mixed-language processing | ✅ code-switch detection (hi-en, te-en); extraction works on Hinglish/Tenglish samples |
| F30 Side-by-side translation | ✅ HF NLLB-200 (markdown + citations preserved) |
| F31 Language preferences | ✅ |
| F32 Translated action items | ✅ NLLB-200 + number/date preservation check |

## Speaker intelligence
| F33 Participant-name attribution | ✅ from captions/transcripts |
|---|---|
| F34 Speaker diarization | ✅ HF WavLM x-vectors + online clustering (tested on synthetic 3-voice audio) |
| F35 Speaker-to-participant mapping | ✅ user-confirmed mapping only |
| F36 Who Said What? | ✅ |
| F37 Speaker-specific search | ✅ |
| F38 Decision attribution | ✅ rules + HF zero-shot NLI (mDeBERTa) second opinion |
| F39 Task attribution | ✅ incl. "I can do that" → antecedent task (simple coreference) |
| F40 Unknown-speaker handling | ✅ generic labels kept and flagged |

## Memory & navigation
| F41 Meeting memory | ✅ incl. HF BERT-NER entities |
|---|---|
| F42 Rolling summary | ✅ chunked + cached |
| F43 Timeline | ✅ |
| F44 Topic-change detection | ✅ |
| F45 Timestamp navigation | ✅ evidence chips jump to the transcript |
| F46 Decision history | ✅ supersedes / superseded_by chains |
| F47 Unresolved-question tracker | ✅ |
| F48 Current-topic indicator | ✅ |

## Q&A and retrieval
| F49 Ask AI | ✅ |
|---|---|
| F50 Follow-up questions | ✅ history-aware query rewriting |
| F51 Semantic search | ✅ hybrid: word + char n-gram TF-IDF + HF multilingual MiniLM embeddings |
| F52 RAG | ✅ retrieval + structured memory + HF RoBERTa-SQuAD2 extractive reader |
| F53 Evidence-linked answers | ✅ |
| F54 Missing-information detection | ✅ |
| F55 Potential contradiction detection | ✅ (polarity / differing figures, flagged as *potential*) |
| F56 Decision-change detection | ✅ |

## Productivity
| F57 Action items · F58 Deadlines · F59 Task status · F60 Personal notes · F61 Exports · F62 Question suggestions · F63 Catch-up check · F64 History search | ✅ |
|---|---|

## Privacy & reliability
| F65 Explicit capture permission | ✅ user-initiated tabCapture; no microphone permission |
|---|---|
| F66 Consent guidance | ✅ shown before first capture and in Settings |
| F67 Private mode | ✅ in-memory database, never written to disk (tested) |
| F68 Transcript deletion | ✅ transcript / meeting / all data |
| F69 Uncertainty indicators | ✅ |
| F70 Source verification | ✅ |
| F71 Capture transparency | ✅ |
| F72 Configurable retention | ✅ hourly purge (tested) |

## Beyond the specification: late joiners and other meeting sources
See [ROOMS.md](ROOMS.md).

| Feature | Status |
|---|---|
| X01 Automatic meeting mode (join → capture, leave → final summary) | ✅ simulated Meet DOM harness |
| X02 Shared rooms (one capturer, live recap for every member) | ✅ unit tests + two-member browser harness (12/12) |
| X03 Late-joiner "What you missed" catch-up (per-member join time) | ✅ tested |
| X04 Capturer handover (leave, heartbeat timeout, captions-off preference) | ✅ tested |
| X05 Google sign-in for members (server-verified token, domain/approval rules) | ✅ verification tested with mocked Google; needs your OAuth client for live use |
| X06 Early Join (Meet/Zoom/Teams, mic and camera off) | ✅ alarm → tab → auto-join harness; Zoom/Teams pre-join screens untested live |
| X07 Official transcript import: Google Meet / Zoom / Teams | ✅ connector tests with mocked APIs; untested against real accounts |
| X08 Recording upload (audio/video → Whisper + diarization) and `.docx` transcripts | ✅ tested |
| X09 Desktop recorder (`tools/desktop_recorder.py`) | ✅ file mode tested end to end with Whisper; live loopback needs `sounddevice` |
