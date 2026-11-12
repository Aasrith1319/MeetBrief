"""Chapters 5–8, references and appendix of the MeetBrief AI report."""
from pathlib import Path

from model import H1, H2, H3, P, Bullets, Table, Figure, Code

FIG = Path(__file__).parent / "fig"

CH5 = [
    H1("5", "Results"),
    P("This chapter reports the measured results. All numbers were produced by the project's evaluation script on the "
      "machine described in Section 4.3. The datasets are small and synthetic, so the results are a sanity check and a "
      "rules-versus-models comparison, not a general accuracy claim."),
    H2("5.1", "Evaluation Metrics"),
    Bullets([
        "**ROUGE-1/2/L F1** (Lin, 2004): unigram, bigram and longest-common-subsequence overlap between a generated summary "
        "and a reference summary.",
        "**Precision, recall, F1** for decisions, proposals, action items and unresolved questions, using fuzzy matching "
        "of extracted items to annotated ones; **owner and deadline accuracy** on matched tasks.",
        "**Q&A accuracy** on answerable questions and **abstention rate** on unanswerable questions.",
        "**Evidence support**: share of abstractive sentences aligned to a supporting transcript segment.",
        "**WER** for speech recognition and **speaker accuracy** after optimal mapping of predicted to true speakers.",
        "**chrF** (Popović, 2015) for round-trip translation (English → Hindi/Telugu → English) and number preservation.",
        "**Latency** in milliseconds for analysis, summary and Q&A.",
    ]),
    H2("5.2", "Result Summary Tables"),
    Table("5.1", "Information extraction and Q&A (rules only vs with Hugging Face models)",
          ["Metric", "Dev: rules", "Dev: models", "Held-out: rules", "Held-out: models"], [
        ["Decisions P / R / F1", "1.0 / 1.0 / 1.0", "1.0 / 1.0 / 1.0", "0.67 / 1.0 / 0.80", "0.67 / 1.0 / 0.80"],
        ["Decision revisions detected", "1/1", "1/1", "0/0", "0/0"],
        ["Proposals P / R / F1", "1.0 / 1.0 / 1.0", "1.0 / 1.0 / 1.0", "1.0 / 0.33 / 0.50", "1.0 / 0.33 / 0.50"],
        ["Action items P / R / F1", "1.0 / 1.0 / 1.0", "1.0 / 1.0 / 1.0", "1.0 / 1.0 / 1.0", "1.0 / 1.0 / 1.0"],
        ["Task owner / deadline accuracy", "1.0 / 1.0", "1.0 / 1.0", "1.0 / 1.0", "1.0 / 1.0"],
        ["Unresolved questions F1", "1.0", "1.0", "1.0", "1.0"],
        ["Q&A answerable correct", "12/12", "12/12", "4/4", "4/4"],
        ["Q&A unanswerable → abstained", "5/5", "5/5", "2/2", "2/2"],
    ], widths=[3.2, 1.7, 1.7, 1.9, 1.9]),
    Table("5.2", "Summary quality (ROUGE F1) and faithfulness",
          ["Metric", "Dev: TextRank", "Dev: abstractive", "Held-out: TextRank", "Held-out: abstractive"], [
        ["Overview ROUGE-1 / 2 / L", "0.449 / 0.327 / 0.425", "0.555 / 0.336 / 0.405", "0.357 / 0.116 / 0.242", "0.550 / 0.367 / 0.430"],
        ["Full catch-up ROUGE-1 / L", "0.382 / 0.314", "0.348 / 0.275", "0.458 / 0.249", "0.408 / 0.247"],
        ["Abstractive sentences evidence-supported", "–", "12/12", "–", "4/4"],
    ], widths=[3.0, 1.75, 1.75, 1.75, 1.75]),
    Figure("5.1", "Overview summary quality: extractive TextRank vs abstractive BART-SAMSum", str(FIG / "rouge.png"), 13.5),
    Table("5.3", "Summarizer selection benchmark (development set)", ["Model", "Overview ROUGE-1", "ROUGE-L", "Sentences supported", "Seconds / meeting"], [
        ["philschmid/bart-large-cnn-samsum (chosen)", "0.554", "0.410", "16/16", "5.31"],
        ["knkarthick/MEETING_SUMMARY", "0.514", "0.375", "10/10", "4.63"],
    ], widths=[3.8, 1.6, 1.2, 1.7, 1.7]),
    Table("5.4", "Dialogue-act classification on 32 labelled sentences", ["Act", "Cue-phrase rules (recall)", "Zero-shot NLI (recall)"], [
        ["decision", "8/8", "0/8"], ["proposal", "4/6", "5/6"], ["task", "6/6", "2/6"], ["question", "5/5", "5/5"],
        ["other", "7/7", "7/7"], ["**Accuracy**", "**0.938**", "**0.594**"],
    ], widths=[2.4, 3.0, 3.0]),
    Figure("5.2", "Dialogue-act recall of cue-phrase rules versus zero-shot NLI", str(FIG / "dialogue_acts.png"), 13.5),
    Table("5.5", "Explanation model benchmark (9 items, human-rated)", ["Model", "Parameters", "Correct", "Partly", "Wrong", "Typical latency"], [
        ["google/flan-t5-large", "780 M", "0", "2", "7", "1–2 s"],
        ["Qwen/Qwen2.5-0.5B-Instruct", "0.5 B", "2", "4", "3", "2–6 s"],
        ["**Qwen/Qwen2.5-1.5B-Instruct (chosen)**", "1.5 B", "**8**", "1", "0", "5–15 s"],
    ], widths=[3.6, 1.4, 1.1, 1.1, 1.1, 1.7]),
    Figure("5.3", "Explanation quality of the three candidate models", str(FIG / "explain.png"), 13.5),
    Table("5.6", "Speech and translation", ["Component", "Metric", "Result"], [
        ["ASR (Whisper base)", "WER on 29.3 s synthetic 3-voice meeting", "0.0 (1.6 s to transcribe)"],
        ["Diarization (WavLM + online clustering)", "Speaker accuracy; speakers found", "1.0; 3 of 3 (1.2 s)"],
        ["Translation en→hi→en (NLLB-200)", "Round-trip chrF; numbers preserved", "0.835; 6/6 (1.22 s / sentence)"],
        ["Translation en→te→en (NLLB-200)", "Round-trip chrF; numbers preserved", "0.827; 6/6 (0.88 s / sentence)"],
    ], widths=[3.4, 3.6, 3.0]),
    Table("5.7", "Latency in milliseconds (held-out meeting, CPU)", ["Operation", "Rules only", "With Hugging Face models"], [
        ["Analyse meeting (memory)", "27.0", "1,071.0"], ["Catch-up summary", "0.9", "5,798.4"], ["Question answering", "4.2", "54.1"],
    ], widths=[3.6, 2.4, 3.4]),
    Figure("5.4", "Latency of the rule-based and model-based configurations", str(FIG / "latency.png"), 13.0),
    H3("5.2.1", "Live multi-participant trial"),
    P("A live test was run with two laptops in one Google Meet call, with the backend on one laptop and the second laptop "
      "connecting over Wi-Fi as a room member. The trial confirmed the end-to-end flow — both laptops joined the same room, "
      "exchanged heartbeats every 10 s, one laptop captured captions for the room while the other stood by and read the "
      "shared summary and catch-up — and exposed several integration problems that the simulated tests had not shown "
      "(Table 5.8). All of them were fixed and covered by new harness checks."),
    Table("5.8", "Issues found in the live trial and their fixes", ["Observed problem", "Root cause", "Fix"], [
        ["No Share prompt; extension never detected the call", "Meet served the meeting at /meet/<code>; only /<code> was recognised",
         "Meeting code matched anywhere in the path; participant tiles as a second in-call signal"],
        ["Captured text \"Summarise captions close\"", "Meet places buttons and icon glyphs inside the caption region",
         "Caption reader removes button and icon text before emitting speech"],
        ["Two laptops captured separately", "Room lookup happened only once at join time", "Look for a room on every 10 s heartbeat"],
        ["Member left and re-joined repeatedly", "Meet hides its toolbar when the mouse is idle", "Leave requires 6 s without call controls"],
        ["Identity ignored after a backend restart", "A failed server check was cached for 60 s", "Saved identity always sent; failures not cached"],
        ["Status updates flooded the server", "\"No captions\" status re-sent every 0.7 s", "Status reported only on change"],
    ], widths=[3.2, 3.4, 3.4]),
    H2("5.3", "Analysis of Results"),
    P("**Extraction.** Rule-based extraction of action items, owners and deadlines is precise and generalises to the "
      "held-out meeting (F1 1.0), because task language is formulaic (\"please … by Friday\", \"I will …\"). Decision "
      "precision drops to 0.67 on held-out data: the rules confirmed one statement that annotators considered a proposal. "
      "Proposal recall (0.33) is the weakest point — suggestions are phrased in many indirect ways (\"what if we…\", \"maybe "
      "the queue could…\") that cue phrases miss."),
    P("**Models versus rules.** Adding models did not change extraction scores, which is expected because the models only "
      "confirm rule-based items. Zero-shot NLI was clearly worse for dialogue acts (accuracy 0.59 vs 0.94): it never "
      "recognised a decision and classified most decisions as suggestions, and in an earlier experiment it added false "
      "decisions, lowering held-out decision precision from 0.67 to 0.50. This justified keeping NLI optional."),
    P("**Summaries.** The abstractive overview improves ROUGE-1 by about 0.10 on the development set and 0.19 on the "
      "held-out set over TextRank, and all generated sentences were supported by transcript evidence. For the *full* "
      "catch-up, ROUGE is slightly lower with the abstractive overview, because the catch-up is dominated by quoted key "
      "moments and structured lists and the paraphrased overview shares fewer exact words with the reference. ROUGE "
      "rewards word overlap rather than correctness, so evidence alignment is reported alongside it."),
    P("**Q&A.** All answerable questions were answered correctly and all unanswerable questions were refused, including "
      "\"why\" questions without a stated reason. The live demo also revealed that a question about a revised plan first "
      "returned the superseded value; re-running the reader on the revising decision fixed this without changing the "
      "benchmark scores."),
    P("**Explanations.** Model size mattered most: Flan-T5-large invented domain meanings (for example describing sharding "
      "as file compression), Qwen2.5-0.5B was often vague, and Qwen2.5-1.5B was correct on 8 of 9 items. Its latency (5–15 s) "
      "is acceptable for an on-demand feature."),
    P("**Speech and translation.** WER 0.0 and perfect speaker accuracy on clean synthetic TTS audio show that the "
      "pipeline works, but real meetings with overlap and noise will be harder. Round-trip chrF above 0.8 and preserved "
      "numbers indicate that meaning survives translation, but human review is still needed for fluency."),
    P("**Latency.** With models, analysis takes about one second and a catch-up summary about six seconds on a laptop CPU; "
      "the rule-only configuration answers in milliseconds, which makes it a useful fallback on weak machines."),
    H3("5.3.1", "Comparison with existing methods"),
    P("Table 5.9 compares MeetBrief qualitatively with earlier research systems and with typical commercial cloud meeting "
      "assistants. Quantitative comparison with published ROUGE scores is not meaningful here, because those are reported "
      "on AMI, ICSI, SAMSum or QMSum test sets while this project's numbers come from small synthetic meetings."),
    Table("5.9", "Comparison with existing approaches", ["Capability", "Classical research systems (e.g. CALO, AMI baselines)",
                                                        "Typical commercial cloud assistants", "MeetBrief AI"], [
        ["Where processing runs", "Server / offline", "Vendor cloud", "User's own laptop (local models)"],
        ["Cost", "Research prototypes", "Subscription", "Free, open-source models"],
        ["Structured decisions, tasks, owners", "Yes (supervised classifiers)", "Usually action items", "Yes, with revision history and evidence"],
        ["Hallucination control", "Extractive only", "Varies, rarely shown", "Evidence alignment + abstention"],
        ["Late joiner catch-up", "No", "Usually only for the host's account", "Shared rooms, per-member \"what you missed\""],
        ["Indian languages / code-switching", "No", "Limited", "Telugu, Kannada, Hindi, Tamil, Hinglish, Telugu–English"],
        ["Explain a statement simply", "No", "Generic chat", "Explain Again: 5 styles × 4 levels, grounded"],
        ["Works without platform captions", "Needs recordings", "Platform-dependent", "Tab audio, desktop recorder, transcript import"],
    ], widths=[2.4, 2.5, 2.5, 2.6]),
]

CH6 = [
    H1("6", "Inferences"),
    H2("6.1", "Key Findings"),
    Bullets([
        "**Hybrid beats either extreme.** Transparent rules give precise, explainable decisions and tasks; models add "
        "fluency (summaries, explanations, translation) and confidence; evidence alignment keeps model output honest.",
        "**Zero-shot NLI is not a drop-in classifier for meeting acts.** It cannot reliably distinguish deciding from "
        "suggesting, so it should only confirm rule-based items.",
        "**Abstention is essential and achievable.** Combining a relevance gate with SQuAD 2.0's no-answer score refused "
        "every unanswerable question in the evaluation without losing answerable ones.",
        "**Model size matters for explanations.** A 1.5 B-parameter instruction-tuned model was the smallest that gave "
        "reliably correct explanations; smaller models hallucinated domain meanings.",
        "**Late-joiner support is a coordination problem, not an NLP problem.** The information must be captured by someone; "
        "shared rooms keyed by the meeting link, one elected capturer and per-member join times solve it cleanly.",
        "**Simulated tests are necessary but not sufficient.** The live trial found six integration issues in DOM detection "
        "and coordination that no unit test had covered.",
        "**A local assistant is practical.** All features run on a student laptop with response times of a few seconds.",
    ]),
    H2("6.2", "Fulfillment of Objectives"),
    Table("6.1", "Fulfillment of the objectives", ["Objective", "Status", "Evidence"], [
        ["O1 Capture", "Achieved (Meet); experimental (Zoom/Teams web)", "Live Meet capture; tab audio; desktop recorder; transcript import; 17-check harness"],
        ["O2 Understanding", "Achieved", "Action-item F1 1.0, decision F1 0.80 (held-out), revisions, questions F1 1.0"],
        ["O3 Faithful summaries", "Achieved", "ROUGE-1 0.55 abstractive; 16/16 sentences evidence-supported"],
        ["O4 Grounded Q&A", "Achieved", "16/16 answerable correct, 7/7 unanswerable abstained"],
        ["O5 Explain and translate", "Achieved", "Qwen2.5-1.5B 8/9 correct; hi/te chrF 0.84/0.83"],
        ["O6 Late joiners", "Achieved", "Shared rooms verified in live two-laptop trial; 23 room tests; 12-check harness"],
        ["O7 Privacy and security", "Achieved", "Local models, private mode, fail-closed access control, DAST scan with 0 open findings"],
        ["O8 Evaluation", "Achieved on small data", "Full benchmark; larger corpora (AMI/QMSum) left for future work"],
    ], widths=[2.4, 2.6, 5.0]),
    P("The objectives were met on the project's own data and in the live trial. Two qualifications remain: the Zoom and "
      "Teams web adapters were implemented but not tested in live calls, and the accuracy figures come from small synthetic "
      "meetings, so performance on long, noisy, real meetings still has to be measured."),
]

CH7 = [
    H1("7", "Impression Report"),
    H2("7.1", "Personal Learning Experience"),
    P("This project was the first time I built an NLP system end to end, from reading a meeting page in the browser to "
      "evaluating each component with proper metrics. The most important lesson was that a model's output is only useful "
      "when it can be verified: adding evidence ids to every sentence, and letting the system say \"I don't know\", made the "
      "assistant trustworthy in a way that a bigger model alone would not. A second lesson came from the live test with a "
      "friend's laptop: features that passed every automated test failed on the real Google Meet page because of a URL "
      "variant, hidden toolbars and buttons inside the caption area. Debugging these from server logs taught me how to "
      "reason about a distributed system from its observable behaviour. {{Personalise this section with your own experience.}}"),
    H2("7.2", "Skill Enhancement"),
    Bullets([
        "**NLP and machine learning:** Transformers for summarization, QA, NER, NLI, translation and generation; sentence "
        "embeddings and hybrid retrieval; classical TextRank, TextTiling and TF-IDF; designing fair rules-vs-models "
        "evaluations and choosing models from benchmarks rather than assumptions.",
        "**Speech processing:** Whisper ASR, speaker embeddings and online clustering for diarization.",
        "**Software engineering:** Chrome MV3 extensions, FastAPI, SQLite, concurrency (serialising state updates and "
        "database access), and writing 88 automated tests and browser harnesses.",
        "**Security:** authentication and authorization design, broken object-level authorization tests, CSP, and dynamic "
        "application security testing with HawkScan.",
        "**Research and communication:** reading the literature, documenting limitations honestly, and writing this report.",
    ]),
    H2("7.3", "Industry / Academic Relevance"),
    P("Meeting intelligence is an active industry area, and privacy regulations make on-device processing increasingly "
      "important for companies, hospitals and educational institutions. The hybrid, evidence-grounded design is directly "
      "relevant to trustworthy AI, where explainability and abstention are required. Academically, the project connects "
      "core NLP course topics — tokenisation, language identification, classification, information extraction, "
      "summarization, question answering, machine translation and evaluation — in one working system, and it provides an "
      "evaluation framework that can be extended to public corpora such as AMI and QMSum."),
]

CH8 = [
    H1("8", "Conclusion & Future Work"),
    P("MeetBrief AI shows that a useful meeting assistant can be built from open models running on a student laptop, "
      "without sending meeting content to any external AI service. The system captures Google Meet captions, tab audio, "
      "desktop audio or imported transcripts; builds a structured meeting memory; produces evidence-aligned summaries; "
      "answers questions with quoted evidence and abstains when information is missing; explains and translates content "
      "into each viewer's language; and gives late joiners a personalised catch-up through shared rooms."),
    P("The main take-away is methodological. Precise structured information (who must do what by when) is best extracted "
      "with transparent rules, while models are most valuable for fluent text and should be constrained by evidence. On "
      "the evaluation data, action items reached F1 1.0, decisions 0.80 on held-out data, Q&A was 16/16 correct with 7/7 "
      "correct abstentions, and the abstractive overview raised ROUGE-1 from 0.36 to 0.55 with every sentence supported. "
      "Benchmarks guided the model choices: rules over zero-shot NLI for dialogue acts, BART-SAMSum over a meeting-specific "
      "summarizer, and Qwen2.5-1.5B over Flan-T5 for explanations."),
    P("The work also has clear limitations. Kannada speech is the weakest language, Telugu and Kannada appear in English "
      "only, the capturing user's own voice needs captions, and a full live five-language test is still pending. "
      "The datasets are small and synthetic, so the reported numbers are not "
      "evidence of performance on long, noisy, real meetings. Proposal detection has low recall. The Zoom and Teams web "
      "adapters are untested in live calls, and caption reading depends on each platform's page structure, which changes "
      "over time. A late joiner benefits only if at least one participant with the extension was present from the start "
      "or an official transcript exists. Small local models are slower and less fluent than large hosted models."),
    H2("", "Future Work"),
    Bullets([
        "Evaluate on public corpora (AMI, ICSI, QMSum) and on real recorded Indian code-switched meetings with human "
        "judgements of faithfulness, explanation clarity and translation fluency.",
        "Improve proposal recall with a small supervised dialogue-act classifier fine-tuned on AMI dialogue-act annotations, "
        "keeping rules for precision.",
        "Add a server-side meeting bot (Google Meet Media API, Zoom Meeting SDK or Teams bots) so that capture does not depend "
        "on any participant's browser.",
        "Verify and harden the Zoom and Teams web adapters, and provide published OAuth apps so transcript import does not "
        "require pasted tokens.",
        "Use overlapped-speech detection and end-to-end diarization for real noisy audio, and evaluate DER.",
        "Offer organisation deployment: HTTPS server, Chrome Enterprise force-install, and verified Google sign-in for all "
        "members.",
        "Quantise models (int8 / 4-bit) to reduce latency and memory on low-end laptops.",
    ]),
]

REFERENCES = [
    "Carletta, J., Ashby, S., Bourban, S., Flynn, M., Guillemot, M., Hain, T., Kadlec, J., Karaiskos, V., Kraaij, W., Kronenthal, M., Lathoud, G., Lincoln, M., Lisowska, A., McCowan, I., Post, W., Reidsma, D., & Wellner, P. (2005). The AMI meeting corpus: A pre-announcement. In *Machine Learning for Multimodal Interaction (MLMI 2005)*, LNCS 3869 (pp. 28–39). Springer.",
    "Chen, S., Wang, C., Chen, Z., Wu, Y., Liu, S., Chen, Z., Li, J., Kanda, N., Yoshioka, T., Xiao, X., Wu, J., Zhou, L., Ren, S., Qian, Y., Qian, Y., Wu, J., Zeng, M., Yu, X., & Wei, F. (2022). WavLM: Large-scale self-supervised pre-training for full stack speech processing. *IEEE Journal of Selected Topics in Signal Processing, 16*(6), 1505–1518.",
    "Devlin, J., Chang, M.-W., Lee, K., & Toutanova, K. (2019). BERT: Pre-training of deep bidirectional transformers for language understanding. In *Proceedings of NAACL-HLT 2019* (pp. 4171–4186).",
    "Gliwa, B., Mochol, I., Biesek, M., & Wawer, A. (2019). SAMSum corpus: A human-annotated dialogue dataset for abstractive summarization. In *Proceedings of the 2nd Workshop on New Frontiers in Summarization* (pp. 70–79).",
    "He, P., Gao, J., & Chen, W. (2023). DeBERTaV3: Improving DeBERTa using ELECTRA-style pre-training with gradient-disentangled embedding sharing. In *International Conference on Learning Representations (ICLR 2023)*.",
    "Hearst, M. A. (1997). TextTiling: Segmenting text into multi-paragraph subtopic passages. *Computational Linguistics, 23*(1), 33–64.",
    "Hsueh, P.-Y., & Moore, J. D. (2007). Automatic decision detection in meeting speech. In *Machine Learning for Multimodal Interaction (MLMI 2007)*, LNCS 4892 (pp. 168–179). Springer.",
    "Janin, A., Baron, D., Edwards, J., Ellis, D., Gelbart, D., Morgan, N., Peskin, B., Pfau, T., Shriberg, E., Stolcke, A., & Wooters, C. (2003). The ICSI meeting corpus. In *Proceedings of IEEE ICASSP 2003* (pp. I-364–I-367).",
    "Lewis, M., Liu, Y., Goyal, N., Ghazvininejad, M., Mohamed, A., Levy, O., Stoyanov, V., & Zettlemoyer, L. (2020a). BART: Denoising sequence-to-sequence pre-training for natural language generation, translation, and comprehension. In *Proceedings of ACL 2020* (pp. 7871–7880).",
    "Lewis, P., Perez, E., Piktus, A., Petroni, F., Karpukhin, V., Goyal, N., Küttler, H., Lewis, M., Yih, W., Rocktäschel, T., Riedel, S., & Kiela, D. (2020b). Retrieval-augmented generation for knowledge-intensive NLP tasks. In *Advances in Neural Information Processing Systems 33* (pp. 9459–9474).",
    "Lin, C.-Y. (2004). ROUGE: A package for automatic evaluation of summaries. In *Text Summarization Branches Out* (pp. 74–81). Association for Computational Linguistics.",
    "Liu, Y., Ott, M., Goyal, N., Du, J., Joshi, M., Chen, D., Levy, O., Lewis, M., Zettlemoyer, L., & Stoyanov, V. (2019). RoBERTa: A robustly optimized BERT pretraining approach. *arXiv preprint arXiv:1907.11692*.",
    "Maynez, J., Narayan, S., Bohnet, B., & McDonald, R. (2020). On faithfulness and factuality in abstractive summarization. In *Proceedings of ACL 2020* (pp. 1906–1919).",
    "Mihalcea, R., & Tarau, P. (2004). TextRank: Bringing order into texts. In *Proceedings of EMNLP 2004* (pp. 404–411).",
    "Murray, G., Renals, S., & Carletta, J. (2005). Extractive summarization of meeting recordings. In *Proceedings of Interspeech 2005* (pp. 593–596).",
    "NLLB Team, Costa-jussà, M. R., Cross, J., Çelebi, O., Elbayad, M., Heafield, K., Heffernan, K., et al. (2022). No language left behind: Scaling human-centered machine translation. *arXiv preprint arXiv:2207.04672*.",
    "Page, L., Brin, S., Motwani, R., & Winograd, T. (1999). *The PageRank citation ranking: Bringing order to the web* (Technical Report 1999-66). Stanford InfoLab.",
    "Park, T. J., Kanda, N., Dimitriadis, D., Han, K. J., Watanabe, S., & Narayanan, S. (2022). A review of speaker diarization: Recent advances with deep learning. *Computer Speech & Language, 72*, 101317.",
    "Popović, M. (2015). chrF: Character n-gram F-score for automatic MT evaluation. In *Proceedings of the Tenth Workshop on Statistical Machine Translation* (pp. 392–395).",
    "Purver, M., Dowding, J., Niekrasz, J., Ehlen, P., Noorbaloochi, S., & Peters, S. (2007). Detecting and summarizing action items in multi-party dialogue. In *Proceedings of the 8th SIGdial Workshop on Discourse and Dialogue* (pp. 18–25).",
    "Qwen Team. (2024). Qwen2.5 technical report. *arXiv preprint arXiv:2412.15115*.",
    "Radford, A., Kim, J. W., Xu, T., Brockman, G., McLeavey, C., & Sutskever, I. (2023). Robust speech recognition via large-scale weak supervision. In *Proceedings of the 40th International Conference on Machine Learning*, PMLR 202 (pp. 28492–28518).",
    "Rajpurkar, P., Jia, R., & Liang, P. (2018). Know what you don't know: Unanswerable questions for SQuAD. In *Proceedings of ACL 2018* (pp. 784–789).",
    "Reimers, N., & Gurevych, I. (2019). Sentence-BERT: Sentence embeddings using Siamese BERT-networks. In *Proceedings of EMNLP-IJCNLP 2019* (pp. 3982–3992).",
    "Reimers, N., & Gurevych, I. (2020). Making monolingual sentence embeddings multilingual using knowledge distillation. In *Proceedings of EMNLP 2020* (pp. 4512–4525).",
    "Snyder, D., Garcia-Romero, D., Sell, G., Povey, D., & Khudanpur, S. (2018). X-vectors: Robust DNN embeddings for speaker recognition. In *Proceedings of IEEE ICASSP 2018* (pp. 5329–5333).",
    "Stolcke, A., Ries, K., Coccaro, N., Shriberg, E., Bates, R., Jurafsky, D., Taylor, P., Martin, R., Van Ess-Dykema, C., & Meteer, M. (2000). Dialogue act modeling for automatic tagging and recognition of conversational speech. *Computational Linguistics, 26*(3), 339–373.",
    "Tjong Kim Sang, E. F., & De Meulder, F. (2003). Introduction to the CoNLL-2003 shared task: Language-independent named entity recognition. In *Proceedings of CoNLL-2003* (pp. 142–147).",
    "Tur, G., Stolcke, A., Voss, L., Peters, S., Hakkani-Tür, D., Dowding, J., Favre, B., Fernández, R., Frampton, M., Frandsen, M., Frederickson, C., Graciarena, M., Kintzing, D., Leveque, K., Mason, S., Niekrasz, J., Purver, M., Riedhammer, K., Shriberg, E., Tien, J., Vergyri, D., & Yang, F. (2010). The CALO meeting assistant system. *IEEE Transactions on Audio, Speech, and Language Processing, 18*(6), 1601–1611.",
    "Vaswani, A., Shazeer, N., Parmar, N., Uszkoreit, J., Jones, L., Gomez, A. N., Kaiser, Ł., & Polosukhin, I. (2017). Attention is all you need. In *Advances in Neural Information Processing Systems 30* (pp. 5998–6008).",
    "Wolf, T., Debut, L., Sanh, V., Chaumond, J., Delangue, C., Moi, A., Cistac, P., Rault, T., Louf, R., Funtowicz, M., Davison, J., Shleifer, S., von Platen, P., Ma, C., Jernite, Y., Plu, J., Xu, C., Le Scao, T., Gugger, S., Drame, M., Lhoest, Q., & Rush, A. M. (2020). Transformers: State-of-the-art natural language processing. In *Proceedings of EMNLP 2020: System Demonstrations* (pp. 38–45).",
    "Yin, W., Hay, J., & Roth, D. (2019). Benchmarking zero-shot text classification: Datasets, evaluation and entailment approach. In *Proceedings of EMNLP-IJCNLP 2019* (pp. 3914–3923).",
    "Zhong, M., Yin, D., Yu, T., Zaidi, A., Mutuma, M., Jha, R., Awadallah, A. H., Celikyilmaz, A., Liu, Y., Qiu, X., & Radev, D. (2021). QMSum: A new benchmark for query-based multi-domain meeting summarization. In *Proceedings of NAACL-HLT 2021* (pp. 5905–5921).",
    "Zhu, C., Xu, R., Zeng, M., & Huang, X. (2020). A hierarchical network for abstractive meeting summarization with cross-domain pretraining. In *Findings of EMNLP 2020* (pp. 194–203).",
]

APPENDIX = [
    H1("", "Appendix"),
    H2("", "Appendix 1: Selected REST API Endpoints"),
    Table("A.1", "Selected backend endpoints", ["Method and path", "Purpose"], [
        ["POST /api/meetings; POST /api/meetings/{id}/segments", "Create a meeting; add caption segments"],
        ["POST /api/meetings/{id}/audio", "Transcribe a 15 s audio chunk (Whisper + diarization)"],
        ["POST /api/upload; POST /api/upload-recording", "Import a transcript file; import a recording (background ASR)"],
        ["POST /api/meetings/{id}/summary", "Catch-up / quick / detailed / chronological / topic / personalised summary"],
        ["POST /api/meetings/{id}/ask", "Grounded question answering with evidence and abstention"],
        ["POST /api/meetings/{id}/explain; POST /api/translate", "Explain Again; translation"],
        ["GET /api/meetings/{id}/decisions | tasks | timeline | speakers", "Structured meeting memory"],
        ["GET /api/meetings/{id}/export?format=md|pdf|txt|json", "Export minutes"],
        ["POST /api/meetings/{id}/finalize", "Final summary when the meeting ends"],
        ["POST /api/rooms/share; GET /api/rooms/lookup", "Share a meeting as a room; find the room of a meeting link"],
        ["POST /api/rooms/{id}/join | heartbeat | segments | leave", "Join, capturer election, capturer-only transcript, leave"],
        ["GET /api/rooms/{id}/catchup", "Personalised \"what you missed\" catch-up"],
        ["POST /api/import/{google_meet|zoom|teams}", "Import the platform's official transcript"],
        ["DELETE /api/meetings/{id}; DELETE /api/data", "Privacy: delete a meeting or all data"],
    ], widths=[4.6, 5.4]),
    H2("", "Appendix 2: Project Structure and How to Run"),
    Code("nlp/\n"
         "  chrome-extension/  MV3 extension: background.js, content/, sidepanel/,\n"
         "                     audio/, lib/identity.js\n"
         "  backend/           FastAPI app: api/, auth.py, capture/, nlp/, rag/,\n"
         "                     memory/, speech/, hf/, database/, connectors/,\n"
         "                     export/, evaluation/, tests/\n"
         "  tools/             desktop_recorder.py\n"
         "  datasets/          sample transcripts, annotations, synthetic audio\n"
         "  research/          measured evaluation results and benchmarks\n"
         "  docs/              architecture, user guide, rooms, evaluation, security\n\n"
         "# start the backend (first run creates .venv and installs dependencies)\n"
         "./run.sh\n"
         "# shared rooms on a LAN with test identities\n"
         "MEETBRIEF_HOST=0.0.0.0 MEETBRIEF_ROOMS_DEV_AUTH=1 ./run.sh\n"
         "# tests and evaluation\n"
         ".venv/bin/python -m pytest backend/tests -q\n"
         ".venv/bin/python -m backend.evaluation.run_eval\n"
         "# Chrome: chrome://extensions > Developer mode > Load unpacked > chrome-extension/"),
    H2("", "Appendix 3: Example Catch-up Output (unedited)"),
    P("The catch-up below was generated by MeetBrief for the sprint-planning meeting; bracketed ids such as [S3] link "
      "each line to the transcript segment that supports it.", keep_next=True),
    P("**Main problem / goal**", align="left", space_after=2, keep_next=True),
    Bullets(["Karthik: The main issue is that we load all the payment provider scripts up front. [S3]"]),
    P("**Overview** *(abstractive — bart-large-cnn-samsum, verify flagged items)*", align="left", space_after=2, keep_next=True),
    Bullets(["The payment page needs to be lazy loaded only when the user selects a payment method and the address "
             "validation should be moved to the backend. [S3] The database migration needs a rollback plan and Sana will "
             "write it by next Monday. [S19] The mobile app release for 2.4 will be postponed to next Tuesday. [S13]"]),
    P("**Decisions**", align="left", space_after=2, keep_next=True),
    Bullets(["Go with lazy loading the payment scripts first, because it is the smallest change with the biggest impact "
             "(by Meera) [S5]",
             "Postpone the 2.4 release to next Tuesday instead, so David has time to fix the Android crash (by Meera) [S13]"]),
    P("**Action items**", align="left", space_after=2, keep_next=True),
    Bullets(["Implement the lazy loading — owner: Karthik; deadline: Wednesday [S6]",
             "Write the rollback plan — owner: Sana; deadline: next Monday [S19]"]),
]
