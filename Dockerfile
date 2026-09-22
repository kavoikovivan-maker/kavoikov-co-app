FROM python:3.13-slim
WORKDIR /app
COPY agno-demo/requirements.txt /app/agno-demo/requirements.txt
RUN pip install --no-cache-dir -r /app/agno-demo/requirements.txt
COPY . /app
WORKDIR /app/agno-demo
ENV PORT=8080
CMD ["python3", "pwa_server.py"]
