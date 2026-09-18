# Pilot 근거 검토 단계: 구현·검증 기록

상태: 첫 단계의 코드와 격리 합성 실행·UI 연결 검증. 실제 모델 연구·외부 운영 연결·M1 전체 완주 아님.

## 구현한 경로

- 실행 계약과 입력을 불변 object로 보관하고 시작 전 입력 검사.
- 역할별 시작/제출/생존 기록, 초기 의견 전원 제출 장벽, 회차별 발언 공개.
- 조정자 결과의 schema·근거 참조·필수 검토·정책/시도 유효성을 검사한 뒤 자료 사용 범위 채택 또는 보완.
- 실패 결과 보존, 새 generation/attempt로 보완, 이전 기록 조회 유지.
- 요청 의도→모델 실행→결과 원형 저장→graph 게시. 게시 실패 후 캐시 재사용; 실행 여부 불명확한 시도는 자동 재호출하지 않음.
- 실행 중 정지/새 시도 전환 이후 결과는 로컬 보존하고 현재 작업으로 게시하지 않음. 명령 내부에서도 정책을 재검사해 읽기/commit 사이 경쟁을 차단.
- 같은 graph로 UI 투영: 단계별 수행 스택, 첫/상호/최종 의견 탭, 원문 펼침, 검사·보완·결과·근거. 45초 이상 생존 기록 미관측 안내는 HEAD 불변 때도 갱신하며 과거 HEAD는 현재 시각으로 낡았다고 표시하지 않음.
- lifecycle 작업이 있는 프로젝트에서 기존 policy completed로 M1 완료를 우회할 수 없음. 첫 단계 accepted는 자료 사용 범위이며 M1 완료 아님.

## 계획 대비 구현 판단

1. 계획의 begin hash-only 계약에는 최초 object 생성 경로가 없었다. `execution.begin`에서 inline contract/input/assignment 또는 이미 commit된 *_ref를 받고 같은 atomic commit으로 bytes/hash를 고정했다. 임의 object 쓰기/임의 state patch API는 추가하지 않았다.
2. 기존 import council에는 선택적 on_event callback을 추가해 기본 호출 호환을 유지했다. 새 runner는 개별 역할 결과의 영속 저장과 재개를 관리한다. 기존 import worker를 새 runner로 자동 교체하지 않았다.
3. 기존 호스트 출력은 rationale/recommendation만 있어 새 조정자 claims/unresolved 계약을 충족하지 못한다. 별도 execution_host adapter와 CLI 진입점을 추가했다. 실호스트는 이번 검증에서 호출하지 않았고 model_id는 기본 모델 미확인으로 정직하게 기록한다.
4. 현재 계약은 evidence_review/research/M1 한 종류다. 목적별 계약·프로필 모델 선택·다른 단계의 successor·Documents/Atlas 자동 dispatch는 다음 구현 단위다. 지원하지 않는 계약/의존성은 거부한다.
5. UI의 알려진 인증 문자열/로컬 경로 가림은 원본 저장과 분리하고 가림 표시를 제공한다. 모든 비밀을 검출한다는 보장은 하지 않는다.

## 검증

- RED 확인 후 구현: 계약 부재, lifecycle 명령 부재, runner/host 부재, 발언 callback 부재, 정책 정지 후 게시 거부, 생존 경고, 민감 문자열 표시 구분.
- 역할 10개 결과(전문가3×3회차+조정자)를 쓰는 합성 실행: 필수 근거 누락이면 needs_work, 새 시도로 보완하면 accepted. M1 상태는 completed가 아님.
- 새 Python 프로세스 복구: 첫 역할 결과 저장 직후 게시 중단. 새 프로세스는 첫 결과를 재사용하고 나머지9개만 호출해 완료했다.
- 독립 리뷰의 정지 직후 게시 경쟁, 생존 미관측 표시 누락, 인용된 인증 문자열/Windows 경로 표시 문제를 수정하고 재검토 통과.
- 실제 viewer HTTP + 브라우저: running→needs_work→revision2→accepted 자동 갱신, 두 시도 보존, 열린 카드 유지, 대화 탭, 과거 HEAD가 미래 accepted를 표시하지 않는 것을 확인.
- 실제 viewer 레이아웃18조건: 밝음/어두움 × 데스크톱1280/1920/2560×메뉴 펼침/접힘, 모바일320/390/768. 가로 넘침·JavaScript 오류0.

증거: `output/evaluations/lifecycle-first-slice/`의 browser-verification.json, layout-verification.json, needs-work.png, accepted.png, mobile-dark.png, 격리 project와 실행 원형. 스크린샷은 합성 검증임을 화면에 표시한다. component 단독 추가 검수는 `/tmp/pilot-execution-ui/`에 있다.

전체 graph suite 탐색에서는 현행 receive가 active QA를 이미 거부하는데 이를 허용한다고 가정한 기존 테스트 준비3건이 실패했다. 테스트를 완료 QA 수신 후 과거 cached-active 상태 재현으로 수정해 기존 검증 목적을 유지했고, 현재 receive의 active 거부/HEAD 불변 테스트를 추가했다. 해당24건 재실행·독립 검토 통과. Atlas 운영 코드는 변경하지 않았다. 전체 graph 탐색 실행은 397 pass/3 위 준비 실패 지점 이후 고비용 실행 중 중단했으며, 전체 suite 통과라고 보고하지 않는다. 최종 검증은 변경 영향의 저장소/명령/에피소드/뷰/Atlas advance와 신규 실행 경로를 선택해 수행한다.

## 확인 및 다음 작업

확인용 실행은 격리 프로젝트로 제공했다. 기존8771 UI가 새 execution.js를404로 반환해 Pilot UI만 재시작했다(PID27216). 최초5초 기동 확인은 시간 초과했으나 이후 실제 브라우저에서 기존 PC/CNT 화면·JS 오류0·새 파일 원형200을 확인했다. Documents·Atlas와 연구 워커는 교체하지 않았다. 기존 연구의 완료/승인/원형과 프로젝트 목록을 변경하지 않았다.

다음 구현은 B: Documents·Atlas의 검증된 수신 결과를 새 work/attempt에 바인딩하고, 수신→검토 배정→원래 작업 반환까지 연결한다. 이후 C의 M1 필수 단계와 전체 종료 gate, D의 모델/표준 산출물, E의 실제 모델·종단 수락을 진행한다. 첫 단계의 구조 검사와 합성 테스트를 과학적 결과 품질 또는 M1 전체 완료로 확대하지 않는다.

최종 선택 회귀: Python **112 passed**, Node **83 passed**. 변경 파일 diff 공백 검사 통과. 전체 suite의 모든 테스트가 통과했다는 뜻은 아니다.

실제 viewer 재검증의 영속 종료 이벤트→화면 반영 관측 지연은 **2,546ms**였다(`timing/browser-verification.json`). 일회 관측이며 지속 성능 보장은 아니다. 기존 UI 동작 점검은 `production-ui-smoke.json`, 확인용 합성 화면은 별도 localhost62641에서 제공했다.
