# FastGPT Content Processor

FastGPT 지식 베이스 콘텐츠 관리 및 처리를 위한 명령줄 도구입니다. 지식 베이스 조회, 콘텐츠 검색, 파일 업로드 및 WeChat 기사 다운로드/정리/업로드 워크플로우를 지원합니다.

## 기능

- **list-datasets**: 모든 FastGPT 데이터셋 목록
- **list-collections**: 데이터셋 내 기사/컬렉션 목록
- **search**: 지식 베이스 내 의미론적 검색
- **upload-file**: 단일 Markdown 파일 업로드
- **upload-folder**: 폴더 내 Markdown 파일 일괄 업로드
- **download-wechat**: MCP를 통한 WeChat 기사 일괄 다운로드
- **clean-wechat**: 2단계 WeChat Markdown 정리
- **download-and-clean**: 원스톱 워크플로우: 다운로드 → 정리 → 업로드

## 설치 및 실행

### 권장 방식: uv

```bash
cd fastgpt-content-processor
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
cp .env.example .env
```

### 대안: venv

```bash
cd fastgpt-content-processor
python3 -m venv .venv
source .venv/bin/activate
python3 -m pip install -r requirements.txt
cp .env.example .env
```

### 명령어 실행

```bash
python3 main.py --help
python3 main.py list-datasets
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 돌연변이"
```

## 사용 예시

### 모든 데이터셋 목록

```bash
python3 main.py list-datasets
```

### 데이터셋 내 기사 목록

```bash
python3 main.py list-collections --dataset-id 697b19a113081cf58b45cac3
```

### 지식 베이스 검색

```bash
python3 main.py search --dataset-id 697b19a113081cf58b45cac3 --query "KRAS 돌연변이"
```

### 단일 파일 업로드

```bash
python3 main.py upload-file --file article.md --dataset-id 697b19a113081cf58b45cac3
```

### 폴더 일괄 업로드

```bash
python3 main.py upload-folder --folder ./articles --dataset-id 697b19a113081cf58b45cac3
```

### WeChat 기사 다운로드

`urls.txt`에 WeChat 기사 URL을 한 줄에 하나씩 작성:

```bash
python3 main.py download-wechat --urls urls.txt --output ./wechat-downloads
```

### WeChat 기사 정리

```bash
python3 main.py clean-wechat --input ./wechat-downloads --output ./cleaned-articles
```

### 통합 워크플로우 (다운로드 → 정리 → 업로드)

```bash
python3 main.py download-and-clean \
  --urls urls.txt \
  --output ./wechat-downloads \
  --cleaned-output ./cleaned-articles \
  --dataset-id 697b19a113081cf58b45cac3
```

## 프로젝트 구조

```
fastgpt-content-processor/
├── main.py                      # CLI 진입점
├── fastgpt_sync.py              # FastGPT API 래퍼
├── fetchers/                    # 콘텐츠 페처 모듈
├── cleaners/                    # 콘텐츠 클리너 모듈
├── utils/                       # 유틸리티
├── tests/                       # 테스트 디렉토리
├── .env.example                 # 환경변수 템플릿
├── requirements.txt             # Python 의존성
└── README.md                    # 문서
```

## 테스트

[`tests/README.md`](tests/README.md)를 참조하세요.

```bash
python3 -m pytest
```

## 로드맵

### 단기: 재현성 및 검증
- `python3` 통일 및 가상환경 문서화
- 핵심 로직 테스트 추가
- FastGPT, MCP, 예제 스크립트 경계 명확화

### 중기: 유지보수성 및 협업
- 클리닝 파이프라인 통합
- CLI 매개변수 및 인터랙티브 경험 최적화
- dry-run / 미리보기 모드 추가
- 세분화된 로깅 및 통계 추가

### 장기: 확장성 및 플랫폼화
- 플러그인 기반 페처 / 클리너 / 업로드 어댑터
- 더 많은 콘텐츠 소스 지원
- 워크플로우 기반 처리 파이프라인
- 설정 가능한 규칙 및 배치 작업 오케스트레이션

## 기여하기

코드, 문서, 테스트, 사용 경험의 기여를 환영합니다.

### 권장 사항
- 요구사항이나 문제를 설명하는 이슈를 먼저 생성하세요
- 로직 변경 전 테스트를 추가하세요
- 문서를 코드와 동기화하세요
- 새 클리닝 규칙 추가 시 샘플 입력/출력을 제공하세요

## 감사의 말

다음 프로젝트와 자료에 감사드립니다:

- [wechat-article-downloader](https://github.com/qiye45/wechatDownload)
- [baoyu-format-markdown](https://github.com/baoyu-tech/markdown-formatter)
- [markdown-frontmatter-doctor](https://github.com/example/frontmatter-doctor)
- [FastGPT API 문서](https://doc.fastgpt.in/docs/development/api/)

## 라이선스

MIT License

---

**다른 언어**: [中文](README.md) | [English](README.en.md) | [Русский](README.ru.md) | [日本語](README.ja.md)
