from __future__ import annotations

from pydantic import BaseModel, Field


class SkillStep(BaseModel):
    capability: str
    parameters_template: dict = Field(default_factory=dict)
    expected_result: str


class SkillDefinition(BaseModel):
    name: str
    description: str
    version: int = 1
    inputs: dict[str, str] = Field(default_factory=dict)
    steps: list[SkillStep]
    success_count: int = 0
    source: str = "manual"


class SkillRegistry:
    def __init__(self) -> None:
        self._skills: dict[str, SkillDefinition] = {}

    def upsert(self, skill: SkillDefinition) -> None:
        current = self._skills.get(skill.name)
        if current and skill.version < current.version:
            raise ValueError("cannot replace a skill with an older version")
        self._skills[skill.name] = skill

    def get(self, name: str) -> SkillDefinition:
        return self._skills[name]

    def list(self) -> list[SkillDefinition]:
        return sorted(self._skills.values(), key=lambda s: s.name)
