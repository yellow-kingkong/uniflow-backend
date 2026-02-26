# Railway용 Dockerfile — WeasyPrint + 한국어 폰트 지원
FROM python:3.11-slim

# ─── 시스템 패키지 ────────────────────────────────────────────────────────
RUN apt-get update && apt-get install -y \
    # 한국어 폰트 (Noto CJK)
    fonts-noto-cjk \
    fonts-noto-cjk-extra \
    # WeasyPrint 의존성 (Pango, Cairo 기반 렌더링)
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    ca-certificates \
    --no-install-recommends \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ─── Python 작업 디렉토리 ────────────────────────────────────────────────
WORKDIR /app

# ─── 패키지 설치 ──────────────────────────────────────────────────────────
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# ─── 앱 복사 ──────────────────────────────────────────────────────────────
COPY . .

# ─── 실행 ────────────────────────────────────────────────────────────────
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
