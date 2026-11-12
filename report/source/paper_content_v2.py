"""IEEE paper, extended with the section structure of the Team 4 reference paper. Existing sections come from
paper_content.py unchanged; only the missing headings and their content are added here."""
import re

import paper_content as pc
from model import Bullets, H2, H3, P, Table

TITLE = pc.TITLE
REFS = pc.REFS
KEYWORDS = pc.KEYWORDS
ABSTRACT = pc.ABSTRACT.replace("exposed six integration faults", "exposed seven integration faults")
assert "seven integration" in ABSTRACT
DEPT, UNI = "SoCSE", "RV University, Bengaluru, India"
AUTHORS = [(n, DEPT, UNI, "{{USN}}") for n in ("G.V. Sashank", "G.V. Aasrith", "K. Sai Bhavesh", "K. Vignesh")]


def section(title):
    """Blocks under an existing H2 heading (without the heading)."""
    i = next(k for k, b in enumerate(pc.BODY) if isinstance(b, H2) and b.title == title)
    j = next((k for k in range(i + 1, len(pc.BODY)) if isinstance(pc.BODY[k], H2)), len(pc.BODY))
    return pc.BODY[i + 1:j]


def renumber(block):
    """Old Table I/II/III become IV/V/VI now that three tables come before them."""
    new = {"I": "IV", "II": "V", "III": "VI"}
    if isinstance(block, Table):
        return Table(new[block.num], block.caption, block.header, block.rows, block.widths, block.size)
    if isinstance(block, P):
        block = P(re.sub(r"Table (III|II|I)\b", lambda m: "Table " + new[m.group(1)], block.text))
    return block


results = [renumber(b) for b in section("Results and Discussion")]
live = results[-1]
a = "The trial exposed six faults missed by simulated tests:"
b = "; and a status message was re-sent every 0.7 s. All were fixed"
assert a in live.text and b in live.text
live = P(live.text.replace("**Live trial.** ", "").replace(a, "The trials exposed seven faults missed by simulated tests:").replace(
    b, "; a status message was re-sent every 0.7 s; and Chrome refused tab capture requested by the service worker, so "
       "capture now follows the user's click on the extension's toolbar icon. All were fixed") +
    " A later call on the multilingual pipeline carried Telugu-labelled speech end to end into the room's transcript as "
    "English; a full five-language live test is still pending.")

BODY = [
    H2("I.", "Introduction"), *section("Introduction"),

    H2("II.", "Related Work"),
    H3("A.", "Prior Work"), *section("Related Work"),
    H3("B.", "Comparative Discussion"),
    P("Table I summarises the surveyed work. Three patterns shape this project. Structured meeting outcomes were studied "
      "early, but with corpus-specific classifiers and server-side processing. Later work improved fluency through "
      "pre-trained models, at the cost of possible hallucination. Speech and translation models now cover Indian languages, "
      "yet they are usually evaluated alone rather than inside a meeting assistant."),
    Table("I", "Summary of related work", ["Work", "Method", "Gap for this project"], [
        ["ICSI, AMI [1], [2]", "Meeting corpora", "English; no live use"],
        ["Stolcke et al. [3]", "HMM dialogue acts", "Needs labelled data"],
        ["TextRank [5]", "Graph ranking", "Extractive only"],
        ["Purver; Hsueh [7], [8]", "Action items, decisions", "Corpus-specific"],
        ["CALO [9]", "Integrated assistant", "Server-side; no late joiners"],
        ["BART, HMNet [12], [14]", "Abstractive summaries", "May hallucinate [16]"],
        ["QMSum [15]", "Query-based summaries", "Benchmark, not a live system"],
        ["RAG, SQuAD 2.0 [17], [18]", "Grounding, no-answer", "Not meeting-specific"],
        ["Whisper, NLLB [24], [25]", "Speech, translation", "Not tied to meeting memory"],
    ], [3.0, 2.6, 2.9], 8),
    H3("C.", "Positioning"),
    P("Meeting summarization, action-item detection, grounded question answering and multilingual speech recognition all "
      "exist. What we did not find is a system that combines them locally, keeps evidence for its outputs, abstains when "
      "the meeting lacks the answer, and serves each late joiner separately. That combination is the contribution."),

    H2("III.", "Research Gaps"),
    P("**Gap 1—Late-joiner support.** Prior assistants [9] serve a meeting as a whole, and commercial tools summarise for "
      "the account that started them. Multi-participant coordination, in which each member receives what they personally "
      "missed, is not addressed."),
    P("**Gap 2—Faithfulness of meeting outputs.** Abstractive models can invent content [16], and retrieval [17] reduces "
      "but does not remove this risk. Outputs need sentence-level evidence and a way to refuse."),
    P("**Gap 3—Local processing.** Meeting content is private, yet most assistants depend on a vendor's cloud. Whether small "
      "open models on a laptop are adequate needs measurement per task."),
    P("**Gap 4—Indian-language meetings.** Corpora such as AMI [2] are English. Speech and translation models [24], [25] "
      "cover Indian languages, but their behaviour inside a live meeting pipeline, including code-switching, is rarely reported."),
    P("**Gap 5—Rules versus models.** Zero-shot classification [21] promises label-free dialogue-act tagging, but its value "
      "against simple rules for meeting decisions is not established."),

    H2("IV.", "Problem Statement"),
    P("Meeting participants who join late, lose their connection, or are less fluent in the meeting language have no "
      "reliable way to recover what was said. Cloud assistants raise privacy concerns, serve only the person who started "
      "them, and may produce unsupported content [16]. This work therefore designs and evaluates a privacy-preserving, "
      "multilingual meeting assistant that captures meetings from captions or audio without external AI services, extracts "
      "decisions and tasks with traceable evidence, produces faithful summaries, abstains when information is absent, and "
      "gives each late joiner a personal catch-up, using only open models that run on a laptop."),

    H2("V.", "Research Questions"),
    P("Table II states the research questions and the prior work behind each."),
    Table("II", "Research questions and their grounding", ["RQ", "Question", "Prior work"], [
        ["RQ1", "Can transparent rules reliably extract decisions, tasks, owners and deadlines, compared with a neural classifier?", "[3], [7], [8], [21]"],
        ["RQ2", "Do abstractive summaries improve on extractive ones while staying supported by evidence?", "[5], [12], [13], [16]"],
        ["RQ3", "Can question answering abstain on absent answers without losing answerable ones?", "[17], [18]"],
        ["RQ4", "Which small open models are adequate for each task on a laptop?", "[12], [21], [26]"],
        ["RQ5", "Can a shared-room protocol give late joiners a catch-up with one capturer in a real call?", "[9]"],
        ["RQ6", "Can local models handle English, Telugu, Kannada, Hindi and Tamil meeting speech?", "[24], [25]"],
    ], [1.0, 5.6, 1.9], 8),

    H2("VI.", "Methodology and System Design"), *section("System Design"),
    H3("D.", "Design Decisions and Justification"),
    Bullets([
        "**Rules for structured facts, models for fluent text.** Owners and deadlines must be exact and traceable, and rules "
        "outperformed zero-shot NLI on dialogue acts (Section X-C).",
        "**Evidence alignment for every generated sentence.** This responds directly to hallucination in abstractive models [16].",
        "**Abstention as a feature.** A relevance gate and a no-answer score [18] let the system refuse instead of guessing.",
        "**One elected capturer per room.** A single writer avoids duplicate transcripts, and heartbeats allow automatic handover.",
        "**Hybrid capture.** Captions give real names and the capturing user's own voice, which tab audio never contains. "
        "Audio fills gaps: a sentence with at least 60% content-word overlap with a caption line is dropped as a duplicate.",
        "**Direct speech-to-English translation.** Whisper small writes Telugu and Kannada text unreliably but translates the "
        "speech far better, so the analysis models read that English, and each viewer reads lines tagged with their source language.",
        "**Everything local.** Each model has a classical fallback, so a missing model reduces quality but does not stop the system.",
    ]),

    H2("VII.", "NLP Pipeline"), *section("NLP Pipeline"),
    H3("F.", "Models"),
    P("Table III lists the open models used. All run locally and can be replaced through configuration."),
    Table("III", "Models used", ["Task", "Model"], [
        ["Speech recognition", "Whisper small (faster-whisper) [24]"],
        ["Speaker embeddings", "WavLM-Base-Plus [23]"],
        ["Summarization", "BART-large-CNN-SAMSum [12], [13]"],
        ["Translation", "NLLB-200-distilled-600M [25]"],
        ["Explanation", "Qwen2.5-1.5B-Instruct [26]"],
        ["Question answering", "RoBERTa-base-SQuAD2 [11], [18]"],
        ["Embeddings", "Multilingual MiniLM-L12 [19], [20]"],
        ["Zero-shot NLI (optional)", "mDeBERTa-v3-base-XNLI [21]"],
        ["Named entities", "BERT-base-NER [10]"],
    ], [3.4, 5.1], 8),

    H2("VIII.", "Datasets and Benchmark"),
    H3("A.", "Datasets"),
    P("We annotated a development set of synthetic meetings (product planning, database performance, Hinglish and "
      "Telugu–English discussions) and a held-out design-review meeting annotated before the first evaluation. A further "
      "32 sentences were labelled with dialogue acts, and a 29.3 s three-voice text-to-speech meeting was used for speech."),
    H3("B.", "Benchmark Design and What Was Realised"),
    P("The rules were written against the development set, so its rule scores are optimistic. The held-out set contains "
      "4 answerable and 2 unanswerable questions; the development set contains 12 and 5. We did not evaluate on AMI or QMSum. "
      "Two changes were made after seeing held-out failures, so that set is only partly unbiased."),

    H2("IX.", "Experimental Design"),
    H3("A.", "Metrics"),
    P("Metrics are ROUGE-1/2/L F1 [27], precision, recall and F1 with fuzzy matching, QA accuracy and abstention, WER, speaker "
      "accuracy and round-trip chrF [28]."),
    H3("B.", "Statistics"),
    P("Samples are small, so we report raw counts and do not claim statistical significance."),
    H3("C.", "Protocol"),
    P("Every text component was run with rules only and with the Hugging Face models on an Apple M2 laptop (generation on the "
      "MPS GPU, other models on CPU). Speech results use Whisper base, the model in use when they were measured; the "
      "system now defaults to Whisper small, and those figures have not been re-measured."),

    H2("X.", "Results"),
    H3("A.", "RQ1 and RQ3: Extraction and Question Answering"), results[0], results[1],
    H3("B.", "RQ2: Summary Quality"), results[2], results[3],
    H3("C.", "RQ4: Model Selection"), results[4], results[5],
    H3("D.", "RQ5: Shared Rooms in a Live Trial"), live,
    H3("E.", "RQ6: Multilingual Speech"),
    P("We ran an informal check with text-to-speech voices, using four sentences per language in live-style 15 s chunks. "
      "English output was nearly exact. Telugu translations kept the meaning well, for example \"Ravi will be working on the "
      "database.\" Hindi and Tamil kept their original script beside the English, with some word errors; one Tamil sentence "
      "rendered evening as morning. Kannada was weakest, with loose translations and some utterances labelled as English. "
      "Chunks took about 9 s on average and 13.6 s at worst, which keeps up with live audio. No accuracy is claimed from this check."),

    H2("XI.", "Discussion"),
    P("Models did not win everywhere. They improved summaries and explanations, but rules were better for dialogue acts, "
      "because zero-shot NLI could not separate deciding from suggesting. Choosing per task from measurement was more "
      "useful than applying a neural model throughout. Abstention held on every unanswerable question in these sets, "
      "which supports treating refusal as a core feature. Most serious faults appeared only in live calls, not in simulation, "
      "so live testing was essential for a browser-based system."),
    Table("VII", "Research questions: findings and status", ["RQ", "Finding", "Status"], [
        ["RQ1", "Rules 0.938 vs NLI 0.594; held-out action-item F1 1.0, decisions 0.80, proposal recall 0.33", "Supported on small sets"],
        ["RQ2", "ROUGE-1 0.36 to 0.55 held-out; sentences evidence-supported", "Supported on small sets"],
        ["RQ3", "16/16 answerable; 7/7 abstained", "Supported on small sets"],
        ["RQ4", "Qwen 1.5B 8 of 9 correct; laptop latency acceptable", "Partly; human-rated, small sample"],
        ["RQ5", "Two-laptop trial worked after seven fixes", "Shown in live trials"],
        ["RQ6", "Four languages usable; Kannada weak", "Informal; live test pending"],
    ], [1.0, 5.0, 2.5], 8),

    H2("XII.", "Threats to Validity and Ethics"),
    Bullets([
        "**Synthetic data.** The evaluation sets are small and synthetic, so the numbers are a sanity check rather than evidence "
        "of performance on long, noisy, real meetings.",
        "**Rule development.** Rules were developed on the development set, and the held-out set was consulted for two fixes.",
        "**Speech tests.** Text-to-speech audio is cleaner than real meetings, and the WER was measured on Whisper base.",
        "**Languages.** Kannada speech is the weakest, Telugu and Kannada are shown in English only, and the multilingual check is informal.",
        "**Capture limits.** Without captions, the capturing user's own voice is not recorded. Caption reading depends on each "
        "platform's page structure, and the Zoom and Teams web adapters were not tested live. Speech that no participant captured cannot be recovered.",
        "**Ethics.** Recording requires the consent of all participants. MeetBrief shows a capture indicator, never names generic "
        "speakers, keeps data local, and supports deletion and private mode.",
    ]),

    H2("XIII.", "Contributions"),
    Bullets([
        "A hybrid pipeline that takes structured facts from transparent rules and fluent text from evidence-aligned open models [5], [12], [16].",
        "Grounded question answering that abstains when the meeting lacks the answer [17], [18].",
        "A shared-room protocol with one elected capturer, automatic handover and per-member catch-up.",
        "A hybrid capture and speech-translation path for English, Telugu, Kannada, Hindi and Tamil meetings [24], [25].",
        "A component-wise comparison of rules and models, with faults found in live trials reported.",
    ], True),

    H2("XIV.", "Scope and Conclusion"),
    P("The work covers online meetings captured through a browser, with Google Meet tested live, and runs on a single laptop "
      "with members on the same network."),
    *section("Conclusion"),
]
