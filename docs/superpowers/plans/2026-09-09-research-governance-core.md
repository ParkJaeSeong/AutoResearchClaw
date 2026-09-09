# 공통 연구 운영 기반 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 공통 연구 운영 기반를 독립 검토 가능한 작은 작업으로 구현한다.

**Architecture:** 공통 append-only 기록 위에 마일스톤별 adapter를 연결한다. 기존 엔진의 경로·승인을 유지하고 신규 프로젝트에서만 확장 정책을 적용한다.

**Tech Stack:** Python >=3.11, pytest, node:test, vanilla JS, 기존 wheel 패키징.

**Spec:** [설계 목차](../specs/2026-09-09-research-governance-design.md).

## 읽는 방법

이 파일은 묶음 목차다. 아래에서 현재 작업서 하나를 열고, 그 작업서에 지정된 공통 계약과 관련 설계만 읽는다. 구현 상태의 기준은 [전체 작업판](2026-09-09-research-governance.md)이다. 완료된 작업의 상세 보고서는 새 작업에 필요할 때만 읽는다.

## Task A01: 공통 기록·참조 계약

[작업서 열기](research-governance/tasks/A01.md)

## Task A02: 저장 공통부와 신규 버전 격리

[작업서 열기](research-governance/tasks/A02.md)

## Task A03: M1 기록의 명시적 가져오기

[작업서 열기](research-governance/tasks/A03.md)

## Task A04: 쟁점 전이·이관·재개

[작업서 열기](research-governance/tasks/A04.md)

## Task A05: 검증 작업과 결과 등록

[작업서 열기](research-governance/tasks/A05.md)

## Task A06: 입장 변화·요약 근거 연결

[작업서 열기](research-governance/tasks/A06.md)

## Task A07: 마일스톤별 차단·인계 판정

[작업서 열기](research-governance/tasks/A07.md)

## Task A08: 의존 관계와 변경 영향

[작업서 열기](research-governance/tasks/A08.md)

## Task A09: 반복·비용 예산과 안전한 재개

[작업서 열기](research-governance/tasks/A09.md)
