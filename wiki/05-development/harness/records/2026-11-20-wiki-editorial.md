# 공개 Wiki 전편의 편집 판정

> 2026년 11월 20일의 공개 Wiki를 기준으로 각 글을 누가 왜 읽는지 판단하고 공개할 글과 저장소에서 추적할 기록을 정한다.

작업 ID는 DOCS-WIKI-102다. 요청은 공개 본문 102편의 검토, 목적별 재작성, PR·필수 CI·별도 Wiki 게시다. 시작 코드는 `f8b5540`, 공개 Wiki는 `ab4cb2a`다. 기존 게시기로 만든 102편과 탐색 파일 2개를 공개본과 대조해 본문 차이가 없음을 확인했다. 원격에 별도로 있는 images 디렉터리는 보존한다.


첫 열은 보존한 원본이다. 삭제는 공개 판본에서의 삭제를 뜻한다. 마지막 열은 같은 질문을 다루는 공개 글 또는 통합 목적지다.

| 기존 원본 | 독자가 여는 이유 | 고유 내용·시점 판단 | 처리 | 관련 공개 글 |
|---|---|---|---|---|
| [README.md](../../../README.md) | 홈에서 첫 실행과 개발 근거를 찾는다 | 기존 9개 분류·이력 목록을 세 갈래 읽기 순서로 교체 | 재작성 | [README.md](../../../README.md) |
| [01-product/problem-definition.md](../../../01-product/problem-definition.md) | 제품이 줄이려는 편집 작업을 이해한다 | 채택률·수정 시간은 측정할 제품 지표로 제시 | 재작성 | [01-product/problem-definition.md](../../../01-product/problem-definition.md) |
| [01-product/README.md](../../../01-product/README.md) | 제품 범위 문서로 이동한다 | 문제 정의와 범위 링크의 중간 목차 | 삭제 | [01-product/problem-definition.md](../../../01-product/problem-definition.md) |
| [01-product/scope-and-reference.md](../../../01-product/scope-and-reference.md) | 어떤 장면을 자동화할지 정한다 | 시작 시각 지정과 후보 선택을 구분하고 제외 범위는 초기 기획으로 보존 | 통합 | [01-product/problem-definition.md](../../../01-product/problem-definition.md) |
| [02-delivery/phase-00-discovery.md](../../../02-delivery/phase-00-discovery.md) | 비교 실험을 준비한다 | 같은 영상·길이·수정 과정을 맞추는 초기 실험 설계 | 저장소 보관 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [02-delivery/phase-01-foundation.md](../../../02-delivery/phase-01-foundation.md) | 기반 구축 당시의 합격 근거를 찾는다 | 2989ee4의 기본 6개·통합 2개는 초기 측정 | 저장소 보관 | [05-development/onboarding.md](../../onboarding.md) |
| [02-delivery/phase-02-video-jobs.md](../../../02-delivery/phase-02-video-jobs.md) | 10초 추출 도입 순서를 확인한다 | 링크 입력으로 변경한 이력과 선점 계약 | 저장소 보관 | [05-development/video-extraction.md](../../video-extraction.md) |
| [02-delivery/phase-03-web-mvp.md](../../../02-delivery/phase-03-web-mvp.md) | 첫 브라우저 작업의 완료 기준을 본다 | 새로고침 및 연속 클릭 시 중복 방지 요구 | 저장소 보관 | [05-development/complete-flow.md](../../complete-flow.md) |
| [02-delivery/phase-04-ai-evaluation.md](../../../02-delivery/phase-04-ai-evaluation.md) | 모델 실험을 설계한다 | 고정 응답 검사와 장르별 실제 모델 비교의 조건 | 저장소 보관 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [02-delivery/phase-05-extension.md](../../../02-delivery/phase-05-extension.md) | 운영 공개 전 투자 조건을 검토한다 | 자원·비용·개선 우선순위는 계획 | 저장소 보관 | [07-governance/status.md](../../../07-governance/status.md) |
| [02-delivery/phase-06-sns-upload.md](../../../02-delivery/phase-06-sns-upload.md) | 외부 전송을 설계하던 조건을 확인한다 | 출력 버전과 확인을 묶고 미확정 결과는 조회 | 저장소 보관 | [05-development/youtube-upload.md](../../youtube-upload.md) |
| [02-delivery/README.md](../../../02-delivery/README.md) | 단계 번호로 문서를 찾는다 | 단계별 원본으로 가는 링크 목록 | 삭제 | [07-governance/status.md](../../../07-governance/status.md) |
| [02-delivery/roadmap.md](../../../02-delivery/roadmap.md) | 후속 검증 순서를 정한다 | 일정 대신 검증 증거로 우선순위를 정함 | 통합 | [07-governance/status.md](../../../07-governance/status.md) |
| [03-architecture/api-contract.md](../../../03-architecture/api-contract.md) | 클라이언트에서 접수·오류를 처리한다 | 202·409 예시와 선택 인증을 현재 API에 맞춤 | 재작성 | [03-architecture/api-contract.md](../../../03-architecture/api-contract.md) |
| [03-architecture/data-and-jobs.md](../../../03-architecture/data-and-jobs.md) | 작업과 파일의 성공 조건을 이해한다 | 파일 생성 뒤 DB 성공 기록이 누락되면 다운로드 차단 | 통합 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [03-architecture/README.md](../../../03-architecture/README.md) | 시스템 문서를 찾는다 | 구성·흐름 글로 가는 중간 목차 | 삭제 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [03-architecture/runtime-flows.md](../../../03-architecture/runtime-flows.md) | 한 요청의 처리 순서를 따라간다 | DB·Redis 준비와 워커 실행의 차이 | 통합 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) | 작업 번호에서 다운로드까지 따라간다 | 대기 상태 조건부 선점과 성공 상태 확인 | 재작성 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [03-architecture/user-auth-data-management.md](../../../03-architecture/user-auth-data-management.md) | 인증 설계의 출발점을 확인한다 | 서버 세션·소유권·삭제와 운영 공개 조건 | 저장소 보관 | [05-development/user-auth-data.md](../../user-auth-data.md) |
| [04-decisions/adr-001-python-runtime.md](../../../04-decisions/adr-001-python-runtime.md) | 런타임 선택을 재검토한다 | Java 경험과 별개로 미디어·AI 도구 연결 비용을 고려 | 저장소 보관 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [04-decisions/adr-002-postgresql-storage.md](../../../04-decisions/adr-002-postgresql-storage.md) | 상태와 바이트의 저장소를 결정한다 | 관계와 트랜잭션은 PostgreSQL, 영상은 파일 볼륨 | 저장소 보관 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [04-decisions/adr-003-redis-celery.md](../../../04-decisions/adr-003-redis-celery.md) | 중복 메시지에서 실행자를 결정한다 | Redis 전달과 DB 선점 경계, 조기 ACK 뒤의 중단 | 유지 | [04-decisions/adr-003-redis-celery.md](../../../04-decisions/adr-003-redis-celery.md) |
| [04-decisions/adr-004-transcript-recommendations.md](../../../04-decisions/adr-004-transcript-recommendations.md) | 전사를 추천의 첫 입력으로 선택한 이유를 본다 | 구간 ID 검증 후 별도 채점, 장면 신호 누락 | 통합 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [04-decisions/README.md](../../../04-decisions/README.md) | ADR을 찾아간다 | 결정문 링크 목록 | 삭제 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [05-development/async-video-jobs.md](../../async-video-jobs.md) | 오래된 작업을 수동 확인한다 | pending·running 중단 확인과 queued 재발행 위험 | 통합 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [05-development/complete-flow.md](../../complete-flow.md) | 후보를 실제 파일로 출력한다 | 원음 확인·편집 버전·다운로드가 이어지는 사용자 단계 | 재작성 | [05-development/complete-flow.md](../../complete-flow.md) |
| [05-development/failure-path-testing.md](../../failure-path-testing.md) | 실패를 재현할 검사 환경을 만든다 | 응답 유실과 프로세스 종료를 서로 다른 수준에서 검사 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/glossary.md](../../glossary.md) | 도구 용어의 정의를 찾는다 | API·워커·전사·회귀 검사 풀이 | 저장소 보관 | [03-architecture/system-overview.md](../../../03-architecture/system-overview.md) |
| [05-development/groq-free-ai.md](../../groq-free-ai.md) | 승인된 계정에서 전사만 실행한다 | 제공자별 스위치·저장 전사 재사용·403 원인 미확정 | 재작성 | [05-development/groq-free-ai.md](../../groq-free-ai.md) |
| [05-development/harness/changes/integration-subtitles-sns.md](../changes/integration-subtitles-sns.md) | 자막과 SNS를 합친 뒤 생긴 회귀를 추적한다 | 만료 초안을 바꾸면 새 요청 번호, 응답 유실은 기존 번호 사용 | 저장소 보관 | [05-development/youtube-upload.md](../../youtube-upload.md) |
| [05-development/harness/changes/README.md](../changes/README.md) | 개선 근거의 저장 방식을 찾는다 | 회귀 조건·결과를 남기는 저장소 운영 규칙 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/changes/recommendation-improvement-loop.md](../changes/recommendation-improvement-loop.md) | 추천 실험 반복을 종료한다 | 검사 실패 우선 처리와 연속 통과 종료 | 저장소 보관 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [05-development/harness/changes/sns-006-upload.md](../changes/sns-006-upload.md) | 중복 게시와 미확정 결과를 판정한다 | 잘못된 채널 안내와 브라우저 UUID 지원 문제를 재현 | 통합 | [05-development/youtube-upload.md](../../youtube-upload.md) |
| [05-development/harness/changes/template.md](../changes/template.md) | 회귀 사례를 기록한다 | 증상·재현·원인·관측값 양식 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/changes/transcript-quality-integration.md](../changes/transcript-quality-integration.md) | 전사 정확도와 가독성을 따로 평가한다 | 121구간 중 단어 사용 22개, 검수 대기 23개 | 저장소 보관 | [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) |
| [05-development/harness/changes/transcript-review-v1.md](../changes/transcript-review-v1.md) | 검수 메타데이터 손실을 추적한다 | 빈 quality를 추가하면 기존 정규화 계약이 깨짐 | 저장소 보관 | [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) |
| [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) | 부분 오류 뒤에 원문을 살린 경계를 이해한다 | 외부 호출 없이 보존 응답 재처리, SNS 선점 경쟁 재현 | 유지 | [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) |
| [05-development/harness/changes/video-001-process-timeout.md](../changes/video-001-process-timeout.md) | 시간 초과 뒤 자식 도구가 남는 원인을 본다 | Windows 부모 종료 대기만으로 자식 종료를 보장하지 못함 | 유지 | [05-development/harness/changes/video-001-process-timeout.md](../changes/video-001-process-timeout.md) |
| [05-development/harness/changes/video-005-groq-free.md](../changes/video-005-groq-free.md) | Groq 전환 때 발생한 환경 오류를 재현한다 | 겹친 입력 카드가 추출 버튼을 가려 그리드 행 분리 | 저장소 보관 | [05-development/groq-free-ai.md](../../groq-free-ai.md) |
| [05-development/harness/changes/video-005-subtitles.md](../changes/video-005-subtitles.md) | 긴 전사를 읽을 수 있게 나눈 이유를 본다 | 21초·173자 합성 재현, 검증한 단어 시각 사용 | 통합 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/README.md](../README.md) | 하네스 파일의 위치를 찾는다 | 개발 규칙과 제품 실행 코드의 책임 표 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/records/2026-11-17-auth-data-plan.md](2026-11-17-auth-data-plan.md) | Google 로그인 도입 당시 결정을 찾는다 | 테스트 계정 승인과 로그인·로그아웃 검증 | 저장소 보관 | [05-development/user-auth-data.md](../../user-auth-data.md) |
| [05-development/harness/records/2026-11-17-complete-flow.md](2026-11-17-complete-flow.md) | 편집과 출력 연결의 최초 검사를 본다 | 고정 버전·대역 브라우저 흐름 | 저장소 보관 | [05-development/complete-flow.md](../../complete-flow.md) |
| [05-development/harness/records/2026-11-17-failure-path-plan.md](2026-11-17-failure-path-plan.md) | 장애 주입 검사가 요구된 이유를 확인한다 | 응답 유실·워커 종료를 각각 재현한 근거 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/records/2026-11-17-local-video-upload.md](2026-11-17-local-video-upload.md) | 파일 전송 뒤 워커 검증을 붙인 과정을 본다 | 전송 완료·자산 준비를 분리한 인수 조건 | 저장소 보관 | [05-development/local-video-upload.md](../../local-video-upload.md) |
| [05-development/harness/records/2026-11-17-main-integration.md](2026-11-17-main-integration.md) | 여러 브랜치의 통합 경위를 추적한다 | 고정 사본 비교와 통합 당시 CI | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/records/2026-11-17-prompt-result-records.md](2026-11-17-prompt-result-records.md) | 프롬프트 기록 절차의 도입 근거를 본다 | 사람과 AI 기여 및 미제공 비용 표기 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [05-development/harness/records/2026-11-17-recommendation-manual-review.md](2026-11-17-recommendation-manual-review.md) | 모델 접근 거절 실험을 재현한다 | 동일 조건 JSON 성공으로 형식 단독 원인 가설 미확정 | 저장소 보관 | [05-development/groq-free-ai.md](../../groq-free-ai.md) |
| [05-development/harness/records/2026-11-17-subtitle-render-spike.md](2026-11-17-subtitle-render-spike.md) | 최초 세로 자막 렌더 실험을 본다 | 합성 샘플과 분리 PR의 출력 검사 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-17-verification-layout.md](2026-11-17-verification-layout.md) | 화면 겹침을 재현한다 | 모바일 폭만 검사해 놓친 데스크톱 카드 겹침과 전체화면 복귀 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/records/README.md](README.md) | 작업 기록을 작성한다 | 공개 가능한 요약·검사·기여를 남기는 규칙 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [05-development/harness/records/template.md](template.md) | 기록의 필드를 확인한다 | 작업별 프롬프트와 결과 양식 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [05-development/harness/requirements-map.md](../requirements-map.md) | 요구사항에서 테스트 함수를 찾는다 | 길이·트랙·원본 해시별 검사 대응표 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/review.md](../review.md) | 리뷰 가능한 근거를 작성한다 | 실패 조건·위치·검사와 완료 보고 기준 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/verification.md](../verification.md) | 변경 후 무엇을 실행할지 결정한다 | 기본 검사·실제 인프라 및 브라우저 검사의 경계 | 재작성 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/video-002-requirements.md](../video-002-requirements.md) | 작업 경쟁 조건을 재현한다 | 발행·선점 경쟁과 늦은 완료를 DB에서 판정 | 저장소 보관 | [04-decisions/adr-003-redis-celery.md](../../../04-decisions/adr-003-redis-celery.md) |
| [05-development/harness/workflow.md](../workflow.md) | AI 변경을 어떤 순서로 검사하는지 읽는다 | 지침·실제 강제 장치와 실패 수정 순서 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness-workflow.md](../../harness-workflow.md) | 이전 하네스 링크에서 이동한다 | 워크플로로 연결하는 호환 별칭 | 삭제 | [05-development/harness/verification.md](../verification.md) |
| [05-development/highlight-recommendations.md](../../highlight-recommendations.md) | 추천 한도보다 적은 후보가 나온 이유를 조사한다 | 147구간·후보 1개·52.5점과 선정 단계별 미관측값 | 재작성 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [05-development/local-video-upload.md](../../local-video-upload.md) | 로컬 원본을 다시 전송하지 않고 쓴다 | 500MiB·20분 및 ready 자산 재사용 | 유지 | [05-development/local-video-upload.md](../../local-video-upload.md) |
| [05-development/onboarding.md](../../onboarding.md) | 로컬 서버를 켜고 준비 상태를 확인한다 | 도구·Compose·종료 시 볼륨 보존 명령 | 유지 | [05-development/onboarding.md](../../onboarding.md) |
| [05-development/portrait-subtitle-sample.md](../../portrait-subtitle-sample.md) | 세로 출력 CLI만 재현한다 | 클립 기준 SRT 시각과 폰트 검증의 초기 실험 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/README.md](../../README.md) | 개발 문서로 이동한다 | 하위 실행 안내 링크 목록 | 삭제 | [05-development/onboarding.md](../../onboarding.md) |
| [05-development/recommendation-improvement-loop.md](../../recommendation-improvement-loop.md) | 추천 피드백 실험을 반복한다 | 수정 회수·종료 정책과 평가자 개입 조건 | 저장소 보관 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [05-development/recommendation-quality-baseline.md](../../recommendation-quality-baseline.md) | 추천 결과의 기준선을 만든다 | 3개 표본과 동일 해시·평가 기준 | 저장소 보관 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [05-development/review-and-done.md](../../review-and-done.md) | 이전 리뷰 링크에서 이동한다 | 현행 리뷰 절차로 가는 호환 별칭 | 삭제 | [05-development/harness/verification.md](../verification.md) |
| [05-development/shorts-display-policy.md](../../shorts-display-policy.md) | 표시 자막 품질 정책을 적용한다 | 불확실한 구간의 SRT 제한과 빠른 자막 규칙 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/subtitle-segmentation.md](../../subtitle-segmentation.md) | 전사에서 표시 자막을 계산한다 | 문자 보존과 단어 시각이 없을 때의 분할 보류 | 저장소 보관 | [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) |
| [05-development/transcript-quality-evaluation.md](../../transcript-quality-evaluation.md) | 사람 정답을 입력하고 CER를 계산한다 | 검수 JSON과 음성으로 정답 팩 구성 | 저장소 보관 | [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) |
| [05-development/transcript-review.md](../../transcript-review.md) | 의심 구간을 듣고 판정한다 | 원문을 보존하고 버전·revision 충돌을 검사 | 저장소 보관 | [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) |
| [05-development/user-auth-data.md](../../user-auth-data.md) | 사용자 자료 보호와 만료를 설정한다 | 인증 세션·7일 만료·사용 중 삭제 차단 | 유지 | [05-development/user-auth-data.md](../../user-auth-data.md) |
| [05-development/verification.md](../../verification.md) | 이전 검사 링크에서 이동한다 | 현행 검증 절차로 가는 호환 별칭 | 삭제 | [05-development/harness/verification.md](../verification.md) |
| [05-development/video-extraction.md](../../video-extraction.md) | DB 없이 영상 구간을 자른다 | 색상 전환 위치·원본 해시·트랙으로 10초 추출 확인 | 재작성 | [05-development/video-extraction.md](../../video-extraction.md) |
| [05-development/web-video-extraction.md](../../web-video-extraction.md) | 추출 화면의 새로고침을 이해한다 | 작업 번호로 복원하고 조회 실패 시 재접수 방지 | 통합 | [05-development/complete-flow.md](../../complete-flow.md) |
| [05-development/word-alignment-recovery.md](../../word-alignment-recovery.md) | 일부 구간의 잘못된 단어 시각을 복구한다 | 구간별 격리·반복 단어·시각 상한 검사 | 저장소 보관 | [05-development/harness/changes/transcription-response-recovery.md](../changes/transcription-response-recovery.md) |
| [05-development/youtube-upload.md](../../youtube-upload.md) | 확인한 파일을 한 번 게시한다 | 로컬 확인·원격 처리·Studio 분류와 제목 대조 | 재작성 | [05-development/youtube-upload.md](../../youtube-upload.md) |
| [06-operations/deployment-and-cost.md](../../../06-operations/deployment-and-cost.md) | 공개 배포 예산을 추정할 조건을 찾는다 | 저장량·연산량·백업·복구의 미확정 계획 | 저장소 보관 | [06-operations/runbook.md](../../../06-operations/runbook.md) |
| [06-operations/README.md](../../../06-operations/README.md) | 운영 안내로 이동한다 | 운영·비용 링크 목록 | 삭제 | [06-operations/runbook.md](../../../06-operations/runbook.md) |
| [06-operations/runbook.md](../../../06-operations/runbook.md) | 준비 API가 503일 때 조치한다 | 디스크 고갈 당시 live 200과 DB·Redis 준비 실패 | 재작성 | [06-operations/runbook.md](../../../06-operations/runbook.md) |
| [07-governance/document-guide.md](../../../07-governance/document-guide.md) | Wiki를 다시 게시한다 | 공개 목록·원격 직접 수정·삭제 대상의 확인 절차 | 재작성 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [07-governance/open-decisions.md](../../../07-governance/open-decisions.md) | 설계 당시 의사결정 대기 목록을 찾는다 | 점수·SNS 등 일부 항목은 후속 구현 전 질문 | 저장소 보관 | [07-governance/status.md](../../../07-governance/status.md) |
| [07-governance/README.md](../../../07-governance/README.md) | 현황 문서로 이동한다 | 상태·게시 기록 링크 목록 | 삭제 | [07-governance/status.md](../../../07-governance/status.md) |
| [07-governance/status.md](../../../07-governance/status.md) | 실제 사용 가능한 범위와 다음 검증을 본다 | 실제 입력 한 건에서의 추천·편집·비공개 게시 결과 | 재작성 | [07-governance/status.md](../../../07-governance/status.md) |
| [07-governance/video-002-work-log.md](../../../07-governance/video-002-work-log.md) | 최초 비동기 PR의 증거를 찾는다 | 발행 경쟁 수정과 해당 CI 실행 번호 | 저장소 보관 | [04-decisions/adr-003-redis-celery.md](../../../04-decisions/adr-003-redis-celery.md) |
| [05-development/harness/records/2026-11-18-wiki-navigation.md](2026-11-18-wiki-navigation.md) | 기존 탐색 주소의 충돌을 추적한다 | workflow 별칭의 legacy 주소 처리 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [07-governance/wiki-publication-history.md](../../../07-governance/wiki-publication-history.md) | 이전 공통 푸터를 복원한다 | 과거 공통 게시 문구의 사본 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [07-governance/verification-history.md](../../../07-governance/verification-history.md) | 과거 실패와 검사 수치를 추적한다 | pytest 진입점에 따른 app 경로 문제의 수정 | 저장소 보관 | [05-development/harness/verification.md](../verification.md) |
| [05-development/harness/records/2026-11-18-real-video-flow.md](2026-11-18-real-video-flow.md) | 오래된 전사 응답을 다시 쓰는 과정을 본다 | 기존 9개와 복구 17개로 만든 미확정 버전 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-18-release-integration.md](2026-11-18-release-integration.md) | 여러 기능의 배포 이력을 확인한다 | PR 병합과 해당 main CI를 분리 기록 | 저장소 보관 | [07-governance/status.md](../../../07-governance/status.md) |
| [05-development/harness/records/2026-11-18-runtime-release.md](2026-11-18-runtime-release.md) | 코드와 실행 환경의 버전을 대조한다 | 독립 개발 DB·워커의 런타임 점검과 자료 보존 | 저장소 보관 | [06-operations/runbook.md](../../../06-operations/runbook.md) |
| [05-development/harness/records/2026-11-18-wiki-readability.md](2026-11-18-wiki-readability.md) | 이전 Wiki 개편을 추적한다 | 동시 게시분을 보존한 당시 9개 분류 | 저장소 보관 | [07-governance/document-guide.md](../../../07-governance/document-guide.md) |
| [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) | 원본 화면 자막으로 새 초안을 평가한다 | 전체 문구와 구간별 차이를 각각 계산 | 재작성 | [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) |
| [05-development/harness/records/2026-11-18-source-caption-loop.md](2026-11-18-source-caption-loop.md) | 문구 점수만 개선된 초안을 판정한다 | 29개 초안의 전체 차이 감소와 구간별 차이 증가 | 통합 | [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) |
| [05-development/harness/records/2026-11-18-caption-alignment.md](2026-11-18-caption-alignment.md) | 화면 전환과 음성 단어 시작을 연결한다 | 18구간 기준선에서 전체·구간별 7/208 | 통합 | [05-development/source-caption-evaluation.md](../../source-caption-evaluation.md) |
| [05-development/harness/records/2026-11-18-flow-caption-web.md](2026-11-18-flow-caption-web.md) | 웹 초안이 원본과 맞는지 확인한다 | 관측 해시·단어 시각·미확정 새 버전 적용 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-18-flow-output-layout.md](2026-11-18-flow-output-layout.md) | 출력의 실제 자막 위치를 확인한다 | Linux에서 발견한 글자 픽셀 위치 실패 | 통합 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) | 렌더 완료 뒤 자막 겹침을 검사한다 | 두 구간의 969프레임과 검수 SRT 34개 대조 | 재작성 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-18-sns-final-output-validation.md](2026-11-18-sns-final-output-validation.md) | 게시한 영상이 승인 내용과 일치하는지 본다 | 해시·채널·Shorts 분류는 일치했으나 제목 미달 | 통합 | [05-development/youtube-upload.md](../../youtube-upload.md) |
| [05-development/harness/records/2026-11-18-flow-runtime.md](2026-11-18-flow-runtime.md) | 실행 환경을 복구할 조건을 확인한다 | 디스크 고갈·ready 503, 복원 후 기존 19개 테이블 대조 | 통합 | [06-operations/runbook.md](../../../06-operations/runbook.md) |
| [05-development/harness/records/2026-11-19-flow-resume.md](2026-11-19-flow-resume.md) | 중단 후 검수를 이어간 이력을 확인한다 | 원음 검수 전 차단과 검수 완료 후 다운로드 | 저장소 보관 | [05-development/harness/records/2026-11-18-final-output-e2e.md](2026-11-18-final-output-e2e.md) |
| [05-development/harness/records/2026-11-20-project-workspace.md](2026-11-20-project-workspace.md) | 후보가 적거나 채점이 거절된 실제 실행을 조사한다 | 제안·채점·서버 선정 기록의 구분과 실패 응답 보관 한계 | 통합 | [05-development/highlight-recommendations.md](../../highlight-recommendations.md) |
| [05-development/harness/records/2026-11-20-worktree-consolidation.md](2026-11-20-worktree-consolidation.md) | 작업 폴더 통합의 근거를 찾는다 | 이전 실험과 main의 비교·비공개 복구본 기록 | 저장소 보관 | [07-governance/status.md](../../../07-governance/status.md) |

사이드바는 세 그룹으로 재작성하고, 같은 링크가 반복되던 공통 푸터는 삭제한다.


## 결과와 검증

공개 본문은 102편에서 21편으로 줄었다. 유지 6편, 재작성 15편, 통합 15편, 저장소 보관 56편, 공개 목록 삭제 10편이다. 참가자는 제품 사용, 요청 한 건의 처리, 실제 실패 사례 순으로 읽을 수 있다. 세 그룹의 사이드바를 생성하며 공통 푸터는 생성하지 않는다. 이 기록도 저장소 전용이다.

기존 원격 문서 전체를 대조한 뒤 접수 오류는 `app/api/jobs.py`와 `app/main.py`, 후보 하한·겹침은 `app/domain/recommendations.py`, 화면의 작업 선택은 `app/static/recommendations.html`에서 확인했다. 자막·게시 수치는 해당 실행 기록에서 확인했다. 단일 실행에서 후보가 줄어든 정확한 단계와 제목 불일치가 발생한 제출 순간은 미확정이다.

로컬에서 Ruff·서식, 기본 검사 425개와 Alembic 오프라인 SQL 생성을 통과했다. 통합 115개는 이 명령의 대상 밖이다. 사용자 승인은 전체 Wiki 개편과 PR·CI·별도 게시이며, 개별 글의 판정과 공개 글 수는 편집 과정에서 결정했다. 유료 모델·영상 처리·SNS 실게시를 다시 실행하지 않았다. 편집 도구의 사용량·비용은 미제공이다.
