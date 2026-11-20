# Shortform 프로젝트 위키

> 긴 영상에서 후보를 추천받고, 자막을 고쳐 짧은 영상으로 만드는 프로젝트입니다. 이 위키는 제품 사용법과 기술 선택의 이유, 실제로 확인한 검사·실패 기록을 함께 설명합니다.

## 백엔드 개발자가 처음 읽는 순서

1. [어떤 문제를 해결하나요?](01-product/problem-definition.md) — 대상 사용자와 제품 가설을 이해합니다.
2. [사용자는 어떻게 영상을 만드나요?](05-development/complete-flow.md) — 입력부터 편집·출력까지 따라갑니다.
3. [어디까지 구현·검증됐나요?](07-governance/status.md) — 기능 동작과 실제 품질의 차이를 확인합니다.
4. [왜 이렇게 설계했나요?](03-architecture/system-overview.md) — 10초 추출 요청을 따라가며 누가 작업을 접수하고, 중복 실행을 막고, 다운로드를 허용하는지 확인합니다.
5. [직접 실행하려면?](05-development/onboarding.md) — 도구를 준비하고 로컬 환경을 시작합니다.

## 목적에 맞는 글 찾기

오른쪽 카테고리를 누르면 글 목록이 펼쳐집니다. 글 제목을 누르면 중간 목차를 거치지 않고 해당 글로 이동합니다. 용어가 낯설면 [용어집](05-development/glossary.md)을 함께 보세요.

| 읽고 싶은 내용 | 시작할 글 |
|---|---|
| 제품 목표와 개발 순서 | [제품 범위](01-product/scope-and-reference.md), [단계별 계획](02-delivery/roadmap.md) |
| 영상 입력·편집·다운로드 | [로컬 파일 업로드](05-development/local-video-upload.md), [전체 사용자 흐름](05-development/complete-flow.md) |
| 음성 인식·자막·추천 | [전사·추천 설정](05-development/groq-free-ai.md), [표시 자막](05-development/subtitle-segmentation.md), [품질 평가](05-development/transcript-quality-evaluation.md) |
| 시스템과 기술 선택 | [실행 흐름](03-architecture/runtime-flows.md), [API](03-architecture/api-contract.md), [설계 결정](04-decisions/README.md) |
| AI와 개발·검증하기 | [하네스 시작](05-development/harness/README.md), [검사 방법](05-development/harness/verification.md), [실패 경로](05-development/failure-path-testing.md) |
| 실패·개선의 실제 근거 | [문제 해결 기록](05-development/harness/changes/README.md), [프롬프트와 작업 결과](05-development/harness/records/README.md) |
| 운영 준비와 장애 대응 | [점검 절차](06-operations/runbook.md), [배포·비용](06-operations/deployment-and-cost.md) |
| 현재 상태와 남은 결정 | [최신 현황](07-governance/status.md), [미결정 사항](07-governance/open-decisions.md) |

## 실제 영상 한 편에서 확인한 것

링크나 로컬 파일을 넣으면 제작실에서 전사와 추천 후보를 열 수 있습니다. 실제 검증에서는 사용자가 한 후보의 자막 34개를 원음과 대조했습니다. 원본 화면의 자막과 겹치는 두 구간에서만 편집 자막을 숨겨 다시 출력하자 MP4에서는 해당 구간의 표시가 사라졌고, 내려받은 SRT에는 34개 자막의 문구와 시간이 유지됐습니다. [편집본과 최종 파일 대조 기록](05-development/harness/records/2026-11-18-final-output-e2e.md)

같은 출력 파일을 비공개로 게시해 YouTube Studio의 Shorts 목록에서 확인했습니다. 게시 제목은 사전 승인안과 달랐고, 같은 원본으로 추천을 다시 실행했을 때 후보는 한 개였습니다. 다음 검증에서는 게시 직전 제목을 대조하고, 모델이 제안한 후보 수와 서버가 제외한 수를 따로 기록해야 합니다. [게시 검증 기록](05-development/harness/records/2026-11-18-sns-final-output-validation.md) · [다음 검증의 우선순위](07-governance/status.md)

일반 CI는 합성 영상과 외부 제공자를 대신하는 테스트 코드로 전체 흐름을 검사합니다. 실제 인식·추천 품질과 최대 업로드 부하는 추가 검증 대상이며 운영 배포는 후속 단계입니다. Google 로그인과 계정별 자료 보호는 선택 기능입니다. 추천 AI와 SNS 업로드는 기본 비활성화이며 실제 호출·전송에는 설정과 해당 자료에 대한 승인이 필요합니다.

[저장소 README](../README.md) · [문서 작성 규칙](07-governance/document-guide.md) · [작업 규칙](../AGENTS.md)

## 새로 연결된 검증 기록

[실제 영상 흐름 검증](05-development/harness/records/2026-11-18-real-video-flow.md) · [실행 환경 반영](05-development/harness/records/2026-11-18-runtime-release.md) · [이전 검사 이력](07-governance/verification-history.md)
