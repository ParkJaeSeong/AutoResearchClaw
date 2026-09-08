# A02 implementation report

Scope: storage common helpers, isolated research-graph-v1 store, explicit operation registry, research init/inspect CLI. A01 d82bce2 was the starting dependency. No source M1 project, experiment execution, approval, installation, or publication occurred.

## Implemented API for A03

`researchclaw.core.research_graph.store.initialize_record(root: Path, *, command_id: str, state: dict, event: dict, objects: dict[str, bytes]) -> dict`

Supply the COMPLETE genesis state and every imported object. The initializer validates and fsyncs a staging store, then renames it to `.researchclaw/research_graph` once. There is no empty target HEAD followed by an import commit. Identical command/state/event/named-object bytes return the ORIGINAL genesis receipt even if HEAD subsequently advanced; other existing genesis payloads are conflicts. A03 must construct/persist stable UUID identity for retries, or read its own matching genesis before reconstruction. Never use random replacement project IDs for a retry.

State requires schema_version=1, workflow_version=research-graph-v1, canonical UUID project_id, content_origin real/synthetic/mixed, and accepts extension projection fields. Project identity cannot change in subsequent commits. A01 record contracts remain the responsibility of domain handlers/migration for structured graph records; byte storage does not reinterpret arbitrary imported legacy JSON as a new graph record.

Events are closed `{schema_version, workflow_version, type: nonempty str, payload: dict}` envelopes. Objects map logical relative POSIX names to bytes. Receipt `{schema_version,workflow_version,id,state,events,objects}` contains cumulative events and SHA256→`{sha256,size}` object refs. HEAD/commit IDs are canonical JSON SHA256. `read_head(root)` validates all reachable ancestry and all committed object bytes. No corruption repair occurs.

`commit_record(root, *, expected_head, command_id, state, event, objects)` compares command payload before optimistic HEAD check, returning original receipts on replay. Commit fingerprints exclude expected_head. Writers/init share project_transaction serialization; post-publication fsync failure must be retried before successful replay.

`commands.register_operation(name, handler)` registers explicit pure handlers. `apply_command(root, *, operation, payload, expected_head, command_id)` freezes public operation/payload fingerprint, replays before running handler, checks snapshot, then publishes under one shared lock. Handler receives detached verified snapshot/payload and returns `{state_patch,event,object_inputs}`. Public request SHA256 is stored under event payload `_command_request` (reserved by dispatcher). Unknown operations raise `unknown_operation`; no arbitrary patch or dynamic import CLI exists.

CLI: `research init ROOT --topic TEXT --content-origin real|synthetic|mixed --json [--max-returns 3] [--max-verification-runs 10]`; cost limit/observed cost None and cost_status unknown. Defaults are explicit initial configuration, not execution permission. Repeated matching init returns original genesis. `research inspect ROOT --json` returns only versions, head/project IDs, content origin and object/event counts, no bodies. A03 can extend its safe import projection in its own CLI boundary. Runtime validation/I/O failures return nonzero generic structured error without private paths.

## Evidence

RED: initial new store suite failed importing absent store/commands. CLI test failed because research parser absent. Deterministic initialization-publication race test failed with project_root_not_empty before the race handling fix.

GREEN: research store/CLI plus existing M1 store/project: 77 passed in 0.90s. Existing M1 subset remains 60 cases. Covered immutable source bytes, command replay/conflict after HEAD advance, stale HEAD, atomic complete genesis, failure before HEAD, failed fsync retry, corrupt and symlink objects, foreign M1/legacy/unrelated roots, concurrent init/writers, immutable project/version envelope, safe CLI and explicit handler registry.

Shared extraction is limited to path validation, canonical bytes/hash and fsynced byte read/write helpers. M1 wrapper symbols/error prefixes and dynamic `_write_file`, `_atomic_head`, `_fsync_directory` publication calls remain intact.

Combined regression: `.venv/bin/python -m pytest tests/codex_native/research_graph tests/codex_native/m1/test_store.py tests/codex_native/m1/test_project.py tests/codex_native/m1/test_m1_cli.py tests/codex_native/m1/test_packet_cli.py tests/codex_native/test_cli.py -q` — 299 passed in 86.95s. `git diff --check` clean.

Independent review pending root coordinator. These are automatic structural/storage fixtures, not host independence or actual research acceptance.
