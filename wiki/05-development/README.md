# 개발과 하네스

> 개발과 하네스에 속한 문서를 찾는 목차입니다. 아래 글의 설명을 읽고 필요한 주제로 이동하세요.

[위키 홈](../README.md)


환경 실행, 검사, AI 협업과 리뷰 절차를 따른다.

- [신입 개발자 시작 안내](onboarding.md) — 처음 참여한 개발자가 코드를 실행하고 정상 상태를 확인하기 위한 안내입니다
- [개발 하네스 시작하기](harness/README.md) — 새 기록에 필요한 목적·원인·검사 항목을 확인합니다.
- [Google 로그인과 7일 자료 관리](user-auth-data.md) — Google 로그인으로 사용자를 식별하고 영상·출력을 계정별로 보호합니다
- [로컬 영상 파일 업로드](local-video-upload.md) — 로컬 영상은 전송이 끝나도 형식과 길이 검증을 통과해야 사용할 수 있습니다
- [AI와 함께 작업하는 절차](harness/workflow.md) — AI가 코드를 바꾸더라도 완료 여부는 실행 가능한 검사와 사람이 확인할 근거로 판단합니다
- [프롬프트·결과와 포트폴리오 근거 기록](harness/records/README.md) — 새 기록에 필요한 목적·원인·검사 항목을 확인합니다.
- [검증 계층과 실행 방법](harness/verification.md) — 검사 종류마다 확인할 수 있는 범위가 다릅니다
- [링크에서 10초 영상 추출](video-extraction.md) — 공개 링크에서 지정한 10초 구간을 원본을 보존하며 추출합니다
- [한국어 자막 포함 세로 영상 샘플 — 출력 1단계](portrait-subtitle-sample.md) — 편집 기능을 연결하기 전에 한국어 자막이 포함된 세로 영상을 작은 합성 샘플로 확인했습니다
- [입력부터 자막 편집·출력·YouTube까지 — FLOW-001](complete-flow.md) — 추천 후보를 고른 뒤 자막을 수정하고 확인한 버전으로 세로 영상을 출력할 수 있습니다
- [실패 경로 E2E 구현 계획 — FAIL-E2E-001](failure-path-testing.md) — 정상 시연만으로는 응답 유실과 워커 중단 때의 중복 실행을 확인할 수 없습니다
- [비동기 10초 추출과 중단 처리](async-video-jobs.md) — 영상 처리가 끝날 때까지 HTTP 요청을 열어 두지 않고 작업 번호로 결과를 조회합니다
- [웹 영상 추출과 브라우저 검증 — VIDEO-003](web-video-extraction.md) — 브라우저에서 영상 추출을 접수하고 상태·미리보기·다운로드를 확인합니다
- [하이라이트 추천과 선택 추출 — VIDEO-004](highlight-recommendations.md) — 한국어 전사에서 여러 후보를 추천하고 사용자가 선택한 구간만 추출합니다
- [Groq 무료 전사·추천 설정](groq-free-ai.md) — 음성 전사와 추천은 각각 켜고 끌 수 있으며, 저장된 전사를 추천에 재사용합니다
- [표시 자막 분할과 SRT](subtitle-segmentation.md) — 음성 인식 결과와 화면에 보여줄 자막은 서로 다른 데이터입니다
- [빠른 숏츠 자막과 웹 검증](shorts-display-policy.md) — 빠른 숏츠에서는 긴 문장을 한꺼번에 보여주기보다 짧게 읽을 수 있어야 합니다
- [구간별 단어 정렬 복구와 경계 실험](word-alignment-recovery.md) — 일부 구간의 단어 시간 오류 때문에 전체 응답의 정렬 정보를 버리지 않도록 바꿨습니다
- [전사 자동 검수와 사람 판정](transcript-review.md) — 음성 인식의 신뢰도 정보는 오인식을 확정하는 정답이 아닙니다
- [전사 품질 평가와 정답 입력](transcript-quality-evaluation.md) — 음성 인식 정확도는 확인한 정답 전사와 비교해야 측정할 수 있습니다
- [실제 추천 품질 기준선 측정 — VIDEO-005](recommendation-quality-baseline.md) — 추천 품질을 비교하려면 입력과 결과를 먼저 고정해야 합니다
- [추천 피드백과 반복 개선 — RECO-EVAL-001](recommendation-improvement-loop.md) — 사람의 후보 평가를 저장해 다음 추천 실험의 비교 근거로 사용합니다
- [YouTube 계정 연결과 확인 후 업로드 — SNS-006](youtube-upload.md) — 확인한 출력 영상을 연결한 YouTube 채널에 한 번 전송합니다
- [VIDEO-002 요구사항과 검증](harness/video-002-requirements.md) — 비동기 작업은 정상 완료뿐 아니라 발행 경쟁과 늦은 완료도 검사해야 합니다
- [코드 리뷰와 완료 기준](harness/review.md) — 코드가 실행되는 것 외에 실패·비용·권한 경계가 지켜지는지도 검토해야 합니다
- [요구사항과 검사 연결](harness/requirements-map.md) — 요구사항이 실제 검사와 연결돼 있는지 확인하는 문서입니다
- [하네스 개선 기록](harness/changes/README.md) — 새 기록에 필요한 목적·원인·검사 항목을 확인합니다.
- [프로젝트 용어집](glossary.md) — 문서에서 사용하는 도구와 작업 용어를 처음 접하는 독자를 위한 사전입니다
