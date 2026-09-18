# Composite knowledge job protocol fixture

2026-09-18. `protocol.json` was captured through a real, temporary loopback uvicorn HTTP service using httpx. It is **synthetic**, not production evidence. Generation command: `uv run --no-sync python tests/export_knowledge_protocol.py`.

The ask child is a fake executable. The update proposal is a fixed synthetic callback. Index failure/recovery is injected. No external LLM, real embedding model, operating library, existing research job, or Documents conversion is used. Independent tests connect the real BM25/graph/vector storage modules with synthetic embeddings.

Captures include dedicated info, submit, partial, resume, persisted, completed resume replay, same-key submit replay, request conflict, malformed range, manifest, EOF and out-of-range responses. `artifacts` contains every QA/page/stage-result chunk, with exact bytes preserved as base64. Verify decoded full hashes, instance/job identity, QA-local candidate identity, and stage history before consuming. The original answer remains identical between partial and persisted; only one ask and one proposal are generated. Credentials are not included. Source references point only to this now-deleted temporary library, not to a live A1 source service.

Package failure/recovery is also covered by `test_package_failure_resume_preserves_qa_and_one_ask` in `tests/test_knowledge_worker.py`: immutable blocked/ready package stage records, restart, one ask, and resume replay. It is not included as a second HTTP capture in this fixture.

Accepted normative contract/plan hashes remain unchanged. This is producer protocol output for Pilot adapter cross-check, not joint acceptance or live-model validation.
