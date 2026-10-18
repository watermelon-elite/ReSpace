FROM python:3.12-slim

# Build from the repository root: docker build -f backend/Dockerfile .
ENV PYTHONUNBUFFERED=1 PLAYWRIGHT_BROWSERS_PATH=/opt/ms-playwright RESPACE_ASSET_ROOT=/app/assets
WORKDIR /app
COPY backend/pyproject.toml ./
COPY backend/respace ./respace
COPY prompts/layouts.md ./prompts/layouts.md
COPY assets ./assets
RUN pip install --no-cache-dir . && playwright install --with-deps chromium \
    && useradd --create-home --uid 10001 respace
USER respace
EXPOSE 8080
CMD ["sh", "-c", "exec uvicorn respace.api:create_app --factory --host 0.0.0.0 --port ${PORT:-8080}"]
