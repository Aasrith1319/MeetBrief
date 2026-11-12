# MeetBrief AI — measured evaluation results

All numbers below were produced by `python -m backend.evaluation.run_eval` on this machine (device: cpu). Datasets are small and synthetic, so treat them as a sanity check and a rules-vs-models comparison, not as general accuracy claims.

## Development set

Rules were developed against this set, so its rule-based scores are optimistic.

| Metric | Rules only | With Hugging Face models |
|---|---|---|
| Decisions P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Decision revisions detected | 1/1 | 1/1 |
| Proposals P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Action items P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Task owner accuracy | 1.0 | 1.0 |
| Task deadline accuracy | 1.0 | 1.0 |
| Unresolved questions P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Q&A answerable correct | 12/12 | 12/12 |
| Q&A unanswerable → abstained | 5/5 | 5/5 |
| Overview ROUGE-1 / 2 / L | 0.449 / 0.327 / 0.425 (TextRank) | 0.555 / 0.336 / 0.405 (abstractive) |
| Full catch-up ROUGE-1 / L | 0.382 / 0.314 | 0.348 / 0.275 |
| Abstractive sentences evidence-supported | – | 12/12 |
| Latency analyze / summary / QA (ms) | 248.4 / 0.7 / 3.5 | 1312.9 / 5477.7 / 111.7 |

With the optional NLI second opinion (`MEETBRIEF_DIALOGUE_ACTS=hybrid`): decisions 1.0 / 1.0 / 1.0, analyze latency 4275.3 ms.

<details><summary>Q&A log (models)</summary>

| Question | Expected | Correct | Engine |
|---|---|---|---|
| Why did the team choose indexing first? | ABSTAIN | ✅ | retrieval + rules |
| Who will complete the indexing changes? | ['Priya'] | ✅ | retrieval + rules |
| When are the indexing changes due? | ['Friday'] | ✅ | retrieval + rules |
| What did Arjun suggest? | ['caching'] | ✅ | retrieval + rules |
| What is the marketing budget? | ABSTAIN | ✅ | retrieval + rules |
| Why did we go with lazy loading first? | ['smallest change'] | ✅ | retrieval + rules |
| When is the 2.4 release now? | ['Tuesday'] | ✅ | deepset/roberta-base-squad2 |
| Who will write the rollback plan? | ['Sana'] | ✅ | retrieval + rules |
| Who is going to update the release notes? | ['no owner', 'unknown', 'not explicitly stated'] | ✅ | retrieval + rules |
| What is the Android crash rate? | ['3 percent'] | ✅ | deepset/roberta-base-squad2 |
| How long will the migration downtime be? | ['20 minutes'] | ✅ | retrieval + rules |
| Which payment providers are used most often? | ABSTAIN | ✅ | retrieval + rules |
| What color will the new checkout button be? | ABSTAIN | ✅ | retrieval + rules |
| Who will draft the email copy? | ['Speaker 2'] | ✅ | retrieval + rules |
| What tool will send the emails? | ABSTAIN | ✅ | retrieval + rules |
| Who will deploy the fix? | ['Rohit'] | ✅ | retrieval + rules |
| What is the token expiry going to be? | ['24 hours'] | ✅ | deepset/roberta-base-squad2 |

</details>

## Held-out set

Annotated before the first evaluation run. Disclosure: two changes were made after looking at failures on this set — (1) a Q&A bug where a reply marked *possibly answers* was reported as "no answer" (fixed; held-out Q&A went 3/4 → 4/4), and (2) removing NLI-added decisions, which lowered decision precision here (0.67 → 0.50). A third change — merging vague confirmations such as "I can do that" into the task they refer to, found on the audio test transcript — also removed one false-positive task here (action-item F1 0.86 → 1.0). Treat this set as only partly unbiased.

| Metric | Rules only | With Hugging Face models |
|---|---|---|
| Decisions P / R / F1 | 0.667 / 1.0 / 0.8 | 0.667 / 1.0 / 0.8 |
| Decision revisions detected | 0/0 | 0/0 |
| Proposals P / R / F1 | 1.0 / 0.333 / 0.5 | 1.0 / 0.333 / 0.5 |
| Action items P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Task owner accuracy | 1.0 | 1.0 |
| Task deadline accuracy | 1.0 | 1.0 |
| Unresolved questions P / R / F1 | 1.0 / 1.0 / 1.0 | 1.0 / 1.0 / 1.0 |
| Q&A answerable correct | 4/4 | 4/4 |
| Q&A unanswerable → abstained | 2/2 | 2/2 |
| Overview ROUGE-1 / 2 / L | 0.357 / 0.116 / 0.242 (TextRank) | 0.55 / 0.367 / 0.43 (abstractive) |
| Full catch-up ROUGE-1 / L | 0.458 / 0.249 | 0.408 / 0.247 |
| Abstractive sentences evidence-supported | – | 4/4 |
| Latency analyze / summary / QA (ms) | 27.0 / 0.9 / 4.2 | 1071.0 / 5798.4 / 54.1 |

With the optional NLI second opinion (`MEETBRIEF_DIALOGUE_ACTS=hybrid`): decisions 0.667 / 1.0 / 0.8, analyze latency 7391.8 ms.

<details><summary>Q&A log (models)</summary>

| Question | Expected | Correct | Engine |
|---|---|---|---|
| Why did we pick the message queue? | ['retries'] | ✅ | retrieval + rules |
| Which queue will we use? | ['SQS'] | ✅ | retrieval + rules |
| Who is writing the design doc? | ['Rajesh'] | ✅ | deepset/roberta-base-squad2 |
| What is the target latency for push notifications? | ['two seconds'] | ✅ | retrieval + rules |
| Do we have budget for the CMS licence upgrade? | ABSTAIN | ✅ | retrieval + rules |
| Which mobile platforms support rich notifications? | ABSTAIN | ✅ | retrieval + rules |

</details>

## Dialogue-act classification (decision / proposal / task / question / other)

32 hand-labelled sentences. Rules accuracy **0.938**; zero-shot NLI (`MoritzLaurer/mDeBERTa-v3-base-mnli-xnli`) accuracy **0.594**.

| Act | Rules recall | NLI recall |
|---|---|---|
| decision | 8/8 | 0/8 |
| proposal | 4/6 | 5/6 |
| task | 6/6 | 2/6 |
| question | 5/5 | 5/5 |
| other | 7/7 | 7/7 |

Zero-shot NLI cannot reliably tell *deciding* from *suggesting*, so it is used only to raise the confidence of rule-extracted items, not to replace the rules.

## Speech (synthetic 3-voice meeting, macOS TTS)

* ASR (faster-whisper `base`): **WER 0.0** on 29.3 s of audio (1.6 s to transcribe).
* Diarization (WavLM x-vectors + online clustering): **speaker accuracy 1.0**, 3 speakers found vs 3 true (1.2 s).
* TTS voices are far cleaner than real meetings; expect higher WER/DER on real audio.

## Translation (NLLB-200, proxy metrics)

| Language | Round-trip chrF | Numbers preserved | s/sentence |
|---|---|---|---|
| hi | 0.835 | 6/6 | 1.22 |
| te | 0.827 | 6/6 | 0.88 |

Round-trip chrF only checks that meaning survives en→X→en; it is not a substitute for human review of Hindi/Telugu fluency.

