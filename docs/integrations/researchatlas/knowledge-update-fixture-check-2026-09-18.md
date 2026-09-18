# Atlas E 합성 fixture 소비자 검사

Atlas tests/fixtures/knowledge-update-v1을 Pilot tests/fixtures/atlas-knowledge-v1에 복사해 고정했다. 비운영·비과학 근거 fixture이며 API 응답 전체 또는 실제 source 서비스가 아니다.

manifest 원형 hash/instance/job, QA/page artifact mapping, 전체 chunk base64·decoded size·offset/eof/hash를 대조했다. 제공된 QA/page 원형과 chunk 복원 바이트가 일치한다. 손상 offset/eof/size/base64/ID, 잘린 스트림, 다른 instance 거절 시험 포함. 새 transport 검사 9개와 기존 inbox/worker 9개 총18개 통과.

검사 범위는 패키지 transport뿐이다. QA 본문 의미/전체 schema 검증, source 실회수, HTTP/MCP·resume·전체 fencing·모델 반영·색인·운영 준비 완료를 뜻하지 않는다. 생산자 fixture에서 이번 검사 범위의 불일치 없음.
