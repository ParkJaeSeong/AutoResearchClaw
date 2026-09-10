# 자료 수집 CLI

`research apply --operation m1.source.capture`는 앞 단계의 검토 완료를 요구하지 않고 확보한 파일을 저장한다. 기존 collect/extract, corpus 승인, 쟁점 해소, M1 인계 조건은 변경하지 않는다.

입력 JSON의 최상위 필드는 `captures` 하나이며, 비어 있지 않은 배열이다. 각 항목에는 아래 필드만 넣는다.

| 필드 | 값 |
| --- | --- |
| source_key | DOI 또는 출처 URL을 나타내는 문자열 |
| source_version | 커밋·자료 버전 또는 원문 해시 |
| access_url | 실제 출처의 http/https URL. 인증 정보를 넣지 않음 |
| access_status | metadata_only, abstract, full_text 중 하나. 파일 확보 범위이며 전부 읽었다는 뜻이 아님 |
| filename | 표시용 파일 이름. 서버가 이 경로를 열지 않음 |
| reading_scope | 실제로 읽고 확인한 범위 |
| limitations | 미확정 사항 문자열 배열. metadata_only/abstract는 한계 필수 |
| producer_id | 수집 기록 작성자. 인증된 사용자 승인으로 해석하지 않음 |
| sha256 | 파일의 실제 SHA256 |
| content_base64 | 같은 파일 바이트의 표준 base64 인코딩 |

파일에서 값을 만들 때는 `hashlib.sha256(path.read_bytes()).hexdigest()`와 `base64.b64encode(path.read_bytes()).decode()`를 사용한다. 해시만 맞춰 적고 파일을 생략할 수 없다. 입력 전체를 검증한 뒤 한 번에 기록하며 오류가 있으면 HEAD는 바뀌지 않는다.

```sh
researchclaw-codex research apply ROOT --operation m1.source.capture \
  --payload captures.json --expected-head HEAD --command-id CAPTURE_COMMAND_ID --json
researchclaw-codex research inspect ROOT --json
```

실패 후 재시도할 때는 같은 입력·command-id를 유지한다. 성공 여부를 모르는 경우도 새 ID로 처음부터 실행하지 않는다. 같은 command-id의 다른 입력은 충돌로 거부한다. 다른 command-id로 동일 파일·메타데이터를 보내면 기존 수집 ID를 재사용하고 재등록 이벤트만 남는다. 바이트 또는 읽기 범위가 바뀌면 기존 기록을 지우지 않고 새 기록을 추가한다.

`inspect`의 `source_captures`와 UI의 ‘확보한 자료’에서 기록을 확인한다. `usage_status=unassessed`는 이 수집 경로에서 사용 판단을 하지 않았다는 뜻이다. 원시 바이트는 불변 저장소에 보존하며 공개 viewer에서는 수집 메타데이터와 외부 출처 연결만 제공한다.
