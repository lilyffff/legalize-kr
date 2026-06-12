# 2단계: LLM 모델 선택 및 경량화 (4-bit + Android 포맷)

이 문서는 `school` 법령 DB를 사용하는 엣지 RAG 앱용 모델을 준비하는 단계입니다.

## 권장 모델 선택

### 1) 우선 경로 (안정성 높음)

- `Qwen/Qwen2.5-3B-Instruct` (멀티링구얼, 한국어 질의 대응 양호, 비게이트)
- 이유:
  - 게이트 모델보다 자동화가 쉽고 재현성이 높음
  - 4bit 양자화 시 스마트폰 구동 난이도가 상대적으로 낮음

### 2) 요청 모델 경로 (게이트 가능)

- `meta-llama/Llama-3.2-3B-Instruct` 또는 `google/gemma-2-2b-it`
- 주의:
  - 모델 라이선스 동의 및 `huggingface-cli login` 필요

## A. GGUF 4bit 변환 (llama.cpp, 권장)

### 준비물

- Git
- CMake
- C++ 빌드 도구(Windows: Visual Studio Build Tools)
- Windows에서는 "x64 Native Tools Command Prompt for VS" 또는 해당 환경변수가 로드된 터미널 권장
- Python 패키지:

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe -m pip install -U huggingface_hub
```

### 실행

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe scripts/quantize_to_gguf.py --model-id Qwen/Qwen2.5-3B-Instruct --quant-type Q4_K_M
```

Llama/Gemma 사용 시:

```powershell
huggingface-cli login
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe scripts/quantize_to_gguf.py --model-id meta-llama/Llama-3.2-3B-Instruct --quant-type Q4_K_M
```

### 산출물

- `models/hf/<model>/...` 원본 HF 체크포인트
- `models/gguf/<model>/model-f16.gguf`
- `models/gguf/<model>/model-q4_k_m.gguf` (안드로이드 배포 타겟)

## B. TensorFlow Lite 변환 (실험 경로)

LLM의 TFLite 변환은 모델별 지원 편차가 큽니다. 본 저장소에는 실험 스크립트를 제공합니다.

### 준비물

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe -m pip install -U torch transformers ai-edge-torch
```

### 실행

```powershell
c:/Users/WJ/AppData/Roaming/uv/python/CPYTHON-3.12.13-WINDOWS-X86_64-NONE/python.exe scripts/export_gemma_to_tflite.py --model-id google/gemma-2-2b-it --output models/tflite/gemma2-2b-it/model.tflite
```

### 참고

- 성공 시 `models/tflite/.../model.tflite` 생성
- 실패 시(unsupported ops 등) GGUF 경로를 기본 채택하고, MediaPipe에서 제공하는 사전 검증 모델 아티팩트 사용 권장
- 현재 Windows 환경에서는 `torch_xla` 의존성으로 실패할 수 있으므로 Linux 기반 변환 환경을 권장

## Android 적용 추천

- 1순위: GGUF(`Q4_K_M`) + llama.cpp Android
- 2순위: TFLite + MediaPipe/LiteRT (모델 지원 확인 필수)

## 배포 전 체크리스트

- [ ] 모델 라이선스 준수
- [ ] RAM/저장공간 측정(앱 대상 기기)
- [ ] 응답속도(TTFT, tokens/sec) 측정
- [ ] 법령 인용 정확도 샘플 테스트(`school_law.db` 연동)
