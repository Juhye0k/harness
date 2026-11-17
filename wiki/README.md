# Shortform 프로젝트 위키

**긴 영상에서 하이라이트를 추천하고, 사용자가 자막을 수정해 숏폼 영상으로 출력하는 서비스를 만든다.** 이 위키는 처음 합류한 개발자가 제품의 목적, 처리 흐름, 개발·검증 방법을 순서대로 이해하도록 안내한다.

> 기준일: 2026-11-18 · 대상: 신입 개발자·프로젝트 검토자

## 지금 어디까지 만들었나

링크·로컬 파일 입력, 한국어 전사 기반 추천, 후보 선택, 자막 편집·저장, 세로 MP4·SRT 다운로드, 확인 후 YouTube 업로드를 연결했다. 자동 검사에서는 AI·YouTube를 시험용 응답으로 대체하고 나머지 API·DB·워커·영상 처리를 실제로 실행한다.

실제 영상의 추천·자막 품질, 편집한 완성본의 실계정 게시, 운영 배포는 각각 별도 확인이 필요하다. 최신 결과는 [현재 현황](07-governance/status.md) 한 곳에서 확인한다.

## 처음 읽는 순서

| 순서 | 읽을 문서 | 읽고 이해할 내용 |
|---|---|---|
| 1 | [문제 정의](01-product/problem-definition.md) | 누구의 어떤 편집 작업을 줄이려는가 |
| 2 | [전체 사용자 흐름](05-development/complete-flow.md) | 영상 입력부터 다운로드까지 무엇을 하는가 |
| 3 | [시스템 구조](03-architecture/system-overview.md)·[실행 과정](03-architecture/runtime-flows.md) | API·DB·Redis·워커가 어떻게 연결되는가 |
| 4 | [개발 환경 시작](05-development/onboarding.md) | 내 컴퓨터에서 어떻게 실행하는가 |
| 5 | [개발 하네스](05-development/harness/README.md) | AI의 변경을 어떤 규칙과 검사로 확인하는가 |
| 6 | [남은 단계](02-delivery/roadmap.md) | 다음에 무엇을 검증하고 확장할 것인가 |

## 목적에 맞게 찾아보기

| 카테고리 | 여기서 찾는 답 |
|---|---|
| [01 제품](01-product/README.md) | 사용자 문제·MVP 범위·참고 제품 |
| [02 실행 계획](02-delivery/README.md) | 단계별 목표·작업 순서·완료 조건 |
| [03 아키텍처](03-architecture/README.md) | 구성 요소·데이터·API·작업 상태 |
| [04 기술 선택](04-decisions/README.md) | FastAPI·PostgreSQL·Redis/Celery를 고른 이유 |
| [05 개발과 하네스](05-development/README.md) | 실행·자막·추천·테스트·AI 협업 |
| [06 운영](06-operations/README.md) | 비용·배포 준비·장애 대응 |
| [07 현황과 문서 관리](07-governance/README.md) | 현재 결과·미결정 사항·과거 검증 근거 |

## 자주 찾는 문서

- 기능이 동작하는지 확인하기: [검증 절차](05-development/harness/verification.md)
- 통신이 끊기거나 워커가 종료됐을 때: [실패 경로 검사](05-development/failure-path-testing.md)·[장애 대응](06-operations/runbook.md)
- 추천과 자막이 실제로 쓸 만한지 평가하기: [추천 평가](05-development/recommendation-improvement-loop.md)·[전사 품질 평가](05-development/transcript-quality-evaluation.md)
- AI에게 요청한 내용과 결과 찾기: [작업 기록](05-development/harness/records/README.md)
- 위키에 새 문서 추가하기: [작성 규칙](07-governance/document-guide.md)

공식 열람 위치는 [GitHub Wiki](https://github.com/Juhye0k/short-form/wiki)다. 저장소의 `wiki/`는 게시 원본이며, 코드 저장소 반영과 Wiki 게시를 따로 관리한다.

[저장소 README](../README.md) · [작업 규칙](../AGENTS.md)
