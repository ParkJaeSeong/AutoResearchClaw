import json
import tempfile
from pathlib import Path

from .models import ProjectState


class StateStore:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.path = self.root / "state.json"

    def load(self) -> ProjectState:
        with self.path.open(encoding="utf-8") as handle:
            return ProjectState.from_dict(json.load(handle))

    def save(self, state: ProjectState) -> None:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            prefix="state-",
            suffix=".tmp",
            delete=False,
            dir=self.root,
        ) as handle:
            json.dump(state.to_dict(), handle, ensure_ascii=False, sort_keys=True)
            handle.flush()
            temp_path = Path(handle.name)
        temp_path.replace(self.path)
