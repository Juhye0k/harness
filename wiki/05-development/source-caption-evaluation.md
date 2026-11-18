# 원본 자막을 이용한 자동 비교 루프

> 원본 화면에 자막이 있는 영상은 문구와 표시 시각을 자동 비교할 수 있다. 이 루프는 원본·편집본을 고정하고 OCR 또는 기존 자막 파일로 초안을 만든 뒤, 같은 화면 자막 기준선과 표시 규칙으로 비교한다. 더 나쁜 초안은 채택하지 않으며 사람의 원음 확인 상태를 대신 변경하지 않는다.

[위키 홈](../README.md) · [개발 목차](README.md)

## 해결하는 문제

기존에는 사용자가 빠진 문구마다 시작·종료 시각을 입력해야 했다. 원본 영상에 이미 자막이 있어도 음성 인식 결과만 사용하면 원본과 다른 단어를 놓치기 쉽다. 원본의 표시 자막을 비교 자료로 이용하고, 단어 시각이 있는 자막 파일이 있으면 분할·표시 시간의 초안도 자동으로 만든다.

화면 자막은 발화를 생략하거나 다듬을 수 있고 OCR도 틀릴 수 있다. 따라서 이 평가의 문자 차이율은 **화면 자막과의 일치**이며, 원음 정답을 사람이 확인한 글자 오류율과 구분한다. 기준 자막이 없는 구간의 점수는 미평가로 남긴다.

## 어떤 순서로 실행하는가

1. 승인된 로컬 원본의 SHA-256과 후보·편집 버전을 고정한다. 원본 전사·이전 편집은 변경하지 않는다.
2. 먼저 제작자 자막 파일이 있는지 확인한다. YouTube 자동 자막은 다른 인식기의 결과이므로 별도 초안으로 취급한다.
3. 화면 자막은 FFmpeg로 하단 영역을 샘플링하고 OCR로 읽는다. 기사 본문이 섞이지 않도록 검은 자막 영역을 분리한다. Windows 한국어 OCR 또는 별도 일회성 Tesseract 도구를 사용하며 외부 모델에 프레임을 보내지 않는다.
4. 반복 관측·판독 불확실성을 확인한다. 화면에서 직접 읽어 보완한 기준선은 해당 프레임의 해시·시각과 묶고, AI 판독임을 기록한다. 이를 사람의 정답으로 바꾸지 않는다.
5. 같은 기준선으로 기존 편집본과 초안을 비교한다. 차이율이 줄어도 긴 자막·과도한 글자 수·겹침을 만들면 채택하지 않는다.
6. 통과한 결과는 새 미확정 편집본으로만 검토한다. 최종 출력·실제 게시 승인은 별도다.

## 파일별 역할

| 역할 | 파일 |
|---|---|
| 원본 보존·제한된 프레임 추출 | [extract_caption_frames.py](../../scripts/extract_caption_frames.py) |
| 한국어 OCR·자막 영역 전처리 | [ocr_windows.ps1](../../scripts/ocr_windows.ps1) |
| 격리된 OCR 도구 | [Dockerfile.ocr-evaluation](../../Dockerfile.ocr-evaluation), [ocr_tesseract.py](../../scripts/ocr_tesseract.py) |
| 기준선·평가·채택 판단 | [source_caption_evaluation.py](../../app/domain/source_caption_evaluation.py) |
| 자동 자막의 단어 시각·분할 제안 | [source_caption_proposal.py](../../app/domain/source_caption_proposal.py) |
| 실행·JSON/HTML 보고서 | [evaluate_source_captions.py](../../scripts/evaluate_source_captions.py) |
| 잘못된 기준선·누락·형식·자동 승인 방지 | [평가 회귀 검사](../../tests/unit/test_source_caption_evaluation.py), [제안 회귀 검사](../../tests/unit/test_source_caption_proposal.py) |

이 파일들은 개발·평가 도구다. 일반 분석 API가 원본 화면 자막을 자동 수집하도록 연결한 구현은 아니다. OCR 도구를 제품 API·워커 이미지에 추가하지 않았고 새 Python 의존성도 없다.

## 입력과 실행 계약

`--ocr`는 원본 해시·샘플 간격·각 프레임의 시각/해시/판독 문구를 가진 비공개 JSON이다. `--editor`는 후보·원본 구간·현재 편집본과 같은 영상의 `source_sha256`을 포함한 고정 스냅샷이다. `--reference`를 지정하면 모든 초안을 같은 프레임 판독 기준선에 비교한다. 프레임 해시가 맞지 않으면 거절한다.

```powershell
uv run python -m scripts.extract_caption_frames --source sample.mp4 --start 58.8 --end 92.2 --fps 10 --roi 0 580 1280 90 --output .artifacts/caption-eval/frames-run
powershell -NoProfile -File scripts/ocr_windows.ps1 -Manifest .artifacts/caption-eval/frames-run/manifest.json -Output .artifacts/caption-eval/ocr-native.json
uv run python -m scripts.evaluate_source_captions --ocr .artifacts/caption-eval/ocr-native.json --editor .artifacts/caption-eval/editor.json --reference .artifacts/caption-eval/reference.json --output .artifacts/caption-eval/report
```

영역 값은 이 샘플의 1280×720 화면에 맞춘 예시다. 다른 영상에서 그대로 사용하지 않는다. FFmpeg가 PATH에 없으면 `--ffmpeg`로 실행 파일을 지정한다. Windows OCR은 설치된 한국어 인식기를 사용하고 언어 모델을 자동 설치하지 않는다. 모든 결과 폴더·파일은 기존 실행과 다른 이름을 사용한다.

단어별 시각이 있는 YouTube JSON3 파일은 `--youtube-captions <파일> --duration-ms <원본길이>`로 추가한다. 표시 끝은 다음 단어 시작으로 계산한 **표시 구간**이며 실제 발화 종료를 알아낸 값은 아니다. 후보 경계를 가로지르는 단어는 잘라 넣지 않고 별도로 보고한다. 1\~3어절·최대 2줄·줄당 14자·0.45\~1.8초·15자/초 안에서 모든 선택 단어를 분할할 수 없으면 초안을 거절한다.

## 평가를 읽는 방법

| 값 | 의미와 제한 |
|---|---|
| 원본 기준 시간 비율 | 안정된 화면 자막이 있는 시간 / 후보 전체 시간. 자막 부재·판독 실패를 성공으로 세지 않음 |
| 화면 자막 대비 문자 차이율 | 한글 NFC·대소문자·공백/문장부호 정규화 후 편집 거리 / 기준 글자 수. 기준 구간에 중심 시각이 있는 출력 자막을 비교하므로 표시 단위와 경계 차이도 영향을 줌 |
| 프레임 교차 확인 | OCR 재구성에 사용하지 않은 홀수 프레임과 비교. 같은 개발 영상의 관측이며 독립 영상 평가가 아님 |
| 표시 규칙 | 길이·글자·어절·읽기 속도·겹침. 내용 정확도와 별도 검사 |
| 채택 판단 | 기준이 없거나 문자 차이율이 나빠지거나 표시 규칙을 어기면 기존본 유지. 개선돼도 미확정 초안만 허용 |

최초 실행의 데이터·수치·실패와 수정은 [원본 자막 기반 실험 기록](harness/records/2026-11-18-source-caption-loop.md)에 있다. 일반 CI는 합성 데이터로 판단 규칙만 검사하고 YouTube·OCR 모델을 호출하지 않는다.
