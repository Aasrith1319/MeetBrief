# User guide

## 1. Install and connect
1. Run `./run.sh` in the project folder and copy the **API token** it prints (also in `data/api_token.txt`).
   Optionally pre-download all Hugging Face models for offline use: `.venv/bin/python -m backend.hf.download`.
2. In Chrome open `chrome://extensions`, enable Developer mode, click **Load unpacked**, select `chrome-extension/`.
3. Click the MeetBrief icon → side panel → **Settings** → enter `http://127.0.0.1:8000` and the token → **Save & test**.

Prefer no extension? Open `http://127.0.0.1:8000/app/` for the same UI in transcript-upload mode.

## 2. Get a transcript in
* **Upload:** *Upload* button → `.txt` (`10:00 — Name: text` or `[00:01:23] Name: text`), `.vtt`, `.srt` or `.json`.
* **Live captions (Google Meet):** turn on captions in Meet, then **Start captions** — or enable *Automatic meeting
  mode* in Settings so capture starts when you join and a final summary is built when you leave.
* **Meeting recording / Meet transcript doc (if you joined late):** *Upload* accepts recordings (.mp4, .m4a, .mp3,
  .wav, .webm, …) and .docx transcripts; recordings are transcribed in the background (a spinner shows progress).
* **Tab audio:** **Tab audio** captures only the current tab's sound (requires `requirements-audio.txt`).
* Tick **Private mode** first if nothing should be written to disk.

## 3. Use the tabs
* **Catch Me Up** – choose a summary type and language. *Since N min ago* recaps only recent discussion; *Live update*
  refreshes every 15 s. Click the suggested questions to ask them.
* **Explain Again** – paste/select text (or right-click selected text on any page → *Explain with MeetBrief*), choose a
  style, level and language. *Explain another way* gives a different attempt.
* **Ask AI** – ask in natural language; click the `S12` chips to see the source line. A yellow *insufficient evidence*
  tag means the transcript doesn't contain the answer.
* **Who Said What?** – contributions per speaker. For generic labels (*Speaker 1*), type the real name and click *Map*.
* **Decisions** – confirmed, revised (history kept), proposals, unresolved questions, potential contradictions.
* **Action Items** – tick to complete; correct the owner/deadline if needed (your edits always win).
* **Timeline / Transcript** – chronological events; search by meaning; side-by-side translation.
* **Notes** – personal notes (kept separate from AI content), exports, search across meetings.
* **Settings** – languages, defaults, retention days, private-mode default, deletion controls, status.

## 4. Privacy checklist
Tell participants you are using MeetBrief, and only capture meetings you may capture. Captions are read only after you
press Start; tab audio is captured only for the tab you choose; the toolbar shows **REC** while capturing. All
processing (speech recognition, summarization, translation, Q&A) runs on your own machine with downloaded models;
nothing is sent to an external AI service.

## 5. Reading model output
* **⚠ weak evidence / not found in transcript** after an Overview sentence means the abstractive model wrote something
  MeetBrief could not match to the transcript — check the cited line or ignore it.
* Explanations marked *generated … general knowledge* come from a small local language model (Qwen2.5-1.5B-Instruct), not from the meeting.
