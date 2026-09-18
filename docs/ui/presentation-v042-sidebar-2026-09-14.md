# Presentation v0.4.2 메뉴 적용 · 2026-09-14

기준: [통합 디자인 가이드 6절](</Users/jspark/orca/Presentation/PPT 디자인/통합_디자인_가이드.md>). Standard의 접힘 화면과 같은 상대 배치와 SVG 도형을 Pilot 연구 UI에 적용했다.

## 적용 내용

- 펼침: 기관 CI 아래 제품 행 오른쪽에 PanelLeftClose 버튼.
- 접힘: 64px 레일, 제품 아이콘 아래 20px 간격으로 PanelLeftOpen 버튼, 그 아래 탐색 메뉴.
- 버튼 40×40px, 반경 8px, 테두리 1px, SVG 20×20px. 터치 포인터에서는 44×44px.
- 접근 이름과 툴팁은 ‘주 메뉴 접기/주 메뉴 펼치기’. aria-expanded, aria-controls, Enter/Space 조작 제공.
- 접힘 선택은 Pilot 전용 localStorage에 저장한다. 저장이 차단돼도 현재 화면에서 동작한다. 모바일 메뉴는 이 값을 변경하지 않는다.
- 접힌 레일 하단 설정 버튼은 메뉴를 펼치고 화면 모드 선택으로 초점을 이동한다.
- 모바일은 브랜드 행 오른쪽 Menu 버튼과 열린 모달 오른쪽 X 버튼을 사용한다. 배경 잠금·Escape·초점 복귀는 유지한다.
- 본문을 다시 생성하거나 연구 요청을 보내지 않고 배치만 바꾼다. 전체 폭 규칙을 유지한다.

## 확인 근거

`output/evaluations/pilot-sidebar-v042/`에 측정값과 화면을 보관한다.

| 검사 | 결과 |
| --- | --- |
| 밝음/어두움 × 1280/1920/2560 × 펼침/접힘 | 12개 조건 통과: 버튼·SVG 크기, 상대 위치, 레일 중심, 20px 간격, 전체 폭 |
| 접힘 상태 재진입, 모바일 왕복, 설정 초점, 저장 차단, Enter/Space | 통과 |
| 작성 중인 Atlas 질문 | 접기/펼치기 후 유지, 전송 없음 |
| 320/390/768px | 페이지 가로 넘침 없음 |
| 기존 화면 검사 | 60개 조건 통과, 브라우저 오류·쓰기 요청 없음 |
| 단계·피드백 UI 단위 검사 | 13개 통과 |

반복 검사는 운영 서버가 제공하는 HTML/CSS/JS와 실제 연구 조회의 고정 응답을 사용했다. API 응답 고정 여부와 별도로 실제 운영 조회 화면은 `live.json`, `live-expanded.png`, `live-collapsed.png`에 기록한다. 검수에서 연구 자료를 생성하거나 단계를 완료 처리하지 않는다.

## 범위와 남은 차이

Pilot의 기존 모바일 전환점 1024px는 유지한다. 따라서 768px는 데스크톱 레일 대신 모달 탐색으로 검사했다. 차트가 없는 현재 연구 화면에서 차트 재배치는 해당 없음이며, 향후 차트 추가 시 별도 검수가 필요하다. 표·본문의 폭과 기존 선택·입력 보존은 현재 화면 검사 범위다. 전 제품 또는 전체 접근성 인증을 뜻하지 않는다.

구현: `researchclaw/codex/research_ui/index.html`, `shell.js`, `styles.css`.
재검사: `PILOT_UI_VIEW=<연구 조회 JSON> PLAYWRIGHT_MODULE=<playwright 경로> node scripts/ui/check_sidebar.cjs`.
