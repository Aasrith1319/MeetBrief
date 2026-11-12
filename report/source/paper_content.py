"""IEEE conference paper content for MeetBrief AI."""
from pathlib import Path

from model import H2, H3, P, Bullets, Table, Figure

FIG = Path(__file__).parent / "fig"

TITLE = "MeetBrief AI: A Privacy-Preserving, Evidence-Grounded Multilingual Meeting Assistant with Shared Rooms for Late Joiners"
AUTHORS = [("{{Author Name 1}}", "School of Computer Science and Engineering", "RV University, Bengaluru, India", "{{email@rvu.edu.in}}"),
           ("{{Author Name 2 (Guide)}}", "School of Computer Science and Engineering", "RV University, Bengaluru, India", "{{email@rvu.edu.in}}")]

ABSTRACT = ("Participants who join an online meeting late, lose their connection, or struggle with its language have no "
            "reliable way to recover what was said, and existing assistants are cloud services that serve only the user who "
            "started them. We present MeetBrief AI, a Chrome extension with a local backend that builds a structured, "
            "evidence-linked meeting memory from live captions, tab or desktop audio, or imported transcripts, using only "
            "open models that run on a laptop. A hybrid pipeline combines cue-phrase rules for dialogue acts, tasks, owners, "
            "deadlines and decision revisions with BART-SAMSum summarization, hybrid sparse–dense retrieval, extractive "
            "question answering that abstains on unanswerable questions, Qwen2.5-1.5B explanations and NLLB-200 translation "
            "into each viewer's language; every generated sentence is aligned to supporting transcript segments. A shared-room "
            "protocol keyed by the meeting link elects one capturer and gives every other participant a personalised "
            "catch-up of what they missed. On annotated meetings, action items reach F1 = 1.0 and held-out decisions "
            "F1 = 0.80; question answering is correct on 16/16 answerable questions with 7/7 correct abstentions; and the "
            "abstractive overview raises ROUGE-1 from 0.36 to 0.55 with all sentences evidence-supported. Rules outperform "
            "zero-shot NLI for dialogue acts (accuracy 0.94 vs 0.59). A live two-device Google Meet trial validated the "
            "protocol and exposed six integration faults, which we report with their fixes.")
KEYWORDS = ("meeting summarization, retrieval-augmented question answering, dialogue acts, speaker diarization, "
            "multilingual NLP, privacy-preserving AI, browser extensions")

BODY = [
    H2("I.", "Introduction"),
    P("Online meetings on Google Meet, Zoom and Microsoft Teams are where teams decide and assign work, yet the spoken "
      "content is rarely recorded in a usable form. The people who most need a recap — late joiners, participants with a "
      "poor connection, or those less fluent in the meeting language — are least able to ask for one. Commercial meeting "
      "assistants address part of this problem, but they process audio and text in the vendor's cloud, are largely "
      "English-first, and summarise only for the account that started them, so a late joiner receives nothing for the "
      "minutes they missed."),
    P("This paper describes MeetBrief AI, an open, fully local meeting assistant built as a Chrome extension and a Python "
      "backend. Its contributions are: (1) a hybrid NLP pipeline in which precise structured facts come from transparent "
      "rules with evidence and fluent text comes from small open models whose output is aligned to the transcript; "
      "(2) grounded question answering that abstains when the meeting does not contain the answer; (3) a shared-room "
      "protocol that gives each late joiner a personalised catch-up with a single elected capturer and automatic "
      "handover; (4) support for Telugu, Kannada, Hindi, Tamil and code-switched speech; and (5) a component-wise evaluation that compares "
      "rules with models and reports failures found in a live trial."),
    H2("II.", "Related Work"),
    P("Early meeting research produced the ICSI [1] and AMI [2] corpora and modelled dialogue acts with HMMs [3]. "
      "Extractive summarization of meetings [4] commonly used graph ranking such as TextRank [5], and TextTiling [6] "
      "segmented topics by lexical cohesion. Purver et al. [7] and Hsueh and Moore [8] detected action items and decisions, "
      "and the CALO assistant [9] integrated these components on a server. Pre-trained Transformers [10], [11] enabled "
      "abstractive summarizers such as BART [12], trained on dialogue data like SAMSum [13], and meeting-specific models "
      "such as HMNet [14]; QMSum [15] introduced query-based meeting summarization. Abstractive models hallucinate [16], "
      "which motivated retrieval-augmented generation [17]. SQuAD 2.0 [18] added unanswerable questions, sentence "
      "encoders [19], [20] enabled multilingual semantic search, and NLI-based zero-shot classification [21] promised "
      "label-free dialogue-act tagging. For speech, x-vectors [22] and WavLM [23] support diarization, Whisper [24] offers "
      "robust multilingual ASR, NLLB-200 [25] covers Indian languages, and small instruction-tuned models such as "
      "Qwen2.5 [26] run on laptops. No prior system we are aware of combines live multi-participant catch-up, local "
      "processing, evidence alignment with abstention, and Indian-language support."),
    H2("III.", "System Design"),
    H3("A.", "Architecture"),
    P("MeetBrief has four layers (Fig. 1): platform adapters in the meeting tab read captions and detect joining and "
      "leaving; a Manifest V3 service worker coordinates capture, rooms and notifications; a FastAPI backend runs the NLP "
      "pipeline and stores the meeting memory in SQLite (or in memory for private meetings); and a side panel presents "
      "catch-up, Explain Again, Ask AI, decisions, tasks, timeline, transcript and export. Captions update progressively, "
      "so a block is emitted only after 1.8 s of stability and only words beyond the longest common prefix are sent; "
      "button and icon text inside the caption region is removed. Without captions, 15 s tab-audio chunks or a desktop "
      "loopback recorder feed Whisper, and official transcripts can be imported from Meet, Zoom and Teams."),
    Figure("1", "MeetBrief architecture. All models run locally; each has a classical fallback.", str(FIG / "architecture.png"), 8.9),
    H3("B.", "Shared Rooms for Late Joiners"),
    P("A meeting is identified by a key derived from its link (e.g. google_meet:abc-defg-hij, accepting both the /code "
      "and /meet/code URL forms). When a signed-in participant joins, the extension looks up the key; if no room exists it "
      "offers to share, and the sharer becomes the capturer. Others are admitted automatically (optionally by e-mail "
      "domain or approval), stand by, and receive a catch-up computed up to their own join time. Members send heartbeats "
      "every 10 s; the server keeps one live capturer, prefers a member whose captions are visible, hands over after 25 s "
      "without heartbeats, closes rooms idle for 15 min so reused links start fresh, and ends the room with a final "
      "summary when the last member leaves (Fig. 2). Only the current capturer may append transcript segments, which are "
      "placed on the room clock, avoiding both duplicates and gaps."),
    Figure("2", "Shared-room protocol: late-joiner catch-up and capturer handover.", str(FIG / "rooms.png"), 8.9),
    H3("C.", "Security and Privacy"),
    P("Requests carry a principal: the owner's token, a server-verified Google identity, or a test identity. Access control "
      "is fail-closed; members can read only meetings of rooms they belong to (others return 404), cannot modify or "
      "delete them, and see other members' e-mail addresses only if they are the sharer. Raw audio is deleted after "
      "transcription, retention is configurable, and the web UI uses a nonce-based CSP. A DAST scan found and we fixed a "
      "database race condition, a permissive CSP and member e-mail exposure."),
    H2("IV.", "NLP Pipeline"),
    H3("A.", "Normalisation and Language Identification"),
    P("All inputs become segments with time, speaker, language and source. Language is identified per segment from "
      "Unicode script ranges, a lexicon of romanised Hindi and Telugu words for code-switching, and a character n-gram "
      "naive-Bayes detector."),
    H3("B.", "Dialogue Acts and Information Extraction"),
    P("Sentences are tagged as decision, proposal, task, question or other with cue-phrase rules. An optional zero-shot "
      "NLI model [21] may raise the confidence of a rule item but never adds items. Tasks receive an owner (addressee or "
      "self-commitment) and a deadline, owners are verified with BERT NER, and confirmations such as \"I can do that by "
      "Friday\" are merged into the request they answer. A later confirmed decision with a revision cue (\"actually\", "
      "\"postpone\") on the same subject supersedes the earlier one, preserving history. Topics are segmented with "
      "TextTiling and labelled with embedding-based MMR keywords."),
    H3("C.", "Evidence-Aligned Summarization"),
    P("TextRank selects quoted key moments; BART fine-tuned on SAMSum writes an overview, chunked hierarchically under "
      "1,024 tokens. Each generated sentence is aligned to its most similar segment with multilingual MiniLM embeddings; "
      "sentences with low support or with entities absent from the transcript are flagged. The catch-up adds options, "
      "confirmed and superseded decisions, tasks and the current topic."),
    H3("D.", "Question Answering with Abstention"),
    P("Queries are rewritten from chat history, then scored by word TF-IDF, character 3–5-gram TF-IDF and dense "
      "embeddings. A relevance gate requires the retrieved passages to cover at least half of the question's content "
      "words, and \"why\" questions need an explicit reason cue. Owner, deadline and decision questions use the memory; "
      "others use RoBERTa-SQuAD2 [11], [18], accepting a span only if it beats the no-answer score. If the span comes from "
      "a superseded decision, the reader is re-run on the revision so the current state leads."),
    H3("E.", "Explanation, Translation and Speech"),
    P("Explain Again retrieves what the meeting said about a term, then explains it in five styles and four levels using "
      "a glossary or Qwen2.5-1.5B, labelled as general knowledge. NLLB-200 translates outputs while preserving citations "
      "and numbers. Whisper small transcribes audio, detects language per utterance among the configured meeting "
      "languages, and translates non-English speech directly into English for the analysis models; WavLM x-vectors are clustered online with a cosine threshold of 0.86 and "
      "persistent centroids, and generic speaker labels are never replaced by guessed names."),
    H2("V.", "Experimental Setup"),
    P("We annotated a development set of synthetic meetings (product planning, database performance, Hinglish and "
      "Telugu–English discussions) used while writing the rules, and a held-out design-review meeting annotated before "
      "the first evaluation. A further 32 sentences were labelled with dialogue acts, and a 29.3 s three-voice TTS meeting "
      "was used for speech. Every text component was run with rules only and with the Hugging Face models on an Apple M2 "
      "laptop (generation on the MPS GPU, other models on CPU). Metrics are ROUGE-1/2/L F1 [27], precision/recall/F1 with "
      "fuzzy matching, QA accuracy and abstention, WER, speaker accuracy and round-trip chrF [28]."),
    H2("VI.", "Results and Discussion"),
    Table("I", "Extraction and QA (rules vs. with models)", ["Metric", "Dev", "Held-out"], [
        ["Decisions P/R/F1", "1.0/1.0/1.0", "0.67/1.0/0.80"],
        ["Proposals P/R/F1", "1.0/1.0/1.0", "1.0/0.33/0.50"],
        ["Action items P/R/F1", "1.0/1.0/1.0", "1.0/1.0/1.0"],
        ["Owner / deadline acc.", "1.0 / 1.0", "1.0 / 1.0"],
        ["QA answerable correct", "12/12", "4/4"],
        ["QA unanswerable abstained", "5/5", "2/2"],
    ], widths=[2.6, 1.6, 1.7], size=7.5),
    P("Table I shows that rule-based task extraction generalises (F1 = 1.0 held-out) because task language is "
      "formulaic, while proposals are the weakest category (recall 0.33) since suggestions are phrased indirectly. Scores "
      "were identical with and without models because models only confirm rule items. QA answered every answerable "
      "question and refused every unanswerable one."),
    Table("II", "Summary quality (ROUGE F1) and faithfulness", ["Metric", "TextRank", "BART-SAMSum"], [
        ["Dev overview R-1/R-2/R-L", "0.449/0.327/0.425", "0.555/0.336/0.405"],
        ["Held-out overview R-1/R-2/R-L", "0.357/0.116/0.242", "0.550/0.367/0.430"],
        ["Sentences evidence-supported", "–", "16/16"],
    ], widths=[2.6, 1.7, 1.7], size=7.5),
    P("The abstractive overview improves ROUGE-1 by 0.10–0.19 (Table II) with every sentence supported; BART-SAMSum also "
      "beat a meeting-specific summarizer (0.554 vs 0.514 ROUGE-1). The full catch-up scores slightly lower with the "
      "abstractive overview because quoted moments dominate it."),
    Table("III", "Model selection benchmarks", ["Comparison", "Result"], [
        ["Dialogue acts: rules vs zero-shot NLI", "acc. 0.938 vs 0.594 (decision recall 8/8 vs 0/8)"],
        ["Explanations: Flan-T5-L / Qwen 0.5B / Qwen 1.5B", "0 / 2 / 8 of 9 correct"],
        ["ASR WER (Whisper base); diarization acc.", "0.0; 1.0 (3 of 3 speakers)"],
        ["Round-trip chrF hi / te (numbers kept)", "0.835 / 0.827 (6/6)"],
        ["Latency analyse / summary / QA (ms)", "27 / 0.9 / 4 rules; 1,071 / 5,798 / 54 models"],
    ], widths=[2.9, 3.0], size=7.5),
    P("Zero-shot NLI never recognised a decision and, when allowed to add items, lowered held-out decision precision from "
      "0.67 to 0.50, so it is optional. Model size mattered for explanations: Flan-T5-large invented domain meanings, "
      "whereas Qwen2.5-1.5B was correct on 8 of 9 items (Table III). Speech results on clean TTS audio and round-trip chrF "
      "are proxies; real noisy meetings and human review remain necessary."),
    P("**Live trial.** Two laptops joined one Google Meet call with the backend on one of them. Both joined the same room, "
      "one captured while the other read the shared catch-up. The trial exposed six faults missed by simulated tests: "
      "Meet served the call at a /meet/code path, so the call was never detected; caption regions contained button text; "
      "room lookup ran only at join time; Meet's idle toolbar hiding looked like leaving; a failed server check was cached "
      "and hid the user's identity; and a status message was re-sent every 0.7 s. All were fixed and covered by new "
      "browser-harness checks, and the system passes 88 automated tests."),
    H2("VII.", "Limitations and Ethics"),
    P("The evaluation sets are small and synthetic, so the numbers are a sanity check rather than evidence of performance "
      "on long, noisy, real meetings. Caption reading depends on each platform's page structure; Zoom and Teams web "
      "adapters were not tested live. Kannada speech is the weakest language, and Telugu and Kannada are shown in English only. Speech that no participant captured cannot be recovered. Recording requires the "
      "consent of all participants; MeetBrief shows a capture indicator, never names generic speakers, keeps data local "
      "and supports deletion and private mode."),
    H2("VIII.", "Conclusion"),
    P("MeetBrief AI shows that a useful, privacy-preserving meeting assistant can be built from open models on a laptop by "
      "combining transparent rules for structured facts with evidence-constrained generation, and that late-joiner "
      "support is best solved by coordination — shared rooms with one elected capturer — rather than by more modelling. "
      "Future work includes evaluation on AMI and QMSum and on real Indian code-switched meetings, a supervised "
      "dialogue-act model to raise proposal recall, a server-side meeting bot, and quantised models for low-end devices."),
]

REFS = [
    'A. Janin et al., "The ICSI meeting corpus," in *Proc. IEEE ICASSP*, 2003, pp. I-364–I-367.',
    'J. Carletta et al., "The AMI meeting corpus: A pre-announcement," in *Proc. MLMI*, LNCS 3869, 2005, pp. 28–39.',
    'A. Stolcke et al., "Dialogue act modeling for automatic tagging and recognition of conversational speech," *Comput. Linguist.*, vol. 26, no. 3, pp. 339–373, 2000.',
    'G. Murray, S. Renals, and J. Carletta, "Extractive summarization of meeting recordings," in *Proc. Interspeech*, 2005, pp. 593–596.',
    'R. Mihalcea and P. Tarau, "TextRank: Bringing order into texts," in *Proc. EMNLP*, 2004, pp. 404–411.',
    'M. A. Hearst, "TextTiling: Segmenting text into multi-paragraph subtopic passages," *Comput. Linguist.*, vol. 23, no. 1, pp. 33–64, 1997.',
    'M. Purver et al., "Detecting and summarizing action items in multi-party dialogue," in *Proc. SIGdial*, 2007, pp. 18–25.',
    'P.-Y. Hsueh and J. D. Moore, "Automatic decision detection in meeting speech," in *Proc. MLMI*, LNCS 4892, 2007, pp. 168–179.',
    'G. Tur et al., "The CALO meeting assistant system," *IEEE Trans. Audio, Speech, Lang. Process.*, vol. 18, no. 6, pp. 1601–1611, 2010.',
    'J. Devlin, M.-W. Chang, K. Lee, and K. Toutanova, "BERT: Pre-training of deep bidirectional transformers for language understanding," in *Proc. NAACL-HLT*, 2019, pp. 4171–4186.',
    'Y. Liu et al., "RoBERTa: A robustly optimized BERT pretraining approach," arXiv:1907.11692, 2019.',
    'M. Lewis et al., "BART: Denoising sequence-to-sequence pre-training for natural language generation, translation, and comprehension," in *Proc. ACL*, 2020, pp. 7871–7880.',
    'B. Gliwa, I. Mochol, M. Biesek, and A. Wawer, "SAMSum corpus: A human-annotated dialogue dataset for abstractive summarization," in *Proc. Workshop New Frontiers in Summarization*, 2019, pp. 70–79.',
    'C. Zhu, R. Xu, M. Zeng, and X. Huang, "A hierarchical network for abstractive meeting summarization with cross-domain pretraining," in *Findings of EMNLP*, 2020, pp. 194–203.',
    'M. Zhong et al., "QMSum: A new benchmark for query-based multi-domain meeting summarization," in *Proc. NAACL-HLT*, 2021, pp. 5905–5921.',
    'J. Maynez, S. Narayan, B. Bohnet, and R. McDonald, "On faithfulness and factuality in abstractive summarization," in *Proc. ACL*, 2020, pp. 1906–1919.',
    'P. Lewis et al., "Retrieval-augmented generation for knowledge-intensive NLP tasks," in *Proc. NeurIPS*, 2020, pp. 9459–9474.',
    'P. Rajpurkar, R. Jia, and P. Liang, "Know what you don\'t know: Unanswerable questions for SQuAD," in *Proc. ACL*, 2018, pp. 784–789.',
    'N. Reimers and I. Gurevych, "Sentence-BERT: Sentence embeddings using Siamese BERT-networks," in *Proc. EMNLP-IJCNLP*, 2019, pp. 3982–3992.',
    'N. Reimers and I. Gurevych, "Making monolingual sentence embeddings multilingual using knowledge distillation," in *Proc. EMNLP*, 2020, pp. 4512–4525.',
    'W. Yin, J. Hay, and D. Roth, "Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach," in *Proc. EMNLP-IJCNLP*, 2019, pp. 3914–3923.',
    'D. Snyder, D. Garcia-Romero, G. Sell, D. Povey, and S. Khudanpur, "X-vectors: Robust DNN embeddings for speaker recognition," in *Proc. IEEE ICASSP*, 2018, pp. 5329–5333.',
    'S. Chen et al., "WavLM: Large-scale self-supervised pre-training for full stack speech processing," *IEEE J. Sel. Topics Signal Process.*, vol. 16, no. 6, pp. 1505–1518, 2022.',
    'A. Radford, J. W. Kim, T. Xu, G. Brockman, C. McLeavey, and I. Sutskever, "Robust speech recognition via large-scale weak supervision," in *Proc. ICML*, 2023, pp. 28492–28518.',
    'NLLB Team et al., "No language left behind: Scaling human-centered machine translation," arXiv:2207.04672, 2022.',
    'Qwen Team, "Qwen2.5 technical report," arXiv:2412.15115, 2024.',
    'C.-Y. Lin, "ROUGE: A package for automatic evaluation of summaries," in *Text Summarization Branches Out*, 2004, pp. 74–81.',
    'M. Popović, "chrF: Character n-gram F-score for automatic MT evaluation," in *Proc. WMT*, 2015, pp. 392–395.',
]
