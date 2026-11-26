# --- build the React app
FROM node:22-slim AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- API + static SPA in one container
FROM python:3.13-slim
RUN pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/app ./app
COPY --from=web /web/dist /app/frontend/dist
ENV PORT=8000 PYTHONUNBUFFERED=1
EXPOSE 8000
CMD ["sh", "-c", "uv run --no-dev uvicorn app.main:app --host 0.0.0.0 --port ${PORT}"]
