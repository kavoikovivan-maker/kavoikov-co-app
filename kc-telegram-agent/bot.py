#!/usr/bin/env python3
import os
import time
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile").strip()

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is missing")
if not GROQ_API_KEY:
    raise SystemExit("GROQ_API_KEY is missing")

TG = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "Ты K&C.agent — персональный AI-ассистент Ивана. "
    "Отвечай по-русски, кратко и по делу. "
    "Если задача техническая — давай конкретные шаги и команды."
)

history = {}

def tg(method, payload=None, timeout=35):
    r = requests.post(f"{TG}/{method}", json=payload or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    return data["result"]

def send(chat_id, text):
    text = str(text)
    for i in range(0, len(text), 4000):
        tg("sendMessage", {"chat_id": chat_id, "text": text[i:i+4000]})

def ask_groq(chat_id, text):
    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": text})
    msgs[:] = msgs[-12:]

    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
        "temperature": 0.4,
        "max_tokens": 1200,
    }
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=60,
    )
    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"].strip()
    msgs.append({"role": "assistant", "content": answer})
    msgs[:] = msgs[-12:]
    return answer

def main():
    me = tg("getMe")
    print(f"Started Telegram bot @{me.get('username', '')}", flush=True)

    offset = None
    while True:
        try:
            payload = {"timeout": 25}
            if offset is not None:
                payload["offset"] = offset
            updates = tg("getUpdates", payload, timeout=35)

            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = (msg.get("text") or "").strip()
                if not chat_id or not text:
                    continue

                if text == "/start":
                    send(chat_id, "K&C.agent подключён. Напиши мне сообщение.")
                    continue
                if text == "/reset":
                    history.pop(chat_id, None)
                    send(chat_id, "Контекст очищен.")
                    continue

                try:
                    send(chat_id, ask_groq(chat_id, text))
                except Exception as e:
                    print(f"Groq error: {e}", flush=True)
                    send(chat_id, "Не смог получить ответ от AI. Проверь GROQ_API_KEY и модель.")

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
