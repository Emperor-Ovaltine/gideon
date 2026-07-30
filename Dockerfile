# Dockerfile for Gideon
FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY ./src ./src

# Run as a non-root user; /app/data holds the SQLite database
RUN useradd --create-home --uid 1000 gideon \
    && mkdir -p /app/data \
    && chown -R gideon:gideon /app
USER gideon

# Expose dashboard port (configurable via DASHBOARD_PORT env var, default 8080)
EXPOSE 8080

CMD ["python", "-m", "src"]
