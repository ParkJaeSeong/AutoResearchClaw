import pytest
from researchclaw.codex.cli import build_parser


def test_atlas_service_cli_requires_explicit_request_key_and_supports_resume():
    p=build_parser()
    args=p.parse_args(['research','atlas-service','ask','/tmp/research','--key','k1','--question','Why?','--question-id','q1','--previous','k0'])
    assert args.service_action=='ask' and args.key=='k1' and args.previous=='k0'
    args=p.parse_args(['research','atlas-service','poll','/tmp/research','--key','k1'])
    assert args.service_action=='poll'
    with pytest.raises(SystemExit):p.parse_args(['research','atlas-service','ask','/tmp/research','--question','Why?','--question-id','q1'])


def test_advance_cli_exposes_resumable_wait_without_deadline():
    p = build_parser()
    args = p.parse_args(['research', 'atlas-service', 'advance', '/tmp/research', '--key', 'k1', '--watch', '--interval', '2'])
    assert args.service_action == 'advance' and args.watch and args.interval == 2
    with pytest.raises(SystemExit):
        p.parse_args(['research', 'atlas-service', 'advance', '/tmp/research', '--key', 'k1', '--interval', '0'])


def test_native_question_command_uses_registered_id():
    p=build_parser()
    args=p.parse_args(['research','atlas-service','ask-question','/tmp/research','--key','k','--question-id','q'])
    assert args.service_action=='ask-question' and args.previous is None


def test_council_command_requires_explicit_host():
    p=build_parser()
    args=p.parse_args(['research','atlas-service','review','/tmp/research','--key','k','--host','/tmp/codex'])
    assert args.service_action=='review' and str(args.host)=='/tmp/codex'
    with pytest.raises(SystemExit):p.parse_args(['research','atlas-service','review','/tmp/research','--key','k'])


def test_outcome_cli_reads_explicit_decision_file():
    p=build_parser()
    args=p.parse_args(['research','atlas-service','outcome','/tmp/research','--key','k','--file','/tmp/outcome.json'])
    assert args.service_action=='outcome' and str(args.file)=='/tmp/outcome.json'
