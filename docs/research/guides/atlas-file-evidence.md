# Atlas 답변 파일을 연구에 연결하기

Atlas가 저장한 QA Markdown을 Pilot에 가져와 사용 범위·결정·추가 질문을 연결한다. Atlas 검색·추출이나 API/MCP 호출을 수행하는 기능은 아니다.

## 화면에서 사용하기

1. 연구 화면의 **Atlas 답변 가져오기**에서 QA 파일을 선택한다. 질문·답변과 참조 위키·추가 후보를 확인한다.
2. **이 연구에 가져오기**로 해당 파일 버전을 저장한다. 같은 파일은 중복 근거를 만들지 않는다.
3. **답변 사용 범위 판단**을 펼쳐 관련 질문, 허용/보류 용도, 한계와 이유를 저장한다.
4. **조정자 결정**에서 검토를 선택하고 결론·이유·한계를 기록한다. 새 판단으로 바꿀 때는 이전 결정을 연결한다.
5. **Atlas에 물어볼 질문**에 부족한 근거와 답이 바꿀 판단을 정리하고 전체 내용을 복사한다. 전송은 사용자가 Atlas에서 직접 한다.

과거 기록을 선택하면 그 시점의 내용만 표시되고 저장 기능은 잠긴다. 최신 화면에서 새 버전이 있으면 이전 답변을 사용한 결정에 안내가 붙는다. 이전 대화와 결론은 변경하지 않는다. 입력 파일 미리보기와 작성 중인 양식은 화면 자동 갱신 중에도 유지한다. 통신 오류로 저장 여부가 불명확하면 고정된 요청 요약의 재확인 버튼을 사용한다. 해당 요청을 확인하기 전에는 그 종류의 새 저장이 잠긴다.

## 첫 사례 파일

`/Users/jspark/orca/projects/ResearchAtlas/data/library/qa/records/qa-abbasi-process-direction-20260912-001.md`

현재 지원 형식은 Atlas schema_version 1 QA Markdown이다. id·question·answer가 필요하다. 원문 PDF나 일반 메모 파일은 QA 입력으로 취급하지 않는다. 한 파일은 최대10 MiB이며, 내부 링크의 PDF·다른 파일을 자동으로 열지 않는다. 출처·원문 위치·해시는 Atlas가 제공한 정보로 보존한다. 내용의 원문 대조나 과학 검증을 Pilot이 수행했다는 뜻은 아니다.

## CLI

```sh
# 미리보기: 연구 기록 변경 없음
researchclaw-codex research atlas-import ROOT ATLAS_QA.md --preview --json

# 현재 HEAD 조회
researchclaw-codex research inspect ROOT --json

# 동일 파일의 원본 바이트를 보존하여 등록
researchclaw-codex research atlas-import ROOT ATLAS_QA.md \
  --expected-head CURRENT_HEAD --command-id UNIQUE_IMPORT_ID --json
```

사용 판단·결정·질문은 각각 `external.review.record`, `external.decision.record`, `external.question.record` 공개 명령으로도 등록한다. 명령에는 정확한 근거·검토·결정 참조를 사용하며 현재 HEAD와 command_id를 지정한다. 상세 입력은 [설계서](../../superpowers/specs/2026-09-12-atlas-file-evidence-design.md)에 설명한다.

실제 에이전트 협의는 기존 `council.prepare`에서 검토 참조를 input_binding으로 고정한 뒤 `research packet`으로 역할별 입력을 받아 진행한다. 독립 초기 의견은 전원 제출 뒤 공개된다. 결정에 연결할 submission_refs는 해당 검토를 실제로 검토한 공개 최종 제출이어야 한다. 파일 가져오기는 에이전트 실행을 시작하거나 발언을 만들지 않는다. submission_refs가 빈 결정은 조정자 단독 기록으로 표시한다.

## 상태의 의미

- **가져옴·검토 전:** 파일을 보존했으며 사용 판단은 아직 없다.
- **범위를 정해 사용:** 지정 용도에서 사용하고 다른 용도는 보류한다.
- **조정자 기록:** 작성자가 기록한 결론이며 에이전트 최종 제출을 대신하지 않는다.
- **추가 질문 초안:** 저장·복사할 수 있는 요청이며 Atlas에 전송된 상태가 아니다.

기존 M1의 자체 수집·추출·승인 조건은 이번 기능으로 통과 처리하지 않는다. 외부 근거 수신 기록과 단계 완료 조건의 통합은 후속 정책 작업이다. 기존 연구 쟁점이나 실험 허가도 변경하지 않는다.
