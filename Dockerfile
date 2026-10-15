# Stage 1: build the React UI (no Node needed on the host).
FROM node:22-alpine AS ui
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm install --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# Stage 2: Python backend that captures traffic and serves the built UI.
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    NETWATCH_DATA=/data \
    NETWATCH_STATIC=/app/static
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/netwatch ./netwatch
COPY --from=ui /ui/dist ./static
VOLUME /data
CMD ["python", "-m", "netwatch.main"]
