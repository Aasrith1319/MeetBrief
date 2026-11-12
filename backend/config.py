"""Runtime configuration for the MeetBrief AI backend.

All settings come from environment variables so that no credentials ever live
in source code (or in the Chrome extension).
"""
from __future__ import annotations

import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent


def _env_bool(name: str, default: bool) -> bool:
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass
class Settings:
    data_dir: Path = field(default_factory=lambda: Path(os.environ.get("MEETBRIEF_DATA_DIR", ROOT_DIR / "data")))
    host: str = os.environ.get("MEETBRIEF_HOST", "127.0.0.1")
    port: int = int(os.environ.get("MEETBRIEF_PORT", "8000"))
    # Hugging Face model choices live in backend/hf/models.py (all run locally).
    # "small" is the smallest Whisper that handles Indian languages acceptably (base garbles Telugu/Kannada)
    whisper_model: str = os.environ.get("MEETBRIEF_WHISPER_MODEL", "small")
    # Languages expected in meetings: speech is only ever labelled as one of these ("all" = any Whisper language)
    meeting_languages: tuple = tuple(x.strip() for x in os.environ.get("MEETBRIEF_LANGUAGES", "en,te,kn,hi,ta").split(",")
                                     if x.strip() and x.strip() != "all")
    # cosine similarity above which two voice segments are treated as the same speaker
    speaker_threshold: float = float(os.environ.get("MEETBRIEF_SPEAKER_THRESHOLD", "0.86"))
    auth_enabled: bool = _env_bool("MEETBRIEF_AUTH", True)
    # Shared rooms: Google OAuth client id (type "Chrome extension") used to verify members' sign-in tokens
    google_client_id: str = os.environ.get("MEETBRIEF_GOOGLE_CLIENT_ID", "")
    # Test-only identities ("Name <email>" header) for trying rooms on one machine without Google sign-in
    rooms_dev_auth: bool = _env_bool("MEETBRIEF_ROOMS_DEV_AUTH", False)
    room_capturer_timeout: float = float(os.environ.get("MEETBRIEF_CAPTURER_TIMEOUT", "25"))
    default_retention_days: int = int(os.environ.get("MEETBRIEF_RETENTION_DAYS", "30"))
    max_upload_bytes: int = int(os.environ.get("MEETBRIEF_MAX_UPLOAD_BYTES", str(5 * 1024 * 1024)))
    max_audio_bytes: int = int(os.environ.get("MEETBRIEF_MAX_AUDIO_BYTES", str(25 * 1024 * 1024)))
    max_recording_bytes: int = int(os.environ.get("MEETBRIEF_MAX_RECORDING_BYTES", str(1024 * 1024 * 1024)))

    @property
    def db_path(self) -> Path:
        return self.data_dir / "meetbrief.sqlite3"

    @property
    def token_path(self) -> Path:
        return self.data_dir / "api_token.txt"

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)

    def api_token(self) -> str:
        """Return the local API token, creating one on first run.

        The token can be pinned with MEETBRIEF_API_TOKEN; otherwise a random
        token is stored with owner-only permissions in the data directory.
        """
        pinned = os.environ.get("MEETBRIEF_API_TOKEN")
        if pinned:
            return pinned
        self.ensure_dirs()
        if self.token_path.exists():
            return self.token_path.read_text().strip()
        token = secrets.token_urlsafe(24)
        old_umask = os.umask(0o077)
        try:
            self.token_path.write_text(token)
        finally:
            os.umask(old_umask)
        return token


settings = Settings()
