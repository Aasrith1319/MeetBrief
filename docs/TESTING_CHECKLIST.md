# Manual testing checklist (live Chrome)

These steps cover what automated tests cannot: the real extension in Chrome and a live Google Meet call.
Tick each box and note the Chrome version.

## Setup
- [ ] `./run.sh` starts; console shows the API token and "Models: Hugging Face (local …)".
- [ ] `chrome://extensions` → Developer mode → Load unpacked → `chrome-extension/` loads with no errors.
- [ ] Toolbar icon opens the side panel. Settings → URL `http://127.0.0.1:8000` + token → *Save & test* → "Connected ✓".
- [ ] Badge in the panel header shows `HF models 8/8` (after `python -m backend.hf.download`).

## Transcript upload (in the extension)
- [ ] Upload `datasets/sample_transcripts/sprint_planning.txt` → catch-up shows Overview, Decisions, Action items.
- [ ] Ask "When is the 2.4 release now?" → answer mentions next Tuesday and the revision note.
- [ ] Select text on any web page → right-click → *Explain with MeetBrief* → Explain tab fills and explains.
- [ ] Notes → export PDF of `telugu_english.txt` → Telugu text renders with joined vowel signs.

## Live captions — Google Meet (two Google accounts or a friend)
- [ ] Join a Meet; turn on **CC**. In the panel the capture line says "Google Meet detected".
- [ ] *Start captions* → consent prompt (first time) → status "Capturing captions", toolbar badge **REC**.
- [ ] Speak 4–5 sentences incl. "Let's go with option A" and "Priya, please send the report by Friday".
- [ ] Within ~5 s the Transcript tab shows each sentence once (no duplicates from progressive captions), with names.
- [ ] Decisions and Action Items update; *Live update* on Catch Me Up refreshes the recap.
- [ ] *Pause* → speak → nothing is added; *Resume* → new speech appears; *Stop* → badge clears.
- [ ] If captions are off: status changes to "Captions not found" with the CC hint.
- [ ] If Meet's caption DOM changed and nothing is captured: update selectors in
      `chrome-extension/content/platform_adapters/google_meet.js` (open DevTools on the caption box).

## Automatic mode
- [ ] Settings → tick *Start capturing automatically…* → Save.
- [ ] Join a Meet call (captions off). Within ~5 s: captions switch on, REC badge, notification "MeetBrief is capturing".
- [ ] Click the notification → side panel opens on Catch Me Up with *Live update* on.
- [ ] Leave the call → notification "Meeting ended — summary ready"; the panel shows the final recap; badge shows ✓.

## Recording import
- [ ] Upload a Meet recording (.mp4) → spinner → recap with Speaker 1/2… labels after processing.

## Tab audio
- [ ] On a tab playing speech (e.g. a YouTube talk), open the panel from the toolbar icon → *Tab audio*.
- [ ] Audio stays audible; status "Processing tab audio"; every ~15 s new segments appear with Speaker 1/2 labels.
- [ ] Map "Speaker 1" to a name in Who Said What? → labels update everywhere.
- [ ] *Stop* ends capture; `ls /tmp | grep meetbrief_audio` shows no leftover audio files.

## Shared rooms (two Chrome profiles, or a classmate on the same server)
- [ ] Server started with `MEETBRIEF_GOOGLE_CLIENT_ID=…` (or `MEETBRIEF_ROOMS_DEV_AUTH=1` for test identities); both
      extensions point at the same Backend URL; Settings → Account shows each person signed in.
- [ ] Profile A joins a Meet → notification *Share this meeting…* → **Share** → badge REC, room banner "You are capturing".
- [ ] Profile B joins 2+ minutes later → notification "joined late" → badge ROOM → *What you missed* covers the start.
- [ ] B's recap updates live while A talks; B's transcript has no duplicate lines.
- [ ] A leaves → within ~25 s B's badge switches to REC and capturing continues.
- [ ] B leaves (last member) → both get "Meeting ended — summary ready".
- [ ] A third account outside an `allowed_domain` room is refused.

## Early Join
- [ ] Schedule tab → add a Meet link starting in 2 minutes → one minute before, a tab opens, mic and camera turn off, Join is pressed.
- [ ] Same with a Zoom link (opens `app.zoom.us/wc/join/…`) and a Teams link.

## Official transcript import / desktop recorder
- [ ] Meet with Transcripts on → after the call, Upload → Import the official transcript → Google Meet → real names appear.
- [ ] Zoom / Teams import with an access token (token is not kept: reopen the panel and the field is empty).
- [ ] `tools/desktop_recorder.py --list-devices`, then record a desktop Zoom call via BlackHole → Ctrl+C prints the summary.

## Privacy
- [ ] Private-mode meeting disappears after restarting the backend; nothing in `data/meetbrief.sqlite3`.
- [ ] Settings → Delete all data removes every meeting.
