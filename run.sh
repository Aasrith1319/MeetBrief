#!/usr/bin/env bash
# Set up (first run) and start the MeetBrief AI backend. Everything runs locally.
#   MEETBRIEF_ML=0     skip the Hugging Face model stack (rule-based NLP only)
#   MEETBRIEF_AUDIO=0  skip Whisper (no tab-audio transcription)
set -euo pipefail
cd "$(dirname "$0")"
if [ ! -d .venv ]; then
  python3 -m venv .venv
  .venv/bin/pip install -q --upgrade pip
  .venv/bin/pip install -q -r requirements.txt
  if [ "${MEETBRIEF_ML:-1}" = "1" ]; then .venv/bin/pip install -q -r requirements-ml.txt || echo "ML deps failed; running rule-based NLP only"; fi
  if [ "${MEETBRIEF_AUDIO:-1}" = "1" ]; then .venv/bin/pip install -q -r requirements-audio.txt || echo "Audio deps failed; tab-audio transcription disabled"; fi
  echo "Tip: download all models now for offline use:  .venv/bin/python -m backend.hf.download"
fi
exec .venv/bin/python -m backend.main
