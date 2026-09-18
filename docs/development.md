# 현재 개발 진입점

확인: 2026-09-19. 파일 존재·호출 관계 확인 기록이며 전체 실행 검증 보고서가 아니다.

## 실제 경로와 남은 연결

| 책임 | 현재 경로 | 상태 |
|---|---|---|
| 프로젝트 생성·목록 | `researchclaw/codex/project_workspace.py` | 생성·등록 기능 존재. 생성은 연구 실행이 아님 |
| 현행 CLI·UI | `researchclaw/codex/research_cli.py`, `research_viewer.py`, `research_ui/` | 연구 기록과 실행 기록 조회 |
| 영속 연구 상태 | `researchclaw/core/research_graph/store.py`, `commands.py` | 기존 기록과 버전·명령 처리 유지 |
| 작업 설명·검토 기록 | `work_episodes.py`, `work_execution.py`, `work_followups.py` | 새 lifecycle와 별도 경로. 에피소드 종료는 단계별 검사 통과가 아님 |
| 새 실행·검사 | `execution_contracts.py`, `execution_lifecycle.py`, `execution_view.py` | `evidence_review` 한 종류만 지원 |
| 새 역할 실행 | `researchclaw/codex/execution_review_runner.py`, `execution_host.py` | 모델 프로필 적용과 전 단계 자동 실행 미완성 |
| Documents→Atlas import 검토 | `document_handoff*`, `import_review*`, `import_council.py` | 기존 요청·검토 경로 보존. 공통 lifecycle 통합 대상 |
| Atlas 질의·응답·지식 반영 | `atlas_*`, `knowledge_*`, `service_*`, `followup_review.py` | 외부 계약별 경로 보존. 단계 종료·후속 실행 통합 대상 |
| 이전 M1 호환 | `m1_cli.py`, `m1_viewer.py`, `m1_ui/` | CLI와 테스트가 참조함. 삭제 전 호환/이전 검증 필요 |
| 원본 파이프라인 | `researchclaw/pipeline/`, 루트 `sentinel.sh` | 현행 자동 연구와 다름. 원본 동작 대조·회귀 테스트 때문에 유지 |

## 개발 순서

1. [단계별 기준](superpowers/specs/2026-09-19-m1-stage-checklist-design.md)을 공통 실행 계약으로 구현한다. 실제 모델 ID·추론 설정과 시작/종료 검사를 같은 실행에 묶는다.
2. 범위→질문→검색 접수까지 실제 실행·UI·재개를 함께 연결해 검증한다.
3. 기존 Documents/Atlas 계약을 바꾸지 않고 공통 실행 기록에 반환한다.
4. 종합·가설·설계·준비·최종 검토를 연결하고 전체 M1을 검증한다.
5. 대체 경로의 호환 검증이 끝난 뒤 중복 실행기·화면을 제거한다.

새 실행기를 추가하기 전에 위 책임 중 어디에 들어가는지 정한다. 외부 서비스 계약의 차이는 어댑터로 유지하고 단계 상태를 별도로 중복 관리하지 않는 방향으로 통합한다. 이는 후속 개발 방향이며 이미 통합됐다는 뜻이 아니다.

## 정리 규칙

- [정리 기록](../archive/legacy/2026-09-19-project-cleanup/README.md)에 실제 이동·삭제 내역을 남겼다.
- 연구 원문·응답·HEAD·요청 영수증·연동 연결 파일은 캐시로 취급하지 않는다.
- 일반 검색에서는 아카이브·연구 산출물을 제외하고 필요할 때 명시적으로 조회한다.
- 테스트 통과, 운영 반영, 실제 모델 실행, UI 확인을 각각 기록한다.

이전 1–23 단계 CLI를 사용하는 기록은 [호환 경로 운영 계약](legacy-cli.md)을 참고한다. 해당 경로의 검증을 새 M1 종단 검증으로 해석하지 않는다.
