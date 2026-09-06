# Stage 13: correcting an overbroad change list

`change_request.paths` names files whose bytes actually change, not the complete
package or an allowed edit surface. Unchanged canonical wrappers still belong in
the candidate package, but not in that list.

Before candidate registration, a council can correct an overbroad list without
rewriting its registered decision. This is a single append-only correction per
round, restricted to a nonempty strict subset of the original list. It cannot
change the algorithm, scientific rationale, action, evidence, runtime budget,
input data, or any approval. Broader changes need a separate design, not this
command. A registered candidate cannot receive a new correction.

## Procedure

1. Compare candidate file hashes with their canonical baseline sources. Identify
   the exact changed paths; do not alter fixed wrappers to make a list match.
2. Show the original decision, candidate diff and proposed shortened list to
   every original supporting role. Obtain each role's actual independent
   reaffirmation that the scientific decision and constraints remain unchanged.
   Never manufacture confirmations or treat coordinator approval as a vote.
3. Save a submission outside the closed candidate directory with these fields:
   - `schema_version`: integer `1`
   - `project_id`, `session_id`: unchanged identifiers
   - `decision`: original registered `{path, sha256, size}` reference
   - `change_request`: `{paths: [...]}` containing only the corrected paths
   - `confirmations`: one object per original supporting role, containing
     `role`, its original `producer`, the identical `change_request`, and a
     nonempty string-list `rationale` recording the reaffirmation
4. Register with the installed CLI:

   ```sh
   researchclaw-codex refinement register-path-correction PROJECT \
     --correction submissions/path-correction.json --json
   ```

   The CLI preserves `decision.json` and writes the immutable sibling
   `path_correction.json`. Exact replay is idempotent; replacement is forbidden.
5. Update the still-unregistered candidate manifest's `change_request` and add
   `path_correction: {path, sha256, size}` referencing the registered correction.
   Keep its `decision` pointing to the unchanged original decision. Re-register
   the candidate normally. The original exact changed-file check still applies.

The CLI validates identities and structure; it does not establish that an agent
really deliberated. Agent provenance must come from the actual task history.
Self-test, execution, result registration and final selection retain their own
confirmation gates. This command neither runs a candidate nor advances Stage 13.
