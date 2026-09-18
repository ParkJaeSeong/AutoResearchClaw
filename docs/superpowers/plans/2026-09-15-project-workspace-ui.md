# Project workspace UI implementation plan

User-approved design: project selector → M1/M2/M3 → research stages → actual execution episodes. Preserve research records and organize storage. This is UI/storage work, not a research-state or POC-completion decision.

## Shared contract

- Workspace catalog explicitly enabled by `research view ROOT --workspace WORKSPACE` (legacy view ROOT remains supported).
- Catalog lists registered project IDs and trusted local roots. No global mutable selected root; every request selects its project with `?project=UUID`. Unknown IDs fail closed. Legacy omitted project uses configured ROOT.
- `GET /api/projects` → `{projects:[{id,name,topic,storage_path,layout}],default_project_id}`. `POST /api/projects` closed `{name,topic,request_id}` → same project entry under `project`. Idempotent request ID; conflicting payload rejected. Origin/content-size safeguards match existing POST routes.
- `GET /api/project-files?project=UUID` → `{files:[{path,size,url}],storage_path}`. Expose only explicit public folders documents/materials/outputs, never .researchclaw, .atlas-link, runs or symlink escapes. File URLs bind project. Existing private artifact allowlist remains unchanged.
- New projects live in WORKSPACE/projects/<ID-or-stable-UUID>/ with project.json, documents/, materials/, outputs/M1,M2,M3/, runs/ and original .researchclaw store. ID and step identity do not depend on display name. Return policy uses existing evidence-driven command. No auto research/Atlas run or scientific approval.
- Existing project root remains authoritative and is catalogued as linked. No moving/deleting hash-backed records, no symlink replacement. Final public bundle copied with hash verification into its documents/outputs; original files remain intact. Legacy locations and mapping documented.
- Client uses project-bound API URLs for every read/write/artifact. Project switching uses page navigation, preserving per-project selection/head/hash and form drafts. No carry-over of old project view or in-flight response into new one.
- Sidebar holds prominent project selector/new button, overview, expandable M1 stage navigation, M2/M3 honestly unsupported (informational pages), project materials, Atlas/settings. Existing standard CI/toggle/rail/mobile contract retained.
- Group existing M1 nodes: scope/questions; search/screen/collect/extract; synthesize/hypothesize; experiment-design; readiness. Actual node/episode IDs and sequence remain unchanged. Explicit UI mapping for legacy named episodes, no invented execution.
- Stage selection filters/reveals its linked actual episodes and node records. Full timeline accessible. M2/M3 do not show M1 content or imply execution support.

## Tasks

- [x] Storage/catalog + HTTP/CLI routes with isolation, malformed paths, idempotent create, private file protection tests.
- [x] UI selector/create, project-bound API, milestone/stage navigation and stage/episode distinction with focused browser tests.
- [x] Register existing project, consolidate verified public bundle, document storage/mapping and preserve original hashes/HEAD.
- [x] Independent review, focused regressions, live server + desktop/mobile/light/dark checks; record limitations.

Ruling: no scientific state updates or new research runs during this task. Existing disputed POC conclusion remains history, not authority for new completion badges.
