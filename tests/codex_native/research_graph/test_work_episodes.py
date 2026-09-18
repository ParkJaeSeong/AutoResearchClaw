from concurrent.futures import ThreadPoolExecutor

import pytest

from researchclaw.core.research_graph import commands, store
from researchclaw.core.research_graph.views import build_view


def apply(root, operation, payload, command_id, expected_head=None):
    head = store.read_head(root)
    return commands.apply_command(
        root,
        operation=operation,
        payload=payload,
        expected_head=expected_head or head["id"],
        command_id=command_id,
    )


def start_payload(identity, **changes):
    value = dict(
        id=identity,
        stage="자료 탐색",
        title=f"회차 {identity}",
        purpose="공개 자료를 확인한다",
        depends_on=[],
        return_to=None,
        return_reason=None,
        review_required=False,
    )
    value.update(changes)
    return value


def conclude_payload(identity, **changes):
    value = dict(
        id=identity,
        execution_status="finished",
        judgment="요청한 확인을 마쳤다",
        remaining="추가 검토 없음",
        next_action="결과를 사용한다",
        next_reason="공개 보고가 준비됐다",
    )
    value.update(changes)
    return value


def init(root):
    return commands.init_project(root, topic="Episode test", content_origin="synthetic")


def test_sequences_follow_start_order_and_do_not_change_when_older_episode_finishes(tmp_path):
    init(tmp_path)
    apply(tmp_path, "episode.start", start_payload("search-1"), "start-1")
    second = apply(tmp_path, "episode.start", start_payload("search-2"), "start-2")
    apply(tmp_path, "episode.conclude", conclude_payload("search-1"), "finish-1")

    rows = build_view(tmp_path)["work_episodes"]
    assert [row["sequence"] for row in rows] == [1, 2]
    assert [row["id"] for row in rows] == ["search-1", "search-2"]
    assert rows[0]["execution_status"] == "finished"
    assert rows[1]["execution_status"] == "running"
    historical = build_view(tmp_path, head_id=second["id"])
    assert historical["work_episodes"][0]["execution_status"] == "running"


def test_notes_keep_submission_order_and_view_has_exact_public_contract(tmp_path):
    init(tmp_path)
    apply(tmp_path, "episode.start", start_payload("analysis", review_required=True), "start")
    for index, kind in enumerate(("dialogue", "tool", "output"), 1):
        apply(tmp_path, "episode.note", dict(id="analysis", kind=kind, author="worker", text=f"public {index}"), f"note-{index}")
    apply(tmp_path, "episode.conclude", conclude_payload("analysis"), "finish")
    apply(tmp_path, "episode.review", dict(id="analysis", decision="continue", reviewer="local-reviewer", feedback="계속 진행"), "review")

    row = build_view(tmp_path)["work_episodes"][0]
    assert list(row) == [
        "id", "stage", "title", "purpose", "depends_on", "return_to", "return_reason",
        "review_required", "sequence", "execution_status", "notes", "conclusion",
        "review_status", "review",
    ]
    assert [note["kind"] for note in row["notes"]] == ["dialogue", "tool", "output"]
    assert row["review_status"] == "continued"
    assert row["review"] == dict(decision="continue", reviewer="local-reviewer", feedback="계속 진행")
    assert "council_submissions" not in row


def test_dependency_requires_finished_and_any_required_continue_review(tmp_path):
    init(tmp_path)
    apply(tmp_path, "episode.start", start_payload("basis", review_required=True), "start-basis")
    with pytest.raises(ValueError, match="episode_dependency_unfinished"):
        apply(tmp_path, "episode.start", start_payload("dependent", depends_on=["basis"]), "early")
    apply(tmp_path, "episode.conclude", conclude_payload("basis"), "finish-basis")
    with pytest.raises(ValueError, match="episode_dependency_review_pending"):
        apply(tmp_path, "episode.start", start_payload("dependent", depends_on=["basis"]), "pending")
    apply(tmp_path, "episode.review", dict(id="basis", decision="revise", reviewer="reviewer", feedback="다시 확인"), "revise")
    with pytest.raises(ValueError, match="episode_dependency_revision_requested"):
        apply(tmp_path, "episode.start", start_payload("dependent", depends_on=["basis"]), "rejected")

    apply(tmp_path, "episode.start", start_payload("independent"), "independent")
    apply(tmp_path, "episode.start", start_payload("basis-review", return_to="basis", return_reason="수정 요청 반영"), "return")
    assert [r["id"] for r in build_view(tmp_path)["work_episodes"]] == ["basis", "independent", "basis-review"]


def test_unknown_dependencies_and_return_context_are_rejected(tmp_path):
    init(tmp_path)
    with pytest.raises(ValueError, match="episode_dependency_missing"):
        apply(tmp_path, "episode.start", start_payload("x", depends_on=["missing"]), "missing-dependency")
    with pytest.raises(ValueError, match="episode_return_context_missing"):
        apply(tmp_path, "episode.start", start_payload("x", return_to="missing", return_reason="재검토"), "missing-return")


def test_finished_episode_is_immutable_except_for_exactly_one_review(tmp_path):
    init(tmp_path)
    apply(tmp_path, "episode.start", start_payload("closed", review_required=True), "start")
    apply(tmp_path, "episode.conclude", conclude_payload("closed"), "finish")
    with pytest.raises(ValueError, match="episode_finished_immutable"):
        apply(tmp_path, "episode.note", dict(id="closed", kind="output", author="worker", text="late"), "late-note")
    with pytest.raises(ValueError, match="episode_finished_immutable"):
        apply(tmp_path, "episode.conclude", conclude_payload("closed", judgment="changed"), "finish-again")
    review = dict(id="closed", decision="continue", reviewer="reviewer", feedback="검토 완료")
    apply(tmp_path, "episode.review", review, "review")
    with pytest.raises(ValueError, match="episode_review_exists"):
        apply(tmp_path, "episode.review", review, "review-again")


@pytest.mark.parametrize(
    "operation,payload",
    [
        ("episode.start", {**start_payload("x"), "extra": "no"}),
        ("episode.start", start_payload("x", depends_on="not-a-list")),
        ("episode.start", start_payload("x", depends_on=["same", "same"])),
        ("episode.start", start_payload("x", review_required=1)),
        ("episode.start", start_payload("x", return_to=None, return_reason="orphan reason")),
        ("episode.note", dict(id="x", kind="private", author="a", text="t")),
        ("episode.note", dict(id="x", kind="tool", author=" ", text="t")),
        ("episode.conclude", conclude_payload("x", execution_status="approved")),
        ("episode.review", dict(id="x", decision="approve", reviewer="r", feedback="f")),
    ],
)
def test_payloads_are_closed_and_strict(tmp_path, operation, payload):
    init(tmp_path)
    before = store.read_head(tmp_path)
    with pytest.raises(ValueError, match="episode_payload_invalid"):
        apply(tmp_path, operation, payload, "bad")
    assert store.read_head(tmp_path) == before


def test_replay_head_conflict_and_concurrent_sequence_allocation_use_real_store(tmp_path):
    initial = init(tmp_path)
    args = dict(operation="episode.start", payload=start_payload("one"), expected_head=initial["id"], command_id="one")
    first = commands.apply_command(tmp_path, **args)
    assert commands.apply_command(tmp_path, **args) == first
    with pytest.raises(ValueError, match="research_graph_command_conflict"):
        commands.apply_command(tmp_path, **{**args, "payload": start_payload("changed")})
    with pytest.raises(ValueError, match="research_graph_head_conflict"):
        commands.apply_command(tmp_path, operation="episode.start", payload=start_payload("stale"), expected_head=initial["id"], command_id="stale")

    current = store.read_head(tmp_path)
    def run(identity):
        try:
            return commands.apply_command(tmp_path, operation="episode.start", payload=start_payload(identity), expected_head=current["id"], command_id=identity)
        except ValueError as error:
            return str(error)
    with ThreadPoolExecutor(2) as pool:
        results = list(pool.map(run, ("two", "three")))
    assert sum(type(result) is dict for result in results) == 1
    assert "research_graph_head_conflict" in results
    assert [row["sequence"] for row in build_view(tmp_path)["work_episodes"]] == [1, 2]


def test_missing_collection_is_empty_and_conclusion_or_review_do_not_approve_science(tmp_path):
    init(tmp_path)
    assert build_view(tmp_path)["work_episodes"] == []
    apply(tmp_path, "episode.start", start_payload("report", review_required=True), "start")
    apply(tmp_path, "episode.conclude", conclude_payload("report"), "finish")
    apply(tmp_path, "episode.review", dict(id="report", decision="continue", reviewer="declared-local", feedback="개발 흐름 계속"), "review")
    view = build_view(tmp_path)
    row = view["work_episodes"][0]
    assert row["execution_status"] == "finished"
    assert row["review_status"] == "continued"
    assert view["approvals"] == []
    assert view["milestones"][0]["status"] == "active"


@pytest.mark.parametrize("outcome", ["finished", "failed"])
def test_continue_review_only_unlocks_successful_dependency(tmp_path, outcome):
    init(tmp_path)
    apply(tmp_path, "episode.start", start_payload("basis", review_required=True), "start")
    apply(tmp_path, "episode.conclude", conclude_payload("basis", execution_status=outcome), "finish")
    apply(tmp_path, "episode.review", dict(id="basis", decision="continue", reviewer="local", feedback="흐름 검토"), "review")
    if outcome == "finished":
        apply(tmp_path, "episode.start", start_payload("next", depends_on=["basis"]), "next")
        assert build_view(tmp_path)["work_episodes"][-1]["id"] == "next"
    else:
        before = store.read_head(tmp_path)
        with pytest.raises(ValueError, match="episode_dependency_unfinished"):
            apply(tmp_path, "episode.start", start_payload("next", depends_on=["basis"]), "next")
        assert store.read_head(tmp_path) == before
