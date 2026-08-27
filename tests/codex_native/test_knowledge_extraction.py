import json

import pytest

from researchclaw.core.knowledge_extraction import validate_knowledge_extraction


VALID_SHORTLIST = """\
{"source_id":"src-full","title":"Crystal graph networks","doi":"10.1000/full","url":"https://example.org/full","decision":"include","reason":"directly relevant","source_type":"article"}
{"source_id":"src-unavailable","title":"Archived framework","url":"https://example.org/unavailable","decision":"include","reason":"relevant framework","source_type":"government_framework"}
{"source_id":"src-excluded","title":"Unrelated article","doi":"10.1000/excluded","url":"https://example.org/excluded","decision":"exclude","reason":"outside scope","source_type":"article"}
"""

VALID_CLAIMS = """\
{"claim_id":"claim-1","source_id":"src-full","claim":"Crystal graphs encode atomic neighborhoods.","evidence_summary":"The method represents crystals as graphs over atoms and bonds.","evidence_level":"full_text","locator":"Methods, section 2","source_url":"https://example.org/full","doi":"10.1000/full","applicability":["materials representation"],"limitations":["Evaluated on crystalline materials"]}
{"claim_id":"claim-2","source_id":"src-full","claim":"The model predicts formation energies.","evidence_summary":"The evaluation reports formation-energy prediction on held-out crystals.","evidence_level":"full_text","locator":"Results, table 1","source_url":"https://example.org/full","doi":"10.1000/full","applicability":["formation energy prediction"],"limitations":[]}
"""

VALID_MANIFEST = """\
{
  "schema_version": 1,
  "project_id": "rc-test",
  "generated_at": "2026-08-27T12:00:00Z",
  "sources": [
    {
      "source_id": "src-full",
      "decision": "include",
      "access_status": "full_text",
      "accessed_at": "2026-08-27T11:00:00Z",
      "access_url": "https://example.org/full",
      "claim_count": 2,
      "failure_reason": null
    },
    {
      "source_id": "src-unavailable",
      "decision": "include",
      "access_status": "unavailable",
      "accessed_at": null,
      "access_url": null,
      "claim_count": 0,
      "failure_reason": "The archived page could not be retrieved"
    }
  ],
  "summary": {
    "included_sources": 2,
    "processed_sources": 2,
    "claim_count": 2,
    "full_text_sources": 1,
    "abstract_sources": 0,
    "metadata_only_sources": 0,
    "unavailable_sources": 1
  }
}
"""


def _messages(issues):
    return "\n".join(issue.message for issue in issues)


_MISSING = object()


def _evidence_access_fixture(
    access_status,
    evidence_level,
    *,
    quantitative_details=_MISSING,
):
    shortlist = (
        '{"source_id":"src-access","title":"Access policy source",'
        '"url":"https://example.org/access","decision":"include",'
        '"reason":"tests evidence access","source_type":"article"}\n'
    )
    claim = {
        "claim_id": "claim-access",
        "source_id": "src-access",
        "claim": "The source describes a supported observation.",
        "evidence_summary": "The accessed material directly states the observation.",
        "evidence_level": evidence_level,
        "locator": "Abstract" if evidence_level == "abstract" else "Source metadata",
        "source_url": "https://example.org/access",
        "applicability": ["access policy testing"],
        "limitations": [],
    }
    if quantitative_details is not _MISSING:
        claim["quantitative_details"] = quantitative_details
    claims = json.dumps(claim, separators=(",", ":")) + "\n"
    status_counts = {
        "full_text_sources": 0,
        "abstract_sources": 0,
        "metadata_only_sources": 0,
        "unavailable_sources": 0,
    }
    status_counts[f"{access_status}_sources"] = 1
    manifest = json.dumps(
        {
            "schema_version": 1,
            "project_id": "rc-test",
            "generated_at": "2026-08-27T12:00:00Z",
            "sources": [
                {
                    "source_id": "src-access",
                    "decision": "include",
                    "access_status": access_status,
                    "accessed_at": "2026-08-27T11:00:00Z",
                    "access_url": "https://example.org/access",
                    "claim_count": 1,
                    "failure_reason": None,
                }
            ],
            "summary": {
                "included_sources": 1,
                "processed_sources": 1,
                "claim_count": 1,
                **status_counts,
            },
        },
        separators=(",", ":"),
    )
    return shortlist, claims, manifest


def _claims_with_first_claim_update(**updates):
    first, second = VALID_CLAIMS.splitlines()
    claim = json.loads(first)
    claim.update(updates)
    return json.dumps(claim, separators=(",", ":")) + "\n" + second + "\n"


def test_valid_claims_and_manifest_have_no_issues():
    issues = validate_knowledge_extraction(
        VALID_SHORTLIST,
        VALID_CLAIMS,
        VALID_MANIFEST,
        "rc-test",
    )

    assert issues == ()


def test_unknown_source_id_is_rejected():
    claims = VALID_CLAIMS.replace('"source_id":"src-full"', '"source_id":"src-unknown"', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "unknown source_id" in _messages(issues)
    assert any(issue.path == "knowledge/extractions.jsonl" for issue in issues)


def test_excluded_source_is_rejected():
    claims = VALID_CLAIMS.replace('"source_id":"src-full"', '"source_id":"src-excluded"', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "excluded source" in _messages(issues)


def test_duplicate_claim_id_is_rejected():
    claims = VALID_CLAIMS.replace('"claim_id":"claim-2"', '"claim_id":"claim-1"')

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "duplicate claim_id" in _messages(issues)


def test_identifier_contradiction_is_rejected():
    claims = VALID_CLAIMS.replace('"doi":"10.1000/full"', '"doi":"10.1000/contradiction"', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "contradicts shortlist doi" in _messages(issues)


def test_source_url_identifier_contradiction_is_rejected():
    claims = VALID_CLAIMS.replace(
        '"source_url":"https://example.org/full"',
        '"source_url":"https://example.org/different"',
        1,
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "contradicts shortlist url" in _messages(issues)


def test_duplicate_normalized_claim_within_source_is_rejected():
    claims = VALID_CLAIMS.replace(
        "The model predicts formation energies.",
        "  CRYSTAL   GRAPHS encode ATOMIC neighborhoods.  ",
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "duplicate normalized claim" in _messages(issues)


def test_same_normalized_claim_from_different_sources_is_valid():
    shortlist = VALID_SHORTLIST.replace('"source_id":"src-unavailable"', '"source_id":"src-second"').replace(
        '"url":"https://example.org/unavailable"',
        '"url":"https://example.org/second"',
    )
    claims = VALID_CLAIMS.replace(
        '"source_id":"src-full","claim":"The model predicts formation energies."',
        '"source_id":"src-second","claim":"Crystal graphs encode atomic neighborhoods."',
    ).replace(
        '"source_url":"https://example.org/full","doi":"10.1000/full","applicability":["formation energy prediction"]',
        '"source_url":"https://example.org/second","applicability":["formation energy prediction"]',
        1,
    )

    issues = validate_knowledge_extraction(shortlist, claims, VALID_MANIFEST, "rc-test")

    assert "duplicate normalized claim" not in _messages(issues)


def test_non_object_source_record_is_rejected():
    shortlist = VALID_SHORTLIST + '["not", "an", "object"]\n'

    issues = validate_knowledge_extraction(shortlist, VALID_CLAIMS, VALID_MANIFEST, "rc-test")

    assert "must be a JSON object" in _messages(issues)
    assert any(issue.path == "literature/shortlist.jsonl" for issue in issues)


def test_non_object_claim_record_is_rejected():
    claims = VALID_CLAIMS + '42\n'

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "must be a JSON object" in _messages(issues)


def test_missing_source_and_claim_strings_are_rejected():
    shortlist = VALID_SHORTLIST.replace('"source_id":"src-full"', '"source_id":""', 1)
    claims = VALID_CLAIMS.replace('"evidence_summary":"The method represents crystals as graphs over atoms and bonds."', '"evidence_summary":null')

    issues = validate_knowledge_extraction(shortlist, claims, VALID_MANIFEST, "rc-test")

    assert "requires non-empty string source_id" in _messages(issues)
    assert "requires non-empty string evidence_summary" in _messages(issues)


def test_invalid_source_and_claim_enums_are_rejected():
    shortlist = VALID_SHORTLIST.replace('"decision":"include"', '"decision":"maybe"', 1)
    claims = VALID_CLAIMS.replace('"evidence_level":"full_text"', '"evidence_level":"unknown"', 1)

    issues = validate_knowledge_extraction(shortlist, claims, VALID_MANIFEST, "rc-test")

    assert "invalid decision" in _messages(issues)
    assert "invalid evidence_level" in _messages(issues)


def test_invalid_claim_list_members_are_rejected():
    claims = VALID_CLAIMS.replace(
        '"applicability":["materials representation"]',
        '"applicability":["materials representation",7]',
    ).replace('"limitations":[]', '"limitations":[false]', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "applicability must contain only non-empty strings" in _messages(issues)
    assert "limitations must contain only strings" in _messages(issues)


def test_duplicate_source_id_is_rejected():
    shortlist = VALID_SHORTLIST.replace('"source_id":"src-unavailable"', '"source_id":"src-full"')

    issues = validate_knowledge_extraction(shortlist, VALID_CLAIMS, VALID_MANIFEST, "rc-test")

    assert "duplicate source_id" in _messages(issues)


def _limit_fixture(source_type, claim_count):
    shortlist = json.dumps(
        {
            "source_id": "src-limit",
            "title": "Claim density source",
            "url": "https://example.org/limit",
            "decision": "include",
            "reason": "tests the claim boundary",
            "source_type": source_type,
        },
        separators=(",", ":"),
    ) + "\n"
    claims = "\n".join(
        json.dumps(
            {
                "claim_id": f"limit-{index}",
                "source_id": "src-limit",
                "claim": f"Distinct supported claim number {index}.",
                "evidence_summary": f"Section {index} contains evidence for this distinct claim.",
                "evidence_level": "full_text",
                "locator": f"Section {index}",
                "source_url": "https://example.org/limit",
                "applicability": ["claim density testing"],
                "limitations": [],
            },
            separators=(",", ":"),
        )
        for index in range(1, claim_count + 1)
    ) + "\n"
    manifest = json.dumps(
        {
            "schema_version": 1,
            "project_id": "rc-test",
            "generated_at": "2026-08-27T12:00:00Z",
            "sources": [
                {
                    "source_id": "src-limit",
                    "decision": "include",
                    "access_status": "full_text",
                    "accessed_at": "2026-08-27T11:00:00Z",
                    "access_url": "https://example.org/limit",
                    "claim_count": claim_count,
                    "failure_reason": None,
                }
            ],
            "summary": {
                "included_sources": 1,
                "processed_sources": 1,
                "claim_count": claim_count,
                "full_text_sources": 1,
                "abstract_sources": 0,
                "metadata_only_sources": 0,
                "unavailable_sources": 0,
            },
        },
        separators=(",", ":"),
    )
    return shortlist, claims, manifest


def test_missing_locator_is_rejected():
    claims = VALID_CLAIMS.replace('"locator":"Methods, section 2"', '"locator":""', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "requires an explicit locator" in _messages(issues)


def test_supporting_excerpt_over_25_words_is_rejected():
    excerpt = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two twenty-three twenty-four twenty-five twenty-six"
    claims = VALID_CLAIMS.replace(
        '"doi":"10.1000/full","applicability"',
        f'"doi":"10.1000/full","supporting_excerpt":"{excerpt}","applicability"',
        1,
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "supporting_excerpt exceeds 25 words" in _messages(issues)


def test_25_word_supporting_excerpt_is_valid():
    excerpt = "one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty twenty-one twenty-two twenty-three twenty-four twenty-five"
    claims = VALID_CLAIMS.replace(
        '"doi":"10.1000/full","applicability"',
        f'"doi":"10.1000/full","supporting_excerpt":"{excerpt}","applicability"',
        1,
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "supporting_excerpt" not in _messages(issues)


def test_metadata_only_quantitative_details_are_rejected():
    claims = VALID_CLAIMS.replace('"evidence_level":"full_text"', '"evidence_level":"metadata_only"', 1).replace(
        '"locator":"Methods, section 2"',
        '"locator":"publisher metadata","quantitative_details":{"value":7,"unit":"samples","condition":"catalog entry"}',
        1,
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "metadata_only claim cannot contain quantitative_details" in _messages(issues)


@pytest.mark.parametrize(
    ("access_status", "evidence_level"),
    (
        ("full_text", "full_text"),
        ("full_text", "abstract"),
        ("full_text", "metadata_only"),
        ("abstract", "abstract"),
        ("abstract", "metadata_only"),
        ("metadata_only", "metadata_only"),
    ),
)
def test_manifest_access_status_allows_non_escalating_claim_evidence(
    access_status,
    evidence_level,
):
    shortlist, claims, manifest = _evidence_access_fixture(access_status, evidence_level)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    assert issues == ()


@pytest.mark.parametrize(
    ("access_status", "evidence_level"),
    (
        ("abstract", "full_text"),
        ("metadata_only", "abstract"),
        ("metadata_only", "full_text"),
    ),
)
def test_claim_evidence_cannot_exceed_manifest_access_status(
    access_status,
    evidence_level,
):
    shortlist, claims, manifest = _evidence_access_fixture(access_status, evidence_level)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    assert (
        f"evidence_level {evidence_level} exceeds manifest access_status {access_status}"
        in _messages(issues)
    )


def test_metadata_access_cannot_gain_quantitative_details_by_claiming_full_text_evidence():
    shortlist, claims, manifest = _evidence_access_fixture(
        "metadata_only",
        "full_text",
        quantitative_details={
            "value": 7,
            "unit": "samples",
            "condition": "catalog entry",
        },
    )

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    messages = _messages(issues)
    assert "evidence_level full_text exceeds manifest access_status metadata_only" in messages
    assert "metadata-only access cannot support quantitative_details" in messages


@pytest.mark.parametrize("value", (7, 7.25, "7 plus or minus 1"))
def test_quantitative_details_accept_a_finite_number_or_non_empty_string_value(value):
    claims = _claims_with_first_claim_update(
        quantitative_details={
            "value": value,
            "unit": "electron volts",
            "condition": "held-out crystal test set",
        }
    )

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert issues == ()


@pytest.mark.parametrize(
    ("details", "expected_message"),
    (
        ([], "quantitative_details must be a JSON object"),
        (
            {"value": 7, "unit": "samples"},
            "quantitative_details requires field condition",
        ),
        (
            {"value": 7, "condition": "test set"},
            "quantitative_details requires field unit",
        ),
        (
            {"unit": "samples", "condition": "test set"},
            "quantitative_details requires field value",
        ),
        (
            {"value": " ", "unit": "samples", "condition": "test set"},
            "quantitative_details value must be a finite number or non-empty string",
        ),
        (
            {"value": True, "unit": "samples", "condition": "test set"},
            "quantitative_details value must be a finite number or non-empty string",
        ),
        (
            {"value": 7, "unit": " ", "condition": "test set"},
            "quantitative_details unit must be a non-empty string",
        ),
        (
            {"value": 7, "unit": "samples", "condition": ""},
            "quantitative_details condition must be a non-empty string",
        ),
        (
            {
                "value": 7,
                "unit": "samples",
                "condition": "test set",
                "precision": 0.1,
            },
            "unknown quantitative_details field: precision",
        ),
    ),
)
def test_quantitative_details_require_the_exact_observed_shape(details, expected_message):
    claims = _claims_with_first_claim_update(quantitative_details=details)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert expected_message in _messages(issues)


def test_quantitative_details_reject_a_non_finite_json_number():
    claims = _claims_with_first_claim_update(
        quantitative_details={
            "value": "overflow",
            "unit": "samples",
            "condition": "test set",
        }
    ).replace('"value":"overflow"', '"value":1e400', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert (
        "quantitative_details value must be a finite number or non-empty string"
        in _messages(issues)
    )


def test_conflicts_with_may_reference_another_claim_declared_later_in_the_artifact():
    claims = _claims_with_first_claim_update(conflicts_with=["claim-2"])

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert issues == ()


@pytest.mark.parametrize(
    ("claim_id", "expected_message"),
    (
        ("claim-1", "conflicts_with cannot reference its own claim_id"),
        ("claim-unknown", "conflicts_with references unknown claim_id: claim-unknown"),
    ),
)
def test_conflicts_with_must_reference_another_existing_claim(claim_id, expected_message):
    claims = _claims_with_first_claim_update(conflicts_with=[claim_id])

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert expected_message in _messages(issues)


def test_empty_applicability_is_rejected():
    claims = VALID_CLAIMS.replace('"applicability":["materials representation"]', '"applicability":[]', 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "applicability must be a non-empty list" in _messages(issues)


@pytest.mark.parametrize(
    "marker",
    (
        "Template key finding",
        "TEMPLATE METHOD SUMMARY",
        "placeholder",
        "Please fill this in before use",
    ),
)
def test_known_placeholder_markers_are_rejected(marker):
    claims = VALID_CLAIMS.replace("Crystal graphs encode atomic neighborhoods.", marker, 1)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert "contains a placeholder marker" in _messages(issues)


def test_general_source_limit_rejects_11_article_claims():
    shortlist, claims, manifest = _limit_fixture("article", 11)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    assert "exceeds claim limit 10" in _messages(issues)


def test_extended_source_limit_rejects_16_government_framework_claims():
    shortlist, claims, manifest = _limit_fixture("government_framework", 16)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    assert "exceeds claim limit 15" in _messages(issues)


def test_extended_source_limit_allows_15_government_framework_claims():
    shortlist, claims, manifest = _limit_fixture("government_framework", 15)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    assert issues == ()


def _changed_manifest(change):
    manifest = json.loads(VALID_MANIFEST)
    change(manifest)
    return json.dumps(manifest, separators=(",", ":"))


@pytest.mark.parametrize(
    ("schema_level", "expected_message"),
    (
        ("top", "manifest has unknown field: extra"),
        ("source", "sources entry 1 has unknown field: extra"),
        ("summary", "summary has unknown field: extra"),
    ),
)
def test_manifest_schema_rejects_unknown_fields_at_every_level(
    schema_level,
    expected_message,
):
    def add_unknown_field(value):
        if schema_level == "top":
            value["extra"] = "not declared"
        elif schema_level == "source":
            value["sources"][0]["extra"] = "not declared"
        else:
            value["summary"]["extra"] = 0

    manifest = _changed_manifest(add_unknown_field)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert expected_message in _messages(issues)


@pytest.mark.parametrize("forbidden_field", ("full_text", "source_text"))
def test_manifest_recursively_rejects_stored_source_payloads(forbidden_field):
    def add_source_payload(value):
        value["sources"][0]["source_payload"] = {
            "download": {
                forbidden_field: "The retrieved source body must not be stored.",
            }
        }

    manifest = _changed_manifest(add_source_payload)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert (
        "forbidden manifest field: "
        f"manifest.sources[0].source_payload.download.{forbidden_field}"
        in _messages(issues)
    )


def test_manifest_missing_included_source_is_rejected():
    manifest = _changed_manifest(lambda value: value["sources"].pop())

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "missing included source: src-unavailable" in _messages(issues)


def test_manifest_duplicate_source_entry_is_rejected():
    def duplicate_source(value):
        value["sources"].append(dict(value["sources"][0]))

    manifest = _changed_manifest(duplicate_source)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "duplicate source_id: src-full" in _messages(issues)


def test_manifest_unknown_or_excluded_source_is_rejected():
    def add_unapproved_sources(value):
        value["sources"].extend(
            [
                {
                    "source_id": "src-excluded",
                    "decision": "include",
                    "access_status": "metadata_only",
                    "accessed_at": "2026-08-27T11:00:00Z",
                    "access_url": "https://example.org/excluded",
                    "claim_count": 1,
                    "failure_reason": None,
                },
                {
                    "source_id": "src-unknown",
                    "decision": "include",
                    "access_status": "metadata_only",
                    "accessed_at": "2026-08-27T11:00:00Z",
                    "access_url": "https://example.org/unknown",
                    "claim_count": 1,
                    "failure_reason": None,
                },
            ]
        )

    manifest = _changed_manifest(add_unapproved_sources)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "excluded source: src-excluded" in _messages(issues)
    assert "unknown source_id: src-unknown" in _messages(issues)


def test_unavailable_manifest_source_with_claims_is_rejected():
    def make_unavailable(value):
        source = value["sources"][0]
        source.update(
            access_status="unavailable",
            accessed_at=None,
            access_url=None,
            failure_reason="Full text and metadata could not be retrieved",
        )

    manifest = _changed_manifest(make_unavailable)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "unavailable source src-full must have zero claims" in _messages(issues)


def test_unavailable_manifest_source_requires_failure_reason():
    manifest = _changed_manifest(lambda value: value["sources"][1].update(failure_reason=""))

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "unavailable source src-unavailable requires a failure_reason" in _messages(issues)


def test_non_unavailable_manifest_source_with_zero_claims_is_rejected():
    def make_metadata_only(value):
        source = value["sources"][1]
        source.update(
            access_status="metadata_only",
            accessed_at="2026-08-27T11:30:00Z",
            access_url="https://example.org/unavailable",
            failure_reason=None,
        )

    manifest = _changed_manifest(make_metadata_only)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "non-unavailable source src-unavailable must have at least one claim" in _messages(issues)


def test_manifest_source_claim_count_must_match_actual_claims():
    manifest = _changed_manifest(lambda value: value["sources"][0].update(claim_count=1))

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "claim_count 1 does not match actual count 2" in _messages(issues)


@pytest.mark.parametrize(
    "summary_field",
    (
        "included_sources",
        "processed_sources",
        "claim_count",
        "full_text_sources",
        "abstract_sources",
        "metadata_only_sources",
        "unavailable_sources",
    ),
)
def test_wrong_summary_count_is_rejected(summary_field):
    def change_summary(value):
        value["summary"][summary_field] += 1

    manifest = _changed_manifest(change_summary)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert f"summary {summary_field}" in _messages(issues)


@pytest.mark.parametrize("timestamp_field", ("generated_at", "accessed_at"))
def test_invalid_manifest_timestamp_is_rejected(timestamp_field):
    def break_timestamp(value):
        if timestamp_field == "generated_at":
            value["generated_at"] = "not-a-timestamp"
        else:
            value["sources"][0]["accessed_at"] = "not-a-timestamp"

    manifest = _changed_manifest(break_timestamp)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert f"invalid {timestamp_field} timestamp" in _messages(issues)


def test_manifest_project_id_must_match_current_project():
    manifest = _changed_manifest(lambda value: value.update(project_id="rc-other"))

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "project_id does not match current project" in _messages(issues)


def test_manifest_rejects_non_object_source_entry():
    manifest = _changed_manifest(lambda value: value["sources"].append("src-invalid"))

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "sources entry 3 must be a JSON object" in _messages(issues)


def test_manifest_rejects_boolean_integer_fields():
    def use_booleans(value):
        value["schema_version"] = True
        value["sources"][0]["claim_count"] = False
        value["summary"]["claim_count"] = True

    manifest = _changed_manifest(use_booleans)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "schema_version must be integer 1" in _messages(issues)
    assert "claim_count must be a non-negative integer" in _messages(issues)
    assert "summary claim_count must be a non-negative integer" in _messages(issues)


def test_manifest_access_fields_follow_availability_status():
    def break_access_fields(value):
        value["sources"][0].update(accessed_at=None, access_url=None, failure_reason="unexpected")
        value["sources"][1].update(
            accessed_at="2026-08-27T11:30:00Z",
            access_url="https://example.org/unavailable",
        )

    manifest = _changed_manifest(break_access_fields)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert "non-unavailable source src-full requires accessed_at" in _messages(issues)
    assert "non-unavailable source src-full requires access_url" in _messages(issues)
    assert "non-unavailable source src-full requires null failure_reason" in _messages(issues)
    assert "unavailable source src-unavailable requires null accessed_at" in _messages(issues)
    assert "unavailable source src-unavailable requires null access_url" in _messages(issues)


@pytest.mark.parametrize("field", ("accessed_at", "access_url", "failure_reason"))
def test_manifest_required_nullable_field_cannot_be_omitted(field):
    def omit_field(value):
        value["sources"][1].pop(field)

    manifest = _changed_manifest(omit_field)

    issues = validate_knowledge_extraction(VALID_SHORTLIST, VALID_CLAIMS, manifest, "rc-test")

    assert f"requires field {field}" in _messages(issues)


ALL_UNAVAILABLE_MANIFEST = """\
{
  "schema_version": 1,
  "project_id": "rc-test",
  "generated_at": "2026-08-27T12:00:00Z",
  "sources": [
    {
      "source_id": "src-full",
      "decision": "include",
      "access_status": "unavailable",
      "accessed_at": null,
      "access_url": null,
      "claim_count": 0,
      "failure_reason": "The full-text source could not be retrieved"
    },
    {
      "source_id": "src-unavailable",
      "decision": "include",
      "access_status": "unavailable",
      "accessed_at": null,
      "access_url": null,
      "claim_count": 0,
      "failure_reason": "The archived page could not be retrieved"
    }
  ],
  "summary": {
    "included_sources": 2,
    "processed_sources": 2,
    "claim_count": 0,
    "full_text_sources": 0,
    "abstract_sources": 0,
    "metadata_only_sources": 0,
    "unavailable_sources": 2
  }
}
"""


def test_empty_claims_are_valid_when_all_included_sources_are_unavailable():
    issues = validate_knowledge_extraction(
        VALID_SHORTLIST,
        "",
        ALL_UNAVAILABLE_MANIFEST,
        "rc-test",
    )

    assert issues == ()


def test_empty_claims_are_rejected_when_any_included_source_is_non_unavailable():
    manifest = json.loads(ALL_UNAVAILABLE_MANIFEST)
    manifest["sources"][0].update(
        access_status="full_text",
        accessed_at="2026-08-27T11:00:00Z",
        access_url="https://example.org/full",
        failure_reason=None,
    )
    manifest["summary"].update(full_text_sources=1, unavailable_sources=1)

    issues = validate_knowledge_extraction(
        VALID_SHORTLIST,
        "",
        json.dumps(manifest, separators=(",", ":")),
        "rc-test",
    )

    assert "artifact must contain at least one JSON object" in _messages(issues)
    assert "non-unavailable source src-full must have at least one claim" in _messages(issues)


@pytest.mark.parametrize("forbidden_field", ("full_text", "source_text"))
def test_claim_closed_schema_rejects_full_source_payloads(forbidden_field):
    first, second = VALID_CLAIMS.splitlines()
    claim = json.loads(first)
    claim[forbidden_field] = "The full source must never be stored in extraction artifacts."
    claims = json.dumps(claim, separators=(",", ":")) + "\n" + second + "\n"

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert f"unknown claim field: {forbidden_field}" in _messages(issues)


@pytest.mark.parametrize("forbidden_field", ("full_text", "source_text"))
def test_claim_closed_schema_rejects_nested_full_source_payloads(forbidden_field):
    first, second = VALID_CLAIMS.splitlines()
    claim = json.loads(first)
    claim["quantitative_details"] = {
        "value": 7,
        "unit": "samples",
        "condition": "catalog evaluation",
        forbidden_field: "The full source must never be stored in nested payloads.",
    }
    claims = json.dumps(claim, separators=(",", ":")) + "\n" + second + "\n"

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert f"forbidden claim field: quantitative_details.{forbidden_field}" in _messages(issues)


@pytest.mark.parametrize(
    ("field", "value"),
    (
        ("locator", "Section with placeholder text"),
        ("supporting_excerpt", "Template key finding"),
        ("applicability", ["Please fill this in"]),
        ("limitations", ["Template method summary"]),
        ("conflicts_with", ["placeholder"]),
        (
            "quantitative_details",
            {"value": 7, "unit": "samples", "condition": "fill this in later"},
        ),
    ),
)
def test_placeholder_scope_rejects_markers_in_all_evidence_fields(field, value):
    first, second = VALID_CLAIMS.splitlines()
    claim = json.loads(first)
    claim[field] = value
    claims = json.dumps(claim, separators=(",", ":")) + "\n" + second + "\n"

    issues = validate_knowledge_extraction(VALID_SHORTLIST, claims, VALID_MANIFEST, "rc-test")

    assert f"{field} contains a placeholder marker" in _messages(issues)


@pytest.mark.parametrize("artifact", ("shortlist", "claims", "manifest"))
def test_non_standard_json_constants_are_rejected(artifact):
    shortlist = VALID_SHORTLIST
    claims = VALID_CLAIMS
    manifest = VALID_MANIFEST
    if artifact == "shortlist":
        shortlist = shortlist.replace(
            '"source_type":"article"}',
            '"source_type":"article","score":Infinity}',
            1,
        )
    elif artifact == "claims":
        claims = claims.replace(
            '"doi":"10.1000/full"',
            '"doi":"10.1000/full","quantitative_details":NaN',
            1,
        )
    else:
        manifest = manifest.replace("{\n", '{\n  "score": -Infinity,\n', 1)

    issues = validate_knowledge_extraction(shortlist, claims, manifest, "rc-test")

    expected_path = {
        "shortlist": "literature/shortlist.jsonl",
        "claims": "knowledge/extractions.jsonl",
        "manifest": "knowledge/extraction_manifest.json",
    }[artifact]
    assert any(
        issue.path == expected_path and "must be valid JSON" in issue.message
        for issue in issues
    )
