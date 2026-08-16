"""Answer-quality presets for the minimal AI analysis vertical slice."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import Literal


class AnswerPresetId(StrEnum):
    """Stable preset identifiers accepted by the public API."""

    STANDARD = "STANDARD"


@dataclass(frozen=True, slots=True)
class AnswerPreset:
    """OpenAI reasoning and text settings for one answer-quality preset."""

    preset_id: AnswerPresetId
    reasoning_effort: Literal["medium"]
    reasoning_mode: None
    text_verbosity: Literal["medium"]


STANDARD_PRESET = AnswerPreset(
    preset_id=AnswerPresetId.STANDARD,
    reasoning_effort="medium",
    reasoning_mode=None,
    text_verbosity="medium",
)


def get_answer_preset(preset_id: AnswerPresetId) -> AnswerPreset:
    """Resolve a supported answer preset without changing the model."""

    if preset_id is AnswerPresetId.STANDARD:
        return STANDARD_PRESET
    raise ValueError(f"Unsupported answer preset: {preset_id}")

