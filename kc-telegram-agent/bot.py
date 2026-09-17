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
    "В группах будь полезным и не спамь: отвечай по упоминанию или ответу на сообщение бота. "
    "Если задача техническая — давай конкретные шаги. "
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

def send(chat_id, text, reply_to=None, thread_id=None):
    text = str(text)
    for i in range(0, len(text), 4000):
        payload = {"chat_id": chat_id, "text": text[i:i+4000]}
        if reply_to:
            payload["reply_parameters"] = {"message_id": reply_to}
        if thread_id:
            payload["message_thread_id"] = thread_id
        tg("sendMessage", payload)

def ask_groq(chat_id, text):
    msgs = history.setdefault(chat_id, [])
    msgs.append({"role": "user", "content": text})
    msgs[:] = msgs[-20:]
    payload = {
        "model": GROQ_MODEL,
        "messages": [{"role": "system", "content": SYSTEM_PROMPT}] + msgs,
        "temperature": 0.4,
        "max_tokens": 1800,
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
    msgs[:] = msgs[-20:]
    return answer

def user_id_of(msg):
    return int((msg.get("from") or {}).get("id") or 0)

def is_owner(msg):
    return bool(OWNER_TELEGRAM_ID) and str(user_id_of(msg)) == OWNER_TELEGRAM_ID

def member(chat_id, user_id):
    return tg("getChatMember", {"chat_id": chat_id, "user_id": user_id})

def is_admin(chat_id, user_id):
    try:
        return member(chat_id, user_id).get("status") in {"creator", "administrator"}
    except Exception:
        return False

def can_moderate(msg):
    chat = msg.get("chat") or {}
    if chat.get("type") == "private":
        return is_owner(msg)
    return is_owner(msg) or is_admin(chat.get("id"), user_id_of(msg))

def target_from_reply(msg):
    user = ((msg.get("reply_to_message") or {}).get("from") or {})
    return int(user["id"]) if user.get("id") else None

def reply_mid(msg):
    return (msg.get("reply_to_message") or {}).get("message_id")

def command_arg(text):
    p = text.split(maxsplit=1)
    return p[1].strip() if len(p) > 1 else ""

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
        "K&C.agent — максимум Telegram Bot API\n\n"
        "AI и сервис:\n"
        "/start /help /status /reset /whoami /chatinfo\n"
        "/say ТЕКСТ — написать от имени бота\n"
        "/poll Вопрос | Ответ1 | Ответ2 — создать опрос\n"
        "/copy — скопировать сообщение, ответом на него\n"
        "/react 👍 — поставить реакцию, ответом на сообщение\n\n"
        "Модерация группы (бот должен быть админом):\n"
        "/delete /pin /unpin\n"
        "/ban /unban /kick\n"
        "/mute МИН /unmute\n"
        "/promote /demote\n"
        "/invite — создать ссылку-приглашение\n\n"
        "Настройки группы:\n"
        "/title НАЗВАНИЕ\n"
        "/description ТЕКСТ\n"
        "/slowmode СЕКУНДЫ\n"
        "/photo — установить фото группы из изображения, ответом на фото\n"
        "/removephoto — удалить фото группы\n\n"
        "Темы форума:\n"
        "/topic НАЗВАНИЕ\n"
        "/closetopic /reopentopic — в текущей теме\n\n"
        "В группах AI отвечает по @упоминанию или если ответить на сообщение бота."
    )

def require_mod(msg, chat_id, message_id):
    if can_moderate(msg):
        return True
    send(chat_id, "Недостаточно прав. Команда доступна владельцу/администратору.", message_id)
    return False

def handle_command(msg, text):
    chat = msg.get("chat") or {}
    chat_id = chat.get("id")
    message_id = msg.get("message_id")
    thread_id = msg.get("message_thread_id")
    cmd = text.split()[0].split("@")[0].lower()
    arg = command_arg(text)

    if cmd == "/start":
        send(chat_id, "K&C.agent подключён и работает.", message_id, thread_id)
        return True
    if cmd == "/help":
        send(chat_id, help_text(), message_id, thread_id)
        return True
    if cmd == "/reset":
        history.pop(chat_id, None)
        send(chat_id, "Контекст очищен.", message_id, thread_id)
        return True
    if cmd == "/whoami":
        send(chat_id, f"Ваш Telegram ID: {user_id_of(msg)}", message_id, thread_id)
        return True
    if cmd == "/status":
        send(chat_id, server_status(), message_id, thread_id)
        return True
    if cmd == "/chatinfo":
        send(
            chat_id,
            f"Chat ID: {chat_id}\nТип: {chat.get('type')}\nТема ID: {thread_id or '-'}\nНазвание: {chat.get('title') or chat.get('username') or chat.get('first_name') or '-'}",
            message_id,
            thread_id,
        )
        return True
    if cmd == "/say":
        if not require_mod(msg, chat_id, message_id): return True
        if not arg:
            send(chat_id, "Использование: /say текст", message_id, thread_id)
        else:
            send(chat_id, arg, None, thread_id)
        return True
    if cmd == "/poll":
        if not require_mod(msg, chat_id, message_id): return True
        parts = [x.strip() for x in arg.split("|") if x.strip()]
        if len(parts) < 3:
            send(chat_id, "Формат: /poll Вопрос | Ответ 1 | Ответ 2", message_id, thread_id)
        else:
            payload = {"chat_id": chat_id, "question": parts[0], "options": [{"text": x} for x in parts[1:11]]}
            if thread_id: payload["message_thread_id"] = thread_id
            tg("sendPoll", payload)
        return True
    if cmd == "/copy":
        if not require_mod(msg, chat_id, message_id): return True
        mid = reply_mid(msg)
        if not mid:
            send(chat_id, "Ответь /copy на сообщение.", message_id, thread_id)
        else:
            payload = {"chat_id": chat_id, "from_chat_id": chat_id, "message_id": mid}
            if thread_id: payload["message_thread_id"] = thread_id
            tg("copyMessage", payload)
        return True
    if cmd == "/react":
        mid = reply_mid(msg)
        if not mid:
            send(chat_id, "Ответь /react 👍 на сообщение.", message_id, thread_id)
        else:
            emoji = arg or "👍"
            tg("setMessageReaction", {"chat_id": chat_id, "message_id": mid, "reaction": [{"type": "emoji", "emoji": emoji}]})
        return True

    admin_cmds = {
        "/delete","/pin","/unpin","/ban","/unban","/kick","/mute","/unmute",
        "/promote","/demote","/invite","/title","/description","/slowmode",
        "/removephoto","/topic","/closetopic","/reopentopic","/photo"
    }
    if cmd not in admin_cmds:
        return False
    if not require_mod(msg, chat_id, message_id):
        return True

    mid = reply_mid(msg)
    target = target_from_reply(msg)

    if cmd == "/delete":
        if not mid: send(chat_id, "Ответь /delete на сообщение.")
        else: tg("deleteMessage", {"chat_id": chat_id, "message_id": mid})
        return True
    if cmd == "/pin":
        if not mid: send(chat_id, "Ответь /pin на сообщение.")
        else: tg("pinChatMessage", {"chat_id": chat_id, "message_id": mid, "disable_notification": True})
        return True
    if cmd == "/unpin":
        if mid: tg("unpinChatMessage", {"chat_id": chat_id, "message_id": mid})
        else: tg("unpinAllChatMessages", {"chat_id": chat_id})
        return True
    if cmd in {"/ban","/kick","/unban","/mute","/unmute","/promote","/demote"} and not target:
        send(chat_id, f"Ответь {cmd} на сообщение пользователя.")
        return True

    if cmd == "/ban":
        tg("banChatMember", {"chat_id": chat_id, "user_id": target})
        send(chat_id, "Пользователь заблокирован.")
        return True
    if cmd == "/kick":
        tg("banChatMember", {"chat_id": chat_id, "user_id": target})
        tg("unbanChatMember", {"chat_id": chat_id, "user_id": target, "only_if_banned": True})
        send(chat_id, "Пользователь удалён из группы.")
        return True
    if cmd == "/unban":
        tg("unbanChatMember", {"chat_id": chat_id, "user_id": target, "only_if_banned": True})
        send(chat_id, "Пользователь разблокирован.")
        return True
    if cmd == "/mute":
        minutes = int(arg) if arg.isdigit() else 60
        until = int(time.time()) + minutes * 60
        tg("restrictChatMember", {
            "chat_id": chat_id, "user_id": target, "until_date": until,
            "permissions": {
                "can_send_messages": False, "can_send_audios": False, "can_send_documents": False,
                "can_send_photos": False, "can_send_videos": False, "can_send_video_notes": False,
                "can_send_voice_notes": False, "can_send_polls": False, "can_send_other_messages": False,
                "can_add_web_page_previews": False, "can_change_info": False,
                "can_invite_users": False, "can_pin_messages": False, "can_manage_topics": False
            }
        })
        send(chat_id, f"Пользователь ограничен на {minutes} мин.")
        return True
    if cmd == "/unmute":
        tg("restrictChatMember", {
            "chat_id": chat_id, "user_id": target,
            "permissions": {
                "can_send_messages": True, "can_send_audios": True, "can_send_documents": True,
                "can_send_photos": True, "can_send_videos": True, "can_send_video_notes": True,
                "can_send_voice_notes": True, "can_send_polls": True, "can_send_other_messages": True,
                "can_add_web_page_previews": True, "can_change_info": False,
                "can_invite_users": True, "can_pin_messages": False, "can_manage_topics": False
            }
        })
        send(chat_id, "Ограничения сняты.")
        return True
    if cmd == "/promote":
        tg("promoteChatMember", {
            "chat_id": chat_id, "user_id": target,
            "can_manage_chat": True, "can_delete_messages": True, "can_manage_video_chats": True,
            "can_restrict_members": True, "can_promote_members": False, "can_change_info": True,
            "can_invite_users": True, "can_pin_messages": True, "can_manage_topics": True
        })
        send(chat_id, "Пользователь повышен до администратора.")
        return True
    if cmd == "/demote":
        tg("promoteChatMember", {
            "chat_id": chat_id, "user_id": target,
            "can_manage_chat": False, "can_delete_messages": False, "can_manage_video_chats": False,
            "can_restrict_members": False, "can_promote_members": False, "can_change_info": False,
            "can_invite_users": False, "can_pin_messages": False, "can_manage_topics": False
        })
        send(chat_id, "Права администратора сняты.")
        return True
    if cmd == "/invite":
        result = tg("createChatInviteLink", {"chat_id": chat_id, "name": "K&C.agent"})
        send(chat_id, result.get("invite_link", "Не удалось создать ссылку."), message_id, thread_id)
        return True
    if cmd == "/title":
        if not arg: send(chat_id, "Использование: /title новое название")
        else:
            tg("setChatTitle", {"chat_id": chat_id, "title": arg[:128]})
            send(chat_id, "Название изменено.")
        return True
    if cmd == "/description":
        tg("setChatDescription", {"chat_id": chat_id, "description": arg[:255]})
        send(chat_id, "Описание изменено.")
        return True
    if cmd == "/slowmode":
        seconds = int(arg) if arg.isdigit() else 0
        tg("setChatPermissions", {"chat_id": chat_id, "permissions": {
            "can_send_messages": True, "can_send_audios": True, "can_send_documents": True,
            "can_send_photos": True, "can_send_videos": True, "can_send_video_notes": True,
            "can_send_voice_notes": True, "can_send_polls": True, "can_send_other_messages": True,
            "can_add_web_page_previews": True, "can_change_info": False,
            "can_invite_users": True, "can_pin_messages": False, "can_manage_topics": False
        }})
        # Telegram Bot API does not expose slow mode editing directly; keep command informative.
        send(chat_id, f"Обычные права участников обновлены. Slow mode {seconds} сек нужно менять в настройках Telegram.")
        return True
    if cmd == "/removephoto":
        tg("deleteChatPhoto", {"chat_id": chat_id})
        send(chat_id, "Фото группы удалено.")
        return True
    if cmd == "/photo":
        reply = msg.get("reply_to_message") or {}
        photos = reply.get("photo") or []
        if not photos:
            send(chat_id, "Ответь /photo на фотографию.")
        else:
            file_id = photos[-1]["file_id"]
            f = tg("getFile", {"file_id": file_id})
            file_path = f["file_path"]
            raw = requests.get(f"https://api.telegram.org/file/bot{TELEGRAM_BOT_TOKEN}/{file_path}", timeout=60)
            raw.raise_for_status()
            files = {"photo": ("chat.jpg", raw.content, "image/jpeg")}
            rr = requests.post(f"{TG}/setChatPhoto", data={"chat_id": chat_id}, files=files, timeout=60)
            rr.raise_for_status()
            if not rr.json().get("ok"): raise RuntimeError(rr.json())
            send(chat_id, "Фото группы обновлено.")
        return True
    if cmd == "/topic":
        if not arg:
            send(chat_id, "Использование: /topic название")
        else:
            result = tg("createForumTopic", {"chat_id": chat_id, "name": arg[:128]})
            send(chat_id, f"Тема создана: {result.get('name', arg)}")
        return True
    if cmd == "/closetopic":
        if not thread_id: send(chat_id, "Команда работает внутри темы форума.")
        else:
            tg("closeForumTopic", {"chat_id": chat_id, "message_thread_id": thread_id})
        return True
    if cmd == "/reopentopic":
        if not thread_id: send(chat_id, "Команда работает внутри темы форума.")
        else:
            tg("reopenForumTopic", {"chat_id": chat_id, "message_thread_id": thread_id})
        return True

    return True

def should_answer_group(msg, text):
    chat = msg.get("chat") or {}
    if chat.get("type") == "private":
        return True
    if BOT_USERNAME and f"@{BOT_USERNAME.lower()}" in text.lower():
        return True
    reply = msg.get("reply_to_message") or {}
    reply_from = reply.get("from") or {}
    return bool(BOT_ID and reply_from.get("id") == BOT_ID)

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
            {"command": "reset", "description": "Очистить AI-контекст"},
            {"command": "whoami", "description": "Мой Telegram ID"},
            {"command": "chatinfo", "description": "Информация о чате"},
            {"command": "say", "description": "Написать от имени бота"},
            {"command": "poll", "description": "Создать опрос"},
            {"command": "pin", "description": "Закрепить сообщение"},
            {"command": "delete", "description": "Удалить сообщение"},
            {"command": "mute", "description": "Ограничить участника"},
            {"command": "ban", "description": "Заблокировать участника"},
        ]})
    except Exception as e:
        print(f"setMyCommands error: {e}", flush=True)

    offset = None
    while True:
        try:
            payload = {
                "timeout": 25,
                "allowed_updates": ["message", "edited_message", "channel_post", "edited_channel_post"]
            }
            if offset is not None:
                payload["offset"] = offset
            updates = tg("getUpdates", payload, timeout=35)

            for upd in updates:
                offset = upd["update_id"] + 1
                msg = (
                    upd.get("message") or upd.get("edited_message") or
                    upd.get("channel_post") or upd.get("edited_channel_post") or {}
                )
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
                        send(chat_id, f"Файл получен: {d.get('file_name','без имени')} ({d.get('file_size',0)} байт)", msg.get("message_id"), msg.get("message_thread_id"))
                    elif msg.get("photo"):
                        send(chat_id, "Фото получено.", msg.get("message_id"), msg.get("message_thread_id"))
                    elif msg.get("voice"):
                        send(chat_id, "Голосовое получено.", msg.get("message_id"), msg.get("message_thread_id"))
                    elif msg.get("video"):
                        send(chat_id, "Видео получено.", msg.get("message_id"), msg.get("message_thread_id"))
                    continue

                if not should_answer_group(msg, text):
                    continue

                if BOT_USERNAME:
                    text = text.replace(f"@{BOT_USERNAME}", "").strip()

                try:
                    send(chat_id, ask_groq(chat_id, text), msg.get("message_id"), msg.get("message_thread_id"))
                except Exception as e:
                    print(f"Groq error: {e}", flush=True)
                    send(chat_id, "Не смог получить ответ от AI.", msg.get("message_id"), msg.get("message_thread_id"))

        except KeyboardInterrupt:
            break
        except Exception as e:
            print(f"Loop error: {e}", flush=True)
            time.sleep(3)

if __name__ == "__main__":
    main()
