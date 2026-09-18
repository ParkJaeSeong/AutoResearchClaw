---
schema_version: 1
id: qa-abbasi-process-direction-20260912-001
type: qa
created_at: '2026-09-12T12:27:21.051225+00:00'
input_sha256: 5d1728a5060d4c1d53c581722f18131c9006acf34c7abe7d83d1719617c4a5ff
question: 동일한 CNT 함량에서 성형 조건에 따른 전기 전도도 차이를 배향만으로 설명할 수 있는가? 다른 공정 변화와 측정 방향은 어떻게
  구분할 것인가?
answer: '**현재 위키와 Abbasi 연구만으로는 전기전도도 차이를 배향만으로 설명했다고 결론내릴 수 없습니다.** 같은 CNT 함량이라도
  성형 공정·시편 형상·열 이력이 함께 달라졌습니다. 배향은 저자가 제시한 중요한 설명이지만, 단독 원인으로 분리해 검증한 결과와는 구분해야 합니다.


  **논문에서 확인한 것과 저자의 해석**


  - **관찰:** PC/MWCNT 5 wt% 시편을 비교한 Figure 16에서 Raman 배향 지표가 높은 공정의 시편일수록 전기전도도가 낮았습니다.
  정확한 표현은 “배향 증가와 전도도 감소가 함께 관찰됐다”입니다.

  - **저자의 해석:** CNT가 정렬되면서 서로 연결될 기회가 줄고, 전도성 연결망을 만들기 어려워진다고 설명합니다. 이는 결과에 대한 기작
  해석이며 다른 공정 효과를 모두 배제했다는 뜻은 아닙니다.


  근거: [Abbasi 위키](/Users/jspark/orca/projects/ResearchAtlas/data/library/wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md),
  [보관 원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf)의
  PDF 13–14쪽 Discussion·Figure 16.


  **특히 다음 구분이 필요합니다.**


  | 구분할 항목 | 원문에서 확인한 내용 | Atlas의 판단 |

  |---|---|---|

  | 공정과 배향 | 압축·사출·마이크로사출에서 유동과 형상이 함께 달라짐(PDF 3·6쪽) | 공정 이름이나 사출 속도를 배향의 직접 측정값으로
  대신하면 안 됨 |

  | 내부 위치와 방향 | 중앙 게이트의 disk는 중심부와 벽 근처의 유동·배향이 다르다고 설명(PDF 10쪽 §4.2) | 배향 지표 하나로
  시편 전체 연결망을 대표한다고 가정하기 어려움 |

  | 냉각·완화 | 얇은 마이크로사출 시편의 빠른 냉각과 제한된 사슬 완화를 논의(PDF 13쪽) | 배향과 함께 변하는 열 이력도 기록해야 함.
  이 문단 자체가 전도도에 대한 독립 효과의 증거는 아님 |

  | CNT 길이 | TEM의 길이는 절단면에서 보이는 CNT 구간의 끝점 간 거리라고 명시(PDF 8쪽 §4.1) | 그 분포만으로 공정에 따른
  실제 CNT 절단·손상을 판정하면 안 됨 |


  저자는 성형 전후 순수 PC 점도가 실험 오차 안에서 비슷해 **해당 공정의 열화가 미미했다**고 보고합니다(PDF 13쪽). 따라서 열화를 이미
  입증된 원인으로 추가해서도 안 됩니다. 위 표의 원문 위치는 모두 같은 [Abbasi 원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf)입니다.


  **측정 방향은 이렇게 분리해야 합니다.**


  Raman의 ∥·⊥는 **편광과 유동 방향의 관계**입니다. 전기전도도의 ∥·⊥는 **전류와 유동 방향의 관계**로 따로 기록해야 합니다. 두
  표기를 같은 의미로 읽으면 안 됩니다.


  원문 §2.6에는 압축 성형 disk의 **두께 방향 DC 저항 측정**이 명시돼 있습니다. 그러나 이것만으로 Figure 16에 포함된 모든
  사출 시편의 전류 방향과 전극 배치까지 확정할 수는 없습니다. 따라서 현재 근거로 “유동 방향 전도도가 감소했다”거나 방향별 감소 크기를 말할
  수 없습니다. [원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf),
  PDF 4쪽 §2.4·§2.6.


  **Atlas가 제안하는 구분 절차**는 다음과 같습니다. 논문에서 이미 수행·검증한 절차라는 뜻은 아닙니다.


  1. 같은 배합·재료 배치·시편 형상을 기준으로 공정 조건을 비교하고, 온도·압력·속도·냉각 및 건조 이력을 남깁니다.

  2. 동일 시편 또는 대응하는 시편에서 유동 평행·면내 수직·두께 방향의 전도도를 구분합니다. 전극 접촉, 측정 온도와 치수를 함께 기록해 방향과
  측정 조건의 차이를 분리합니다.

  3. 배향은 별도로 측정하고, 같은 위치의 분산·응집과 연결망도 확인합니다. CNT 손상 여부를 평가한다면 절단면의 겉보기 길이와 실제 길이를
  구분해야 합니다.

  4. 방향과 다른 관측 조건을 맞춘 뒤에도 배향과 전도도의 관계가 남는지 봅니다. 그래도 미측정 공정 효과가 남을 수 있으므로 곧바로 단독 인과관계로
  승격하지 않습니다.


  배향을 측정할 수 없는 현재 Pilot 설계에서는 **“공정 A와 B의 전도도 차이”를 검증 대상으로 삼고, 배향에 의한 연결망 변화는 가능한
  설명으로 남기는 것**이 적절합니다. 배향 효과와 다른 설명을 구별하려면 시편별 전극 배치·측정 방향, 대응하는 배향·미세구조 자료가 추가로 필요합니다.


  이번 답변은 위키 2개와 Abbasi v1의 관련 원문 구절을 확인한 결과입니다. Abbasi 상세 연구 그래프는 조회 0건이어서 위키·원문으로
  보완했으며, 독립된 여러 논문의 교차 검증은 아닙니다.

  '
project: null
consulted_pages:
- path: wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md
  page_id: page-23d3622f1c524198
  sha256: f68d90c10088193b6ce796b7c7f81414c4751a8b0a45dfb29ac6fa6511534afa
- path: wiki/concepts/필러-배향과-퍼콜레이션-page-3d08ab5c5315405c.md
  page_id: page-3d08ab5c5315405c
  sha256: cf72e995ffd04a97d4b51459e8718ae2c031eb78ca7d0daa5a59c029a917b4a9
candidates:
- id: C1
  text: 중앙 게이트 disk의 중심부에는 주 방사 유동에 수직인 배향, 벽 근처에는 방사 유동 방향 배향을 설명한다. 평균 배향 지표와 시편
    내부 분포를 구분할 필요가 있다.
  tag: addition
  source_refs:
  - source_id: source-274e322ab43944d1
    version: 1
    locator: PDF 10쪽 §4.2 Raman spectroscopy
    raw_path: raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf
    sha256: 3d4e6bec0d17fec23c3c2ed38c2a3fc852c8f28eff629b247bed967b28da52b7
  target_pages:
  - path: wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md
    page_id: page-23d3622f1c524198
    sha256: f68d90c10088193b6ce796b7c7f81414c4751a8b0a45dfb29ac6fa6511534afa
- id: C2
  text: Fig7의 nanotube length는 TEM 절단면에 보이는 구간의 끝점 간 거리이며 절단 방향과 배향의 영향을 받는다. 실제 CNT
    길이·손상 분포로 직접 해석하지 않는다.
  tag: addition
  source_refs:
  - source_id: source-274e322ab43944d1
    version: 1
    locator: PDF 8쪽 §4.1, Fig6–7 설명
    raw_path: raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf
    sha256: 3d4e6bec0d17fec23c3c2ed38c2a3fc852c8f28eff629b247bed967b28da52b7
  target_pages:
  - path: wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md
    page_id: page-23d3622f1c524198
    sha256: f68d90c10088193b6ce796b7c7f81414c4751a8b0a45dfb29ac6fa6511534afa
- id: C3
  text: 저자는 얇은 마이크로사출 시편의 빠른 냉각·사슬 완화 제한을 논의하고, 순수 PC의 성형 전후 점도가 실험 오차 안에서 비슷해 해당
    공정 열화가 미미하다고 보고한다. 전기전도도에 대한 열 이력의 독립 효과를 검증한 것으로 확대하지 않는다.
  tag: addition
  source_refs:
  - source_id: source-274e322ab43944d1
    version: 1
    locator: PDF 13쪽 §4.5 말미·Discussion 앞
    raw_path: raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf
    sha256: 3d4e6bec0d17fec23c3c2ed38c2a3fc852c8f28eff629b247bed967b28da52b7
  target_pages:
  - path: wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md
    page_id: page-23d3622f1c524198
    sha256: f68d90c10088193b6ce796b7c7f81414c4751a8b0a45dfb29ac6fa6511534afa
---

# 질문

동일한 CNT 함량에서 성형 조건에 따른 전기 전도도 차이를 배향만으로 설명할 수 있는가? 다른 공정 변화와 측정 방향은 어떻게 구분할 것인가?

# 당시 답변

**현재 위키와 Abbasi 연구만으로는 전기전도도 차이를 배향만으로 설명했다고 결론내릴 수 없습니다.** 같은 CNT 함량이라도 성형 공정·시편 형상·열 이력이 함께 달라졌습니다. 배향은 저자가 제시한 중요한 설명이지만, 단독 원인으로 분리해 검증한 결과와는 구분해야 합니다.

**논문에서 확인한 것과 저자의 해석**

- **관찰:** PC/MWCNT 5 wt% 시편을 비교한 Figure 16에서 Raman 배향 지표가 높은 공정의 시편일수록 전기전도도가 낮았습니다. 정확한 표현은 “배향 증가와 전도도 감소가 함께 관찰됐다”입니다.
- **저자의 해석:** CNT가 정렬되면서 서로 연결될 기회가 줄고, 전도성 연결망을 만들기 어려워진다고 설명합니다. 이는 결과에 대한 기작 해석이며 다른 공정 효과를 모두 배제했다는 뜻은 아닙니다.

근거: [Abbasi 위키](/Users/jspark/orca/projects/ResearchAtlas/data/library/wiki/references/Flow-induced-orientation-of-multiwalled-carbon-nanotubes-in--source-274e322ab43944d1-v1.md), [보관 원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf)의 PDF 13–14쪽 Discussion·Figure 16.

**특히 다음 구분이 필요합니다.**

| 구분할 항목 | 원문에서 확인한 내용 | Atlas의 판단 |
|---|---|---|
| 공정과 배향 | 압축·사출·마이크로사출에서 유동과 형상이 함께 달라짐(PDF 3·6쪽) | 공정 이름이나 사출 속도를 배향의 직접 측정값으로 대신하면 안 됨 |
| 내부 위치와 방향 | 중앙 게이트의 disk는 중심부와 벽 근처의 유동·배향이 다르다고 설명(PDF 10쪽 §4.2) | 배향 지표 하나로 시편 전체 연결망을 대표한다고 가정하기 어려움 |
| 냉각·완화 | 얇은 마이크로사출 시편의 빠른 냉각과 제한된 사슬 완화를 논의(PDF 13쪽) | 배향과 함께 변하는 열 이력도 기록해야 함. 이 문단 자체가 전도도에 대한 독립 효과의 증거는 아님 |
| CNT 길이 | TEM의 길이는 절단면에서 보이는 CNT 구간의 끝점 간 거리라고 명시(PDF 8쪽 §4.1) | 그 분포만으로 공정에 따른 실제 CNT 절단·손상을 판정하면 안 됨 |

저자는 성형 전후 순수 PC 점도가 실험 오차 안에서 비슷해 **해당 공정의 열화가 미미했다**고 보고합니다(PDF 13쪽). 따라서 열화를 이미 입증된 원인으로 추가해서도 안 됩니다. 위 표의 원문 위치는 모두 같은 [Abbasi 원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf)입니다.

**측정 방향은 이렇게 분리해야 합니다.**

Raman의 ∥·⊥는 **편광과 유동 방향의 관계**입니다. 전기전도도의 ∥·⊥는 **전류와 유동 방향의 관계**로 따로 기록해야 합니다. 두 표기를 같은 의미로 읽으면 안 됩니다.

원문 §2.6에는 압축 성형 disk의 **두께 방향 DC 저항 측정**이 명시돼 있습니다. 그러나 이것만으로 Figure 16에 포함된 모든 사출 시편의 전류 방향과 전극 배치까지 확정할 수는 없습니다. 따라서 현재 근거로 “유동 방향 전도도가 감소했다”거나 방향별 감소 크기를 말할 수 없습니다. [원문 v1](/Users/jspark/orca/projects/ResearchAtlas/data/library/raw/articles/source-274e322ab43944d1/v1/abbasi-2010.pdf), PDF 4쪽 §2.4·§2.6.

**Atlas가 제안하는 구분 절차**는 다음과 같습니다. 논문에서 이미 수행·검증한 절차라는 뜻은 아닙니다.

1. 같은 배합·재료 배치·시편 형상을 기준으로 공정 조건을 비교하고, 온도·압력·속도·냉각 및 건조 이력을 남깁니다.
2. 동일 시편 또는 대응하는 시편에서 유동 평행·면내 수직·두께 방향의 전도도를 구분합니다. 전극 접촉, 측정 온도와 치수를 함께 기록해 방향과 측정 조건의 차이를 분리합니다.
3. 배향은 별도로 측정하고, 같은 위치의 분산·응집과 연결망도 확인합니다. CNT 손상 여부를 평가한다면 절단면의 겉보기 길이와 실제 길이를 구분해야 합니다.
4. 방향과 다른 관측 조건을 맞춘 뒤에도 배향과 전도도의 관계가 남는지 봅니다. 그래도 미측정 공정 효과가 남을 수 있으므로 곧바로 단독 인과관계로 승격하지 않습니다.

배향을 측정할 수 없는 현재 Pilot 설계에서는 **“공정 A와 B의 전도도 차이”를 검증 대상으로 삼고, 배향에 의한 연결망 변화는 가능한 설명으로 남기는 것**이 적절합니다. 배향 효과와 다른 설명을 구별하려면 시편별 전극 배치·측정 방향, 대응하는 배향·미세구조 자료가 추가로 필요합니다.

이번 답변은 위키 2개와 Abbasi v1의 관련 원문 구절을 확인한 결과입니다. Abbasi 상세 연구 그래프는 조회 0건이어서 위키·원문으로 보완했으며, 독립된 여러 논문의 교차 검증은 아닙니다.
