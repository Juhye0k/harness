# 개발과 하네스 문서 찾기

**처음 실행한다면 시작 안내를, 기능을 수정한다면 해당 기능 계약과 검증 절차를 읽는다.** 아래 문서는 작업 목적별로 묶었다. 모든 문서를 순서대로 읽을 필요는 없다.

[위키 홈](../README.md)

## 처음 합류했을 때

1. [신입 개발자 시작 안내](onboarding.md)에서 환경을 실행한다.
2. [입력부터 자막 편집·출력까지](complete-flow.md)에서 사용자 흐름을 따라간다.
3. [개발 하네스](harness/README.md)에서 작업 규칙과 검사 위치를 익힌다.

## 입력·영상 처리·출력

| 하고 싶은 작업 | 문서 |
|---|---|
| 링크의 10초 구간 추출 | [영상 추출 CLI](video-extraction.md) |
| 로컬 영상 파일 입력 | [파일 업로드](local-video-upload.md) |
| 비동기 작업·중단 처리 이해 | [비동기 작업](async-video-jobs.md) |
| 추출 웹의 상태·오류 처리 | [웹 영상 추출](web-video-extraction.md) |
| 후보 선택·자막 수정·최종 영상 생성 | [전체 사용자 흐름](complete-flow.md) |
| 외부 호출 없이 한글 출력 확인 | [세로 출력 샘플 CLI](portrait-subtitle-sample.md) |

## 전사·추천·자막 품질

| 하고 싶은 작업 | 문서 |
|---|---|
| 추천 방식·선택 추출 이해 | [하이라이트 추천](highlight-recommendations.md) |
| 무료 제공자 설정 | [Groq 설정](groq-free-ai.md) |
| 자막 분할·SRT 확인 | [표시 자막](subtitle-segmentation.md)·[빠른 숏츠 정책](shorts-display-policy.md) |
| 단어 시각이 부족한 구간 다루기 | [단어 정렬 복구](word-alignment-recovery.md) |
| 의심 전사와 원음 확인 | [전사 검수](transcript-review.md) |
| 정답 전사로 인식 정확도 측정 | [전사 품질 평가](transcript-quality-evaluation.md) |
| 추천 후보의 사용 가능성 평가 | [기준선 측정](recommendation-quality-baseline.md)·[피드백과 반복 개선](recommendation-improvement-loop.md) |

## 계정·자료·게시

- [Google 로그인·내 자료·7일 관리](user-auth-data.md)
- [YouTube 연결·최종 확인·업로드](youtube-upload.md)

## AI와 개발하고 검증하기

- 작업 시작: [AI 협업 절차](harness/workflow.md)
- 구현 결과 확인: [검증 순서](harness/verification.md)·[실패 경로 E2E](failure-path-testing.md)
- 리뷰와 완료 판단: [코드 리뷰](harness/review.md)
- 요구사항의 검사 위치: [전체 연결표](harness/requirements-map.md)·[비동기 작업 연결표](harness/video-002-requirements.md)
- 무엇을 요청하고 얻었는지 기록: [프롬프트·결과 기록](harness/records/README.md)
- 반복 실패의 원인 찾기: [하네스 개선 이력](harness/changes/README.md)
- 낯선 용어 확인: [용어집](glossary.md)
