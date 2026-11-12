# NLP concepts → where they are implemented

Every model runs **locally** (Hugging Face Transformers / Sentence-Transformers / faster-whisper). No paid or external
AI API is used. Each neural component has a classical fallback so the system degrades gracefully.

| Concept (spec §9) | Technique used in MeetBrief | Code |
|---|---|---|
| Automatic Speech Recognition | Whisper (encoder-decoder Transformer, CTranslate2 build) on 15 s WebM/Opus chunks; VAD filter; word timestamps | `backend/speech/speech_recognition.py` |
| Speaker diarization | WavLM-Base-Plus x-vector embeddings (`microsoft/wavlm-base-plus-sv`) + **online agglomerative clustering** with cosine threshold; centroids persist across chunks | `backend/speech/diarization.py` |
| Language identification | Unicode script ranges (Telugu, Devanagari, …) → romanised Hindi/Telugu lexicon (code-switching) → `langdetect` (naive Bayes over char n-grams) | `backend/nlp/language_detection.py` |
| Text normalisation | caption de-duplication (prefix deltas), filler removal, fragment merging, timestamp parsing (VTT/SRT/JSON/text) | `backend/capture/transcript_normalizer.py`, `chrome-extension/content/caption_capture.js` |
| Extractive summarization | **TextRank**: PageRank over a TF-IDF cosine-similarity sentence graph, with problem/reason boosts | `backend/nlp/text_utils.py`, `summarization.py` |
| Abstractive summarization | **BART-large fine-tuned on SAMSum** dialogue summaries (`philschmid/bart-large-cnn-samsum`), hierarchical chunking under the 1024-token limit | `backend/nlp/summarization.py` |
| Hallucination control | **claim–evidence alignment**: each generated sentence ↔ most similar transcript segment (dense cosine) + novel-entity check; unsupported sentences flagged ⚠ | `backend/nlp/evidence_alignment.py` |
| Machine translation | **NLLB-200 distilled 600M** (200 languages incl. Hindi, Telugu); markdown/citation-preserving; number-preservation check | `backend/nlp/translation.py` |
| Text simplification / explanation | lexical substitution + sentence splitting; curated glossary; small instruction-tuned LLM **Qwen2.5-1.5B-Instruct** with concise prompts (simplify / example / step-by-step / analogy / detailed × 4 levels) — chosen over Flan-T5-large by a benchmark (`research/explanation_benchmark.md`) | `backend/nlp/simplification.py`, `glossary.py` |
| Named Entity Recognition | **BERT-base-NER** (CoNLL-03), word-level aggregation of sub-tokens; used for entity lists and to verify task owners | `backend/hf/models.py::_ner`, `memory/meeting_state.py` |
| Text classification (dialogue acts) | cue-phrase rules (accuracy 0.94 on 32 labelled sentences) vs **zero-shot NLI** (`mDeBERTa-v3-base-mnli-xnli`, hypotheses "The speaker makes a decision / suggests an idea / asks a question…", accuracy 0.59) — NLI is an optional confidence booster (`MEETBRIEF_DIALOGUE_ACTS=hybrid`) | `backend/nlp/decision_extraction.py`, `dialogue_acts.py` |
| Information extraction | rule-based extraction of task / owner / deadline (regex + addressee & self-commitment patterns), decision revision linking, question–answer pairing |
| Coreference (simple) | "Sure, I can do that by Friday" is resolved to the request it answers ("Rishi, please compress the images") and merged as the owner's confirmation; hints which generic speaker is which participant | `action_extraction.py`, `decision_extraction.py`, `question_tracking.py` |
| Sentence embeddings | `paraphrase-multilingual-MiniLM-L12-v2` (50+ languages) | `backend/rag/embeddings.py` |
| Semantic search | **hybrid retrieval**: word TF-IDF + char 3–5-gram TF-IDF + dense embeddings, speaker/time filters | `backend/rag/embeddings.py`, `retrieval.py` |
| Question answering / RAG | retrieve → relevance gate (content-word coverage) → structured-memory intents → **extractive QA with RoBERTa-base-SQuAD2** (uses the *no-answer* score to abstain) → evidence quoting | `backend/rag/answer_generation.py` |
| Topic detection | **TextTiling** (depth scores over TF-IDF window similarity) + transition cues; **KeyBERT-style** labels (embeddings + MMR) | `backend/nlp/topic_detection.py` |
| Context management | rolling summary of 20-segment chunks (cached), follow-up query rewriting from chat history, structured meeting memory | `backend/memory/`, `rag/retrieval.py::contextualize_query` |
| Contradiction detection | high-similarity sentence pairs with polarity (negation) or numeric mismatch | `backend/nlp/contradiction.py` |
| Uncertainty handling | abstention, `unknown`/`uncertain` fields, model-detected flags, confidence calibration from rule–model agreement | throughout |
| Evaluation | ROUGE-1/2/L, P/R/F1, WER, chrF, speaker-mapping accuracy — implemented from scratch | `backend/evaluation/metrics.py`, `run_eval.py` |
