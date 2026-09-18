# Pilot–Atlas T1 구현과 사용법

2026-09-13. Pilot HTTP 연결·프로젝트 바인딩·요청 이력·원형 수신·기존 근거 등록과 UI를 구현했다. Atlas와 [구현 협의 및 코드 검토](atlas-pilot-implementation-reply.md)를 진행했다. 기능 구현과 별도 시험 연구에서의 T1 결과를 아래에 구분한다.

## 구현된 흐름

1. **Atlas 연결 확인**: 서버 설정의 연결 파일에서 URL/토큰을 읽고 info·프로젝트 목록을 조회한다. 브라우저에 토큰을 전달하지 않는다.
2. **이 프로젝트 연결**: 기존 Atlas 프로젝트 ID·instance·선택 이유·이전 연결을 연구별 journal에 보존한다.
3. **질문 보내기**: 원문 질문·관련 질문 ID·전송 payload·요청 키를 먼저 저장한다. 후속 질문은 이전 질문·QA 참조와 새 질문을 실제 전송 본문에 포함한다.
4. **진행 상황 확인**: 저장한 job을 조회한다. 접수 응답이 유실돼 ID가 없으면 같은 키·고정 payload를 재전송한다.
5. **답변과 근거 가져오기**: QA 원형·참고 페이지·source 원본의 길이·해시를 검사한다. QA를 기존 external.evidence.import 명령으로 등록한다. 원문 대조나 연구 사용 판단을 자동 생성하지 않는다.
6. **사용 범위 판단**: 기존 패널에서 사용/제한/보류 등을 기록한다. **이 답변에 이어 질문**으로 다음 질문을 작성한다.

원문을 받지 못해도 유효한 QA는 보존하고 누락된 근거를 표시한다. **참고 원문 다시 받기**는 같은 질문을 재실행하지 않으며 이전 수신 시도도 보존한다. 연구 HEAD 충돌로 등록만 실패하면 보존된 같은 QA로 오프라인 등록 재시도가 가능하다.

## 실행

작업 경로: `/Users/jspark/orca/AutoResearchClaw/.worktrees/m1-research-graph`.

```sh
PILOT_ATLAS_CONNECTION_FILE=/Users/jspark/orca/projects/ResearchAtlas/output/atlas-18765.json .venv/bin/python -m researchclaw.codex.cli research view   output/evaluations/pilot-atlas-t1/research --port 8770
```

`research view`의 root를 기존 연구 graph root로 바꾸면 해당 연구에서 같은 기능을 사용할 수 있다. 이 설정 없이 시작한 UI는 ‘아직 Atlas 연결 설정이 없습니다’라고 표시한다. 설정 파일은 본인 소유·0600 일반 파일이어야 한다. 서비스 주소는 127.0.0.1 HTTP만 사용하며 환경 프록시·redirect를 따르지 않는다.

현재 실행해 둔 [연결 시험 UI](http://127.0.0.1:8770/)에서 **Atlas 연결 확인**을 누르면 저장한 두 질문과 결과를 볼 수 있다. 기존 운영 연구 UI와 서버는 이번 시험을 위해 중단하지 않았다.

## 에이전트 CLI

UI와 같은 서비스 동작을 `research atlas-service`로 호출할 수 있다. 위 연결 파일 환경 설정을 동일하게 사용하며 토큰을 인자로 전달하지 않는다.

```sh
.venv/bin/python -m researchclaw.codex.cli research atlas-service connect ROOT --json
.venv/bin/python -m researchclaw.codex.cli research atlas-service bind ROOT --project ATLAS_PROJECT_ID --reason '이 연구의 자료 검토' --json
.venv/bin/python -m researchclaw.codex.cli research atlas-service ask ROOT --key UNIQUE_REQUEST_KEY --question '확인할 질문' --question-id QUESTION_ID --json
.venv/bin/python -m researchclaw.codex.cli research atlas-service poll ROOT --key UNIQUE_REQUEST_KEY --json
.venv/bin/python -m researchclaw.codex.cli research atlas-service receive ROOT --key UNIQUE_REQUEST_KEY --expected-head CURRENT_GRAPH_HEAD --json
```

ROOT는 Pilot research graph의 실제 경로다. 후속 ask에는 새 키와 `--previous 이전요청키`를 사용한다. `status ROOT --json`은 보존 기록을 조회하고, `supporting ROOT --key 요청키 --json`은 참고 원문만 다시 받는다. CLI를 사용할 수 있다는 사실과 연구 조정자가 자동 호출하도록 연결된 것은 구분한다.

## 기록 위치와 책임

- `.atlas-link/journal.sqlite3`: 바인딩 이력, 요청 원문/전송 payload, job/receipt, QA 응답과 등록 결과, 참고 자료 수신 결과. 통신 기록이며 M1 단계 상태를 대신하지 않는다.
- `.atlas-link/objects/<sha256>`: 실제 수신한 불변 원형 파일. 원본 해시로 재확인한다.
- 기존 research graph: QA 근거 등록·사용 판단·결정·후속 질문 초안 등 기존 명령이 생성한 연구 기록.

토큰은 위 기록에 저장하지 않는다. 요청 키는 연구별로 고유하게 사용한다. 기존 요청의 바인딩은 새 기본 프로젝트 선택으로 변경되지 않는다. 자료실 instance나 응답 계약이 다르면 중단한다. 후속 ask는 Atlas의 독립 실행이며 대화 메모리에 의존하지 않는다.

## 실제 T1 결과

별도 시험 연구: `output/evaluations/pilot-atlas-t1/research`. 실제 연구의 단계·승인·M1 완료 조건을 변경하지 않았다. Atlas에는 허용된 새 질문 두 건이 추가됐다.

| 항목 | 질문 1 | 후속 질문 2 |
| --- | --- | --- |
| request_key | pilot-t1-20260913-q1 | pilot-t1-20260913-q2 |
| job | job-dcc8d0d0ac3a4f06 | job-da83bf989a7840a7 |
| Atlas 상태 | completed | completed |
| QA 원형 SHA-256 | d86027b5f6bc742a93133e92c3406adefe12a38758395ad064a3f2e469eacc86 | db9e6a22625b90642c0269a0977e50a14d304c09021fe842010689f644869a75 |
| Pilot 근거 ID | 72062914-12c8-5c85-b256-f5eb7c78e97d | 2f53f2fd-8049-56bf-8774-a1bf2793eee6 |
| 원형 수신 | QA·참고 페이지3개·원본PDF1개 | QA·참고 페이지3개·원본PDF1개 |
| 사용 판단 | 자료 공백과 추가 질문 정리에 제한 | 문헌 검색·비교 변수 초안에 제한 |

두 요청은 같은 Atlas instance `4578a369-9f11-45b0-adb7-f95704aebfc9`, 프로젝트 `project-95e043c2a0c341af`를 사용했다. 원본 PDF는 2,492,841바이트이며 SHA-256은 `b98142474a50703044b3f5dae64335973bf0b6e0e4ea569d52e01d36fc7d5dd7`이다. 원형은 동일 해시 객체로 공유한다.

첫 답변은 현재 연결 프로젝트 자료에서 CNT 공정·전류 방향별 전도도 비교를 확인하지 못했다고 설명했다. 후속 답변은 이전 QA를 다시 확인하고 다음 문헌에 필요한 비교 항목을 제안했다. 이를 배향 효과의 입증/반증이나 실제 실험 조건 확정으로 처리하지 않았다.

첫 source 수신에서 소비자가 EOF의 next_offset=null을 거절했다. 회귀 테스트 후 수정해 원본만 다시 받았으며, 실패 이력을 보존했다. 질문을 다시 실행하거나 QA를 재작성하지 않았다.

상세 수신·등록·사용 판단 근거: `output/evaluations/pilot-atlas-t1/verification.json`. 최종 시험 연구 HEAD: `22d38fb950b9a95bd91c5c4f19e2dad87bcf6289951b9fd47a5608ce234bcaaa`.

## 검증과 제한

- 관련 Python 회귀 **93개 통과**, UI 자동 검사 **14개 통과**. Atlas 재검토에서도 최초 중요 문제 R1–R4 해소를 확인했다(Atlas가 별도로 호출한 15개 테스트와 20개 경계 확인은 이 93개와 합산하지 않는다).
- 전송 유실·바인딩 변경·키 충돌·instance/receipt·원형 오류·오프라인 등록·EOF·후속 맥락·오류 한도 보존을 회귀 검사했다.
- 실제 UI에서 프로젝트 조회, job 재조회, 등록 재시도의 중복 방지, 후속 질문 맥락을 확인했다. 1440/768/390px와 light/dark의 6개 조합에서 가로 넘침과 JavaScript 오류가 없었다.
- 서버를 다시 시작한 뒤 저장된 두 요청을 조회했다. 실제 질문을 자동으로 재실행하지 않았다.
- UI 진행 상태는 **진행 상황 확인** 버튼으로 갱신한다. 백그라운드 자동 실행·자동 M1 완료 기능을 추가하지 않았다.
- 업로드·프로젝트 생성·변환 연결·지정 analyze는 Atlas 미지원 상태이며 이번 Pilot 작업에 포함하지 않는다. 자동 연구 조정자가 이 클라이언트를 정책에 따라 호출하는 것은 다음 연결 작업이다.

### 추가 전체 회귀 검사 상태

관련 93개 Python·14개 UI 검사와 실제 T1 검증은 통과했다. 별도로 시작한 전체 research_graph 회귀 검사도 **671개 통과(1514.67초)**로 완료됐다. 이 실행은 후속 advance 기능 추가 이전의 수집 기준이다. 실제 Atlas 작업이나 연구 데이터를 변경하는 검사가 아니다.
