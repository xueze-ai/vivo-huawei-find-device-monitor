FROM mcr.microsoft.com/playwright/python:v1.61.0-noble
USER root
RUN apt-get update && apt-get install -y --no-install-recommends x11vnc novnc websockify && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN mkdir -p /data && chown pwuser:pwuser /data && chmod +x /app/start.sh
USER pwuser
ENV DISPLAY=:99 TZ=Asia/Shanghai PYTHONUNBUFFERED=1
ENTRYPOINT ["/app/start.sh"]
