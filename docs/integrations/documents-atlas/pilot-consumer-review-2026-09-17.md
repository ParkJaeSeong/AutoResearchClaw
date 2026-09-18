# Atlas 첫 구현에 대한 Pilot 소비자 연결 검토

2026-09-17. Atlas `implementation-2026-09-17.md`, `import_contract.py`, `document_imports.py`와 Pilot journal/view를 읽기 대조했다. 운영 호출·서비스 설정·실제 논문·연구 상태는 변경하지 않았다. Atlas 시험 통과는 담당 보고이며 이번 검토에서 재실행하지 않았다.

## 수용

신규 consumer 전용 인증과 기존 A1 인증 분리, 공급자 capability 확인, Documents 원형 artifact를 선택하는 `original_ref={role:source_original}`, 불변 결과 해시 검증 후 이벤트 ACK 방향을 수용한다. 신규 기능 비활성/503을 기존 ask로 대체하지 않는다. 계약 본문 변경은 요구하지 않는다.

## Pilot 연결 전에 필요한 보완

1. **공급자 값 고정**: `package_fingerprint`는 Documents receipt/task의 실제 값으로 저장·전달한다. 원문 `source.sha256`, Documents `request_sha256`, Atlas 요청 fingerprint와 서로 대체하지 않는다. 값이 없으면 Atlas 접수만 보류하며 변환을 새로 요청하지 않는다. Documents 접수 전 연구 의뢰 초안과, receipt 이후 확정한 Atlas 전송 payload를 분리해 후자를 영속 고정한다. 현재 journal은 초안과 receipt를 보관할 수 있지만 완성 payload 조합/검증 어댑터는 없다.
2. **요청 키 대응**: 현재 journal은 Documents operation/key를 기준으로 이벤트 request_key도 비교한다. Atlas 예제처럼 별도 import key를 쓰면 맞지 않는다. Documents operation/key와 Atlas request_key를 명시적으로 매핑한다. 같은 key의 convert.file/convert.jats가 Atlas consumer/key 공간에서 충돌하지 않도록 한다.
3. **영수증과 가변 상태 분리**: `import.receipt_ref`를 고정 영수증으로 검증·보관한다. phase/updated_at/lease 등 가변 필드를 포함한 import 응답 전체를 고정 영수증으로 비교하지 않는다. 이벤트 `acknowledged`도 가변 조회 필드이므로 불변 event payload와 분리한다. ACK 전 false→후 true 재조회가 충돌하면 안 된다. 현재 journal에 원 응답 전체를 그대로 전달하면 충돌할 수 있다.
4. **완료 이벤트와 진행 조회 분리**: UI의 waiting_conversion/fetching/organizing 표시는 GET import의 최근 관측 snapshot을 저장해 연결한다. terminal/needs_attention 이벤트만 기다려 중간 진행을 추정하지 않는다. 현재 UI는 receipt와 수신 이벤트 기반이며 중간 상태 조회 연결은 아직 없다. snapshot 관측 시각과 오래된 응답에 의한 상태 역행도 처리해야 한다.
5. **결과 검증**: `import.result.record`를 명시된 UTF-8 canonical JSON으로 직렬화해 sha256을 확인한다. event.result_ref의 import_id/sha256, instance/consumer/project/요청 대응을 대조한 후 원 결과와 처리 기록을 영속 저장하고 event ID ACK한다. needs_attention 등 result_ref 없는 알림은 진단 수신으로 처리하며 지식화 완료로 표시하지 않는다. 로컬 기록 경로를 다운로드 URL로 만들지 않는다.
6. **인증과 재조정**: 별도 안전한 연결 파일을 사용하고 기존 A1 파일을 덮어쓰지 않는다. cursor=null 종료 후 새 조회는 첫 페이지에서 시작하고 중복 event ID를 제거한다. 프로젝트별 journal 밖의 다른 프로젝트 이벤트는 해당 프로젝트로 안전하게 분배하거나 보존 대기하며 임의 ACK하지 않는다.

## 모의 통합 시험

- Documents 응답 유실→operation/key 복구→공급자 package 값 보존→Atlas 제출; 중복 변환 없음.
- file/jats 동일 로컬 key가 서로 다른 Atlas key로 전달되고 이벤트가 원 요청에 연결됨.
- `import.receipt_ref` 동일/phase 변경, event 동일/acknowledged 변경은 정상 재조회.
- 변환 대기→정리 중→partial 진행 관측; 오래된 관측은 최신 상태를 되돌리지 않음.
- 결과 해시·instance·consumer·import 불일치는 ACK하지 않음; 저장 후 ACK 유실 재전송 성공.
- cursor 재조정과 여러 Pilot 프로젝트 간 이벤트 분배; 타 프로젝트 원문·토큰 UI 비노출.

## 결론

Atlas 신규 schema를 Pilot 어댑터의 기준으로 사용할 수 있다. 현재 Pilot journal/UI를 그대로 네트워크 응답에 연결하는 것은 준비되지 않았다. 위 보완은 Pilot 소비자 구현 과제로 기록한다. 이번 대조에서 Atlas 계약 변경이 필요한 차단점은 발견하지 않았으며, 공급자 실제 응답/권한과 세 서비스 왕복은 별도 검증한다.
