# 현재 Pilot 실행 경로

설치된 `researchclaw-codex --help`와 `researchclaw-codex research --help`로 기능을 확인한다. 체크아웃에서는 해당 환경의 Python으로 `python -m researchclaw.codex.cli`가 같은 진입점이다. 도구가 없는 환경에서 임의의 설치·모델 구성을 연구 수행으로 대체하지 않는다.

## 프로젝트 형식에 맞는 조회

| ROOT의 기록 | 첫 조회 | 진행 경로 |
| --- | --- | --- |
| `.researchclaw/research_graph/HEAD.json` | `researchclaw-codex research inspect ROOT --json` | 현재 그래프 |
| `.researchclaw/m1/` | `researchclaw-codex m1 --help` | 지원되는 이전 M1 조회 명령 확인 |
| `.researchclaw/state.json` | `researchclaw-codex status ROOT --json` | `legacy-workflow.md`를 읽고 기존 절차 재개 |
| 기록 없음 | 질문·ROOT·자료 출처·실행 정책 확인 | 새 그래프 생성 |

여러 형식이 섞였거나 읽기가 실패하면 형식 충돌·복구를 확인한다. 기존 기록 위에 init하거나 파일을 직접 고쳐 해결하지 않는다.

## 새 그래프

명령 형식: `researchclaw-codex research init ROOT --topic TOPIC --content-origin real|synthetic|mixed --json`.
출처 값은 실제 입력에 맞춰 하나를 선택한다. 사용자가 실제 연구 주제로 시작을 요청하고 합성 입력이 없으면 real로 시작한다는 가정을 명시할 수 있다. 출처가 섞였거나 불명확하면 확인한다. 생성은 에이전트 작업 시작이나 M1 완료를 뜻하지 않는다.

현재 init 구현의 정책 기본값은 `--max-returns 3`, `--max-verification-runs 10`이다. 이를 사용자가 정한 연구 한도나 문헌 수 제한으로 해석하지 않는다. 생성 전 현재 정책과 사용자 요구를 대조한다. 사용자가 임의 한도 없이 진행하라고 했는데 런타임에 유한 기본값만 있다면 그 차이를 설명하고 정책을 먼저 정한다. 무한값을 지원한다고 가정하거나 형식에 없는 값을 넣지 않는다. 기존 정책을 임의로 높이거나 우회하지 않는다. 별도 정책 요청이 없고 기본값이 작업 범위와 충돌하지 않으면 사용한 기본값을 알리고 진행할 수 있으며, 기본값 확인만을 위해 반복 승인을 요구하지 않는다.

생성 뒤 inspect로 ROOT·project_id·HEAD를 확인한다. 문헌 연구를 synthetic으로 표시하거나 그래프 완료 조건을 우회해 최종 연구로 만들지 않는다.

## 현재 작업·Atlas·UI

- 그래프 쓰기: `research apply`의 도움말·등록 payload 계약을 확인한다. `--expected-head`와 `--command-id`를 사용한다. HEAD가 바뀌면 최신 상태를 읽고 판단을 재검토한다.
- 역할 입력: `research packet ROOT --assignment ASSIGNMENT_ID --json`으로 실제 배정의 입력을 확인한다. 새로운 역할명만 적었다고 배정·실행이 등록되는 것은 아니다.
- Atlas: `research atlas-service --help`에서 connect/status/bind/ask-question/poll/receive/advance/review/outcome 등 실제 지원을 확인하고 필요한 하위 명령의 도움말을 읽는다. 먼저 기존 세션·요청 상태를 확인하고, connect/bind는 필요한 경우만 수행한다. 연결·기능·프로젝트 소속을 확인하며 접수 중 요청을 중복 제출하지 않는다. 부분 기능 지원을 전체 API 계약 완료로 표현하지 않는다.
- 화면: 이미 같은 ROOT의 뷰어가 있으면 해당 URL을 사용한다. 없으면 `research view ROOT --port 0`으로 실행하고 반환된 로컬 주소를 연다. 서버 응답·실제 화면을 확인하기 전 ‘UI 연결 완료’라고 하지 않는다. 서버 연결을 에이전트 실행으로 해석하지 않는다.

체크아웃에서 상세 계약이 필요하면 `docs/integrations/researchatlas/README.md`와 실제 서버 안내를 찾아 읽는다. 배포된 스킬에 저장소 문서가 없으면 사용 가능한 CLI/API 계약을 확인하고, 미확인 payload나 엔드포인트를 추측하지 않는다.
