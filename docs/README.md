# Pilot 문서 진입점

## 현재 개발

- [실행 경로와 남은 통합 작업](development.md): 실제 코드 진입점, 미완성 연결, 보존해야 할 경로.
- [M1 단계별 통합 점검 기준](superpowers/specs/2026-09-19-m1-stage-checklist-design.md): 11단계의 입력·모델·훅·산출물·되돌림·UI 기준. 설계 초안이며 구현 완료가 아니다.
- [실행 생명주기 설계](superpowers/specs/2026-09-18-pilot-execution-lifecycle.md): 공통 실행 기록과 첫 구현 범위.

## 유지하는 공통 기준

- [연구 운영 기준](research/guides/README.md), [작업 패킷](research/prompts/m1/task-packet.md), [Pilot 스킬](../skills/researchpilot/SKILL.md).
- [Atlas 연동](integrations/researchatlas/README.md): 실제 계약과 소비자 기록. 신규 설계와 배포된 기능을 구분한다.
- [UI 가이드](ui/README.md): 화면 구성·문구·상태·검수 기준.

## 과거 기록

- [이전 고분자 복합소재 사례](research/2026-09-10-polymer-sdl/README.md): 과거 사례 기록이며 현재 활성 프로젝트를 뜻하지 않는다.
- [원본·이전 자료](../archive/README.md), [이번 정리 내역](../archive/legacy/2026-09-19-project-cleanup/README.md).
- `superpowers/plans/`, `superpowers/acceptance/`, `evaluations/`, `audits/`는 필요한 작업의 문서만 읽는다. 과거 검증을 현재 전체 시스템 검증으로 해석하지 않는다.

연구 원형·에이전트 원응답·재개 상태는 기존 프로젝트 저장 경로에 보존한다. 일반 소스 검색은 `.ignore`로 아카이브와 로컬 산출물을 제외한다. 과거 기록을 조사할 때에는 `rg --no-ignore`와 대상 경로를 명시한다.
