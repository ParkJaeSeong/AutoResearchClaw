"""Parse the bounded Atlas schema-version-1 QA Markdown format."""

from __future__ import annotations

import hashlib
import math
from typing import Any

import yaml
from yaml.events import AliasEvent


MAX_QA_BYTES = 10 * 1024 * 1024
_MAX_ALIASES = 100
_MAX_METADATA_DEPTH = 100
_MAX_METADATA_NODES = 100_000
_OPTIONAL_FIELDS = ("project", "consulted_pages", "candidates")


class _AtlasLoader(yaml.SafeLoader):
    def __init__(self, stream: str) -> None:
        super().__init__(stream)
        self.alias_count = 0
        self.node_count = 0
        self.composition_depth = 0

    def compose_node(self, parent: Any, index: Any) -> Any:
        self.node_count += 1
        if self.node_count > _MAX_METADATA_NODES:
            raise ValueError("atlas_metadata_limit")
        self.composition_depth += 1
        try:
            if self.composition_depth > _MAX_METADATA_DEPTH:
                raise ValueError("atlas_metadata_limit")
            if self.check_event(AliasEvent):
                self.alias_count += 1
                if self.alias_count > _MAX_ALIASES:
                    raise ValueError("atlas_alias_limit")
            return super().compose_node(parent, index)
        finally:
            self.composition_depth -= 1


def _construct_mapping(loader: _AtlasLoader, node: yaml.MappingNode, deep: bool = False) -> dict:
    loader.flatten_mapping(node)
    result = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        try:
            duplicate = key in result
        except TypeError as exc:
            raise ValueError("atlas_metadata") from exc
        if duplicate:
            raise ValueError("atlas_duplicate_key")
        result[key] = loader.construct_object(value_node, deep=deep)
    return result


_AtlasLoader.add_constructor(
    yaml.resolver.BaseResolver.DEFAULT_MAPPING_TAG,
    _construct_mapping,
)


def _frontmatter(text: str) -> str:
    lines = text.splitlines()
    if not lines or lines[0] != "---":
        raise ValueError("atlas_frontmatter")
    try:
        end = lines.index("---", 1)
    except ValueError as exc:
        raise ValueError("atlas_frontmatter") from exc
    return "\n".join(lines[1:end])


def _json_value(
    value: Any,
    active: set[int] | None = None,
    seen: set[int] | None = None,
    depth: int = 0,
    budget: list[int] | None = None,
) -> None:
    if depth > _MAX_METADATA_DEPTH:
        raise ValueError("atlas_metadata_limit")
    if budget is None:
        budget = [_MAX_METADATA_NODES]
    budget[0] -= 1
    if budget[0] < 0:
        raise ValueError("atlas_metadata_limit")
    if value is None or isinstance(value, (str, bool, int)):
        return
    if isinstance(value, float):
        if not math.isfinite(value):
            raise ValueError("atlas_metadata")
        return
    if active is None:
        active = set()
    if seen is None:
        seen = set()
    if isinstance(value, list):
        marker = id(value)
        if marker in active:
            raise ValueError("atlas_metadata")
        if marker in seen:
            raise ValueError("atlas_alias_limit")
        seen.add(marker)
        active.add(marker)
        for item in value:
            _json_value(item, active, seen, depth + 1, budget)
        active.remove(marker)
        return
    if isinstance(value, dict):
        marker = id(value)
        if marker in active:
            raise ValueError("atlas_metadata")
        if marker in seen:
            raise ValueError("atlas_alias_limit")
        seen.add(marker)
        active.add(marker)
        for key, item in value.items():
            if not isinstance(key, str):
                raise ValueError("atlas_metadata")
            _json_value(item, active, seen, depth + 1, budget)
        active.remove(marker)
        return
    raise ValueError("atlas_metadata")


def _mapping_list(metadata: dict, field: str) -> list[dict]:
    value = metadata.get(field, [])
    if not isinstance(value, list) or any(not isinstance(item, dict) for item in value):
        raise ValueError("atlas_metadata")
    return value


def _validate_text_fields(row: dict, fields: tuple[str, ...]) -> None:
    for field in fields:
        if field in row and (not isinstance(row[field], str) or not row[field].strip()):
            raise ValueError("atlas_metadata")


def _validate_page(row: dict) -> None:
    _validate_text_fields(row, ("path", "page_id", "sha256"))


def _validate_candidate(row: dict) -> None:
    _validate_text_fields(row, ("id", "text", "tag"))
    for field in ("source_refs", "target_pages"):
        if field not in row:
            continue
        nested = row[field]
        if not isinstance(nested, list) or any(not isinstance(item, dict) for item in nested):
            raise ValueError("atlas_metadata")
        if field == "target_pages":
            for page in nested:
                _validate_page(page)
        else:
            for source in nested:
                _validate_text_fields(source, ("source_id", "locator", "raw_path", "sha256"))
                if "version" in source and type(source["version"]) is not int:
                    raise ValueError("atlas_metadata")


def parse_atlas_qa(data: bytes) -> dict:
    """Validate and normalize an Atlas QA Markdown file without reading links."""
    if not isinstance(data, bytes):
        raise ValueError("atlas_bytes")
    if len(data) > MAX_QA_BYTES:
        raise ValueError("atlas_file_too_large")
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise ValueError("atlas_utf8") from exc

    try:
        metadata = yaml.load(_frontmatter(text), Loader=_AtlasLoader)
    except ValueError:
        raise
    except RecursionError as exc:
        raise ValueError("atlas_yaml") from exc
    except yaml.YAMLError as exc:
        raise ValueError("atlas_yaml") from exc
    if not isinstance(metadata, dict):
        raise ValueError("atlas_metadata")

    version = metadata.get("schema_version")
    if type(version) is not int or version != 1:
        raise ValueError("atlas_schema_version")
    for field in ("id", "question", "answer"):
        value = metadata.get(field)
        if not isinstance(value, str) or not value.strip():
            raise ValueError(f"atlas_{field}")

    project = metadata.get("project")
    if project is not None and not isinstance(project, (str, dict)):
        raise ValueError("atlas_metadata")
    consulted_pages = _mapping_list(metadata, "consulted_pages")
    candidates = _mapping_list(metadata, "candidates")
    for page in consulted_pages:
        _validate_page(page)
    for candidate in candidates:
        _validate_candidate(candidate)

    active: set[int] = set()
    seen: set[int] = set()
    budget = [_MAX_METADATA_NODES]
    for value in metadata.values():
        _json_value(value, active, seen, budget=budget)

    return {
        "schema_version": version,
        "id": metadata["id"],
        "question": metadata["question"],
        "answer": metadata["answer"],
        "project": project,
        "consulted_pages": consulted_pages,
        "candidates": candidates,
        "file_sha256": hashlib.sha256(data).hexdigest(),
        "missing_fields": [field for field in _OPTIONAL_FIELDS if field not in metadata],
    }
