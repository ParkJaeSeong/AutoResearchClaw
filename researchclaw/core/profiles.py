"""Domain research profiles loaded from package data."""

from dataclasses import dataclass
from pathlib import Path
import re

import yaml

from .paths import resolve_contained_path

_PROFILE_ID_PATTERN = re.compile(r"[a-z][a-z0-9_]{0,63}")
_PROFILE_ROOT = Path(__file__).parent / "data" / "profiles"
_PROFILE_FILES = {"materials_ai": "materials_ai.yaml"}


@dataclass(frozen=True)
class ResearchProfile:
    id: str
    display_name: str
    preferred_sources: tuple[str, ...]
    quality_checks: tuple[str, ...]
    metric_guidance: tuple[str, ...]


def load_profile(profile_id: str) -> ResearchProfile:
    if not isinstance(profile_id, str) or _PROFILE_ID_PATTERN.fullmatch(profile_id) is None:
        raise ValueError(f"invalid profile id: {profile_id}")
    profile_file = _PROFILE_FILES.get(profile_id)
    if profile_file is None:
        raise ValueError(f"unknown profile: {profile_id}")
    path = resolve_contained_path(_PROFILE_ROOT, profile_file, kind="profile")
    if not path.is_file():
        raise ValueError(f"unknown profile: {profile_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid profile: {profile_id}")
    if data.get("id") != profile_id:
        raise ValueError(f"profile ID mismatch: requested {profile_id}, loaded {data.get('id')}")
    fields = ("display_name", "preferred_sources", "quality_checks", "metric_guidance")
    if not isinstance(data.get("display_name"), str) or not data["display_name"]:
        raise ValueError(f"invalid profile: {profile_id}")
    if any(
        not isinstance(data.get(field), list)
        or not data[field]
        or any(not isinstance(value, str) or not value for value in data[field])
        for field in fields[1:]
    ):
        raise ValueError(f"invalid profile: {profile_id}")
    return ResearchProfile(
        id=data["id"],
        display_name=data["display_name"],
        preferred_sources=tuple(data["preferred_sources"]),
        quality_checks=tuple(data["quality_checks"]),
        metric_guidance=tuple(data["metric_guidance"]),
    )
