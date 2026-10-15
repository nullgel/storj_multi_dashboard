# Lightweight Python Alpine base image
FROM python:3.12-alpine

# Set working directory
WORKDIR /app

# Python unbuffered logging and default config/port environment
ENV PYTHONUNBUFFERED=1 \
    CONFIG_PATH=/config/config.json \
    PORT=8888

# Create config mount directory and static directory
RUN mkdir -p /config /app/static

# Copy server and static web assets
COPY server.py /app/
COPY static/ /app/static/

# Web dashboard port
EXPOSE 8888

# Native container healthcheck via /health endpoint
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
  CMD wget -qO- http://127.0.0.1:${PORT}/health || exit 1

# Start dashboard server
CMD ["python3", "server.py"]
