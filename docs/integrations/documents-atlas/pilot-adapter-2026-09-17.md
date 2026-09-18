# Pilot 연결 어댑터 첫 구현

2026-09-17. v1 계약은 그대로 유지한다. 실제 서비스 접수·실제 논문 처리·M1 변경 없이 합성 응답과 임시 HTTP 서버로 시험했다.

## 구현

- `document_handoff_adapter.py`: Documents capability/instance 확인, operation별 영수증 복구, 공급자 task 원문 해시·package 값 확인, 별도 Atlas key와 전송 payload 고정, 접수·진행 관측·결과 검증·이벤트 ACK.
- `document_handoff_transport.py`: 별도 0600 연결 파일을 사용하는 loopback HTTP. JSON/JATS 및 일반 파일 multipart 제출. 명시적 RECEIPT_NOT_FOUND(404)일 때만 최초 제출한다. 401/403/임의404/응답 유실에서는 새 제출로 우회하지 않는다. 파일/자산은 저장된 SHA-256과 다시 대조한다.
- `document_handoff.py`: 고정 Atlas payload, 가변 snapshot, 로컬 오류 저장. 이벤트 acknowledged는 불변 payload 비교에서 제외한다. 전송 요청 본문과 인증 토큰은 분리하며 파일 바이트를 journal에 넣지 않는다.
- `document_handoff_runner.py`: 기존 journal을 대상으로 한 단발 또는 60초 주기 관찰. 프로젝트 HEAD를 대조하고 연구 상태를 수정하지 않는다. 서비스/에이전트 자동 시작은 하지 않는다.
- UI: snapshot의 중간 상태와 확인 필요 표시. 검증한 결과가 저장된 경우에만 결과 수신 및 읽은 범위·미확인 사항을 표시한다. 연구 사용 채택은 별도다.

## 저장·전송 규칙

프로젝트 `.document-handoff/journal.sqlite3`에 별도 요청 operation/key를 유지한다. Documents 접수 영수증을 받은 뒤 Atlas payload를 고정한다. Atlas key는 Pilot 프로젝트+Documents operation+key의 SHA-256으로 생성해 file/jats 키 충돌을 피한다. request_sha256은 supplier package 값으로 쓰지 않는다. 현재 supplier task의 `input_fingerprint`(또는 명시적 `package_fingerprint`)를 사용하며 없으면 영수증을 보존한 채 접수를 보류한다.

Documents journal 요청에는 `config_revision`, `retrieval_consumer_id`, `original_path`가 필요하다. JATS assets는 각각 `path`, `sha256`, `href`, 선택 `source_url`을 저장한다. Atlas 요청 초안에는 구현 schema의 연구 목적·source·프로젝트·scope·indexes·original_ref 등이 필요하다. UI에서 원문 path·토큰을 반환하지 않는다. 요청 준비 화면/사용자용 등록 명령은 후속 작업이며 journal을 임의로 채우지 않는다.

Documents receipt의 result_ref/acknowledged_at, Atlas import의 phase/lease 등 가변 필드는 고정 영수증과 분리한다. 이벤트 중복 제거 후 단일 import 조회 결과와 event.result_ref의 import/hash를 비교하고, canonical JSON 해시와 Documents result identity를 확인한다. 그 결과 원형을 journal에 커밋한 다음 event ID별 ACK한다. 해시 실패는 ACK하지 않는다. ACK 응답 유실이면 이미 저장된 결과를 재처리하지 않고 ACK를 재전송한다. 다른 Pilot 프로젝트의 이벤트는 건너뛰고 ACK하지 않는다. 해당 프로젝트 observer가 따로 수신한다.

## 명시적 실행

새 운영 요청 없이 기존 접수 기록만 연결 시험하려면 격리 프로젝트와 합성 서버를 먼저 사용한다. 운영 실행에는 양 서버 capability·전용 소비자 등록·안전한 연결 파일이 필요하다. 기존 Atlas A1 연결 파일을 덮어쓰지 않는다.

```sh
.venv/bin/python -m researchclaw.codex.document_handoff_runner PROJECT_ROOT \
  --documents-connection /absolute/private/documents-pilot.json \
  --atlas-connection /absolute/private/atlas-import-pilot.json
```

`--watch`를 붙이면 각 관찰 사이 60초를 기다린다. 이는 Atlas의 Documents 600초 조회와 다르다. SIGINT는 기록을 보존한다. 서비스로 자동 설치하지 않았다. journal 파일이 없으면 새 연구/요청을 생성하지 않고 실행 오류다. 기존 pending 요청은 전송될 수 있으므로 운영 activation은 별도 공동 수락 후 진행한다.

## 검증과 한계

- Python 신규/기존 journal·adapter·transport·runner·view·A1 service/CLI/viewer 회귀 47개 통과, Node UI 회귀 32개 통과.
- 실제 임시 HTTP: Documents 접수 직후 연결 유실→영수증 복구, 전송 1회. Atlas HTTP 접수/진행/결과/ACK 재조회. 모델 실행 없음.
- 메모리 공급자: package 구분, Atlas 접수 응답 유실 재전송, ACK 유실, 변조 결과 ACK 차단, capability 차단, 타 프로젝트 이벤트 무ACK, 과거 snapshot 역행 방지.
- Pilot 생성 payload를 현재 Atlas `import_contract.normalize`에 직접 전달해 동일성 확인. 이 검사는 Atlas 서비스 배포 검증이 아니다.
- UI 합성 화면 6폭×2테마 및 검색/필터/펼침·과거 상태 분리 확인.

남은 것: Documents·Atlas 실제 운영 설정 및 capability 활성화, 요청 준비/제출 UI, 원문·변환 결과 열기, 서비스 관리형 observer 배포, 실제 세 서비스 왕복 수락. 일반 multipart와 JATS 자산 묶음은 공급자 실제 수락 시험을 추가해야 한다. 현재 큰 파일은 제한된 크기로 메모리 전송하며 streaming 업로드가 아니다. 저장된 source bytes 해시만 검증하는 것은 내용의 과학적 타당성을 보증하지 않는다.

### 2026-09-17 실제 이벤트 tail 확인

이벤트 응답은 빈 `events=[]`에서도 현재 위치의 `next_cursor`를 반환한다. Pilot은 빈 페이지에서 이번 연속 조회를 끝내고 cursor를 journal에 보관하며, 60초 뒤 그 위치부터 관찰한다. 최초 빈 응답의 위치 0도 보존한다. import 목록의 종료 규칙(`next_cursor=null`)과 구분하고 두 API의 cursor를 교환하지 않는다. 이벤트 ACK는 별도 처리한다. 재시작 시 저장 위치를 재사용하며 서버가 `invalid_cursor`를 반환할 때만 처음부터 재조회하고 기존 이벤트 ID로 중복 처리를 방지한다. 관련 회귀 검사를 포함한 handoff 테스트 24개 통과. 기존 원격 task/import는 재접수하거나 재시작하지 않았다.
