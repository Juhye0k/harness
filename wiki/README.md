# Shortform 프로젝트 위키

> 게시 이력: 이전 원본 `0167efd`의 PR #5와 세로 출력 샘플 PR #6은 main에 병합됐다. 이번 통합 변경은 `feat/integrate-transcript-quality` 브랜치 게시 대상이며 운영 배포·실제 Google 로그인 검증과 구분한다.

> 기준일: 2026-11-15 · 대상: 처음 합류한 개발자와 프로젝트 검토자

롱폼 영상에서 복수 하이라이트를 추천하고, 사용자가 자막을 수정해 숏폼으로 출력하는 서비스를 만든다. 개발 과정에서는 AI 코딩 에이전트의 변경을 검증할 하네스도 함께 개선한다.

**10초 추출과 한국어 전사 기반 하이라이트 추천·선택 추출을 연결했다.** 추천 AI는 기본 비활성화이며 실제 모델 품질은 미평가다. SNS-006은 [확인 후 YouTube 업로드](05-development/youtube-upload.md)를 추가하며 별도 승인된 합성 영상으로 실제 비공개 Shorts 업로드·Studio 분류를 확인했다. 자막 편집·운영 배포·자동 복구는 후속 단계다. [추천 실행 안내](05-development/highlight-recommendations.md)와 [현황](07-governance/status.md)에서 검증 범위를 확인한다.

공식 문서 열람 위치는 [GitHub Wiki](https://github.com/Juhye0k/short-form/wiki)다. 카테고리별 목차와 사이드바에서 세부 문서를 탐색한다. 코드 저장소의 wiki/ 폴더에는 게시 원본을 보관한다.

## 처음 읽는 순서

최근 [실제 자막 품질 평가와 두 변경 통합](05-development/harness/changes/transcript-quality-integration.md)을 진행했다. 원문·시간 범위는 보존했으나 고정 샘플의 표시 가독성 초안은 미달이며, 인식 정확도는 확인된 정답 전사가 필요하다.

1. [문제 정의](01-product/problem-definition.md)와 [범위](01-product/scope-and-reference.md)
2. [현황과 검증 근거](07-governance/status.md)
3. [단계별 실행 계획](02-delivery/roadmap.md)
4. [시스템 구조](03-architecture/system-overview.md)와 [실행 흐름](03-architecture/runtime-flows.md)
5. [기술 선택 근거](04-decisions/README.md)
6. [개발 환경 시작](05-development/onboarding.md)과 [하네스 시작하기](05-development/harness/README.md)

## 카테고리

| 카테고리 | 찾을 수 있는 내용 |
|---|---|
| [01 제품](01-product/README.md) | 문제·사용자·가치·MVP·참고 제품 |
| [02 실행 계획](02-delivery/README.md) | 0~6단계 설계와 완료 기준 |
| [03 아키텍처](03-architecture/README.md) | 구성도·현재/목표 흐름·데이터·API |
| [04 의사결정](04-decisions/README.md) | FastAPI·PostgreSQL·Redis/Celery와 대안 |
| [05 개발](05-development/README.md) | 실행·검사·AI 협업·리뷰·용어 |
| [06 운영](06-operations/README.md) | 배포·비용·확장·장애 점검 |
| [07 관리](07-governance/README.md) | 구현 현황·미결정 사항·문서 규칙 |

## 자주 찾는 질문

- Redis와 Celery는 무엇이 다른가? → [ADR-003](04-decisions/adr-003-redis-celery.md)
- 지금 호출할 수 있는 API는? → [현재 API](03-architecture/api-contract.md)
- 다음에 무엇을 구현하는가? → [2단계](02-delivery/phase-02-video-jobs.md)
- 점수가 좋아졌는지 어떻게 아는가? → [AI 평가](02-delivery/phase-04-ai-evaluation.md)
- ready는 정상인데 워커가 응답하지 않는다면? → [점검 절차](06-operations/runbook.md)
- 어디까지 결정됐는가? → [미결정 목록](07-governance/open-decisions.md)
- AI에게 어떤 요청을 했고 무엇을 얻었는가? → [프롬프트·결과와 포트폴리오 근거](05-development/harness/records/README.md)

## 문서 사용 원칙

구현 사실은 코드·검사 근거와 함께, 계획은 완료 조건과 함께 읽는다. 정하지 않은 공급자·일정·품질 목표는 임의로 확정하지 않는다. 문서를 추가할 때는 [작성 규칙](07-governance/document-guide.md)을 따른다.

[저장소 README](../README.md) · [작업 규칙](../AGENTS.md) · [아키텍처 SVG](../docs/architecture.svg)
