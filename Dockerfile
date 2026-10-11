# ---- 1. build the React UI -------------------------------------------------------------
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- 2. Python runtime: FastAPI serves the API and the built UI on one port -----------
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    ARTIFACT_DIR=/app/artifacts FRONTEND_DIST=/app/frontend/dist SQLITE_PATH=/app/data/reviews.db
WORKDIR /app
COPY backend/requirements.txt backend/requirements.txt
RUN pip install -r backend/requirements.txt
COPY backend/app backend/app
COPY backend/triage backend/triage
# the trained model + held-out demo alarms (run scripts/train.py before building)
COPY artifacts/model.joblib artifacts/report.json artifacts/
COPY artifacts/demo artifacts/demo
COPY --from=ui /ui/dist frontend/dist
RUN useradd --system --uid 10001 app && mkdir -p /app/data && chown -R app /app/data
USER app
WORKDIR /app/backend
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=4)" || exit 1
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--proxy-headers"]
