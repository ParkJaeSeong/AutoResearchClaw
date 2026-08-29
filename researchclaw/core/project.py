"""Durable local research-project lifecycle."""

from __future__ import annotations

from dataclasses import dataclass, replace
from pathlib import Path
from typing import TYPE_CHECKING
from uuid import uuid4

from .models import ProjectState, StageStatus, StageTenSnapshot
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
        store = StateStore(state_path.parent)
        state = store.load()
        if (
            state.stage_10_snapshot.status == "legacy_missing"
            and state.current_stage < 10
        ):
            state = replace(
                state,
                stage_10_snapshot=StageTenSnapshot("not_prepared", ()),
            )
            store.save(state)
        if state.current_stage == 6 and 5 in state.completed_stages:
            from .approval import approval_matches_state, load_approval_record
            from .contracts import FOUNDATION_STAGE_IDS, LITERATURE_APPROVAL_STAGE, get_contract
            from .knowledge_extraction import KnowledgeIssue, validate_extraction_shortlist
            from .paths import resolve_project_artifact

            record = load_approval_record(root, LITERATURE_APPROVAL_STAGE)
            approval_is_current = (
                all(stage_id in state.completed_stages for stage_id in FOUNDATION_STAGE_IDS)
                and record is not None
                and record.decision == "approve"
                and approval_matches_state(root, state, record)
            )
            prerequisite_issues: tuple[KnowledgeIssue, ...] = ()
            if approval_is_current:
                (shortlist_relative_path,) = get_contract(LITERATURE_APPROVAL_STAGE).required_outputs
                try:
                    shortlist_path = resolve_project_artifact(root, shortlist_relative_path)
                    shortlist_text = shortlist_path.read_text(encoding="utf-8")
                except (OSError, UnicodeError, ValueError) as error:
                    prerequisite_issues = (
                        KnowledgeIssue(
                            "invalid_format",
                            shortlist_relative_path,
                            f"approved shortlist cannot be read: {error}",
                        ),
                    )
                else:
                    prerequisite_issues = validate_extraction_shortlist(shortlist_text)

            if prerequisite_issues:
                relevant_hashes = {
                    path: artifact.sha256
                    for path, artifact in state.artifacts.items()
                    if path in get_contract(LITERATURE_APPROVAL_STAGE).required_outputs
                }
                state = replace(
                    state,
                    current_stage=LITERATURE_APPROVAL_STAGE,
                    status=StageStatus.NEEDS_REVISION,
                    completed_stages=tuple(
                        stage_id
                        for stage_id in state.completed_stages
                        if stage_id < LITERATURE_APPROVAL_STAGE
                    ),
                    next_action="validate_stage",
                    last_error={
                        "error_class": StageStatus.NEEDS_REVISION.value,
                        "stage_id": LITERATURE_APPROVAL_STAGE,
                        "attempt_number": state.retry_counts.get(
                            str(LITERATURE_APPROVAL_STAGE),
                            0,
                        )
                        + 1,
                        "issues": [
                            {
                                "code": issue.code,
                                "path": issue.path,
                                "message": issue.message,
                            }
                            for issue in prerequisite_issues
                        ],
                        "artifact_hashes": relevant_hashes,
                        "recommended_action": "revalidate_stage_and_request_new_approval",
                        "retry_state": "approval_invalidated",
                    },
                )
                store.save(state)
            elif approval_is_current and state.next_action == "report_foundation_milestone_only":
                state = replace(state, next_action="prepare_stage")
                store.save(state)
        if (
            state.current_stage == 8
            and 7 in state.completed_stages
            and state.next_action == "report_synthesis_milestone_only"
        ):
            state = replace(state, next_action="prepare_stage")
            store.save(state)
        if (
            state.current_stage == 9
            and 8 in state.completed_stages
            and state.next_action == "report_hypothesis_milestone_only"
        ):
            state = replace(state, next_action="prepare_stage")
            store.save(state)
        if (
            state.current_stage == 10
            and 9 in state.completed_stages
            and state.next_action == "report_validation_design_milestone_only"
        ):
            state = replace(state, next_action="prepare_stage")
            store.save(state)
        return cls(root=root, state=state)

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
