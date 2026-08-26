"""Durable local research-project lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .models import ProjectState
from .profiles import load_profile
from .state import StateStore

if TYPE_CHECKING:
    from .handoff import HandoffSummary


@dataclass(frozen=True)
class ResearchProject:
    root: Path
    state: ProjectState

    @classmethod
    def create(cls, root: Path, topic: str, profile: str) -> "ResearchProject":
        root = Path(root)
        if root.exists() and not root.is_dir():
            raise ValueError(f"project root is not a directory: {root}")
        if root.exists() and any(root.iterdir()):
            raise ValueError(f"project root is non-empty: {root}")

        load_profile(profile)
        root.mkdir(parents=True, exist_ok=True)
        metadata_root = root / ".researchclaw"
        metadata_root.mkdir()
        for directory in ("artifacts", "evaluation", "approvals"):
            (root / directory).mkdir()

        state = ProjectState.new(
            project_id=f"rc-{uuid4().hex[:12]}",
            topic=topic,
            profile=profile,
        )
        StateStore(metadata_root).save(state)
        from .events import EvaluationEvent, event_log_for

        event_log_for(root).append(
            EvaluationEvent.create("project_created", state.project_id, {"topic": topic, "profile": profile})
        )
        return cls(root=root, state=state)

    @classmethod
    def open(cls, root: Path) -> "ResearchProject":
        root = Path(root)
        state_path = root / ".researchclaw" / "state.json"
        if not state_path.is_file():
            raise ValueError(f"project state.json not found: {state_path}")
        return cls(root=root, state=StateStore(state_path.parent).load())

    def status_dict(self) -> dict[str, object]:
        return self.state.to_dict()

    def persist_state(self, state: ProjectState) -> "ResearchProject":
        """Persist a replacement state and return the refreshed project value."""
        StateStore(self.root / ".researchclaw").save(state)
        return type(self)(root=self.root, state=state)

    def build_handoff(self) -> "HandoffSummary":
        """Reconstruct a durable handoff after reopening project files."""
        from .events import EvaluationEvent, event_log_for
        from .handoff import build_handoff

        handoff = build_handoff(self)
        event_log_for(self.root).append(
            EvaluationEvent.create(
                "resume",
                handoff.project_id,
                {
                    "current_stage": handoff.current_stage,
                    "status": handoff.status,
                    "next_action": handoff.next_action,
                },
            )
        )
        return handoff
