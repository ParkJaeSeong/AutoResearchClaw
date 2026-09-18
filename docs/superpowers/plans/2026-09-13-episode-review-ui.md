# 작업 회차 개발 검토 UI

사용자가 종료한 회차에서 계속 진행/수정 요청과 의견을 저장한다. 연구 결론은 변경하지 않는다. 후속 작업의 실제 실행·자동 배정은 이 기능에 포함하지 않는다. 기존 episode.start의 의존 검사를 통해 허용/대기가 반영된다.

- POST /api/episodes/review: {id,decision,feedback,expected_head,command_id}. reviewer는 서버가 'local-ui-user'로 고정한다. 로컬 UI의 사용자 입력이며 인증된 서명은 아니다. arbitrary operation/author 필드는 받지 않는다.
- 본문 JSON max65536 bytes, same-origin/Host/Content-Length/Content-Type 검사. 기존 episode.review handler의 종료조건·한번검토·HEAD·멱등을 재사용한다. 응답 {head_id,episode_id,review_status,review}. 구조화 오류 400/403/409/413/503; 비밀원문 오류 노출 금지.
- UI: 종료+review_required+미검토 회차에서 의견 textarea 및 '계속 진행'/'수정 요청' 제공. 무응답을 승인하지 않는다. 실제 실험 승인이 아니라 후속 흐름 허용임을 짧게 표시한다.
- 과거 HEAD(현재와 같은 HEAD라도 pin mode)에서는 저장 불가. 보기 전환·자동 갱신 중 draft 유지. 입력은 한 번 submit 후 pending; 네트워크/5xx 응답 유실은 동일 frozen payload+command_id 재시도만 허용한다. 확정 4xx는 의견 유지하고 최신기록 갱신/재입력. 성공 후 조회실패는 저장성공으로 구분하며 재전송하지 않는다.
- 기존 view callback 및 keyed details 보존. 원래 기록·개발 검토 상태를 대리생성하지 않는다. 현재 UI 기준의 작은 공통 폼 사용.
- TDD: HTTP 실제로 합성root 저장/재전송/외부origin/잘못된필드/HEAD충돌/중복검토 검사. UI fakeDOM 또는 browser로 draft/모드/응답유실/저장후조회실패 검사. 실제 합성viewer에서 입력→저장→갱신 확인.

파일: episode_review.js(신규), episodes.js/app.js(연결), episode_http.py(신규), research_viewer.py(라우트), tests/codex_native/research_graph/test_episode_http.py 및 test_episode_review_ui.mjs(신규), 사용가이드.

## 결과

2026-09-13 구현 완료. Python35개(HTTP13·viewer4·회차18), Node49개 통과. 별도 합성 프로젝트에서 실제 UI 제출1건→새로고침 후 검토 유지, 1440/390px 표시를 확인했다. 독립 리뷰에서 지적한 짧은 HTTP 본문·중복 JSON 키·깊은 JSON 처리 수정과 재검토를 마쳤다. 저장 후 receipt 유실503 재전송도 단일 검토를 유지한다.

55383 예시와8771 실제 조회 서버를 갱신했으며 두 연구 HEAD는 유지했다. 사용자 예시 검토는 제출하지 않고 열린 입력 폼을 보여준다. 실제 실험/에이전트 시작과 후속 회차 자동 생성은 이번 범위 밖이다. 증거: output/evaluations/episode-review-ui/.
