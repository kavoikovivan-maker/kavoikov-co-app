#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p data
if ! command -v ollama >/dev/null; then echo 'Ollama отсутствует. Установите его с ollama.com, затем повторите запуск.'; exit 1; fi
if [ ! -x .venv/bin/python ]; then python3 -m venv .venv; fi
if ! .venv/bin/python -c 'from agno.agent import Agent; from agno.models.ollama import Ollama' 2>/dev/null; then .venv/bin/python -m pip install -r requirements.txt; fi
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null; then
 OLLAMA_HOST=127.0.0.1:11434 nohup ollama serve >data/ollama.log 2>&1 &
 for n in {1..20}; do if curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then break; fi; sleep 1; done
fi
if ! OLLAMA_HOST=127.0.0.1:11434 ollama list | awk '{print $1}' | grep -qx 'qwen2.5:3b'; then echo 'Нужно скачать qwen2.5:3b через ollama pull qwen2.5:3b'; exit 1; fi
if curl -fsS http://127.0.0.1:4173/api/health >/dev/null 2>&1; then echo 'Порт 4173 занят работающим сервером. Сначала остановите его, не запускайте второй.'; exit 1; fi
nohup .venv/bin/python -u pwa_server.py >data/server.log 2>&1 &
echo $! >data/server.pid
sleep 1
curl -fsS http://127.0.0.1:4173/api/health
printf '\nОткройте порт 4173 в Ports, оставьте Private.\n'
