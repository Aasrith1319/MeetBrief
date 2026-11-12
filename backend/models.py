"""Core data models (spec section 7) and API request/response schemas."""
from __future__ import annotations

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

SourceType = Literal["caption", "transcript", "audio", "upload"]
SummaryMode = Literal["quick", "detailed", "chronological", "topic", "personalized", "catchup"]
ExplainStyle = Literal["simplify", "example", "step_by_step", "detailed", "analogy"]
Difficulty = Literal["beginner", "intermediate", "advanced", "expert"]


class Segment(BaseModel):
    """7.1 Transcript segment."""

    meeting_id: str = ""
    segment_id: str = ""
    idx: int = 0
    start_time: Optional[float] = None  # seconds from meeting start
    end_time: Optional[float] = None
    text: str
    # English version of a non-English line (Whisper speech translation); summaries, Q&A and memory read this
    text_en: Optional[str] = None
    # set when `text` was swapped for text_en for analysis (service.load): the words as spoken, for display
    original_text: Optional[str] = None
    language: Optional[str] = None
    language_confidence: Optional[float] = None
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None  # only when reliably supplied or mapped
    source_type: str = "transcript"
    confidence: Optional[float] = None
    flags: list[str] = Field(default_factory=list)

    @property
    def speaker_label(self) -> str:
        return self.speaker_name or self.speaker_id or "Unknown speaker"


class Evidence(BaseModel):
    segment_id: str
    start_time: Optional[float] = None
    speaker: Optional[str] = None
    text: str = ""
    score: Optional[float] = None


class Decision(BaseModel):
    """7.2 Decision record."""

    decision_id: str
    summary: str
    status: Literal["proposed", "confirmed", "superseded", "uncertain"]
    speaker: Optional[str] = None
    timestamp: Optional[float] = None
    evidence_segments: list[str] = Field(default_factory=list)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    confidence: float = 0.5
    topic: Optional[str] = None
    source: str = "rules"  # rules | rules+model | model (zero-shot NLI, needs verification)


class ActionItem(BaseModel):
    """7.3 Action item."""

    task_id: str
    task_text: str
    owner: str = "unknown"
    owner_source: Literal["explicit", "speaker_self", "user", "unknown"] = "unknown"
    deadline: str = "unspecified"
    status: Literal["open", "completed", "uncertain"] = "open"
    evidence_segments: list[str] = Field(default_factory=list)
    timestamp: Optional[float] = None
    assigned_by: Optional[str] = None
    confidence: float = 0.5
    flags: list[str] = Field(default_factory=list)


class OpenQuestion(BaseModel):
    question_id: str
    text: str
    asked_by: Optional[str] = None
    timestamp: Optional[float] = None
    status: Literal["unresolved", "answered", "uncertain"] = "unresolved"
    evidence_segments: list[str] = Field(default_factory=list)
    answer_segments: list[str] = Field(default_factory=list)


class Topic(BaseModel):
    topic_id: str
    label: str
    keywords: list[str] = Field(default_factory=list)
    start_idx: int
    end_idx: int
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    summary: str = ""
    segment_ids: list[str] = Field(default_factory=list)


class Contradiction(BaseModel):
    kind: Literal["potential_contradiction", "decision_change"]
    description: str
    evidence_segments: list[str]


class MeetingMemory(BaseModel):
    """7.4 Meeting memory: structured, evolving representation of the meeting."""

    meeting_id: str
    segment_count: int = 0
    participants: list[str] = Field(default_factory=list)
    languages: dict[str, int] = Field(default_factory=dict)
    topics: list[Topic] = Field(default_factory=list)
    current_topic: Optional[Topic] = None
    decisions: list[Decision] = Field(default_factory=list)
    action_items: list[ActionItem] = Field(default_factory=list)
    open_questions: list[OpenQuestion] = Field(default_factory=list)
    contradictions: list[Contradiction] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)
    entity_types: dict[str, str] = Field(default_factory=dict)
    terms: list[str] = Field(default_factory=list)
    rolling_summary: str = ""
    suggested_questions: list[str] = Field(default_factory=list)


# ---------------------------------------------------------------- requests
class MeetingCreate(BaseModel):
    title: str = "Untitled meeting"
    platform: str = "upload"
    private: bool = False
    source_type: str = "transcript"
    url: Optional[str] = None


class SegmentIn(BaseModel):
    text: str = Field(max_length=10000)
    text_en: Optional[str] = Field(default=None, max_length=10000)
    start_time: Optional[float] = None
    end_time: Optional[float] = None
    speaker_id: Optional[str] = None
    speaker_name: Optional[str] = None
    language: Optional[str] = None
    source_type: str = "caption"
    confidence: Optional[float] = None


class SegmentsIn(BaseModel):
    segments: list[SegmentIn] = Field(max_length=500)


class TranscriptText(BaseModel):
    text: str
    format: Optional[str] = None  # auto-detected when omitted
    title: Optional[str] = None
    private: bool = False


class SummaryRequest(BaseModel):
    mode: SummaryMode = "quick"
    language: str = "en"
    focus: Optional[Literal["decisions", "tasks", "technical", "general"]] = None
    from_time: Optional[float] = None
    to_time: Optional[float] = None


class ExplainRequest(BaseModel):
    text: str = Field(max_length=4000)
    style: ExplainStyle = "simplify"
    difficulty: Difficulty = "beginner"
    language: str = "en"
    segment_id: Optional[str] = None
    previous_explanation: Optional[str] = None  # "Repeat explanation" / another attempt


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str = Field(max_length=8000)


class AskRequest(BaseModel):
    question: str = Field(max_length=2000)
    language: str = "en"
    history: list[ChatTurn] = Field(default_factory=list, max_length=20)
    speaker: Optional[str] = None
    from_time: Optional[float] = None
    to_time: Optional[float] = None


class TranslateRequest(BaseModel):
    text: str = Field(max_length=20000)
    target_language: str
    source_language: Optional[str] = None


class TaskUpdate(BaseModel):
    status: Optional[Literal["open", "completed", "uncertain"]] = None
    owner: Optional[str] = None
    deadline: Optional[str] = None


class SpeakerMapping(BaseModel):
    speaker_id: str
    speaker_name: str


class NoteIn(BaseModel):
    text: str = Field(max_length=10000)
    segment_id: Optional[str] = None


class PreferencesIn(BaseModel):
    values: dict[str, Any]
