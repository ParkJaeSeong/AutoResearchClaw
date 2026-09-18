# 연구 실행 문서 요구사항 감사

감사일: 2026-09-18. 대상 checkout: `.worktrees/m1-research-graph`. 이 문서는 문서의 약속·수락 조건과 문서가 스스로 밝힌 구현 경계를 대조한다. 코드·현재 프로세스·운영 연구 상태를 검증한 보고서가 아니다. 외부 서비스를 호출하거나 연구 상태를 바꾸지 않았다.

## 핵심 판단

1. **사용자가 기대한 최종 제품은 단일 검토 CLI가 아니라 현재 마일스톤까지 이어지는 연구 실행이다.** 공통 수신, 검토 실행, 후속 ask 각각의 완료가 자율 루프 완료로 승격되면 안 된다. 최신 로드맵도 지속 관찰기·다중 역할 입력 장벽·모델 설정·표준 산출물·UI를 남은 일로 명시한다.
2. **시작/종료 훅·실패 시 재작업·중간 발언 표시 약속은 존재하지만, 하네스 계약은 아직 상세 수락 기준이 부족하다.** 9/18 리팩토링 완료 기록이 새 하네스 구현 완료를 뜻하지 않는다고 명시한다.
3. **자동 검사와 의미 검토를 분리해야 한다.** 현행 프롬프트 규약의 상당 부분은 조정자의 수동 의무이며 CLI/API 채택 경계까지 강제하는 자동 검사기는 후속이다.
4. **문서 상태가 시점별로 중첩된다.** 9/09 고정 복귀 예산·M2 설계 경계, 9/13 개발 검토 대기, 9/18 자동 M1 종료·정책 채택을 같은 수준의 최신 규칙으로 읽으면 충돌한다. 과거 실행 기록은 보존하되 새로운 연구 정책은 AGENTS.md와 뒤의 명시적 합의를 우선해야 한다.

## 요구사항 추적표

표의 ‘검증 요구’는 이번 감사에서 통과했다는 뜻이 아니다. `현재`는 현재 운영 합의, `설계/후속`은 명시적 요구이되 구현 완료가 아님, `역사`는 과거 범위/회귀 보존 의무다. 문서 위치는 저장소 상대 경로와 줄 번호다.

| ID | 요구사항·교차 합의 | 근거 | 상태·누락되기 쉬운 수락 기준 |
| --- | --- | --- | --- |
| DOC-01 | 허용된 현재 마일스톤까지 자율 진행하고 다음 마일스톤 전 멈춘다. 단계마다 승인을 새로 요구하지 않는다. | `AGENTS.md:13`; `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:8,16-20,157` | 현재. 실제 클릭 없는 M1 진행과 경계 정지의 종단 증거 필요. 작업 수 0/외부 completed를 완료로 사용 금지. |
| DOC-02 | M1은 연구에서는 설계·착수 준비 포함, 조사·계획에서는 목적별 작성 입력 준비. M4를 M3 뒤 필수로 두지 않는다. | `AGENTS.md:19-31`; `docs/research/prompts/m1/protocol.md:31-37` | 현재. 연구/평가/계획 세 경로에 같은 실험 gate를 일괄 적용하지 않는 검사 필요. |
| DOC-03 | 시작 전 목적·페르소나·필수 입력 접근·출력/검수 기준을 검사한다. | `docs/research/prompts/m1/protocol.md:25,43-54,113-118,134-138`; `docs/research/prompts/m1/task-packet.md:14-60` | 현재 운영/자동화 후속. 배정 프롬프트는 실행 payload schema가 아님. 입력 미확인 시 영향 작업만 보완해야 한다. |
| DOC-04 | 종료 시 형식·참조·버전·실행 상태와 의미 채택을 구분한다. 실패 초안은 보존하되 채택/완료로 승격하지 않는다. | `docs/research/prompts/m1/protocol.md:109-122`; `docs/research/prompts/m1/quality-checks.md:27-36` | 현재 운영/후속. UI 밖 CLI/API 우회와 재시작 후 동일 거부 시험이 필요. |
| DOC-05 | 시작/종료 훅, 훅 실패에 따른 재작업, 도구 완료→배정→반환, 발언별 기록, 무인 복구를 제공한다. | `docs/superpowers/plans/2026-09-18-harness-refactor-foundation.md:3,14-16` | 설계/후속. 훅 API·판정 상태·재실행 식별자·실패 후 소유자·종료 원자성의 수락 기준이 해당 문서에 없음. 리팩토링 검증 숫자로 완료 대체 불가. |
| DOC-06 | 단계 종류와 수행 순서를 분리하고 돌아오면 이유·영향·이전 회차를 연결한 새 기록으로 남긴다. | `docs/research/guides/work-episodes.md:3,42,48`; `docs/superpowers/specs/2026-09-13-pilot-autonomous-research-design.md:17-25` | 현재/일부 구현 기록. 과거 결과 덮어쓰기 없이 병렬 시작 순서 유지와 실제 이동 표시 필요. |
| DOC-07 | 재검토는 공백→영향 판단→증거→종료 조건→미확인 시 처리로 결정하며 횟수만으로 중단/인계 차단하지 않는다. | `docs/research/guides/return-policy.md:3-21,39-62`; `docs/research/prompts/m1/protocol.md:126` | 현재. 기존 프로젝트 정책 보존, 명시 변경 필요. assess-work가 모든 경로에 자동 연결됐다고 주장 금지. |
| DOC-08 | 반복은 같은 질문·입력·작업·기준의 의미로 판단한다. UUID/문구/역할 변경만으로 새 근거로 세지 않는다. | `docs/superpowers/specs/research-governance/lifecycle.md:47`; `docs/research/guides/return-policy.md:60-62` | 현재. 자연어 의미 동등성을 완전 자동으로 판단한다는 보장 없음. 과학적 가치와 입력 hash 변경을 구분할 평가 필요. |
| DOC-09 | 같은 snapshot으로 독립 초기 의견을 받고 전원 제출 뒤 공개한다. 새 자료는 새 revision이다. | `AGENTS.md:72-78`; `docs/superpowers/specs/research-governance/rules.md:7,22-28`; `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:117-123` | 현재. 공유 Atlas ask/위키를 통한 미공개 의견 누출 검사까지 필요. 역할 수/모델명은 독립성 증거 아님. |
| DOC-10 | 발언 원문·조정자 해설·도구 보고를 구분하고 발언·판단 변화·반론을 쉽게 추적한다. | `AGENTS.md:80,108`; `docs/research/guides/work-episodes.md:40,54,60-64`; `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:149` | 현재. 저장된 9개 의견이 있다는 사실과 발언별 실시간 전달을 구분. 원문/화면 일치와 미공개 상태 검사 필요. |
| DOC-11 | 자료 확보·실제 읽은 범위·용도별 사용 판단을 각각 기록한다. 출처 위치·version/hash·해석 한계를 보존한다. | `docs/research/prompts/m1/protocol.md:77,84,88-105`; `docs/integrations/researchatlas/README.md:13-15` | 현재. PDF 보유/QA 수신을 원문 직접 확인으로 승격 금지. 동일 실험 재인용도 독립 근거로 집계 금지. |
| DOC-12 | 핵심 주장만 실제 지지 관계·반례를 검토하고 탐색/초안에는 불필요한 전체 심사를 강제하지 않는다. | `docs/research/prompts/m1/protocol.md:11-25,90-92`; `docs/research/prompts/m1/task-packet.md:3,79-85` | 현재. 결함의 의존 범위만 보류하는 정상/거부 사례 모두 필요. 총점·다수결로 핵심 결함 상쇄 금지. |
| DOC-13 | 피드백은 당시 결론 버전에 묶고 접수→영향→재검토→반영 여부→수정 결론을 보존한다. | `AGENTS.md:84-93`; `docs/research/guides/work-episodes.md:76-88` | 현재. 피드백 저장/후속 계획 저장/실제 후속 실행은 별개. 진행 중인 의존 작업에 피드백 도착 시 처리는 9/13 설계 56행에서 후속으로 남음. |
| DOC-14 | 모델/추론 프로필은 앱 사본·기능별 선택·지원 옵션 검증·작업 시작 snapshot을 제공한다. 요청값/확인값/미확인을 구분한다. | `docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md:41-49,102-108` | 승인된 개발 기본안/후속. 두 작업에 서로 다른 지원 설정, 실행 중 변경/삭제, 인증 오류, 미지원 옵션 시험 필요. persona≠model; 실패 자동 전환 금지; CLI 전역 설정 덮어쓰기 금지. |
| DOC-15 | 단계 산출물은 versioned JSON 기준에서 Markdown을 생성하고 세 단계 이상을 같은 renderer로 읽는다. | `docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md:51-58`; `docs/superpowers/specs/2026-09-13-pilot-autonomous-research-design.md:42-50` | 설계/후속. schema·renderer·출처까지 역추적·과거 버전 재현·변환본 표시가 수락 기준. 텍스트 note만으로 완성 아님. |
| DOC-16 | 마일스톤 산출물을 manifest/hash/읽기용 요약으로 Presentation에 인계하고 반환 보고서의 원 패키지 버전을 연결한다. | `docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md:69-75,104` | 설계/후속. 소비자 API 존재 가정 금지. 로컬 경로 문자열만 전달하지 말고 필요한 파일을 제공. 주요 주장→산출물→근거 역추적 필요. |
| DOC-17 | 외부 처리·내부 전달·연구 작업을 서로 다른 상태축으로 유지한다. ACK≠읽음≠검토≠채택. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:81-97`; `docs/integrations/documents-atlas/contract-v1.md:16,111-113` | 현재 계약. 필수 입력을 못 읽은 역할은 received 아닌 needs_input. 전달 및 읽기 제공 관측 기록 필요. |
| DOC-18 | 요청 outbox→송신, 원형 저장→inbox 전달, 작업 점유→실행, 결과 저장→수신 확인 순서와 중간 종료 복구. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:127-131`; `docs/integrations/documents-atlas/contract-v1.md:74,109-115` | 현재 계약/통합 후속. 외부 모델 exactly-once를 주장하지 않으며 중복 채택을 막아야 한다. |
| DOC-19 | 재개는 PID/대화창 아닌 work/role/round/input revision과 저장 결과로 한다. 종료된 작업 재호출을 피한다. | `skills/researchpilot/SKILL.md:16-20`; `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:89,137` | 현재. 역할 소멸은 needs_input/명시 재배정. 대화 기억 없이 복구되는 시험 필요. |
| DOC-20 | 사용자 stop은 전체 신규 실행을 막고 개별 자원 제약은 해당 작업만 대기시킨다. 늦은 결과는 보존하되 자동 채택하지 않는다. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:135-139,171` | 현재 계약. commit 직전 work/input/policy revision+generation fencing, 정지/역할 교체/완료 경쟁 시험 필요. |
| DOC-21 | rollback은 이력 삭제나 원격 취소와 같지 않다. 변경 영향을 받은 판단만 새 이벤트로 재검증한다. | `docs/superpowers/specs/research-governance/lifecycle.md:24,41,45,51`; `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:135` | 현재. import cancel≠Documents 취소≠위키 rollback. 훅 실패시 어떤 파생 상태를 무효화할지 별도 계약 필요. |
| DOC-22 | 공통 consumer 이벤트를 먼저 영속화하고 프로젝트별 분배한다. ACK 이후에도 전달 의무를 복구한다. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:95-97`; `docs/integrations/documents-atlas/contract-v1.md:109-115` | 현재 계약. 비대상 이벤트를 버리고 cursor만 이동 금지. 중복/역순/ACK 유실/재시작 시험 필요. |
| DOC-23 | 자료별 검토→통합 Atlas 질의→종합 토론→근거 부족별 적절한 후속 행동을 수행한다. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:101-113,153-157` | 설계/부분 연결. collect_sources/review/revise_design까지 실제 실행 경로가 있는지 별도 대조. ask 하나 실행 가능이 전체 루프 아님. |
| DOC-24 | answer/knowledge 복수 결과를 보존하고 wiki 저장/색인/연구 완료를 분리한다. 위키 결과만으로 토론 재생성 금지. | `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md:143-145`; `docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md:169-171` | 일부 연결 기록. 격리 fake ask 공동 HTTP 시험은 실제 모델/운영 수락 아님 (`docs/integrations/researchatlas/knowledge-update-live-check-2026-09-18.md:3,21`). |
| DOC-25 | UI는 실제 event→projection 단일 기록, 현재 위치·이유·다음 행동·대화/근거를 보여주고 서버 연결을 에이전트 생존으로 표시하지 않는다. | `AGENTS.md:112-118`; `docs/research/guides/work-episodes.md:54`; `docs/superpowers/plans/2026-09-18-harness-refactor-foundation.md:9,14` | 현재/하네스 후속. 실시간 freshness·heartbeat·끊김 표시의 구체 성능/지연 수락 기준은 불충분. |
| DOC-26 | 실제 브라우저와 실제 역할 제출을 관측해야 한다. DOM/fixture 통과만으로 완료 금지. | `docs/superpowers/specs/research-governance/ui.md:7-11`; `docs/superpowers/plans/research-governance/tasks/E06.md:19,44-48` | 미완료 작업판 기록. 선택/스크롤·단절복구·긴 발언·XSS·키보드·두 theme/viewport 및 원문 일치 확인 필요. |
| DOC-27 | 동시 mutation, HEAD 공개 전후 종료, 동일/충돌 command 재시도, 거부시 HEAD 보존, 옛 bytes 보존을 확인한다. | `docs/superpowers/plans/research-governance/tasks/E05.md:19-27,44-45`; `docs/superpowers/specs/research-governance/acceptance.md:14,17` | 현재 수락 의무. 기존 단계/M1 데이터 무변경과 checkout 밖 설치본 검증을 단위 테스트 숫자로 대체 금지. |
| DOC-28 | 단일/다중 에이전트를 고정 입력·동일 도구/예산으로 비교하고 오류·거짓 해소·반복·시간/비용을 측정한다. | `docs/superpowers/specs/research-governance/rules.md:18`; `docs/superpowers/plans/research-governance/tasks/E07.md:19-24,44-45` | 작업판 미착수. blind 판정·사전 rubric·unknown 비용 null·성능 악화 보존 필요. 합의율은 정확도가 아님. |
| DOC-29 | 새 프로젝트 전체 공개 경로로 완주하며 seed checkpoint로 우회하지 않는다. fixture/호스트/연구/브라우저/설치 검증을 구분한다. | `docs/superpowers/specs/research-governance/acceptance.md:15-20`; `docs/research/prompts/m1/quality-checks.md:34-36` | 현재 수락 의무. 운영 연구에 synthetic 검수 결론/승인을 추가하지 않는다. |
| DOC-30 | 기존 POC 가상 설계·CSV 검증 완료와 새 PC/CNT 활성 연구·실제 실험 준비를 분리한다. | `AGENTS.md:36-38`; `docs/research/2026-09-10-polymer-sdl/m1-poc-result.md:1-53` | 역사/현재 분리. POC 문서의 정밀 측정 요구를 새 연구 자동 완료나 POC 재개 요구로 오독 금지. |

## 문서상 확인된 미완료와 해석 충돌

- **후속 계획≠실행.** `docs/research/guides/work-episodes.md:80-88`은 계획만 저장하고 새 회차 배정/실행을 후속으로 둔다. 최신 로드맵 `:151-165`는 ask_atlas와 첫 단일 검토를 연결했지만 지속 watcher·여러 역할 공통 장벽·모델/표준 산출물/UI를 남긴다. 오래된 ‘후속 실행 전’ 문구와 최신 구현 기록 둘 다 범위를 명시해야 한다.
- **공통 새 하네스는 미구현.** `docs/superpowers/plans/2026-09-18-harness-refactor-foundation.md:14-16`. legacy UI 분리·71 Node/11 Python 통과·운영 재기동의 완료와 구별된다. 기존 POC 브라우저 확인도 별도라고 적혀 있다.
- **자동 hook은 규약 자동 강제와 연결해야 한다.** `docs/research/prompts/m1/protocol.md:134-140`의 후속 자동화 1–3을 훅 작업에 매핑한 수락표가 필요하다. 시작 실패가 초안 저장까지 막거나 끝내기 훅 통과가 과학적 타당성 보증으로 표시되면 규약 위반이다.
- **고정 복귀 한도 충돌.** `docs/superpowers/specs/2026-09-08-m1-contracts-design.md:38-46`의 응답 1회/추가 복귀 2회, `docs/superpowers/specs/research-governance/lifecycle.md:49`의 max_returns, `skills/researchpilot/references/pilot-runtime.md:21`의 init 기본 3회는 서로 다른 시점/엔진이다. 최신 `docs/research/guides/return-policy.md:3,16-21,62`가 연구 운영 원칙이며 저장된 정책 전환은 명시적이다. 문서 수정만으로 옛 root 정책이 바뀌지 않는다.
- **마일스톤 경계 충돌.** 오래된 3마일스톤 그래프와 `docs/superpowers/specs/research-governance/lifecycle.md:11`의 M2 설계는 AGENTS의 최신 M1 설계·M4 분기에 종속된다. 과거 코드의 존재와 최신 계약 구현 완료를 혼동하지 않아야 한다.
- **개발 검토 대기와 자율 운영.** `skills/researchpilot/SKILL.md:35`와 `docs/research/guides/work-episodes.md:32,46-50`은 개발 검토를 선택한 연구의 의존 작업 대기다. 최신 service design `:8,16-20`은 정상 자동 흐름에 매 단계 승인 추가 금지다. 프로젝트별 실제 선택을 식별할 정책과 UI 표시가 필요하며 어느 쪽도 일괄 승인 생성으로 풀면 안 된다.
- **정책 결정 상태가 오래 남아 있다.** service design `:4`와 knowledge-feedback-discussion 제목 절은 정책 미확정이라고 하지만 통합 로드맵 `:95-108`은 P1–P6 권고를 승인된 개발 기본안으로 기록한다. 현재 구현·배포 승인은 아니나 매번 정책을 처음부터 다시 묻는 근거도 아니다.
- **통합 계약≠배포.** Documents contract `:22,28`의 신규 미지원 설명은 계약 시점이다. 이후 adapter/consumer/live 기록을 함께 봐야 하며 그 기록도 운영 수락까지 자동 확장되지 않는다. 최신 capability를 실제 확인하지 않고 현재 지원 여부를 단정할 수 없다.
- **아카이브 설계의 위치.** `archive/legacy/2026-09-13-design-reset/README.md:3-7`은 고정 단계 설계 22개와 철회 Zotero 제안을 현재 작업 지시에서 분리한다. 그 안의 단계 번호·승인 gate를 새 graph의 강제 흐름으로 재도입하지 않는다. 원형 보존·내구성·재개·거짓 실행 금지 등은 현행 문서가 다시 요구하는 범위에서 유효하다.

## 우선 추가할 수락 증거 묶음

1. **H1 시작/종료 훅:** 허용·보완하며 진행·해당 판단 보류, 검증 도중 입력 변경, 훅/프로세스 종료, 초안 보존, CLI/API 우회 거부. 각 결과의 event와 다음 작업/owner를 대조한다.
2. **H2 무인 루프:** 원문 일부 누락→적합성 검토→추가 수집/질의→새 공통 입력→독립/상호 검토→채택 또는 한정→M1 경계 정지. 타이머·고정 회수·agent natural-language 'done'을 완료 근거로 쓰지 않는다.
3. **H3 복구·정지:** 요청 전/접수 후/ACK 후/모델 응답 후/최종 commit 전 강제 종료, stop/역할 교체/질문 변경, 늦은 결과. 중복 모델 호출 수와 중복 채택 수를 따로 기록한다.
4. **H4 UI:** 실제 제출 발언과 원문/표시 시간, 비공개 회차 장벽, 연결 끊김, 선택/스크롤 보존, old snapshot 잠금, 실제 판단·이동과 화면 대조. 성능 수치와 허용 지연은 아직 결정 필요하다.
5. **H5 모델/산출물:** 두 작업별 고정 설정 및 변경/삭제 오류, 세 단계 공통 산출물 renderer, 이전 version 재현, 보고서 주요 주장 원문 역추적.
6. **H6 품질:** 고정 오류 corpus·독립 oracle·단일/다중 비교. 실제 운영 모델을 호출하지 않은 fixture/HTTP 시험의 검증 범위를 명시한다.

## 읽기 범위와 한계

다음 원장은 파일별 목록·줄 수·검토 수준을 남긴다. **전체 파일을 정독했다는 주장은 하지 않는다.** 프로그램으로 모든 대상 파일의 내용에서 heading/키워드를 추출한 것은 full read가 아니다. 큰 통합 출력 일부가 도구에서 잘려서 확인되지 않은 본문도 보수적으로 scan으로 처리했다. 본문의 requirement 출처는 개별 재조회 또는 출력에서 실제 확인된 구절에 한정했다. 외부 Atlas/Documents 프로젝트의 링크 대상 원문은 이 감사에서 열지 않았다. 코드·실제 테스트 통과·운영 프로세스 검증은 담당 감사의 증거와 결합해야 한다.

- FULL: 본문 전체를 이 감사에서 확인.
- SCAN: 파일 inventory 및 프로그램 heading/선택 키워드·부분 본문 확인. 모든 문장의 의미 검토 아님.
- INVENTORY: 이름/크기만 확인한 범위 밖 archive 참고 파일.

총 330개 Markdown: FULL 19, SCAN 284, INVENTORY 27.

| 파일 | 줄 수 | 수준 |
| --- | ---: | --- |
| `AGENTS.md` | 126 | FULL |
| `archive/README.md` | 14 | INVENTORY |
| `archive/legacy/2026-09-13-design-reset/README.md` | 9 | FULL |
| `archive/legacy/2026-09-13-design-reset/docs/integrations/researchatlas/zotero-collection-flow-2026-09-13.md` | 29 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-27-codex-native-foundation.md` | 1110 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-27-codex-native-knowledge-extraction.md` | 546 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-29-codex-native-computational-package.md` | 410 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-29-codex-native-development-execution.md` | 257 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-29-codex-native-resource-planning.md` | 602 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-29-codex-native-stage-12-research-result.md` | 479 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-08-30-stage12-trustworthy-execution-evidence.md` | 553 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-09-01-stage13-multi-agent-refinement.md` | 538 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-09-05-agent-experiment-bridge.md` | 113 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-09-06-stage15-research-decision.md` | 321 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/plans/2026-09-07-stage-agent-roles.md` | 359 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-27-autoresearchclaw-codex-design.md` | 355 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-27-codex-native-knowledge-extraction-design.md` | 230 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-29-codex-native-computational-package-design.md` | 206 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-29-codex-native-development-execution-design.md` | 249 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-29-codex-native-resource-planning-design.md` | 156 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-29-codex-native-stage-12-research-result-design.md` | 234 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-08-30-stage12-trustworthy-execution-evidence-design.md` | 357 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-09-01-stage13-multi-agent-refinement-design.md` | 294 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-09-05-agent-experiment-bridge.md` | 181 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-09-06-stage15-research-decision-design.md` | 130 | SCAN |
| `archive/legacy/2026-09-13-design-reset/docs/superpowers/specs/2026-09-07-stage-agent-roles-design.md` | 145 | SCAN |
| `archive/legacy/2026-09-13-design-reset/skills/researchclaw/SKILL.md` | 54 | SCAN |
| `archive/legacy/2026-09-18-harness-reset/README.md` | 5 | INVENTORY |
| `archive/legacy/2026-09-18-harness-reset/output/evaluations/pc-cnt-live-flow-20260918/design-draft.md` | 53 | INVENTORY |
| `archive/legacy/docs/CHANGELOG_ANTHROPIC_ADAPTER.md` | 332 | INVENTORY |
| `archive/legacy/docs/CODE_REVIEW_2026-07-03.md` | 150 | INVENTORY |
| `archive/legacy/docs/DOMAIN_INTEGRATION_GUIDE.md` | 868 | INVENTORY |
| `archive/legacy/docs/HITL_GUIDE.md` | 620 | INVENTORY |
| `archive/legacy/docs/TESTER_GUIDE.md` | 587 | INVENTORY |
| `archive/legacy/docs/TESTER_GUIDE_CN.md` | 595 | INVENTORY |
| `archive/legacy/docs/TESTER_GUIDE_JA.md` | 587 | INVENTORY |
| `archive/legacy/docs/debate_engine.md` | 204 | INVENTORY |
| `archive/legacy/docs/examples/medical_observational_demo.md` | 50 | INVENTORY |
| `archive/legacy/pilot-readme-before-milestones-2026-09-15.md` | 393 | INVENTORY |
| `archive/upstream/LEGACY_UPSTREAM_AGENT_GUIDE.md` | 90 | INVENTORY |
| `archive/upstream/LEGACY_UPSTREAM_README.md` | 867 | INVENTORY |
| `archive/upstream/RESEARCHCLAW_CLAUDE.md` | 165 | INVENTORY |
| `archive/upstream/docs/README_AR.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_CN.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_DE.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_ES.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_FR.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_JA.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_KO.md` | 754 | INVENTORY |
| `archive/upstream/docs/README_PT.md` | 790 | INVENTORY |
| `archive/upstream/docs/README_RU.md` | 786 | INVENTORY |
| `archive/upstream/docs/integration-guide.md` | 882 | INVENTORY |
| `archive/upstream/docs/showcase/SHOWCASE.md` | 583 | INVENTORY |
| `docs/integrations/documents-atlas/README.md` | 25 | SCAN |
| `docs/integrations/documents-atlas/agreement-v1.md` | 24 | SCAN |
| `docs/integrations/documents-atlas/contract-v1.md` | 135 | SCAN |
| `docs/integrations/documents-atlas/pilot-adapter-2026-09-17.md` | 45 | SCAN |
| `docs/integrations/documents-atlas/pilot-consumer-review-2026-09-17.md` | 29 | SCAN |
| `docs/integrations/documents-atlas/pilot-review-worker-2026-09-17.md` | 13 | SCAN |
| `docs/integrations/documents-atlas/polling-handoff-proposal-2026-09-17.md` | 123 | SCAN |
| `docs/integrations/researchatlas/README.md` | 65 | FULL |
| `docs/integrations/researchatlas/atlas-loop-reply.md` | 313 | SCAN |
| `docs/integrations/researchatlas/atlas-pilot-implementation-reply.md` | 204 | SCAN |
| `docs/integrations/researchatlas/cfpp-import-review-reconnect-2026-09-18.md` | 16 | SCAN |
| `docs/integrations/researchatlas/contracts.md` | 45 | SCAN |
| `docs/integrations/researchatlas/direct-collection-flow-2026-09-13.md` | 31 | SCAN |
| `docs/integrations/researchatlas/knowledge-update-consumer-review-2026-09-18.md` | 52 | SCAN |
| `docs/integrations/researchatlas/knowledge-update-development-request-2026-09-18.md` | 21 | SCAN |
| `docs/integrations/researchatlas/knowledge-update-fixture-check-2026-09-18.md` | 7 | SCAN |
| `docs/integrations/researchatlas/knowledge-update-live-check-2026-09-18.md` | 21 | SCAN |
| `docs/integrations/researchatlas/knowledge-update-protocol-check-2026-09-18.md` | 9 | SCAN |
| `docs/integrations/researchatlas/pilot-a1-plan-review.md` | 60 | SCAN |
| `docs/integrations/researchatlas/pilot-atlas-loop.md` | 68 | SCAN |
| `docs/integrations/researchatlas/pilot-review-v1.md` | 205 | SCAN |
| `docs/integrations/researchatlas/pilot-t1-implementation.md` | 83 | SCAN |
| `docs/integrations/researchatlas/projects.md` | 68 | SCAN |
| `docs/integrations/researchatlas/review.md` | 97 | SCAN |
| `docs/integrations/researchatlas/tasks.md` | 82 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/README.md` | 110 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/abbasi-figure-review.md` | 63 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/README.md` | 21 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/atlas-qa.md` | 182 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/brief.md` | 9 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/case-application.md` | 200 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/decision-draft.md` | 15 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/decision.md` | 37 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/domain-final.md` | 17 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/domain-initial.md` | 30 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/domain-response.md` | 23 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/execution-final.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/execution-initial.md` | 29 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/execution-response.md` | 21 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/method-final.md` | 21 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/method-initial.md` | 30 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/method-response.md` | 27 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/minimal-design.md` | 71 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/previous-decision.md` | 67 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/previous-execution-spec.md` | 85 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/registration.md` | 14 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-review/synthesis-hypotheses.md` | 84 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/atlas-service-loop/README.md` | 42 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/condition-lineage-review.md` | 155 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/discovery-selection.md` | 68 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/execution-spec.md` | 87 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/README.md` | 62 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/accounting-repair-20260915.md` | 34 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/analysis-plan.md` | 52 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d1-proposal.md` | 17 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/domain-final.md` | 9 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/domain-initial.md` | 13 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/domain-response.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/execution-final.md` | 9 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/execution-initial.md` | 13 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/execution-response.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/method-final.md` | 9 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/method-initial.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d2-reviews/method-response.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/d4-start-inputs-20260915.md` | 73 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/electrode-layout-v2.md` | 72 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/electrode-layout.md` | 59 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/manufacturing-contrast.md` | 36 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/measurement-csv-binding-v2.md` | 43 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/measurement-evidence-criteria.md` | 37 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/measurement-method.md` | 48 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/measurement-review-20260914.md` | 48 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/readiness-audit.md` | 44 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/return-policy-20260915.md` | 26 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/domain-final.md` | 9 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/domain-initial.md` | 13 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/domain-response.md` | 15 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/execution-final.md` | 7 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/execution-initial.md` | 13 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/execution-response.md` | 13 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/method-final.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/method-initial.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/reviews/method-response.md` | 11 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-design/start-readiness.md` | 35 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/experiment-preparation.md` | 54 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/README.md` | 32 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/decision-before-final.md` | 54 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/decision.md` | 67 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/domain-final.md` | 30 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/domain-initial.md` | 53 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/domain-response.md` | 45 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/execution-final.md` | 34 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/execution-initial.md` | 56 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/execution-response.md` | 55 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/input.md` | 28 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/methodology-final.md` | 36 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/methodology-initial.md` | 81 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review/methodology-response.md` | 64 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/hypothesis-review.md` | 68 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/issue-impact-review.md` | 33 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/m1-poc-issues.md` | 268 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/m1-poc-result.md` | 53 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/preprocessing-review.md` | 62 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/question-scope-review.md` | 46 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/remaining-source-audit.md` | 120 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/restart.md` | 80 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/resume-check.md` | 50 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/resumed-source-review.md` | 24 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/search-reconnect-dialogue.md` | 239 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/search-reconnect.md` | 65 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/selection-correction-dialogue.md` | 125 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/selection-correction.md` | 26 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/selection.md` | 58 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/source-analysis.md` | 57 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/sources.md` | 20 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/stage6-status.md` | 30 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/stage6-synthesis.md` | 50 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/target-pair-review.md` | 61 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/virtual-lab/README.md` | 67 | SCAN |
| `docs/research/2026-09-10-polymer-sdl/virtual-lab/v2/README.md` | 46 | SCAN |
| `docs/research/guides/README.md` | 35 | SCAN |
| `docs/research/guides/atlas-file-evidence-verification.md` | 24 | SCAN |
| `docs/research/guides/atlas-file-evidence.md` | 46 | SCAN |
| `docs/research/guides/coordinator.md` | 63 | SCAN |
| `docs/research/guides/issue-scope-changes.md` | 15 | SCAN |
| `docs/research/guides/m1-evidence-basis.md` | 53 | SCAN |
| `docs/research/guides/m1-external-inputs.md` | 40 | SCAN |
| `docs/research/guides/m1-preparation-handoff.md` | 43 | SCAN |
| `docs/research/guides/milestones.md` | 58 | SCAN |
| `docs/research/guides/project-storage.md` | 51 | SCAN |
| `docs/research/guides/research-agents.md` | 77 | SCAN |
| `docs/research/guides/return-policy.md` | 62 | FULL |
| `docs/research/guides/source-capture.md` | 30 | SCAN |
| `docs/research/guides/work-episodes.md` | 88 | FULL |
| `docs/research/prompts/m1/README.md` | 46 | SCAN |
| `docs/research/prompts/m1/assessment.md` | 44 | SCAN |
| `docs/research/prompts/m1/common.md` | 135 | SCAN |
| `docs/research/prompts/m1/examples.md` | 68 | SCAN |
| `docs/research/prompts/m1/planning.md` | 47 | SCAN |
| `docs/research/prompts/m1/protocol.md` | 140 | FULL |
| `docs/research/prompts/m1/quality-checks.md` | 36 | FULL |
| `docs/research/prompts/m1/research.md` | 44 | SCAN |
| `docs/research/prompts/m1/spec/README.md` | 34 | SCAN |
| `docs/research/prompts/m1/spec/inputs-evidence.md` | 83 | SCAN |
| `docs/research/prompts/m1/spec/purpose-roles.md` | 78 | SCAN |
| `docs/research/prompts/m1/spec/review-handoff.md` | 88 | SCAN |
| `docs/research/prompts/m1/task-packet.md` | 100 | FULL |
| `docs/superpowers/plans/2026-09-08-m1-a-foundation.md` | 153 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-a-verification.md` | 98 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-b-evidence.md` | 160 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-b-verification.md` | 146 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-c-council.md` | 157 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-c-verification.md` | 48 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-d-loops-ui.md` | 153 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-d-verification.md` | 51 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-e-integration.md` | 175 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-host-verification.md` | 19 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-progress.md` | 45 | SCAN |
| `docs/superpowers/plans/2026-09-08-m1-transition.md` | 217 | SCAN |
| `docs/superpowers/plans/2026-09-08-stage-agent-roles-verification.md` | 76 | SCAN |
| `docs/superpowers/plans/2026-09-09-m1-ui-test-guide.md` | 47 | SCAN |
| `docs/superpowers/plans/2026-09-09-m1-ui-test.md` | 24 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-a-verification.md` | 64 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-a04-verification.md` | 33 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-a05-verification.md` | 32 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-acceptance.md` | 47 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-common-verification.md` | 41 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-core.md` | 51 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-m1-verification.md` | 92 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-m1.md` | 43 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-m2.md` | 39 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance-m3.md` | 35 | SCAN |
| `docs/superpowers/plans/2026-09-09-research-governance.md` | 125 | SCAN |
| `docs/superpowers/plans/2026-09-10-discovery-ui.md` | 39 | SCAN |
| `docs/superpowers/plans/2026-09-12-atlas-file-evidence.md` | 81 | SCAN |
| `docs/superpowers/plans/2026-09-12-m1-evidence-basis.md` | 42 | SCAN |
| `docs/superpowers/plans/2026-09-12-m1-external-inputs.md` | 32 | SCAN |
| `docs/superpowers/plans/2026-09-13-atlas-request-episodes.md` | 20 | SCAN |
| `docs/superpowers/plans/2026-09-13-council-episodes.md` | 17 | SCAN |
| `docs/superpowers/plans/2026-09-13-episode-review-ui.md` | 18 | SCAN |
| `docs/superpowers/plans/2026-09-13-pilot-atlas-t1.md` | 44 | SCAN |
| `docs/superpowers/plans/2026-09-13-review-followups.md` | 29 | SCAN |
| `docs/superpowers/plans/2026-09-13-work-episodes.md` | 61 | SCAN |
| `docs/superpowers/plans/2026-09-15-project-workspace-ui.md` | 25 | SCAN |
| `docs/superpowers/plans/2026-09-17-import-review-preparation.md` | 46 | SCAN |
| `docs/superpowers/plans/2026-09-17-import-review-worker.md` | 15 | SCAN |
| `docs/superpowers/plans/2026-09-17-pilot-handoff-adapter.md` | 12 | SCAN |
| `docs/superpowers/plans/2026-09-17-pilot-handoff-journal.md` | 40 | SCAN |
| `docs/superpowers/plans/2026-09-18-harness-refactor-foundation.md` | 16 | FULL |
| `docs/superpowers/plans/2026-09-18-pilot-integrated-development-roadmap.md` | 171 | SCAN |
| `docs/superpowers/plans/research-governance/README.md` | 10 | SCAN |
| `docs/superpowers/plans/research-governance/common.md` | 27 | FULL |
| `docs/superpowers/plans/research-governance/tasks/A01.md` | 45 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A02.md` | 47 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A03.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A04.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A05.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A06.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A07.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A08.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/A09.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B01.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B02.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B03.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B04.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B05.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B06.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/B07.md` | 46 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C01.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C02.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C03.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C04.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C05.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/C06.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/D01.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/D02.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/D03.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/D04.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/D05.md` | 44 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E01.md` | 45 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E02.md` | 48 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E03.md` | 45 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E04.md` | 45 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E05.md` | 45 | FULL |
| `docs/superpowers/plans/research-governance/tasks/E06.md` | 48 | SCAN |
| `docs/superpowers/plans/research-governance/tasks/E07.md` | 45 | FULL |
| `docs/superpowers/plans/research-governance/tasks/E08.md` | 44 | SCAN |
| `docs/superpowers/specs/2026-09-08-m1-contracts-design.md` | 63 | SCAN |
| `docs/superpowers/specs/2026-09-08-three-milestone-research-graph-design.md` | 253 | SCAN |
| `docs/superpowers/specs/2026-09-09-research-governance-design.md` | 61 | SCAN |
| `docs/superpowers/specs/2026-09-12-atlas-file-evidence-design.md` | 94 | SCAN |
| `docs/superpowers/specs/2026-09-12-atlas-m1-evidence-route-design.md` | 150 | SCAN |
| `docs/superpowers/specs/2026-09-13-pilot-autonomous-research-design.md` | 135 | FULL |
| `docs/superpowers/specs/2026-09-17-atlas-triggered-research-review-design.md` | 123 | SCAN |
| `docs/superpowers/specs/2026-09-18-atlas-knowledge-feedback-discussion.md` | 43 | SCAN |
| `docs/superpowers/specs/2026-09-18-pilot-service-request-design.md` | 175 | SCAN |
| `docs/superpowers/specs/research-governance/acceptance.md` | 20 | FULL |
| `docs/superpowers/specs/research-governance/budget-inputs.md` | 75 | SCAN |
| `docs/superpowers/specs/research-governance/contracts.md` | 36 | SCAN |
| `docs/superpowers/specs/research-governance/council-inputs.md` | 99 | SCAN |
| `docs/superpowers/specs/research-governance/dependency-inputs.md` | 85 | SCAN |
| `docs/superpowers/specs/research-governance/evidence-origin-inputs.md` | 52 | SCAN |
| `docs/superpowers/specs/research-governance/gate-inputs.md` | 65 | SCAN |
| `docs/superpowers/specs/research-governance/issue-policy-inputs.md` | 70 | SCAN |
| `docs/superpowers/specs/research-governance/lifecycle.md` | 51 | FULL |
| `docs/superpowers/specs/research-governance/m1-evidence-inputs.md` | 97 | SCAN |
| `docs/superpowers/specs/research-governance/m1-handoff-inputs.md` | 168 | SCAN |
| `docs/superpowers/specs/research-governance/m1-node-inputs.md` | 96 | SCAN |
| `docs/superpowers/specs/research-governance/m1-review-inputs.md` | 115 | SCAN |
| `docs/superpowers/specs/research-governance/m1-search-inputs.md` | 76 | SCAN |
| `docs/superpowers/specs/research-governance/m1-view-inputs.md` | 76 | SCAN |
| `docs/superpowers/specs/research-governance/milestones.md` | 18 | SCAN |
| `docs/superpowers/specs/research-governance/position-inputs.md` | 42 | SCAN |
| `docs/superpowers/specs/research-governance/rules.md` | 28 | FULL |
| `docs/superpowers/specs/research-governance/scope.md` | 19 | SCAN |
| `docs/superpowers/specs/research-governance/ui.md` | 11 | FULL |
| `docs/superpowers/specs/research-governance/verification-inputs.md` | 31 | SCAN |
| `skills/researchpilot/SKILL.md` | 43 | FULL |
| `skills/researchpilot/references/agent-roles.md` | 27 | SCAN |
| `skills/researchpilot/references/approval-policy.md` | 35 | SCAN |
| `skills/researchpilot/references/computational-package.md` | 357 | SCAN |
| `skills/researchpilot/references/evaluation-rubric.md` | 18 | SCAN |
| `skills/researchpilot/references/hypothesis-generation.md` | 43 | SCAN |
| `skills/researchpilot/references/knowledge-extraction.md` | 81 | SCAN |
| `skills/researchpilot/references/legacy-workflow.md` | 51 | SCAN |
| `skills/researchpilot/references/m1-council.md` | 343 | SCAN |
| `skills/researchpilot/references/m1-host-contract.md` | 28 | SCAN |
| `skills/researchpilot/references/m1-hypotheses.md` | 61 | SCAN |
| `skills/researchpilot/references/pilot-collection.md` | 20 | SCAN |
| `skills/researchpilot/references/pilot-runtime.md` | 32 | FULL |
| `skills/researchpilot/references/refinement.md` | 173 | SCAN |
| `skills/researchpilot/references/research-decision.md` | 186 | SCAN |
| `skills/researchpilot/references/resource-planning.md` | 302 | SCAN |
| `skills/researchpilot/references/result-analysis.md` | 228 | SCAN |
| `skills/researchpilot/references/stages.md` | 33 | SCAN |
| `skills/researchpilot/references/synthesis.md` | 37 | SCAN |
| `skills/researchpilot/references/validation-design.md` | 55 | SCAN |
