"""Pure access and validation for the bundled stage role catalog."""

import json
from pathlib import Path


_FIELDS = {
    "schema_version",
    "stage_id",
    "protocol_version",
    "activation",
    "mode",
    "roles",
    "existing_protocol",
}
_ROLE_FIELDS = {
    "role_id",
    "responsibility",
    "required_questions",
    "judgment_criteria",
    "authority_limits",
}
_JUDGES = {"domain", "methodology", "critical_reproducibility", "coordinator"}


def _mode(stage_id: int) -> str:
    if stage_id in {4, 6, 11, 12}:
        return "work_and_verify"
    if stage_id in {10, 13}:
        return "implementation_council"
    return "judgment_council"


def _protocol(stage_id: int) -> str:
    return {
        12: "user_execution_handoff",
        13: "registered_refinement_council",
        14: "registered_analysis_council",
        15: "registered_decision_council",
    }.get(stage_id, "single_author_validation")


def _invalid() -> ValueError:
    return ValueError("agent_roles_catalog_invalid")


def _nonblank(value: object) -> bool:
    return isinstance(value, str) and bool(value.strip())


def _nonblank_list(value: object) -> bool:
    return (
        isinstance(value, list)
        and bool(value)
        and all(_nonblank(item) for item in value)
    )


def _expected_roles(mode: str) -> set[str]:
    if mode == "work_and_verify":
        return {"worker", "verifier"}
    if mode == "implementation_council":
        return _JUDGES | {"implementation"}
    return _JUDGES


def _validate_catalog(raw: object) -> dict[int, dict[str, object]]:
    if not isinstance(raw, list) or len(raw) != 15:
        raise _invalid()

    indexed: dict[int, dict[str, object]] = {}
    for stage in raw:
        if not isinstance(stage, dict) or set(stage) != _FIELDS:
            raise _invalid()
        if type(stage["schema_version"]) is not int or stage["schema_version"] != 1:  # noqa: E721
            raise _invalid()
        if type(stage["protocol_version"]) is not int or stage["protocol_version"] != 1:  # noqa: E721
            raise _invalid()
        stage_id = stage["stage_id"]
        if type(stage_id) is not int or not 1 <= stage_id <= 15:  # noqa: E721
            raise _invalid()
        if stage_id in indexed:
            raise _invalid()
        if stage["activation"] != "guidance_only":
            raise _invalid()
        mode = stage["mode"]
        if not isinstance(mode, str) or mode != _mode(stage_id):
            raise _invalid()
        if stage["existing_protocol"] != _protocol(stage_id):
            raise _invalid()

        roles = stage["roles"]
        if not isinstance(roles, list) or not roles:
            raise _invalid()
        role_ids: set[str] = set()
        for role in roles:
            if not isinstance(role, dict) or set(role) != _ROLE_FIELDS:
                raise _invalid()
            role_id = role["role_id"]
            if not isinstance(role_id, str) or role_id in role_ids:
                raise _invalid()
            role_ids.add(role_id)
            if not _nonblank(role["responsibility"]):
                raise _invalid()
            for field in (
                "required_questions",
                "judgment_criteria",
                "authority_limits",
            ):
                if not _nonblank_list(role[field]):
                    raise _invalid()
        if role_ids != _expected_roles(mode):
            raise _invalid()
        indexed[stage_id] = stage

    if set(indexed) != set(range(1, 16)):
        raise _invalid()
    return indexed


def describe_stage_roles(stage_id: int) -> dict[str, object]:
    """Return a validated guidance-only description for one supported stage."""
    if type(stage_id) is not int or not 1 <= stage_id <= 15:  # noqa: E721
        raise ValueError("agent_roles_stage_unsupported")
    path = Path(__file__).parent / "data" / "agent_roles.json"
    raw = json.loads(path.read_text(encoding="utf-8"))
    return _validate_catalog(raw)[stage_id]
