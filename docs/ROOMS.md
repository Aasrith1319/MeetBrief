# Shared rooms, late joiners and other meeting sources

This document covers everything MeetBrief does so that **someone who joins late (or never had captions) still gets the
whole meeting**. The capture paths, from most to least preferred:

| Situation | What covers it |
|---|---|
| At least one participant has MeetBrief | **Shared room**: one member captures, everyone (including late joiners) gets the live recap |
| You must not be late | **Early Join**: MeetBrief opens and joins the meeting one minute early (mic and camera off) |
| The host recorded, or turned on transcripts | **Official transcript import** (Google Meet, Zoom, Teams), or upload the recording or transcript file |
| Meeting runs in a desktop app or on the phone | **Desktop recorder** (`tools/desktop_recorder.py`) |
| Nobody captured anything | Not recoverable. No tool can reconstruct speech that was never captured |

---

## 1. Shared rooms

### How it works

1. Priya joins a meeting with the extension. MeetBrief reads the meeting key from the link
   (`google_meet:abc-defg-hij`, `zoom_web:<meeting id>`, `teams_web:<thread id>`) and asks the server whether a room
   exists for it.
2. If none exists, Priya gets a notification: **"Share this meeting with MeetBrief?"** → *Share* / *Not now*.
   With *Settings → Account → "Share every meeting I join as a room without asking"* on, MeetBrief shares without asking.
3. *Share* creates the room, and Priya becomes the **capturer**: her tab sends captions (or tab audio) into the room.
4. Rahul joins 10 minutes later with the extension. His extension finds the same meeting key, joins the room
   automatically and shows **"You joined late — here's what you missed"**. The side panel's room banner has
   *What you missed* (a personalised catch-up of everything before *his* join time) and then the same live recap,
   decisions and tasks as everyone else. His tab stays on **standby** (badge `ROOM`) so nothing is captured twice.
5. **Handover:** each member's extension sends a heartbeat every 10 s. If the capturer leaves, closes the tab, or misses
   heartbeats for 25 s, the next member in the call becomes the capturer automatically. A member whose captions are
   on is preferred over a capturer that reports captions are off.
6. When the **last member leaves**, the room ends and everyone gets the final summary ("Meeting ended — summary ready").

### Access rules (enforced by the server)

* Every caller must be signed in: a Google account verified by the server, or a dev identity in test mode.
* The extension must report being **in the call**. Knowing the link alone is not enough to join.
* Optional, chosen by the sharer: **same email domain** only (e.g. `@college.edu`) and/or **approval** by the sharer.
* Members can read the room's meeting (summary, Ask AI, decisions, tasks, transcript, export) but cannot delete it,
  change it, or push segments unless they are the current capturer. Personal notes are private to each member.
* A member can only see meetings of rooms they belong to (other ids return 404).

### Running a shared server

Everyone in a room must use **the same backend**. For a class demo:

* **Same Wi-Fi:** on the host laptop run `MEETBRIEF_HOST=0.0.0.0 ./run.sh`, then everyone sets
  *Settings → Backend URL* to `http://<laptop-ip>:8000`. Plain HTTP on a shared network is fine for a demo only.
* **Real use:** deploy the backend behind HTTPS (any VM or PaaS with a reverse proxy such as Caddy or nginx) and point
  the extensions at `https://your-host`.

### Google sign-in setup (one time, free)

1. Open <https://console.cloud.google.com/>, then create a project (e.g. "MeetBrief").
2. **APIs & Services → OAuth consent screen:** choose *External* and fill in the app name and your email. Then pick
   who may sign in:
   * **Anyone with a Google account (recommended, you don't need to know the members):** click **Publish app**
     (status *In production*). Sign-in only asks for `openid`, `email` and `profile`, which are non-sensitive scopes,
     so Google does not require app verification for this.
   * **Only people you list:** leave the status on **Testing** and add their Google accounts under *Test users*
     (up to 100). Anyone else gets "access blocked". Useful for a closed demo group.

   The optional Google Meet transcript import (§3) asks for an extra, sensitive scope. An unverified published app
   still works for it: people see a "Google hasn't verified this app" screen and can click *Advanced → Continue*.
3. **APIs & Services → Credentials → Create credentials → OAuth client ID:**
   * Application type: **Web application**
   * Authorized redirect URI: the value shown in the extension under *Settings → Account* ("Google OAuth redirect URI for this extension"). It looks like
     `https://<extension-id>.chromiumapp.org/`. The ID changes if the unpacked extension is loaded from another
     folder or machine, so add one URI per ID.
4. Copy the **Client ID**. You do **not** need the client secret: the extension uses the implicit flow, and the server
   only checks that tokens were issued for this client ID.
5. Start the server with it:
   ```bash
   MEETBRIEF_GOOGLE_CLIENT_ID=1234-abc.apps.googleusercontent.com ./run.sh
   ```
6. In the extension, open *Settings → Account → Sign in with Google*.
7. *(Optional, for the Google Meet import in §3)* enable the **Google Meet REST API** in the same project and add the
   scope `https://www.googleapis.com/auth/meetings.space.readonly` to the consent screen.

The server verifies every Google token with Google's tokeninfo endpoint (audience must equal your client ID, email
must be verified) and caches the result for 5 minutes. Tokens stay in the extension's session storage and are never
written to disk.

### Testing without Google (dev identities)

```bash
MEETBRIEF_ROOMS_DEV_AUTH=1 ./run.sh
```

Then set a name and email under *Settings → Account* (test-mode name + email → *Use this identity*) in each Chrome profile. The server trusts
the `X-MeetBrief-Dev-User` header, so **never enable this on a server other people can reach**. The automated
harness `chrome-extension/dev/rooms_harness.html` drives two simulated members (Priya on time, Rahul late) through
share, late-join catch-up, duplicate refusal, handover and room end against such a server.

---

## 2. Early Join

*Schedule* tab → paste a Google Meet, Zoom or Teams link, add a title and the start time, then **Add**.

* One minute before the start, MeetBrief opens the meeting in a new tab. Zoom links are converted to the browser client
  (`https://app.zoom.us/wc/join/<id>`). MeetBrief then turns the **microphone and camera off** and presses **Join**.
  If the host has a waiting room, you are admitted like anyone else.
* Once in the call, the usual automatic mode takes over. With *"Share it as a MeetBrief room"* ticked on the schedule entry,
  the room is shared without a prompt, so later joiners get everything from the start.
* Chrome must be running and the computer awake. Alarms do not fire while the machine sleeps.
* Joining is done by clicking the platform's own buttons. If a platform changes its pre-join screen, the tab still
  opens and you click *Join* yourself.

---

## 3. Official transcript connectors

*Upload* tab → **Import the official transcript**. Pick the provider and paste the meeting link or ID. The import
replaces the open meeting's transcript (for room members, the room's meeting) and rebuilds every summary with real
speaker names.

| Provider | Host must | Access needed |
|---|---|---|
| Google Meet | turn on *Transcripts* in the call (Workspace editions that include it) | Google sign-in with scope `meetings.space.readonly` (requested when you import) |
| Zoom | use cloud recording with *Create audio transcript* (Pro or higher) | a Zoom OAuth access token with `cloud_recording:read:list_recording_files` |
| Microsoft Teams | turn on transcription (Microsoft 365) | a Microsoft Graph token with `OnlineMeetingTranscript.Read.All` + `OnlineMeetings.Read` (some tenants need admin consent) |

Access tokens are used **once** for the request and never stored. Paste them only into the extension's field, never
into chat or a file. Transcripts are usually available a few minutes after the meeting ends.

If you have the file instead (a recording `.mp4/.m4a/.mp3/.wav/.webm`, or a transcript `.docx/.txt/.vtt/.srt/.json`),
use **Upload**. Recordings are transcribed with Whisper and speaker-separated in the background.

---

## 4. Desktop recorder

For meetings in a desktop app (Zoom, Teams or Webex clients), phone bridges or in-room calls:

```bash
.venv/bin/pip install sounddevice
.venv/bin/python tools/desktop_recorder.py --list-devices
.venv/bin/python tools/desktop_recorder.py --title "Lab sync" --device "BlackHole 2ch"
```

* Pick a **loopback** device to capture what the meeting app plays. On macOS, install BlackHole and create a
  *Multi-Output Device* (speakers + BlackHole) in Audio MIDI Setup. On Windows, use *Stereo Mix* / WASAPI loopback.
  On Linux, use a `.monitor` source. A microphone device works for in-room meetings.
* Audio is sent in 15 s chunks to `/api/meetings/{id}/audio`, transcribed with Whisper, speaker-labelled and deleted.
  Press **Ctrl+C** to stop: the meeting is finalized and the final summary printed. It also appears in the side panel.
* Test mode without a microphone:
  `tools/desktop_recorder.py --title Test --file datasets/evaluation_data/audio/three_speakers.wav`
* Options: `--api` (default `http://127.0.0.1:8000`), `--token` (default: `data/api_token.txt`), `--language`,
  `--chunk`, `--meeting <id>` (append to an existing meeting), `--no-finalize`.
* Known limitation: a sentence spoken across a chunk boundary is split into two segments.

**Record only meetings where every participant has agreed.**

---

## Limits and future work

* The live caption reader is tested against a simulated Google Meet DOM. Meet changes its markup often, so check it
  on a live call (see TESTING_CHECKLIST). Zoom and Teams web adapters are experimental.
* A room needs at least one participant with the extension *in the call* from the start. Otherwise the early part
  is lost unless the host's official transcript or recording is imported.
* Future work: a server-side meeting bot (Google Meet Media API / Zoom Meeting SDK / Teams bots) that joins without
  any participant's browser; Chrome Enterprise force-install for organisations ("mandatory" extension); published
  Zoom/Teams OAuth apps so imports don't need pasted tokens.
