import json
from pathlib import Path

from .models import ProjectState
from .persistence import atomic_write_json


class StateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "state.json"

    def load(self) -> ProjectState:
        with self.path.open(encoding="utf-8") as handle:
            return ProjectState.from_dict(json.load(handle))

    def save(self, state: ProjectState) -> None:
        atomic_write_json(self.path, state.to_dict(), prefix="state-")
