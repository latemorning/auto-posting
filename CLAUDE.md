# CLAUDE.md

이 파일은 Claude Code가 이 저장소에서 작업할 때 참고하는 안내 문서입니다.

## 실행

```bash
python auto_post.py
```

실행 시 두 가지가 함께 시작됩니다:
- Flask API 서버 (포트 5000)
- 매일 `post_time`에 자동 포스팅하는 스케줄러

## 아키텍처

게시글을 매일 자동으로 순차 포스팅하는 단일 파이썬 스크립트(`auto_post.py`).

**데이터 흐름:**
1. `main()` — API 스레드 시작 + 스케줄 루프 진입
2. `run_api_server()` — Flask 서버를 daemon 스레드로 실행 (포트 5000)
3. `create_post()` — `{일련번호} {요일(한글)}` 형식으로 제목 생성, `post_to_board()` 호출, `logs/YYYYMMDD.log`에 기록, 일련번호 증가 후 `save_config()` 호출
4. `post_to_board(driver, config, title)` — Selenium headless Chrome으로 로그인 → 글쓰기 페이지 이동 → 제목/본문 입력 → 제출

**의존성 (requirements.txt):**
- `anthropic` — Claude API (예정, 미사용)
- `requests` — HTTP 요청 (예정, 미사용)
- `schedule` — 스케줄링 (사용 중)
- `selenium` — 브라우저 자동화 (사용 중)
- `flask` — 일련번호 관리 REST API (사용 중)
- `pytest`, `pytest-mock` — 단위/통합 테스트 (사용 중)

**config.json 필드:**
- `current_serial` — 자동 증가 게시글 번호 (현재 1126)
- `board_url` — 게시판 URL
- `post_time` — 매일 자동 실행 시각 (기본값 `"09:00"`)
- `login_url` — 로그인 페이지 URL
- `write_url` — 글쓰기 페이지 URL
- `username` — 로그인 아이디
- `password` — 로그인 비밀번호
- `selectors` — Selenium에서 사용할 CSS 셀렉터 모음
  - `username_input`, `password_input`, `login_button`
  - `title_input`, `content_input`, `submit_button`

**게시글 제목 형식:** `{일련번호} {요일}` (예: `1126 금`)
요일 약자: 월 화 수 목 금 토 일

## 일련번호 관리 API

| Method | Path | 설명 |
|--------|------|------|
| `GET` | `/serial` | 현재 일련번호 조회 |
| `PUT` | `/serial` | 일련번호를 특정 값으로 설정 (body: `{"value": 1200}`) |
| `POST` | `/serial/increment` | 일련번호 +1 후 반환 |
| `POST` | `/post` | 즉시 게시글 작성 (백그라운드 실행) |

```bash
curl http://localhost:5000/serial
curl -X PUT http://localhost:5000/serial -d '{"value":1200}' -H 'Content-Type: application/json'
curl -X POST http://localhost:5000/serial/increment
```

## 변경 이력

### 2026-03-20
**버그 수정 — `auto_post.py`**
- 로그인 버튼 클릭 후 `wait.until(EC.url_changes(login_url))` 추가
  - 기존: 로그인 완료 전에 글쓰기 페이지로 이동 → `TimeoutException`
  - 수정: 로그인 후 URL 전환을 대기한 뒤 글쓰기 페이지로 이동

**셀렉터 수정 — `config.json`**
- `login_button`: `input[onclick='Secu_Ck()']` → `input[type='image'][src*='out_b2.gif']`
  - 사이트 HTML 변경으로 기존 셀렉터가 `NoSuchElementException` 발생

**테스트 추가 — `tests/test_auto_post.py`**
- 22개 테스트 (단위 + Flask API 통합)
  - `TestGetDayOfWeek` — 월~일 7개 요일 반환값
  - `TestConfigIO` — `load_config` / `save_config` 왕복 정합성
  - `TestPostToBoard` — Selenium Mock으로 `driver.get()` 순서, `send_keys`/`click` 횟수
  - `TestCreatePost` — 로그 파일 생성, 제목 형식, 일련번호 증가
  - `TestFlaskAPI` — GET/PUT/POST 정상·오류 응답
- 실행: `pytest tests/ -v`
