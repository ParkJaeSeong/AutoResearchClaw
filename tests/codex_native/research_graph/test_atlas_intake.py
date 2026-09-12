import hashlib
import json
from pathlib import Path

import pytest

from researchclaw.core.research_graph import atlas_format
from researchclaw.core.research_graph.atlas_format import MAX_QA_BYTES, parse_atlas_qa


SAMPLE = Path("docs/research/2026-09-10-polymer-sdl/atlas-review/atlas-qa.md")


def qa_bytes(extra="", body="# 질문\n\nVisible body\n"):
    return (
        "---\n"
        "schema_version: 1\n"
        "id: qa-1\n"
        "question: What changed?\n"
        "answer: |\n"
        "  An answer with a table.\n"
        "\n"
        "  | A | B |\n"
        "  |---|---|\n"
        f"{extra}"
        "---\n"
        f"{body}"
    ).encode()


def test_actual_atlas_qa_preserves_metadata_and_hash_without_raw_body():
    data = SAMPLE.read_bytes()

    parsed = parse_atlas_qa(data)

    assert parsed["schema_version"] == 1
    assert parsed["id"] == "qa-abbasi-process-direction-20260912-001"
    assert parsed["question"].startswith("동일한 CNT 함량에서")
    assert parsed["answer"].startswith("**현재 위키와 Abbasi 연구만으로는")
    assert parsed["project"] is None
    assert parsed["consulted_pages"][0]["page_id"] == "page-23d3622f1c524198"
    assert parsed["candidates"][0]["source_refs"][0]["version"] == 1
    assert parsed["file_sha256"] == hashlib.sha256(data).hexdigest()
    assert parsed["missing_fields"] == []
    assert set(parsed) == {
        "schema_version", "id", "question", "answer", "project",
        "consulted_pages", "candidates", "file_sha256", "missing_fields",
    }
    assert "Visible body" not in json.dumps(parsed, ensure_ascii=False)


def test_optional_metadata_defaults_without_inventing_values():
    parsed = parse_atlas_qa(qa_bytes())

    assert parsed["project"] is None
    assert parsed["consulted_pages"] == []
    assert parsed["candidates"] == []
    assert parsed["missing_fields"] == ["project", "consulted_pages", "candidates"]


def test_utf8_bom_and_nested_json_metadata_are_supported():
    data = b"\xef\xbb\xbf" + qa_bytes(
        "project:\n"
        "  slug: pilot\n"
        "  flags: [true, null, 3.5]\n"
        "consulted_pages:\n"
        "- path: wiki/page.md\n"
        "  metadata: {sections: [one, two]}\n"
        "candidates: []\n"
    )

    parsed = parse_atlas_qa(data)

    assert parsed["project"] == {"slug": "pilot", "flags": [True, None, 3.5]}
    assert parsed["consulted_pages"][0]["metadata"]["sections"] == ["one", "two"]


def test_file_larger_than_ten_mib_is_rejected_before_parsing():
    data = b"x" * (MAX_QA_BYTES + 1)

    with pytest.raises(ValueError, match="atlas_file_too_large"):
        parse_atlas_qa(data)


@pytest.mark.parametrize(
    ("data", "error"),
    [
        (b"not frontmatter", "atlas_frontmatter"),
        (b"---\nschema_version: 1\nid: qa\n", "atlas_frontmatter"),
        (b"---\n[broken\n---\n", "atlas_yaml"),
        (b"\xff---\n---\n", "atlas_utf8"),
        (b"---\n- item\n---\n", "atlas_metadata"),
    ],
)
def test_malformed_documents_are_rejected(data, error):
    with pytest.raises(ValueError, match=error):
        parse_atlas_qa(data)


@pytest.mark.parametrize("version", ["1", 1.0, True, 0, 2])
def test_schema_version_must_be_integer_one(version):
    data = qa_bytes().replace(b"schema_version: 1", f"schema_version: {json.dumps(version)}".encode())

    with pytest.raises(ValueError, match="atlas_schema_version"):
        parse_atlas_qa(data)


@pytest.mark.parametrize("field", ["id", "question", "answer"])
@pytest.mark.parametrize("value", ["", "   ", "[]", "{}", "null"])
def test_required_text_fields_must_be_nonblank_strings(field, value):
    fields = {"id": "qa", "question": "question", "answer": "answer"}
    fields[field] = value
    data = (
        "---\n"
        "schema_version: 1\n"
        f"id: {fields['id']}\n"
        f"question: {fields['question']}\n"
        f"answer: {fields['answer']}\n"
        "---\n"
    ).encode()

    with pytest.raises(ValueError, match=f"atlas_{field}"):
        parse_atlas_qa(data)


def test_duplicate_yaml_keys_are_rejected():
    data = qa_bytes("id: second-id\n")

    with pytest.raises(ValueError, match="atlas_duplicate_key"):
        parse_atlas_qa(data)


def test_excessive_yaml_aliases_are_rejected():
    aliases = ", ".join("*value" for _ in range(101))
    data = qa_bytes(f"project:\n  seed: &value [x]\n  expanded: [{aliases}]\n")

    with pytest.raises(ValueError, match="atlas_alias_limit"):
        parse_atlas_qa(data)


def test_nested_alias_expansion_is_rejected_before_materializing_a_bomb():
    data = qa_bytes(
        "project:\n"
        "  level1: &level1 [x, x, x, x, x, x, x, x, x]\n"
        "  level2: &level2 [*level1, *level1, *level1, *level1, *level1, *level1, *level1, *level1, *level1]\n"
        "  level3: &level3 [*level2, *level2, *level2, *level2, *level2, *level2, *level2, *level2, *level2]\n"
        "  level4: &level4 [*level3, *level3, *level3, *level3, *level3, *level3, *level3, *level3, *level3]\n"
        "  expanded: [*level4, *level4, *level4, *level4, *level4, *level4, *level4, *level4, *level4]\n"
    )

    with pytest.raises(ValueError, match="atlas_alias_limit"):
        parse_atlas_qa(data)


def test_deeply_nested_yaml_is_reported_as_bounded_atlas_error():
    nested = "[" * 2000 + "x" + "]" * 2000

    with pytest.raises(ValueError, match="atlas_(yaml|metadata_limit)"):
        parse_atlas_qa(qa_bytes(f"project: {nested}\n"))


def test_yaml_composition_stops_at_node_limit_before_constructing_full_tree(monkeypatch):
    compose_calls = 0
    original = atlas_format._AtlasLoader.compose_node

    def counted_compose(loader, parent, index):
        nonlocal compose_calls
        compose_calls += 1
        return original(loader, parent, index)

    monkeypatch.setattr(atlas_format, "_MAX_METADATA_NODES", 10)
    monkeypatch.setattr(atlas_format._AtlasLoader, "compose_node", counted_compose)
    data = qa_bytes("project: {items: [" + ", ".join("x" for _ in range(1000)) + "]}\n")

    with pytest.raises(ValueError, match="atlas_metadata_limit"):
        parse_atlas_qa(data)
    assert compose_calls <= 11


@pytest.mark.parametrize(
    "extra",
    [
        "consulted_pages:\n- path: []\n",
        "consulted_pages:\n- page_id: {}\n",
        "candidates:\n- id: []\n",
        "candidates:\n- source_refs:\n  - source_id: []\n",
        "candidates:\n- source_refs:\n  - version: one\n",
        "candidates:\n- source_refs:\n  - locator: {}\n",
        "candidates:\n- source_refs:\n  - sha256: []\n",
        "candidates:\n- target_pages:\n  - path: {}\n",
    ],
)
def test_known_optional_source_fields_reject_wrong_nested_types(extra):
    with pytest.raises(ValueError, match="atlas_metadata"):
        parse_atlas_qa(qa_bytes(extra))


@pytest.mark.parametrize(
    "extra",
    [
        "project: 42\n",
        "consulted_pages: {}\n",
        "consulted_pages: [page.md]\n",
        "candidates: candidate\n",
        "candidates: [candidate]\n",
        "candidates:\n- id: C1\n  source_refs: source-1\n",
        "candidates:\n- id: C1\n  target_pages: [page.md]\n",
        "project:\n  created: 2026-09-12\n",
        "project:\n  1: value\n",
    ],
)
def test_invalid_optional_or_nested_metadata_types_are_rejected(extra):
    with pytest.raises(ValueError, match="atlas_metadata"):
        parse_atlas_qa(qa_bytes(extra))


def test_file_size_limit_is_applied_to_original_bytes():
    with pytest.raises(ValueError, match="atlas_file_too_large"):
        parse_atlas_qa(b"x" * (10 * 1024 * 1024 + 1))
