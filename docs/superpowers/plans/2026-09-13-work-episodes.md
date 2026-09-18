# 작업 회차 기록과 스택 UI Implementation Plan

> **For agentic workers:** Use superpowers:subagent-driven-development to implement and review the bounded tasks below.

**Goal:** 단계와 수행 순서를 분리한 회차를 저장하고 연구 과정 화면에서 최신 시작 순서로 읽는다.

**Architecture:** 기존 불변 research_graph 저장소와 apply_command의 잠금·HEAD·멱등 처리를 재사용한다. work_records 비용 집계와 별개인 work_episodes 컬렉션을 추가한다. 기존 기록을 추정으로 이전하지 않는다.

**Tech Stack:** Python, 기존 HTTP viewer, vanilla JavaScript, pytest, node:test, Playwright.

**Spec:** ../specs/2026-09-13-pilot-autonomous-research-design.md

## Global Constraints

- 실제 연구 상태, Atlas, M1 완료 조건을 변경하지 않는다. 합성 프로젝트에서 검증한다.
- 순서는 시작 등록 시 정수로 발급하며 단계명·완료 순서와 별개다.
- 회차 기록은 실행자가 남긴 보고이며 실제 프로세스 실행을 증명하지 않는다.
- 최초 범위는 저장·조회와 개발 검토 규칙이다. 기존 실행기의 자동 기록, 브라우저 검토 제출, Markdown 내보내기, 상세 API 지연 조회는 다음 작업으로 남긴다.
- 기존 개인 작업이 섞인 checkout이므로 자동 commit·reset하지 않는다.

## Task 1: 회차 명령과 조회

Files: `researchclaw/core/research_graph/work_episodes.py` (new), `commands.py`, `views.py`, `tests/codex_native/research_graph/test_work_episodes.py` (new).

Interfaces:
- `episode.start`: `{id, stage, title, purpose, depends_on:[], return_to:null|id, return_reason:null|string, review_required:bool}`.
- `episode.note`: `{id, kind:'dialogue'|'tool'|'output', author, text}`. 공개 가능한 보고만 입력한다. 독립 토론의 미공개 발언을 자동 수입하지 않는다.
- `episode.conclude`: `{id, execution_status:'finished'|'failed', judgment, remaining, next_action, next_reason}`. 종료 후 원 회차는 수정하지 않고 재검토 회차를 만든다.
- `episode.review`: `{id, decision:'continue'|'revise', reviewer, feedback}`. 종료한 회차에 한 번만 기록. CLI는 로컬 권한의 검토자 선언이며 사용자 인증이 아니다.
- 시작은 모든 depends_on이 finished이고 검토가 불필요하거나 continue일 때만 허용한다. revise는 원 결과를 지우지 않고 독립 재검토 회차(return_to)로 이어간다. return_to는 문맥 연결이며 실행 의존성이 아니다.
- `view.work_episodes`: row = 시작 필드 + sequence, execution_status, notes[], conclusion:null|object, review_status(not_required|pending|continued|revision_requested), review:null|object. 미기록 기존 프로젝트는 [].

- [x] RED: init→start 두 회차→먼저 시작한 회차 종료, sequence=[1,2] 보존. 미완료 의존·검토 대기·수정 요청은 거절, 독립 회차는 허용. 중복 command 재전송·HEAD 충돌·과거 HEAD·notes 순서·종료 후 불변·잘못된 필드 검사.
- [x] GREEN: 엄격한 필드 검사를 하는 순수 handler와 명시적 registry를 추가하고 공개 view를 연결한다.
- [x] VERIFY: `.venv/bin/python -m pytest tests/codex_native/research_graph/test_work_episodes.py -q`.

## Task 2: 공통 카드 UI

Files: `researchclaw/codex/research_ui/episodes.js` (new), `app.js`, `styles.css`, `research_viewer.py`, `tests/codex_native/research_graph/test_episode_ui.mjs` (new).

Consumes: view.work_episodes; Produces: `renderEpisodes(root, view)` and `orderedEpisodes(view)`.

- [x] RED: reversed sequence regardless of finish state; input array unchanged; missing collection empty; hostile text inert; closed cards expand to purpose/conclusion/process/outputs; distinct pending review.
- [x] GREEN: 연구 과정 상단에 회차 스택, 단계·회차·작업 상태·검토 상태 표시. details/data-key로 펼침 보존. 기존 단계 지도와 조회 기능 유지. 기록이 없으면 기존 기록에 회차가 없다는 안내를 보여준다.
- [x] VERIFY: `node --test tests/codex_native/research_graph/test_episode_ui.mjs tests/codex_native/research_graph/test_research_ui.mjs`.

## Task 3: 통합 검증과 사용 안내

Files: `docs/ui/components.md`, `docs/ui/review.md`, `docs/research/guides/work-episodes.md` (new), synthetic artifacts under `output/evaluations/work-episodes/`.

- [x] 합성 프로젝트에서 탐색→분석 종료/검토 대기→독립 재탐색을 기록해 실제 viewer HTTP로 확인한다.
- [x] 밝게/어둡게, 1440·768·390px에서 펼침·넘침과 원문 표시를 확인한다.
- [x] backend/UI 독립 리뷰, 관련 기존 테스트, diff check 결과와 미구현 범위를 기록한다.

## Decisions

개발 검토는 회차별 review_required로 먼저 제공한다. 프로젝트 기본 설정과 실행기 자동 적용은 다음 통합에서 수행한다. 실험 권한이나 기존 gate를 대체하지 않는다. 구조화 기준 저장은 기존 불변 저장소를 유지하며 읽기용 work/ 폴더 출판은 별도 작업으로 분리한다.

## Execution result

2026-09-13: Task 1–3 첫 구현·검증 완료. backend18 + 기존Python15 + Node40 통과, 합성 브라우저10검사 통과. 자동 실행 연계는 Global Constraints에 명시한 다음 범위다. 로딩 성능 해결을 주장하지 않는다.
