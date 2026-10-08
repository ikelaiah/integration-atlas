# Integration Atlas — optional convenience image.
#
# The application is designed to run without Docker:
#     pip install -e . && atlas serve
# This image exists for people who would rather not manage a Python
# environment. It is not required and adds no functionality.

FROM node:22-alpine AS frontend
WORKDIR /ui
COPY frontend/package.json frontend/package-lock.json* ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    ATLAS_DATA_DIR=/data \
    ATLAS_STATIC_DIR=/app/frontend/dist

COPY pyproject.toml README.md ./
COPY backend/ ./backend/
RUN pip install --no-cache-dir .

COPY --from=frontend /ui/dist ./frontend/dist
COPY examples/ ./examples/

VOLUME ["/data"]
EXPOSE 8000

# Seeds the demo estate on first run so there is something to look at.
CMD ["sh", "-c", "atlas demo || true; atlas serve --host 0.0.0.0 --port 8000"]
