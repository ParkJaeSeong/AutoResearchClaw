"""Domain research profiles loaded from package data."""

from dataclasses import dataclass
from pathlib import Path

import yaml


@dataclass(frozen=True)
class ResearchProfile:
    id: str
    display_name: str
    preferred_sources: tuple[str, ...]
    quality_checks: tuple[str, ...]
    metric_guidance: tuple[str, ...]


def load_profile(profile_id: str) -> ResearchProfile:
    path = Path(__file__).parent / "data" / "profiles" / f"{profile_id}.yaml"
    if not path.is_file():
        raise ValueError(f"unknown profile: {profile_id}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"invalid profile: {profile_id}")
    return ResearchProfile(
        id=str(data["id"]),
        display_name=str(data["display_name"]),
        preferred_sources=tuple(str(value) for value in data["preferred_sources"]),
        quality_checks=tuple(str(value) for value in data["quality_checks"]),
        metric_guidance=tuple(str(value) for value in data["metric_guidance"]),
    )
