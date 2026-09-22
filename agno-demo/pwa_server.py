#!/usr/bin/env python3
import json
import hashlib
import os
import sqlite3
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlparse


ROOT = Path(__file__).resolve().parent / "pwa"
DB_PATH = Path(os.environ.get("KAVOIKOFF_DB_PATH", ROOT.parent / "data" / "chats.db"))
DB_PATH.parent.mkdir(exist_ok=True)
PORT = int(os.environ.get("PORT", "4173"))
FREE_MODEL = os.environ.get("GROQ_FREE_MODEL", "openai/gpt-oss-20b")
PRO_MODEL = os.environ.get("GROQ_PRO_MODEL", "openai/gpt-oss-120b")
FREE_DAILY_MESSAGES = int(os.environ.get("FREE_DAILY_MESSAGES", "10"))
PRO_DAILY_MESSAGES = int(os.environ.get("PRO_DAILY_MESSAGES", "200"))
GROQ_BASE_URL = "https://api.groq.com/openai/v1"
SYSTEM_PROMPT = (
    "Ты — личный ИИ-помощник внутри приложения Kavoikoff&CO. "
    "Отвечай естественно и по делу, по умолчанию на русском языке. "
    "Помогай с программированием, продуктами, рабочими задачами и технологиями напитков. "
    "Сохраняй контекст текущего диалога, уточняй только действительно необходимое. "
    "Ты один помощник и ведёшь обычный прямой диалог с пользователем. "
    "Не заявляй об абсолютной анонимности или возможностях, которых у приложения нет."
)


def init_db() -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS chats (
                id TEXT PRIMARY KEY,
                title TEXT NOT NULL,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS clients (
                id_hash TEXT PRIMARY KEY,
                plan TEXT NOT NULL CHECK(plan IN ('free', 'pro')),
                created_at TEXT NOT NULL
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS daily_usage (
                id_hash TEXT NOT NULL,
                usage_day TEXT NOT NULL,
                message_count INTEGER NOT NULL DEFAULT 0,
                PRIMARY KEY(id_hash, usage_day)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS messages (
                id TEXT PRIMARY KEY,
                chat_id TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('user', 'assistant')),
                content TEXT NOT NULL,
                created_at TEXT NOT NULL,
                FOREIGN KEY(chat_id) REFERENCES chats(id)
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS jobs (
                id TEXT PRIMARY KEY,
                payload TEXT NOT NULL,
                state TEXT NOT NULL,
                result TEXT NOT NULL
            )
            """
        )
        for job_id, payload, result in conn.execute(
            "SELECT id, payload, result FROM jobs WHERE state IN ('queued', 'generating')"
        ).fetchall():
            partial = json.loads(result)
            job_payload = json.loads(payload)
            if len(job_payload) >= 3:
                conn.execute(
                    """
                    UPDATE daily_usage SET message_count=MAX(0, message_count-1)
                    WHERE id_hash=? AND usage_day=?
                    """,
                    (job_payload[2], time.strftime("%Y-%m-%d", time.gmtime())),
                )
            partial["error"] = "Сервер перезапущен. Сообщение автоматически повторно не отправлялось."
            conn.execute(
                "UPDATE jobs SET state='error', result=? WHERE id=?",
                (json.dumps(partial, ensure_ascii=False), job_id),
            )


init_db()


def clean_input(value: str | None) -> str:
    text = (value or "").strip()
    return text[:8000]


def clean_output(value: str | None) -> str:
    text = (value or "").strip()
    return text[:24000]


def get_chat_messages(chat_id: str | None, limit: int = 24) -> list[dict]:
    if not chat_id:
        return []
    with sqlite3.connect(DB_PATH) as conn:
        exists = conn.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone()
        if not exists:
            return []
        rows = conn.execute(
            """
            SELECT role, content FROM (
                SELECT role, content, created_at, rowid
                FROM messages WHERE chat_id=?
                ORDER BY created_at DESC, rowid DESC LIMIT ?
            ) ORDER BY created_at ASC, rowid ASC
            """,
            (chat_id, limit),
        ).fetchall()
    return [{"role": role, "content": content} for role, content in rows]


def run_assistant(message: str, chat_id: str | None = None, plan: str = "free", progress=lambda content: None) -> dict:
    api_key = os.environ.get("GROQ_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GROQ_API_KEY не настроен на сервере")

    from openai import OpenAI

    client = OpenAI(api_key=api_key, base_url=GROQ_BASE_URL, timeout=90.0)
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    messages.extend(get_chat_messages(chat_id))
    messages.append({"role": "user", "content": message})
    started = time.perf_counter()
    model = PRO_MODEL if plan == "pro" else FREE_MODEL
    completion = client.chat.completions.create(
        model=model,
        messages=messages,
        max_completion_tokens=1800,
        stream=True,
    )
    parts = []
    last_progress = 0.0
    for chunk in completion:
        delta = chunk.choices[0].delta.content if chunk.choices else None
        if not delta:
            continue
        parts.append(delta)
        now = time.perf_counter()
        if now - last_progress >= 0.12:
            progress(clean_output("".join(parts)))
            last_progress = now
    content = clean_output("".join(parts))
    if not content:
        content = "Не удалось получить текст ответа. Попробуйте сформулировать запрос ещё раз."
    return {
        "content": content,
        "time_sec": round(time.perf_counter() - started, 3),
        "model": model,
    }


def save_exchange(message: str, answer: dict, chat_id: str | None = None) -> str:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    with sqlite3.connect(DB_PATH) as conn:
        if chat_id and not conn.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone():
            chat_id = None
        if not chat_id:
            chat_id = uuid.uuid4().hex
            title = " ".join(message.split())[:64] or "Новый чат"
            conn.execute("INSERT INTO chats VALUES (?, ?, ?, ?)", (chat_id, title, now, now))
        else:
            conn.execute("UPDATE chats SET updated_at=? WHERE id=?", (now, chat_id))
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, 'user', ?, ?)",
            (uuid.uuid4().hex, chat_id, message, now),
        )
        conn.execute(
            "INSERT INTO messages VALUES (?, ?, 'assistant', ?, ?)",
            (uuid.uuid4().hex, chat_id, answer["content"], now),
        )
    return chat_id


def fetch_chats() -> list[dict]:
    with sqlite3.connect(DB_PATH) as conn:
        conn.row_factory = sqlite3.Row
        chats = conn.execute(
            "SELECT id, title, created_at, updated_at FROM chats ORDER BY updated_at DESC"
        ).fetchall()
        items = []
        for chat in chats:
            messages = conn.execute(
                "SELECT role, content, created_at FROM messages WHERE chat_id=? ORDER BY created_at, rowid",
                (chat["id"],),
            ).fetchall()
            items.append(
                {
                    "id": chat["id"],
                    "title": chat["title"],
                    "created_at": chat["created_at"],
                    "updated_at": chat["updated_at"],
                    "messages": [dict(message) for message in messages],
                }
            )
    return items


JOB_LOCK = threading.Lock()


class QuotaExceeded(Exception):
    pass


def client_hash(value: str | None) -> str:
    parsed = uuid.UUID(value or "")
    return hashlib.sha256(str(parsed).encode("utf-8")).hexdigest()


def usage_day() -> str:
    return time.strftime("%Y-%m-%d", time.gmtime())


def usage_info(conn: sqlite3.Connection, id_hash: str) -> dict:
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn.execute(
        "INSERT OR IGNORE INTO clients VALUES (?, 'free', ?)",
        (id_hash, now),
    )
    plan = conn.execute("SELECT plan FROM clients WHERE id_hash=?", (id_hash,)).fetchone()[0]
    row = conn.execute(
        "SELECT message_count FROM daily_usage WHERE id_hash=? AND usage_day=?",
        (id_hash, usage_day()),
    ).fetchone()
    used = row[0] if row else 0
    limit = PRO_DAILY_MESSAGES if plan == "pro" else FREE_DAILY_MESSAGES
    return {"plan": plan, "used": used, "limit": limit, "remaining": max(0, limit - used), "usage_day": usage_day()}


def claim_usage(conn: sqlite3.Connection, id_hash: str) -> str:
    info = usage_info(conn, id_hash)
    if info["used"] >= info["limit"]:
        raise QuotaExceeded()
    conn.execute(
        """
        INSERT INTO daily_usage (id_hash, usage_day, message_count) VALUES (?, ?, 1)
        ON CONFLICT(id_hash, usage_day) DO UPDATE SET message_count=message_count+1
        """,
        (id_hash, usage_day()),
    )
    return info["plan"]


def release_usage(id_hash: str) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            UPDATE daily_usage SET message_count=MAX(0, message_count-1)
            WHERE id_hash=? AND usage_day=?
            """,
            (id_hash, usage_day()),
        )


def read_job(job_id: str) -> dict | None:
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT state, result FROM jobs WHERE id=?", (job_id,)).fetchone()
    return {"job_id": job_id, "state": row[0], **json.loads(row[1])} if row else None


def update_job(job_id: str, state: str, data: dict) -> None:
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            "UPDATE jobs SET state=?, result=? WHERE id=?",
            (state, json.dumps(data, ensure_ascii=False), job_id),
        )


def worker(job_id: str, message: str, chat_id: str | None, id_hash: str, plan: str) -> None:
    base = {"user_message": message, "plan": plan}
    try:
        update_job(job_id, "generating", base)
        def report_partial(content: str) -> None:
            update_job(job_id, "generating", {**base, "assistant": {"content": content}})

        answer = run_assistant(message, chat_id, plan, report_partial)
        saved_chat_id = save_exchange(message, answer, chat_id)
        update_job(job_id, "done", {**base, "assistant": answer, "chat_id": saved_chat_id})
    except Exception as exc:
        release_usage(id_hash)
        print("Chat failed:", type(exc).__name__, flush=True)
        public_error = str(exc) if isinstance(exc, RuntimeError) else "Помощник не завершил ответ. Проверьте ключ и журнал сервера."
        update_job(job_id, "error", {**base, "error": public_error})


class ChatHandler(SimpleHTTPRequestHandler):
    PUBLIC_FILES = {
        "/", "/index.html", "/styles.css", "/sw.js", "/app.js", "/manifest.webmanifest",
        "/icon.svg", "/icon-180.png", "/icon-192.png", "/icon-512.png",
    }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        parsed_url = urlparse(self.path)
        path = parsed_url.path
        if path == "/api/health":
            return self.send_json(
                {"status": "ok", "assistant": "configured" if os.environ.get("GROQ_API_KEY") else "missing_key"}
            )
        if path == "/api/chats":
            return self.send_json({"items": fetch_chats()})
        if path == "/api/usage":
            try:
                id_hash = client_hash(parse_qs(parsed_url.query).get("client_id", [""])[0])
            except (ValueError, AttributeError):
                return self.send_json({"error": "Некорректный идентификатор приложения"}, 400)
            with sqlite3.connect(DB_PATH) as conn:
                info = usage_info(conn, id_hash)
            return self.send_json(info)
        if path.startswith("/api/jobs/"):
            job = read_job(path.rsplit("/", 1)[-1])
            return self.send_json(job or {"error": "Задание не найдено"}, 200 if job else 404)
        if path not in self.PUBLIC_FILES:
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        if urlparse(self.path).path not in self.PUBLIC_FILES:
            return self.send_error(404)
        super().do_HEAD()

    def do_POST(self):
        if urlparse(self.path).path != "/api/chat":
            return self.send_error(404)
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.send_json({"error": "Недопустимый источник"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 20000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            message = clean_input(data.get("message"))
            job_id = data.get("request_id", "")
            chat_id = data.get("chat_id") or None
            id_hash = client_hash(data.get("client_id"))
            uuid.UUID(job_id)
            if not message or (chat_id and not isinstance(chat_id, str)):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.send_json({"error": "Нужно сообщение до 8000 символов"}, 400)

        payload = json.dumps([message, chat_id, id_hash], ensure_ascii=False)
        with JOB_LOCK, sqlite3.connect(DB_PATH) as conn:
            previous = conn.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
            if previous:
                if previous[0] != payload:
                    return self.send_json({"error": "Идентификатор уже используется"}, 409)
                return self.send_json(read_job(job_id), 200)
            if chat_id and not conn.execute("SELECT 1 FROM chats WHERE id=?", (chat_id,)).fetchone():
                return self.send_json({"error": "Чат не найден"}, 404)
            if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued', 'generating')").fetchone():
                return self.send_json({"error": "Помощник уже отвечает. Дождитесь завершения."}, 409)
            try:
                plan = claim_usage(conn, id_hash)
            except QuotaExceeded:
                return self.send_json({"error": "Бесплатный лимит на сегодня закончился", "code": "daily_limit"}, 429)
            result = json.dumps({"user_message": message, "plan": plan}, ensure_ascii=False)
            conn.execute("INSERT INTO jobs VALUES (?, ?, 'queued', ?)", (job_id, payload, result))
            conn.commit()
            threading.Thread(target=worker, args=(job_id, message, chat_id, id_hash, plan), daemon=True).start()
        return self.send_json({"job_id": job_id, "state": "queued", "user_message": message, "plan": plan}, 202)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("Referrer-Policy", "no-referrer")
        super().end_headers()

    def send_json(self, payload, status=200):
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        try:
            self.wfile.write(body)
        except (BrokenPipeError, ConnectionResetError):
            pass


if __name__ == "__main__":
    server = ThreadingHTTPServer(("0.0.0.0", PORT), ChatHandler)
    print(f"Serving Kavoikoff&CO on port {PORT}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
