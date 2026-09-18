# Atlas completion review worker plan

> Execute inline with superpowers:executing-plans.

Goal: Explicitly started local observer receives results, prepares frozen input, and runs individual review once per task. Preserve the existing completed trial without model replay.

Scope: existing approved individual review and trigger design. No synthesis, source collection, research adoption, UI deployment or OS startup.

- [x] Add regression tests: replay skips completed council; changed context or missing page blocks only its task; project lock prevents overlapping worker; errors are stored for inspection rather than silent model retry.
- [x] Implement `import_review_worker.py`: finite `tick` function, explicit CLI and 60 second watch. Lock one project during dispatch, call existing handoff cycle, reconcile and prepare inputs, invoke existing council, save result reference after completion. No global time limit. Keep per-task errors independent.
- [x] Expand host role prompt responsibilities with role version, bias, competing explanations, input receipt and limits. Preserve no peer disclosure in initial phase and source provenance boundary. Do not repeat completed trial solely for prompt improvement.
- [x] Validate existing PC/CNT completed trial and attach to queue result using task ID/packet hash. Exercise worker with a callback that fails if a model is launched. Check HEAD unchanged.
- [x] Run handoff/import/council regression tests and record delivery limits.

Delivery: explicit watcher started on the existing PC/CNT project. Existing completed trial attached by task/packet hash and reused without model calls; HEAD unchanged. Role prompt v2 adds responsibilities, conditions, bias, competing explanations and input receipt. These prompts apply to new runs; the prior trial was not rerun. Regression suite 44 passed plus added project lock test passed separately. UI and OS service installation remain separate. The project lock coordinates this worker only, not all pre-existing manual research writers.
