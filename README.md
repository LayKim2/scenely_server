# Scenely Server

파이썬 서버 프로젝트 (FastAPI, Celery, Deepgram STT, Gemini).

**Python 3.10+ 필요** (deepgram-sdk 등 의존성 요구).

## 로컬 실행 (Mac)

### 1. Python 3.10+ 사용

시스템 기본이 3.9라면 Homebrew로 3.11 설치 후 해당 버전으로 venv 생성:

```bash
brew install python@3.11
cd /path/to/scenely_server
rm -rf .venv
python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2. Redis & PostgreSQL

```bash
brew install redis postgresql@15
brew services start redis
brew services start postgresql@15
```

**PostgreSQL에 `scenely` 유저/DB 생성** (한 번만 하면 됨). 기본 `DATABASE_URL`은 `postgresql://scenely:scenely@localhost:5432/scenely` 입니다.

```bash
# 방법 1: psql로 접속 후 (Mac 로그인 사용자로)
psql postgres -c "CREATE USER scenely WITH PASSWORD 'scenely' CREATEDB;"
psql postgres -c "CREATE DATABASE scenely OWNER scenely;"

# 방법 2: createuser/createdb (비밀번호는 대화형으로 입력)
createuser -s scenely -P   # 비밀번호 입력 시 scenely
createdb -O scenely scenely
```

`.env`에 `REDIS_URL`, `DATABASE_URL` 등 설정. DB만 다르게 쓰려면 `DATABASE_URL`을 바꾸면 됨.

### 3. API 서버

```bash
source .venv/bin/activate
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- API: http://localhost:8000  
- Swagger: http://localhost:8000/docs  

### 4. 잡 처리용 Worker (선택)

```bash
source .venv/bin/activate
celery -A app.workers.celery_app worker --loglevel=info
```

## Docker

```bash
docker-compose up --build
```

## 프로젝트 구조

```
scenely_server/
├── app/
│   ├── main.py          # FastAPI 앱
│   ├── api/routes/      # auth, jobs, media, lessons, stt
│   ├── core/            # db, auth, models
│   ├── services/        # deepgram_stt, gemini, s3, ffmpeg
│   └── workers/         # Celery tasks
├── requirements.txt
└── docker-compose.yml
```
