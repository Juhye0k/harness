# 과거 구현·검증 이력

> 최신 상태 화면에서 분리한 과거 검사·게시 이력을 보존합니다. 당시의 통과·실패를 확인하는 기록이며 현재 기능의 품질 판정으로 읽지 않습니다.

이 문서는 이전 현황 페이지를 보존한 **작업 당시의 기록**이다. 현재 가능한 기능과 다음 작업은 [현재 현황](status.md)을 먼저 읽는다. 아래의 ‘미구현’, ‘미게시’, 검사 개수는 해당 시점의 상태이며 최신 상태를 뜻하지 않는다.

> 문서 분리일: 2026-11-18 · 용도: 과거 실패·검사·게시 근거 보존

[위키 홈](../README.md) · [관리 목차](README.md)

당시 Wiki는 코드 `9f2762e` 기준으로 게시됐고, [CI 실행](https://github.com/Juhye0k/short-form/actions/runs/44105330718)의 checks·integration이 통과했다. 이 원격 게시 정보를 확인한 뒤 본문을 분리했다.

## 이전 현황 페이지 원문

### 당시 문서: 구현 현황과 검증 기록



[위키 홈](../README.md) · [카테고리 목차](README.md)

## 현재 상태

main 통합 검증(2026-11-17): 인증·전사 검증 커밋과 미커밋 편집·최종 출력·로컬 업로드·추천 평가·실패 경로 작업을 고정 사본에서 검증한다. 기본 375개·Ruff·서식·migration 0008 오프라인 SQL, 일반/통합 이미지 빌드는 통과했다. 전체 통합과 원격 반영 결과는 [INTEGRATE-001](../05-development/harness/records/2026-11-17-main-integration.md)에 기록한다. 아래 수치는 각 작업 시점의 이력이며 통합 검증을 대체하지 않는다.

RECO-EVAL-001 120B 동작 검증: 키·모델을 유지한 채 `groq-records-low-2048-v1` 프로필로 승인된 전체 전사의 실제 후보 생성·채점에 성공했고 최종 후보 2개를 로컬 수작업 평가 페이지에 연결했다. 관련 회귀 70개·합성 Chrome 웹 평가 1개 통과. 사람 판정은 아직 없으며 전체 verify는 별도 인증·업로드 작업의 정적 오류로 중단됐다. 동일 조건 A/B에서 기존 JSON 입력도 성공했으므로 JSON 형식을 403의 단독 원인으로 단정하지 않는다. 413/429 한도 오류와 별개로 403의 정확한 제공자 내부 규칙은 미확정이다. [실험·검증·남은 제한](../05-development/harness/records/2026-11-17-recommendation-manual-review.md).

FLOW-001 로컬 구현(2026-11-17): 링크 입력 → 다중 추천 → 후보 선택 → 자막 편집·확인·불변 저장 → 비동기 720×1280 출력 → MP4/클립 SRT 다운로드 → 기존 YouTube 확인·업로드를 연결했다. 기본 **365개**, 같은 앱 스냅샷의 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **84개**와 출력 접수 중 편집 잠금의 추가 브라우저 **1개**가 통과했다. 모델·다운로드·YouTube만 합성 대역으로 사용했으며 실제 인식·추천 품질이나 편집 결과의 실계정 게시를 완료한 것은 아니다. 기존 8000 개발 DB는 전환하지 않고 8001의 분리된 리허설을 제공한다. [흐름·계약](../05-development/complete-flow.md), [작업·실패 근거](../05-development/harness/records/2026-11-17-complete-flow.md). 이번 작업의 커밋·푸시·Wiki 게시는 수행하지 않았다.

2026-11-17 게시 준비: 승인된 전사 복구·숏츠 표시/검증 화면·추천 평가·Google 인증·7일 자료 관리·하네스 기록을 통합했다. 아래의 로컬 미게시 문구와 검사 수치는 각 작업 당시 이력이며 현재 게시 검증 결과는 별도 기록한다.

자막 포함 세로 출력 1단계: [고정 합성 샘플 CLI](../05-development/portrait-subtitle-sample.md)를 추가했다. 한국어 자막을 입힌 10초·720×1280 MP4·클립 기준 SRT·미리보기를 생성한다. 최신 main에서 이번 작업만 분리한 브랜치의 기본 **281개**·Linux 출력 **28개**·실제 인프라 통합 **58개**가 통과했다. 편집 UI·비동기 최종 출력·실제 발화 정렬은 후속이다. 기존 혼합 작업 폴더의 검증 이력은 [작업 기록](../05-development/harness/records/2026-11-17-subtitle-render-spike.md)에서 구분한다. GitHub Wiki 게시 전이다.
AUTH-DATA-001 로컬 구현·실계정 로그인 확인: Google 로그인·테스트 계정 승인·서버 세션, 업무 API·파일·SNS 소유권 검사, 새 자료 7일 만료·삭제·탈퇴를 추가했다. 커밋 `94f2474`의 인증 코드와 분리된 8002 API·DB에서 실제 테스트 계정 1개의 Google 인증·pending 등록·승인 후 내 자료 접근·새로고침 시 세션 유지·로그아웃 후 세션 제거와 접근 차단을 확인했다. 기존 자료는 보존하고 자동 귀속하지 않으며 기존 8000 DB 전환·운영 배포·실제 자료 삭제는 미실행이다. [설정·정리·제한](../05-development/user-auth-data.md)과 [작업 기록](../05-development/harness/records/2026-11-17-auth-data-plan.md)을 따른다.

자막 편집·최종 출력의 첫 기술 확인(2026-11-17): [합성 샘플 CLI](../05-development/portrait-subtitle-sample.md)를 추가했다. Windows·Linux production 이미지에서 한글 1~2줄을 입힌 10.0초·720×1280 MP4와 클립 기준 SRT·미리보기·검사 보고서를 생성했다. 기본 **334개**, Linux 출력 회귀 **28개**, 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **64개**와 검증 중 갱신된 브라우저 검사 **1개**가 통과했다. 한글 모양·줄바꿈은 PNG로 별도 확인했다. 입력은 고정 합성 영상과 시험음이며 실제 발화 정렬·가독성 평가는 아니다. 편집 저장·UI·비동기 최종 출력·SNS 연결은 후속이다. [작업 기록과 소스 범위](../05-development/harness/records/2026-11-17-subtitle-render-spike.md). 커밋·푸시·Wiki 게시 전이다.

SHORTS-001: 빠른 자막 정책 `shorts-display-v1`과 기존 웹앱의 `/verification`을 추가했다. 1~3어절·1줄 중심·최대 2줄·0.45~1.8초·15자/초 기준이며, 미확정 구간이 있는 새 정책의 완성본 SRT는 서버에서 409로 차단한다. 실제 샘플은 정상 원 구간 19개·자막 60개(모두 1줄, 최장 1.68초), 검수 필요 102개로 전체 품질은 미달이다. 동시 작업에 의한 소스 변경을 감지해 별도 실행 스냅샷을 고정했고 기본 **303개**·실제 인프라 통합 **63개**를 통과했다. 배포한 로컬 API의 앱 해시가 검사 기록과 일치하며, 이후 작업 폴더 변경의 통과를 뜻하지 않는다. 원음 동기 자막·모바일 폭·새로고침 무변경·다운로드 차단을 실제 웹에서도 확인했다. [실행 기준과 제한](../05-development/shorts-display-policy.md). 커밋·푸시·Wiki 게시 전이다.

RECO-EVAL-001 로컬 구현: 추천 평가 CLI에 원본·전사 입력 고정, 선택과 사용 가능 판정 분리, 구간 수정 이유, 회차 비교를 추가했다. 별도 반복 실행기는 등록된 주요 문제·사람 확인과 같은 코드의 연속 2회 전체 검사 통과로 종료한다. 고정 수정 횟수는 없고 실행 시간 한도를 적용한다. 기본 331개·실제 인프라/브라우저 통합 64개 통과. 실제 사람 평가 1~3회와 AI 코딩 작업자 연결은 아직 수행하지 않았다. [사용법과 제한](../05-development/recommendation-improvement-loop.md), [검증·개선 기록](../05-development/harness/changes/recommendation-improvement-loop.md).

SNS-006 실제 계정 검증 완료: OAuth 채널 연결 후 승인된 720×1280·음성 포함 10초 합성 출력을 비공개로 업로드했다. YouTube API의 채널·제목·비공개·아동용 여부·처리 완료와 Studio Shorts 탭의 실제 분류를 확인했다. SNS 분리 워크트리의 기본 151개·통합 54개가 통과했다. OAuth 실패 코드 비노출과 오류 안내 유지 회귀 검사를 반영하며, 통합 브랜치의 기존 로그 보호·초안 재작성·상태 조회 경쟁 수정은 보존한다. [상세 기록](../05-development/harness/changes/sns-006-upload.md). 자동 세로 변환·운영 배포·원격 게시를 완료한 것으로 설명하지 않는다.

TR-EVAL-002 / SUB-ALIGN-003 통합: 두 워크트리의 평가 도구·정답 입력 화면·구간별 단어 복구·검사를 현재 로컬 브랜치 `feat/integrate-transcript-quality`에 통합했다. 기본 **282개**, 합친 코드의 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **61개** 통과. 개발 API·워커에도 반영하고 보존 응답으로 새 검토 결과를 별도로 만들었다. 승인된 실제 샘플은 원 전사 121개·단어 복구 22개·표시 자막 125개다. 원문·시각 순서·영상 범위는 통과했으나 표시 제약 위반 23개·최장 21.483초·최대 9줄로 가독성 초안은 미달이다. 확인된 정답 전사가 없어 CER·탐지 품질은 평가 불가다. [평가 근거와 후속 과제](../05-development/harness/changes/transcript-quality-integration.md). 커밋·푸시·Wiki 게시 전이다.

TR-001 후속 수정: 실제 전사 응답의 보조 단어 정보 불일치가 전사 전체를 실패시키는 문제를 수정했다. 원문·구간 시간·신뢰도를 보존하고 단어 정렬 제한을 명시한다. 승인된 샘플은 보존 응답을 오프라인으로 복구했으며 실패 이력은 유지했다. 기본 **256개**, 격리 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **59개** 통과. 실제 전사 화면의 121개 구간·검수 필터·음성 재생·새로고침 무변경도 확인했다. 통합 검사에서 발견한 SNS 상태 조회 선점 경쟁을 함께 수정했다. 이 변경은 로컬 상태이며 커밋·푸시·Wiki 게시 전이다. [상세 근거와 제한](../05-development/harness/changes/transcription-response-recovery.md)을 따른다.

전사 자동 검수 로컬 구현: 규칙·선택 신뢰도 기반 의심 구간, 음성 Range 재생, 버전별 사람 판정과 revision 충돌 검사, 보고서·비표시 구간 표본을 추가했다. 기본 검사 **251개**, 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **57개** 통과. [전사 검수 안내](../05-development/transcript-review.md). 기존 전사를 자동 재호출하지 않으며 새 Groq 분석은 quality-v3 캐시를 사용한다. 실제 탐지 품질·검수 시간 절감은 아직 평가하지 않았다.

2026-11-16 통합 검증: 자막 분할·SRT와 SNS-006 변경을 Groq 전사 기반 위에 통합했다. Docker 엔진 복구 후 기본 **235개**, 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 **56개**를 통과했다. SNS 워커 로그 보호와 만료 초안 재작성 결함을 회귀 검사와 함께 수정했다. 커밋·푸시·GitHub CI·Wiki 게시·실계정 업로드는 아직 수행하지 않았다. [통합 근거와 남은 검사](../05-development/harness/changes/integration-subtitles-sns.md)를 따른다. 아래의 Docker 차단·개별 검사 수치는 통합 전 이력이다.

기존 한국어 샘플 한 건의 실제 Groq 전사 생성은 성공했지만 정답 전사 대비 정확도와 새 word/segment v2의 실제 음성 정렬 품질은 미평가다. 기존 기록의 키 미설정 상태는 당시 이력이며 현재 설정값·사용자 데이터는 공개 문서에 기록하지 않는다.

VIDEO-005-SUBTITLES 로컬 변경(2026-11-16): [표시 자막·SRT](../05-development/subtitle-segmentation.md)를 원본 전사와 분리했다. Groq word+segment v2 캐시·원문/단어 시각 검증·제품 초안·검토 필요 표시·웹 다운로드를 추가했다. 실제 AI·사용자 영상 전송·SNS·커밋·푸시·Wiki 게시는 수행하지 않았다. Windows Edge와 로컬 HTTP/저장소 대역으로 72개 자막·원본 36개·SRT·모바일 폭·새로고침·조회 오류·안전한 검토 문구 표시를 확인했다. 이는 실제 DB·Celery 통합 성공을 뜻하지 않는다. 첫 전용 통합 이미지 빌드는 성공했으나 최종 코드 재빌드는 Docker BuildKit I/O 오류와 호스트 공간 부족으로 실패해 실제 PostgreSQL·Redis·Celery·Linux Chromium 통합은 미실행이다. 이후 호스트 공간 회복 뒤에도 Docker가 제한 시간 내 응답하지 않았다. 최종 `uv run python scripts/verify.py`는 기본 201개 통과·통합 34개 제외, Ruff·서식·Alembic 오프라인 SQL 통과다. 상세 제한은 자막 계약과 하네스 개선 기록을 따른다.

VIDEO-005 후속 로컬 변경: 전사·추천 제공자 설정을 분리하고 웹 기본 작업을 전사 전용으로 변경했다. 성공한 전사의 시간별 조회와 이후 추천의 캐시 재사용을 제공한다. 기본 157개·통합 33개 통과. 입력/결과 카드 겹침으로 발견한 브라우저 실패를 수정했다. 실제 키 미설정으로 Groq 인증·음성 인식 품질은 미검증이며 원격 게시 전이다. 아래 150개·31개 기록은 분리 전 단계의 검증 이력이다.

VIDEO-005 로컬 작업: [Groq 무료 전사·추천](../05-development/groq-free-ai.md) 연동과 무료 모드 회귀 검사를 추가했다. 기본 검사 150개, 격리 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 검사 31개가 통과했다. 키 미설정으로 실제 Groq 인증·무료 잔량·한국어 품질은 미검증이며 AI는 비활성 상태다. 이번 변경은 아직 커밋·푸시·Wiki 게시 전이다. [하네스 개선 기록](../05-development/harness/changes/video-005-groq-free.md)을 참고한다.

SNS-006은 성공 출력에 대한 YouTube OAuth 연결·최종 확인·업로드·중복 차단·미확정 전송 조회를 추가한다. 기본 비활성화이며 실계정 OAuth·실제 게시·운영 배포는 수행하지 않았다. [설정과 제한](../05-development/youtube-upload.md), [검사·작업 기록](../05-development/harness/changes/sns-006-upload.md)을 따른다.

VIDEO-004는 한국어 전사 기반 추천·후보 선택 추출과 원본·전사 재사용을 추가한다. [실행 계약](../05-development/highlight-recommendations.md)을 따른다. 기본 설정은 AI 비활성화이며 실제 모델 품질·요금은 아직 평가하지 않았다.

VIDEO-003은 웹 입력·작업 상태·새로고침 복구·미리보기·다운로드를 연결한다. [웹 사용·검사 계약](../05-development/web-video-extraction.md)을 기준으로 한다. 아래 VIDEO-002 기록은 당시 API 구현의 근거이며 웹 기능은 별도 검증한다.

VIDEO-002의 CLI·비동기 API는 [PR #1](https://github.com/Juhye0k/short-form/pull/1)로 main에 병합됐다. VIDEO-003은 그 기반 위의 웹 사용자 흐름이다. 실제 AI 추천이나 공개 웹 서비스 운영 완료를 의미하지 않는다. 이전 커밋·게시 근거는 [VIDEO-002 작업 기록](video-002-work-log.md)에 남긴다.

| 항목 | 상태 | 근거 |
|---|---|---|
| FastAPI 생존·준비 점검 | 구현 | [main.py](../../app/main.py) |
| DB 연결·migration 환경 | 구현 | [db.py](../../app/db.py), [migrations](../../migrations) |
| Redis·Celery 진단 | 구현 | [worker.py](../../app/worker.py) |
| Compose·CI·검사 | 구현 | [compose.yaml](../../compose.yaml), [CI](../../.github/workflows/ci.yml) |
| 업무 테이블·API | 로컬 구현 | video_jobs, 접수·조회·다운로드 API |
| 링크 입력·10초 추출 CLI | 로컬 구현 | [실행·계약](../05-development/video-extraction.md), [서비스](../../app/services/video.py) |
| 링크 입력·업무 워커 연결 | 로컬 구현 | 기존 영상 서비스·업로드 검증을 Celery에 연결; 로컬 파일 입력 구현 |
| 전사 기반 AI 추천·선택 추출 | 구현·로컬 검증 완료 | VIDEO-004, 제공자 대역 통합 검사 / 실제 모델 품질 미평가 |
| 다운로드 API / 웹 화면 / 자막 편집 | 로컬 구현 | FLOW-001 편집본 고정·비동기 세로 출력·클립 SRT |
| YouTube 업로드 | 로컬 구현·실제 비공개 Shorts 분류 확인 | SNS-006, 브라우저 세션별 OAuth·최종 확인·제공자 대역 검사 |
| 일반 사용자 인증 | 선택 활성화 구현·실계정 로컬 검증 | Google 로그인·자료 소유권·7일 만료; 운영 HTTPS는 별도 |
| 운영 배포·자동 복구 | 미구현 | 현재 Compose는 로컬 개발용 |
| 카테고리형 프로젝트 위키 | 작성 | [위키 홈](../README.md) |

## 확인된 검증 증거

### SNS-006 — YouTube 업로드

- `feat/sns-upload`의 로컬 변경이다. 계정·출력 버전·제목·공개 범위·아동용 여부에 묶인 확인과 비공개 기본값, 중복 전송 차단, 미확정 세션 조회를 구현했다. 실계정 OAuth·실제 게시·커밋·푸시·Wiki 게시는 수행하지 않았다.
- 최종 기본 검사 149개·Ruff·서식·Alembic SQL 통과, SNS 기본 검사 31개 통과. 수정 전 인프라 전체 통합은 51개 통과·브라우저 1개 실패였으며, 브라우저 수정 후 같은 회귀 함수를 별도 로컬 Chrome/API 대역 환경에서 통과했다.
- Docker 재빌드 중 저장소 I/O 오류·호스트 디스크 공간 부족이 발생했다. 최종 인프라 통합 53개 재실행과 테스트 스택 정리는 미확인이다. 기존 개발 스택이나 Docker 엔진을 재시작하지 않았다. [상세 검증·차단 사항](../05-development/harness/changes/sns-006-upload.md)을 따른다.

### VIDEO-004 — 전사 기반 추천

- 원본 1회 준비, 한국어 전사 재사용, 최대 5개 후보 추천, 후보 선택 후 가변 길이 출력 흐름을 구현했다.
- 실제 Azure/OpenAI 어댑터는 구현했지만 유료 호출은 하지 않았다. 일반 CI는 합성 영상과 고정 제공자 대역을 사용한다.
- 기본 검사 118개, 실제 PostgreSQL·Redis·Celery·FFmpeg·Chromium 통합 검사 31개가 통과했다. Ruff·서식·Alembic SQL도 통과했다. 원격 CI 근거는 PR과 Wiki 게시 기록에서 확인한다.
- 첫 통합 실행에서 진단 테스트가 공유 Celery 결과 저장소 캐시 때문에 실패했다. 진단용 앱을 분리한 후 기존 27개와 새 통합 3개가 모두 통과했다. 전사 응답 형식·시간 역전과 추천 화면 조회 실패·안전한 텍스트 출력 회귀 검사를 추가한 최종 결과도 통과했다.
- 실제 한국어 인식률·상위 후보 품질·제공자 요금·부하·강제 종료 복구는 미검증이다. 자동 재시도·자동 복구는 제공하지 않는다.
- [실행·검증 계약](../05-development/highlight-recommendations.md), [기술 결정](../04-decisions/adr-004-transcript-recommendations.md).


### VIDEO-003 — 웹 추출 흐름

- 입력·접수·상태·새로고침 복구·미리보기·다운로드를 FastAPI 정적 화면으로 연결했다.
- 기본 검사 86개 통과. 실제 인프라 통합 27개 통과하며 그중 14개는 Chromium 브라우저 검사다.
- 데스크톱 결과 화면과 모바일 390px 입력 화면을 캡처해 확인했다. 일반 실행 이미지와 테스트 이미지의 브라우저 의존성을 분리한다.
- Safari·Firefox·실제 모바일 기기·부하 검사는 미실행이다. 상세 계약·발견 사항은 [웹 추출 기록](../05-development/web-video-extraction.md)을 따른다.

### VIDEO-002 — 비동기 영상 추출

- 시작 커밋 `000fee0`, 작업 브랜치 `feat/video-002-async-extraction`. 아래는 로컬 작업 트리 검사이며 원격 CI 결과가 아니다.
- 게시한 구현 커밋 [32e992c](https://github.com/Juhye0k/short-form/commit/32e992cdefccb9668bcbc2af38499486961da89c)의 [GitHub Actions 43694535440](https://github.com/Juhye0k/short-form/actions/runs/43694535440)에서 checks·integration 모두 성공했다. 아래 로컬 결과와 구분한다.
- `uv run python scripts/verify.py`: Ruff·서식·기본 검사 82개·Alembic 오프라인 SQL 통과, 통합 13개 제외.
- `docker compose -f compose.integration.yaml run --rm runner`: 실제 PostgreSQL·Redis·Celery·FFmpeg 통합 검사 13개 통과. 동시 선점·발행 경쟁·수동 실패/완료 경쟁·재전달·실패·HTTP 다운로드 포함.
- 일반 production 이미지 빌드와 마이그레이션·API·워커 실행 성공. 테스트 워커의 대역 없이 공개 MP4를 시작 5초부터 처리해 출력 10.0초·음성 유지·전체 디코딩·원본 보존을 확인하고 HTTP로 732,218바이트 다운로드했다.
- 샌드박스에서 별도 실행한 DB 검사 1개는 pytest 공용 임시 경로 권한으로 실행되지 못했다. 이후 격리 Linux 컨테이너에서 동일 검사를 포함한 13개 전체 통과를 확인했다. 초기 통합 빌드에서 `.dockerignore`의 tests 제외를 발견하고 테스트 단계에서만 복사하도록 수정했다.
- 기존 Starlette/httpx 경고와 로컬 pytest 캐시 권한 경고는 남아 있다. 실제 워커 강제 종료·hard timeout 실험, 자동 복구, 부하 검사는 수행하지 않았다. soft timeout 처리는 대역 예외로, 중단 후 상태 충돌은 실제 DB로 검사했다.
- [실행 안내](../05-development/async-video-jobs.md), [요구사항·회귀 검사](../05-development/harness/video-002-requirements.md), [기술 결정](../04-decisions/adr-003-redis-celery.md).

### VIDEO-001 — 링크 기반 추출

- 작업 시작 커밋: `b549c6b6088f087420fec225ed0bc6761082a2cc`. 아래는 로컬 커밋 직전 검증 근거이며 원격 CI·Wiki 게시는 별도다.
- `uv run python scripts/verify.py`: Ruff·서식·56개 검사·Alembic 오프라인 검사 통과, 인프라 검사 2개 제외. 기존 Starlette/httpx 사용 중단 예정 경고와 샌드박스의 pytest 캐시 쓰기 권한 경고는 남아 있으며 검사 실패는 아니다. 문서 상대 링크와 `git diff --check`도 확인했다.
- 공개 MP4 `https://media.w3.org/2010/05/sintel/trailer.mp4`: 5초부터 추출, 출력 10.0초, 음성 유지·전체 디코딩·원본 SHA-256 동일 확인.
- 공개 YouTube `aqz-KE-bpKQ`: 5초부터 추출, 출력 10.0초, 같은 검사 통과.
- 사용 도구: FFmpeg/FFprobe 9.0.2, Deno 2.9.8, yt-dlp 2026.10.26. 실제 버전·시간·검사 JSON은 Git 제외 `.artifacts/video-runs`에 보관한다.
- 실패 사례: 첫 MP4 샘플은 HTTP 403, 첫 YouTube 테스트 영상 `BaW_jenozKc`는 unavailable. 실패를 성공으로 처리하지 않고 `DOWNLOAD_FAILED`로 기록했다. 다른 공개 샘플로 성공 경로를 확인했다.
- Docker Desktop Linux 엔진이 실행되지 않아 로컬 PostgreSQL·Redis·Celery 통합 검사와 Docker 빌드는 수행하지 못했다. 기존 통합 CI는 유지한다.
- 하네스에서 발견한 결함과 해결 근거: [시간 초과 후 자식 프로세스가 남는 문제](../05-development/harness/changes/video-001-process-timeout.md). 상세 재현·수정·제한은 해당 기록에서 관리한다.
- 커밋 전 재검증: 기본 56개 검사 통과, 공개 MP4 실행 `49b9c201e66a4c87b2d97a3421a95374`와 YouTube 실행 `39debadee5374a56861c4a6e71b3a2b5` 모두 시작 5초·출력 10.0초·음성 유지·디코딩·원본 보존 검사 통과. 결과 JSON·영상은 로컬 산출물에만 보관한다. Docker 엔진은 계속 미실행 상태여서 실제 인프라 검사와 이미지 빌드는 미실행이다.

### 하네스 파일 구조 정리

제품 코드는 유지하고 검사를 unit·process·media·integration으로 분리했다. [하네스 시작 문서](../05-development/harness/README.md), 요구사항 연결표, 개선 기록 양식을 추가했다. 이전 문서 경로는 새 위치 안내로 유지하며 원격 Wiki에는 아직 게시하지 않았다.

- 이동 전후 수집 항목 58개와 테스트 함수·클래스의 구문 구조가 동일함을 확인했다. 제품 코드·의존성·검사 진입점·CI 설정의 파일 해시도 작업 시작 시점과 동일하다.
- `uv run python scripts/verify.py`: 기본 검사 56개 통과, 인프라 검사 2개 제외; Ruff·서식·Alembic 오프라인 검사 통과. 문서 링크·연결표의 테스트 이름·diff 공백 검사도 통과했다.
- 실제 인프라와 외부 링크 검사는 이번 문서·배치 변경에서 재실행하지 않았다. 원격 CI·Wiki 게시는 미실행이며 기존 Starlette/httpx 및 pytest 캐시 권한 경고는 남아 있다.

### 기존 개발 기반

- 기준 코드 커밋: [2989ee4](https://github.com/Juhye0k/short-form/commit/2989ee45f27b8c26804058b7ce17458cd0d42d48).
- [CI 실행 43672654952](https://github.com/Juhye0k/short-form/actions/runs/43672654952): checks와 integration 성공.
- 기본 검사 6개, 실제 인프라 통합 검사 2개, Alembic 설정·접속, Compose 설정, Docker 빌드 확인.
- 통합 실행은 GitHub Linux 환경의 결과다. 당시 로컬 Docker 엔진이 꺼져 있어 로컬 통합 성공 증거는 없다.

이는 해당 커밋의 증거이며 이후 커밋의 성공을 자동으로 보장하지 않는다. 최신 변경은 해당 커밋 CI를 별도로 확인한다.

## 하네스 개선 이력

첫 CI에서 `uv run pytest`가 app을 찾지 못했다. 기본 검사에서 쓰던 `python -m pytest`와 실행 경로가 달랐기 때문이다. pytest의 pythonpath를 명시해 두 진입점이 같은 루트를 사용하도록 수정했고 재실행으로 확인했다. 테스트를 제거하거나 실패를 무시하지 않았다.

CI 액션 런타임 경고를 정리하고 runner를 Ubuntu 24.04로 고정했다. 현재 잠금 파일은 패키지 버전을 기록하지만 Docker 기본 이미지 태그까지 불변 digest로 고정한 구성은 아니다.

## 다음 작업

승인된 한국어 샘플·제공자·예산으로 실제 전사 정확도와 상위 후보 유용성을 평가할 수 있다. SNS 실제 검증은 별도 계정·출력·제목·공개 범위를 승인한 뒤 진행한다. 자막 편집·다른 SNS·시각 신호·자동 복구는 별도 요구사항으로 정한다.

<details>
<summary>작성 시점과 상태 이력</summary>

> 게시 이력: 이전 원본 `0167efd`의 PR #5와 세로 출력 샘플 PR #6은 main에 병합됐다. 이번 통합 변경은 `feat/integrate-transcript-quality` 브랜치 게시 대상이며 운영 배포·실제 Google 로그인 검증과 구분한다.

> 상태: 2026-11-16 기준 스냅샷 · 기준일: 2026-11-16 · 유지관리: 프로젝트 개발자

</details>
