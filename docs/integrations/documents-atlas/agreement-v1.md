# 문서 지식화 계약 v1 공동 확정

2026-09-17 · **Pilot·Atlas·Documents 최종 수용 완료.**

- 계약 식별자: `pilot-documents-atlas/1.0`
- 규범 본문: [contract-v1.md](contract-v1.md)
- 최종 원형 바이트 SHA-256: `d637ec4cb15c714b77783c1d3d9e13e06fcc30e94195dfb9e29bd496c1d50a38`
- Pilot: 사용자 요청에 따라 두 담당 검토를 통합하고 본문과 수용 문서의 동일 해시를 확인해 수용한다.
- Atlas: [최종 수용](/Users/jspark/orca/projects/ResearchAtlas/docs/integrations/documents-atlas/contract-v1-acceptance-2026-09-17.md)의 ‘최종 수용 — 보완본 확인’. 필수 2건 해소·차단점 없음.
- Documents: [최종 수용](/Users/jspark/orca/documents/doc/integrations/pilot-atlas/acceptance-v1-2026-09-17.md)의 ‘최종 수용 — 2026-09-17’. 필수 보완 해소·차단점 없음.

## 확정 내용

Pilot 변환 접수 → Atlas 영속 import 의뢰 → 최초 1회 및 600초 주기 Documents 조회 → 고정 결과 회수·지식화 → Pilot 60초 이벤트 조회·event ID ACK.

MCP/HTTP는 동일 의미·영수증을 공유한다. 원문 동일 재변환은 source/version 유지 및 extraction/result·위키 이력 추가. 기존 A1 ask와 재시작 시 기존 작업 자동 실행 금지는 유지한다. 신규 보관 정책은 자동 만료 없음·미회수 삭제 보호·명시적 강제 삭제 tombstone이며 ACK는 연구 채택이나 삭제 허가가 아니다.

최종 수정: operation 필수 영수증 조회와 convert.file/convert.jats 분리, 인증된 Pilot 제출자/고정 Atlas 회수자 허용 매핑, receipt·consumer·정확한 result_ref에 묶인 ACK, 다른 의뢰·결과 보호. key 복구는 원 접수자 인증으로 제한한다.

## 확인과 다음 작업

본문 링크·형식 검사와 해시 대조를 수행했다. 자동 서비스 수락 시험은 아직 실행하지 않았다. 담당자는 §8의 작은 구현 단위를 기준으로 계획을 작성한다. Documents identity/접수 멱등·snapshot/회수 계약을 우선하고 Atlas 및 Pilot은 같은 고정 계약 fixture로 병행 준비할 수 있다.

**계약 확정은 코드 구현·배포·실제 문서 변환·원문 등록·M1 연구 재개가 아니다.** 현재 새 논문은 XML 확보·발췌 QA 단계로 유지한다. 규범 변경이 필요하면 수정본 해시와 영향·수용 기록을 별도로 남긴다.
