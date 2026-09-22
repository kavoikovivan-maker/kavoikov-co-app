#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data

if [ -z "${GROQ_API_KEY:-}" ]; then
  echo 'GROQ_API_KEY не найден. Добавьте ключ в Codespaces Secrets или переменные сервера.'
  exit 1
fi

if [ ! -x .venv/bin/python ]; then
  python3 -m venv .venv
fi
if ! .venv/bin/python -c 'from openai import OpenAI' 2>/dev/null; then
  .venv/bin/python -m pip install -r requirements.txt
fi
if curl -fsS http://127.0.0.1:4173/api/health >/dev/null 2>&1; then
  echo 'Порт 4173 занят работающим сервером. Сначала остановите его, не запускайте второй.'
  exit 1
fi

nohup .venv/bin/python -u pwa_server.py >data/server.log 2>&1 &
echo $! >data/server.pid
sleep 1
curl -fsS http://127.0.0.1:4173/api/health
printf '\nОткройте порт 4173 в разделе Ports.\n'
