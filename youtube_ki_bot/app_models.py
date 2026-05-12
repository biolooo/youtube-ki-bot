from dataclasses import asdict, dataclass, field
from typing import Optional


@dataclass(frozen=True)
class GenerationRequest:
    topic: str
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    goal: Optional[str] = None
    tone: Optional[str] = None
    target_length_seconds: Optional[int] = None
    constraints: Optional[str] = None
    freeform_brief: Optional[str] = None
    top_k: int = 5

    def to_prompt_brief(self) -> str:
        parts = [f"Thema: {self.topic}"]
        if self.goal:
            parts.append(f"Ziel: {self.goal}")
        if self.tone:
            parts.append(f"Ton: {self.tone}")
        if self.target_length_seconds:
            parts.append(f"Ziellaenge: {self.target_length_seconds} Sekunden")
        if self.constraints:
            parts.append(f"Vorgaben: {self.constraints}")
        if self.freeform_brief:
            parts.append(f"Freitext: {self.freeform_brief}")
        return "\n".join(parts)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class RetrievalRequest:
    query_text: str = ""
    platform: Optional[str] = None
    format_label: Optional[str] = None
    hook_label: Optional[str] = None
    top_k: int = 5

    @classmethod
    def from_generation_request(cls, request: GenerationRequest) -> "RetrievalRequest":
        return cls(
            query_text=request.to_prompt_brief(),
            platform=request.platform,
            format_label=request.format_label,
            hook_label=request.hook_label,
            top_k=request.top_k,
        )

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class GeneratedScriptPayload:
    title_ideas: list = field(default_factory=list)
    hook: str = ""
    script: str = ""
    cta: str = ""
    why_this_should_work: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)
