# 3단계: 안드로이드 엣지 AI 환경 설정

목표: 스마트폰에서 LLM을 직접 구동하고, `school_law.db`를 로컬 검색에 사용합니다.

이 저장소에서는 두 경로를 지원합니다.

- 경로 A (권장): `llama.cpp for Android` + GGUF(Q4)
- 경로 B (대안): `MediaPipe LLM Inference API` + TFLite 모델

---

## 경로 A: llama.cpp for Android (권장)

이 저장소에는 이미 안드로이드 샘플 앱이 포함되어 있습니다.

- 앱 경로: `vendor/llama.cpp/examples/llama.android`
- 앱 모듈: `vendor/llama.cpp/examples/llama.android/app`

### 1) 모델 + DB 자산 배치

먼저 Q4 GGUF 모델과 SQLite DB를 앱 assets로 복사합니다.

```powershell
.\.venv\Scripts\python.exe scripts/stage_android_assets.py --model models/gguf/Qwen__Qwen2.5-3B-Instruct/model-q4_k_m.gguf
```

배치 결과:

- `vendor/llama.cpp/examples/llama.android/app/src/main/assets/models/school-q4.gguf`
- `vendor/llama.cpp/examples/llama.android/app/src/main/assets/db/school_law.db`
- `vendor/llama.cpp/examples/llama.android/app/src/main/assets/edge_assets_manifest.json`

### 2) Android Studio 실행

1. Android Studio에서 `vendor/llama.cpp/examples/llama.android`를 프로젝트로 엽니다.
2. Gradle sync 후 디바이스(최소 SDK 33)에 설치합니다.
3. 앱에서 모델 선택 UI가 나오면 assets에 복사된 GGUF를 선택합니다.

### 3) GPU/NPU 가속 역할

- llama.cpp Android는 기기별 네이티브 백엔드(주로 CPU + SIMD, 일부 구성은 GPU 경로)로 토큰 생성을 수행합니다.
- 실무에서는 모델 크기(Q4), 스레드 수, 생성 길이로 지연시간/발열/배터리를 튜닝합니다.

---

## 경로 B: MediaPipe LLM Inference API (대안)

MediaPipe 경로는 TFLite/LiteRT 모델 아티팩트 호환성이 핵심입니다.

### 1) Gradle 의존성(개념)

앱 모듈(`app/build.gradle.kts`)에 MediaPipe LLM inference 관련 의존성을 추가합니다.
(버전은 공식 문서 최신값으로 고정 권장)

```kotlin
dependencies {
    implementation("com.google.mediapipe:tasks-genai:<latest>")
}
```

### 2) 모델 준비

- `scripts/export_gemma_to_tflite.py`는 실험 스크립트입니다.
- Windows 환경에서는 `torch_xla` 제약으로 실패할 수 있으므로 Linux 변환 환경 또는 사전 검증된 MediaPipe 모델 사용을 권장합니다.

### 3) 런타임 역할

- MediaPipe LLM Inference API는 기기 하드웨어(CPU/GPU/NPU)에서 모델 추론을 실행하도록 런타임을 제공
- 앱은 토큰 스트리밍 결과를 UI와 RAG 파이프라인(`school_law.db` 검색 결과 주입)에 연결

---

## 로컬 DB(RAG) 연동 기본 패턴

1. 사용자 질문 수신
2. SQLite FTS(`article_fts`, `chunks_fts`)로 상위 근거 조문 검색
3. 검색 근거를 프롬프트 컨텍스트로 구성
4. LLM 엔진(llama.cpp 또는 MediaPipe)으로 생성
5. 답변 + 근거 조문 표시

SQLite 예시 쿼리:

```sql
SELECT law_name, doc_type, article_no, snippet(chunks_fts, 4, '[', ']', '...', 18)
FROM chunks_fts
WHERE chunks_fts MATCH '고등교육 AND 등록금'
LIMIT 10;
```

---

## 이 저장소 기준 체크리스트

- [ ] `build/school_law.db` 생성 완료
- [ ] Q4 GGUF 모델 생성 완료
- [ ] `scripts/stage_android_assets.py`로 앱 assets 반영 완료
- [ ] 안드로이드 디바이스에서 모델 로드/질의 응답 확인
- [ ] 법령 근거 검색(FTS) + 답변 연결 확인
