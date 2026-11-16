# VIDEO-005 — 무료 제공자 전환과 검증 환경 개선

> 상태: 로컬 구현·자동 검사 완료 / 실제 모델 미검증 · 기준일: 2026-11-15

[위키 홈](../../../README.md) · [하네스 개선 기록](README.md)

## 목적과 완료 기준

예산 0원·로컬 LLM 미사용 요청에 따라 Groq Free 전사·추천 경로를 연결한다. 무료 모드에서 유료 제공자로 넘어가지 않고, 제공자 변경으로 전사 캐시나 대기 작업이 혼용되지 않아야 한다. 실제 호출·품질 평가는 키와 샘플 설정 이후다. 작업 브랜치는 `feat/video-005-quality-baseline`, 이번 변경 커밋은 아직 없다.

## 제품 변경과 검사

제품은 `app/adapters/groq.py`의 고정 endpoint·모델·시간 제한, `ai.py`의 모드 선택, 분석 서비스의 MP3 전처리·캐시 버전 분리다. 하네스는 `tests/unit/test_groq_provider.py`와 분석 파이프라인 검사, 실제 FFprobe를 이용하는 통합 대역, 무료 설정 안내와 preflight다. 전사·추천 프롬프트는 기존 `recommendations-v1`을 유지한다. 비용을 API가 제공하지 않으면 null로 기록한다.

## 발견한 실패와 수정

- 통합 runner의 pytest 수집 단계에서 `test_quality_evaluation.py`가 `scripts`를 import하지 못했다. 기존 테스트 이미지는 tests만 복사하고 평가 스크립트를 포함하지 않았다. Dockerfile의 integration 단계에 scripts를 포함했다. 테스트 제외나 assertion 완화 없이 전체 통합 검사를 다시 실행했다.
- 설정 확인 명령을 파일 경로로 실행하면 app import가 실패했다. 프로젝트 안내는 `uv run python -m scripts.evaluate_recommendations preflight`로 고정하고 실제 실행했다.
- malformed 추천의 message가 null인 경우 일반 예외로 빠질 수 있어 객체 형식을 검사하고 `MODEL_RESPONSE_INVALID` 회귀 검사를 추가했다.

## 관측 결과

- `uv run python scripts/verify.py`: Ruff·서식·기본 테스트 150개·Alembic 오프라인 SQL 통과. integration 31개는 기본 명령에서 제외.
- 격리 Compose runner: 통합 31개 통과. 실제 DB·Redis·워커·MP3(16kHz/mono)·추출·브라우저를 검사하고 외부 AI는 대역만 사용했다. 이후 malformed message 보강은 기본 검사에서 추가 검증했다.
- preflight: 무료/유료 모드 false, Groq 키 없음, 인증 미검증. 키 값이나 원문 응답을 출력하지 않았다.
- 격리 프로젝트 컨테이너·테스트 볼륨 정리 완료. 개발 데이터는 정리 대상이 아니다.
- 기존 FastAPI/Starlette의 httpx 사용 중단 예정 경고 1개는 남아 있으며 테스트 실패는 아니다.

계정의 실제 무료 상태·모델 가용성·한국어 품질은 미검증이다. 무료 확인 플래그는 제공자 과금 정책을 강제하지 않으며 실제 사용 전 사람이 계정 상태를 확인한다. 공개 서비스용 사용자 인증·사용자별 할당량·영구 무료 운영은 이번 완료 기준에 포함하지 않는다. 원격 CI·PR·Wiki 게시도 이번 로컬 검사 결과와 구분한다.

## 후속: 전사와 추천 분리

음성 인식부터 확인하자는 요청에 따라 `TRANSCRIPTION_PROVIDER=groq`, `RECOMMENDATION_PROVIDER=none`을 기본 제공자 설정으로 정했다. 웹의 전사 전용 요청은 mode를 저장하고 LLM 단계 전에 종료한다. 성공한 전사를 읽는 GET은 캐시 선점 메서드를 사용하지 않으며 동일 자산·버전을 이후 추천에서 재사용한다. 실제 외부 호출 스위치는 여전히 기본 false다.

기본 검사 157개가 통과했다. 최초 통합 검사에서는 32개 통과, 기존 추천 브라우저 검사 1개 실패를 발견했다. 입력 카드와 결과 카드가 공통 `.card`의 동일 grid 행을 차지해 추가된 입력 필드가 추출 버튼을 덮었다. `#analysis-panel`을 별도 행으로 배치해 수정했다. 강제 클릭이나 테스트 타임아웃 연장으로 우회하지 않는다.

수정 후 격리 통합 검사 33개 모두 통과했다. 전사 전용→읽기 전용 조회→동일 전사 재사용 추천, 새로고침 후 재접수 없음, 기존 추천·추출·다운로드를 검증했다. 실제 Groq 인증·음성 인식 품질은 키 미설정으로 미검증이다. preflight에서 전사 groq·추천 none·호출 스위치 false를 확인했으며 키 값은 출력하지 않았다.
