"""Durable local research-project lifecycle."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from .models import ProjectState
from .profiles import load_profile
from .state import StateStore


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
