#!/usr/bin/env python3
import os
import time
import socket
import shutil
import requests
from dotenv import load_dotenv

load_dotenv()

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "").strip()
GROQ_MODEL = os.getenv("GROQ_MODEL", "openai/gpt-oss-120b").strip()
OWNER_TELEGRAM_ID = os.getenv("OWNER_TELEGRAM_ID", "").strip()

if not TELEGRAM_BOT_TOKEN:
    raise SystemExit("TELEGRAM_BOT_TOKEN is missing")
if not GROQ_API_KEY:
    raise SystemExit("GROQ_API_KEY is missing")

TG = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}"
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"

SYSTEM_PROMPT = (
    "Ты K&C.agent — персональный AI-ассистент Ивана. "
    "Отвечай по-русски, кратко и по делу. "
    "Если задача техническая — давай конкретные шаги и команды. "
    "Не утверждай, что выполнил внешнее действие, если оно реально не выполнено."
)

history = {}
BOT_ID = None
BOT_USERNAME = ""

def tg(method, payload=None, timeout=35):
    r = requests.post(f"{TG}/{method}", json=payload or {}, timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if not data.get("ok"):
        raise RuntimeError(data)
    return data["result"]

def send(chat_id, text, reply_to=None):
    text = str(text)
    for i in range(0, len(text), 4000):
        payload = {"chat_id": chat_id, "text": text[i:i+4000]}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to}
        tg("sendMessage", payload)

def ask_groq(chat_id, text):
    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": text})
    msgs[:] = msgs[-16:]
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
        "temperature": 0.4,
        "max_tokens": 1600,
    }
    r = requests.post(
        GROQ_URL,
        headers={"Authorization": f"Bearer {GROQ_API_KEY}", "Content-Type": "application/json"},
        json=payload,
        timeout=90,
    )
    r.raise_for_status()
    answer = r.json()["choices"][0]["message"]["content"].strip()
    msgs.append({"role": "assistant", "content": answer})
    msgs[:] = msgs[-16:]
    return answer

def user_id_of(msg):
    return int((msg.get("from") or {}).get("id") or 0)

def is_owner(msg):
    if not OWNER_TELEGRAM_ID:
        return False
    return str(user_id_of(msg)) == OWNER_TELEGRAM_ID

def is_admin(chat_id, user_id):
    try:
        member = tg("getChatMember", {"chat_id": chat_id, "user_id": user_id})
        return member.get("status") in {"creator", "administrator"}
    except Exception:
        return False

def can_moderate(msg):
    chat = msg.get("chat") or {}
    if chat.get("type") == "private":
        return is_owner(msg)
    return is_owner(msg) or is_admin(chat.get("id"), user_id_of(msg))

def target_from_reply(msg):
    reply = msg.get("reply_to_message") or {}
    user = reply.get("from") or {}
    uid = user.get("id")
    if not uid:
        return None
    return int(uid)

def server_status():
    total, used, free = shutil.disk_usage("/")
    return (
        "K&C server\n"
        f"Host: {socket.gethostname()}\n"
        f"Disk: {used // (1024**3)} / {total // (1024**3)} GB\n"
        f"Model: {GROQ_MODEL}\n"
        "Telegram agent: online"
    )

def help_text():
    return (
        "K&C.agent команды:\n"
        "/start — проверка связи\n"
        "/help — команды\n"
        "/reset — очистить AI-контекст\n"
        "/whoami — показать Telegram ID\n"
        "/status — состояние агента/сервера\n"
        "/chatinfo — данные текущего чата\n"
        "\nАдминистрирование группы (бот должен быть админом):\n"
        "/delete — удалить сообщение, ответом на него\n"
        "/pin — закрепить сообщение, ответом на него\n"
        "/unpin — открепить сообщение, ответом на него\n"
        "/ban — заблокировать пользователя, ответом на его сообщение\n"
        "/unban — разблокировать пользователя, ответом на его сообщение\n"
        "\nВ личном чате просто пиши текст — отвечу через AI."
    )

def handle_command(msg, text):
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    cmd = text.split()[0].split("@")[0].lower()

    if cmd == "/start":
        send(chat_id, "K&C.agent подключён и работает.", message_id)
        return True
    if cmd == "/help":
        send(chat_id, help_text(), message_id)
        return True
    if cmd == "/reset":
        history.pop(chat_id, None)
        send(chat_id, "Контекст очищен.", message_id)
        return True
    if cmd == "/whoami":
        send(chat_id, f"Ваш Telegram ID: {user_id_of(msg)}", message_id)
        return True
    if cmd == "/status":
        send(chat_id, server_status(), message_id)
        return True
    if cmd == "/chatinfo":
        send(
            chat_id,
            f"Chat ID: {chat_id}\nТип: {chat.get('type')}\nНазвание: {chat.get('title') or chat.get('username') or chat.get('first_name') or '-'}",
            message_id,
        )
        return True

    if cmd in {"/delete", "/pin", "/unpin", "/ban", "/unban"}:
        if not can_moderate(msg):
            send(chat_id, "Недостаточно прав для этой команды.", message_id)
            return True
        reply = msg.get("reply_to_message") or {}
        reply_mid = reply.get("message_id")

        if cmd == "/delete":
            if not reply_mid:
                send(chat_id, "Ответь командой /delete на сообщение, которое нужно удалить.")
            else:
                tg("deleteMessage", {"chat_id": chat_id, "message_id": reply_mid})
            return True

        if cmd == "/pin":
            if not reply_mid:
                send(chat_id, "Ответь командой /pin на сообщение.")
            else:
                tg("pinChatMessage", {"chat_id": chat_id, "message_id": reply_mid, "disable_notification": True})
            return True

        if cmd == "/unpin":
            if reply_mid:
                tg("unpinChatMessage", {"chat_id": chat_id, "message_id": reply_mid})
            else:
                tg("unpinAllChatMessages", {"chat_id": chat_id})
            return True

        target = target_from_reply(msg)
        if not target:
            send(chat_id, f"Ответь командой {cmd} на сообщение пользователя.")
            return True

        if cmd == "/ban":
            tg("banChatMember", {"chat_id": chat_id, "user_id": target})
            send(chat_id, "Пользователь заблокирован.")
            return True
        if cmd == "/unban":
            tg("unbanChatMember", {"chat_id": chat_id, "user_id": target, "only_if_banned": True})
            send(chat_id, "Пользователь разблокирован.")
            return True

    return False

def should_answer_group(msg, text):
    chat = msg.get("chat") or {}
    if chat.get("type") == "private":
        return True
    if BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text.lower():
        return True
    reply = msg.get("reply_to_message") or {}
    reply_from = reply.get("from") or {}
    return BOT_ID and reply_from.get("id") == BOT_ID

def main():
    global BOT_ID, BOT_USERNAME
    me = tg("getMe")
    BOT_ID = me.get("id")
    BOT_USERNAME = me.get("username", "")
    print(f"Started Telegram bot @{BOT_USERNAME}", flush=True)

    try:
        tg("setMyCommands", {"commands": [
            {"command": "start", "description": "Проверка подключения"},
            {"command": "help", "description": "Все команды"},
            {"command": "status", "description": "Статус агента"},
            {"command": "reset", "description": "Очистить контекст"},
            {"command": "whoami", "description": "Мой Telegram ID"},
            {"command": "chatinfo", "description": "Информация о чате"},
        ]})
    except Exception as e:
        print(f"setMyCommands error: {e}", flush=True)

    offset = None
    while True:
        try:
            payload = {"timeout": 25, "allowed_updates": ["message", "channel_post"]}
            if offset is not None:
                payload["offset"] = offset
            updates = tg("getUpdates", payload, timeout=35)

            for upd in updates:
                offset = upd["update_id"] + 1
                msg = upd.get("message") or upd.get("channel_post") or {}
                chat = msg.get("chat") or {}
                chat_id = chat.get("id")
                text = (msg.get("text") or msg.get("caption") or "").strip()
                if not chat_id:
                    continue

                if text.startswith("/") and handle_command(msg, text):
                    continue

                if not text:
                    if msg.get("document"):
                        d = msg["document"]
                        send(chat_id, f"Файл получен: {d.get('file_name','без имени')} ({d.get('file_size',0)} байт)")
                    elif msg.get("photo"):
                        send(chat_id, "Фото получено. Поддержку анализа изображений подключим отдельной моделью.")
                    elif msg.get("voice"):
                        send(chat_id, "Голосовое получено. Распознавание голоса подключим отдельным модулем.")
                    continue

                if not should_answer_group(msg, text):
                    continue

                if BOT_USERNAME:
                    text = text.replace(f"@{BOT_USERNAME}", "").strip()

                try:
                    send(chat_id, ask_groq(chat_id, text), msg.get("message_id"))
                except Exception as e:
                    print(f"Groq error: {e}", flush=True)
                    send(chat_id, "Не смог получить ответ от AI. Проверь GROQ_API_KEY и модель.", msg.get("message_id"))

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
