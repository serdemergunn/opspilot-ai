# Build context: repository root (see docker-compose.yml).
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
WORKDIR /app
COPY apps/ai-service/requirements.lock ./
# Exact, tested dependency tree; --no-deps keeps pip from resolving anything that is not pinned.
RUN pip install --no-deps -r requirements.lock
COPY apps/ai-service/opspilot_ai ./opspilot_ai
RUN useradd --system --uid 10001 app
USER app
EXPOSE 8090
CMD ["uvicorn", "opspilot_ai.main:app", "--host", "0.0.0.0", "--port", "8090"]
