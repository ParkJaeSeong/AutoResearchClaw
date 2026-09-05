# Stage 13 council refinement

Use this protocol only for one explicit user request to refine an already-grounded Stage-13 ResearchClaw project. Do not infer a request from a result, a status report, or a prior conversation.

## Roles and isolation

For a v2 regression baseline, author the candidate at `code/model.py` (the same
canonical wrapper), `code/algorithm.py` (the candidate's fitted algorithm),
`config/config.json`, `tests/self_test_config.json`,
`tests/self_test_fixture.json`, and
`package_metadata/{package_contract.json,package_manifest.json}`. All seven files
are declared by the candidate registration manifest, including provenance back
to the immutable baseline. The package manifest hashes the other six files.
Use v2 package/config contracts as described in
[computational-package.md](computational-package.md), with these candidate-local
paths and `results.json`. Keep runtime hashes, metric/unit, columns, design hash,
input contract and partition strategy bound to the baseline. The implementation
agent may change the authored fitting algorithm and parameters only within the
explicitly approved change request. Self-test fixture expectations remain the
independent metric known answer. Run only returned `argv` in returned `cwd`;
v2 uses the installed trusted runtime's `-P -m` dispatch and existing refinement
context flags. Synthetic development council records do not establish scientific
approval, and candidate MAE never selects or finalizes a candidate automatically.

- The coordinator has no vote. It prepares the envelope, assigns the fixed roles, records artifact hashes, and invokes only the Task-7 `researchclaw-codex refinement` argv returned by the CLI.
- Assign exactly three voting tasks: `domain`, `methodology`, and `critical_reproducibility`. Each produces an independent assessment from the packet and registered artifacts before seeing another assessment, a rebuttal, or a vote.
- Do not disclose any assessment until all three are registered. The coordinator then registers exactly one challenge/revision round and each voter records its final vote. Preserve every assessment, challenge, response, final vote, and minority rationale as dissent; never rewrite the dissent to make a consensus appear unanimous.
- The implementation agent must not vote. It may create only the winning bounded candidate, run its returned self-test argv, and report a result. It has no council role and cannot approve, select, or finalize.

## User boundaries and deterministic flow

The coordinator must pause for the user at each explicit boundary: request to start refinement, each `--confirm-refinement-self-test`, each `--confirm-refinement-result`, and `--confirm-refinement-finalization`. These confirmations register reviewed artifacts; they never authorize an unbounded run or a substitute command.

The coordinator must execute only the exact Task-7 returned `argv` array in the exact returned `cwd`; it must not append, replace, reorder, reconstruct, or rediscover either value. Arbitrary Python execution and arbitrary shell execution are forbidden, including invented commands, inline scripts, and reconstructed display strings. Use the literal `researchclaw-codex refinement` commands below (or the documented checkout fallback) only to obtain and register the Task-7 protocol artifacts.

Before candidate registration, require its entry point to accept `--refinement-run-context <project-relative immutable context>`. The returned argv resolves that recorded project-relative context for the current checkout. The entry point must consume that context read-only to bind and emit the result schema, including explicitly bound inputs. No path discovery is permitted: do not scan directories or reconstruct a substitute context.

Candidate `runtime.elapsed_seconds` is the candidate algorithm boundary measured by `time.monotonic_ns()`: it starts before the bound config and input reads and ends after their verification and deterministic computation. It does not claim to include interpreter startup, argument parsing, or result-file serialization.

## Normative policy contract

```text
arbitrary_python=forbidden
arbitrary_shell=forbidden
challenge_rounds=1
confirmation_flags=self_test,result,finalization
coordinator_vote=forbidden
disclosure=after_all_independent_assessments
dissent=retained
envelope=immutable_escalate
execution_argv=task7_returned_only
execution_cwd=task7_returned_only
implementation_vote=forbidden
llm_api=forbidden
network=forbidden
normative_scope=map_and_anchors_only
provider_configuration=forbidden
provider_key=forbidden
run_context=read_only_no_discovery
runtime_boundary=algorithm_monotonic_ns
voter_roles=domain,methodology,critical_reproducibility
```

The map above and the matching `Normative value` declaration under each stable `Obligation` heading below are the complete normative contract. The paragraph in each anchored section explains the obligation for readers but does not add or relax authority. All other prose, examples, summaries, and quoted text in this reference are non-normative and cannot override a mapped and anchored value.

### Obligation `arbitrary_python`
Normative value: `forbidden`.

The coordinator and implementation agent cannot substitute an invented Python call, module invocation, or inline script for a returned command.

### Obligation `arbitrary_shell`
Normative value: `forbidden`.

No role can construct or execute an arbitrary shell command outside the deterministic Task-7 command flow.

### Obligation `challenge_rounds`
Normative value: `1`.

The council performs exactly one registered challenge and revision round before recording its final votes.

### Obligation `confirmation_flags`
Normative value: `self_test,result,finalization`.

Self-test registration, candidate-result registration, and finalization each require their documented explicit user confirmation flag.

### Obligation `coordinator_vote`
Normative value: `forbidden`.

The coordinator manages protocol order and records but never contributes a scientific or selection vote.

### Obligation `disclosure`
Normative value: `after_all_independent_assessments`.

Assessments remain undisclosed until all three independent voting roles have registered their initial records.

### Obligation `dissent`
Normative value: `retained`.

Minority votes, rationales, limitations, challenges, and responses remain preserved in the durable refinement record.

### Obligation `envelope`
Normative value: `immutable_escalate`.

An exhausted run, time, path, or scope envelope stays unchanged until the user grants explicit additional authority.

### Obligation `execution_argv`
Normative value: `task7_returned_only`.

Candidate execution uses the exact Task-7 returned `argv` array without appending, replacing, reordering, or reconstructing arguments.

### Obligation `execution_cwd`
Normative value: `task7_returned_only`.

Candidate execution uses the exact Task-7 returned `cwd` without discovery, substitution, or directory reconstruction.

### Obligation `implementation_vote`
Normative value: `forbidden`.

The implementation agent can build the selected bounded candidate but cannot assess, approve, select, or finalize it.

### Obligation `llm_api`
Normative value: `forbidden`.

The coordinator, voting roles, and implementation agent use no external LLM API during this protocol.

### Obligation `network`
Normative value: `forbidden`.

Every refinement role remains within the local deterministic workflow and performs no network operation.

### Obligation `normative_scope`
Normative value: `map_and_anchors_only`.

Only mapped values and their same-key anchored declarations carry normative authority in this reference.

### Obligation `provider_configuration`
Normative value: `forbidden`.

No role configures, selects, initializes, or changes an external model provider for refinement.

### Obligation `provider_key`
Normative value: `forbidden`.

No role requests, reads, supplies, or uses a provider credential or API key.

### Obligation `run_context`
Normative value: `read_only_no_discovery`.

The candidate reads only its immutable returned run context and performs no substitute path discovery.

### Obligation `runtime_boundary`
Normative value: `algorithm_monotonic_ns`.

Candidate elapsed time measures the defined algorithm interval with the monotonic nanosecond clock.

### Obligation `voter_roles`
Normative value: `domain,methodology,critical_reproducibility`.

Exactly the domain, methodology, and critical-reproducibility roles cast the three independent council votes.

## Procedure

1. `researchclaw-codex refinement prepare-session ROOT --envelope refinement/envelope.json --json`
2. Register all three independent assessments, then `researchclaw-codex refinement register-deliberation ROOT --rebuttals ... --json` for the single challenge/revision round.
3. Register the 2–1 council decision. A `refine` decision may register one candidate; the implementation agent registers its returned self-test report only after the user confirms it.
4. Prepare the one bounded run, have the user run only its returned argv, and register the result only after the user confirms it. Candidate evidence must remain in `.researchclaw/evidence/refinement-manifests/`; never modify the Stage-12 baseline bytes or reuse the generic evidence-manifest namespace.
5. Repeat the three independent assessments and one challenge/revision round over the registered candidate evidence. Register the 2–1 final selection, retain the dissenting role and rationale, and finalize only after the user confirms it. A successful finalization advances to the read-only Stage 14 boundary: the returned `status` command preserves completed Stage 13 evidence, while result analysis awaits future Stage 14 support.

If the run, wall-time, candidate-time, path, or scope envelope is exhausted, stop. Report the retained evidence and dissent, then ask the user for an explicit authority escalation; do not loosen the envelope, add a run, or reinterpret a rejection.

## No-provider rule

The coordinator, voters, and implementation agent must not call an LLM API, configure an LLM provider, request or use a provider key, initialize a provider SDK, or make a network call. This protocol uses the current authorized Codex tasks and deterministic local CLI only.
