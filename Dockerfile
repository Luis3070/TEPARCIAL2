FROM node:22-bookworm-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    EH4000_DB_PATH=/data/eh4000_integrity.sqlite3 \
    EH4000_UPLOAD_DIR=/data/uploads
WORKDIR /app
COPY backend/requirements-prod.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt \
    && useradd --create-home --uid 10001 appuser \
    && mkdir -p /data/uploads \
    && chown -R appuser:appuser /data
COPY backend/app/ ./backend/app/
COPY backend/__init__.py ./backend/__init__.py
COPY outputs/qa_summary.json outputs/qa_tests.csv outputs/sd_inspections_qa.csv outputs/qa_maintenance_events.csv ./outputs/
COPY outputs/maintenance/maintenance_features.csv outputs/maintenance/zone_snapshot.csv outputs/maintenance/maintenance_summary.json ./outputs/maintenance/
COPY DATOSCRUDOS/EH4000_historial_grietas.xlsx ./DATOSCRUDOS/
COPY frontend/public/assets/ ./frontend/public/assets/
COPY --from=frontend-build /app/frontend/dist ./frontend/dist
USER appuser
EXPOSE 8080
CMD ["uvicorn", "backend.app.main:app", "--host", "0.0.0.0", "--port", "8080", "--proxy-headers"]
