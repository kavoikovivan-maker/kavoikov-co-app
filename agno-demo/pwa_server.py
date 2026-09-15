#!/usr/bin/env python3
import json
import sqlite3
import threading
import time
import uuid
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler
from pathlib import Path
from urllib.parse import urlparse


ROOT = Path(__file__).resolve().parent / "pwa"
DB_PATH = ROOT.parent / "data" / "discussions.db"
DB_PATH.parent.mkdir(exist_ok=True)
if not DB_PATH.exists():
    source = ROOT / "discussions.db"
    if not source.exists():
        source = ROOT / "discussions.backup.db"
    if source.exists():
        with sqlite3.connect(source) as src, sqlite3.connect(DB_PATH) as dst:
            src.backup(dst)
PORT = 4173
OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL_ID = "qwen2.5:3b"


def sanitize_text(value: str | None) -> str:
    text = (value or "").strip()
    text = text.replace("\r", " ").replace("\n", " ")
    text = " ".join(text.split())
    return text[:1200]


def init_db() -> None:
    conn = sqlite3.connect(DB_PATH)
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS sessions (
            id TEXT PRIMARY KEY,
            idea TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            role TEXT NOT NULL,
            content TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    conn.execute("CREATE TABLE IF NOT EXISTS jobs (id TEXT PRIMARY KEY, payload TEXT NOT NULL, state TEXT NOT NULL, result TEXT NOT NULL)")
    for job_id, result in conn.execute("SELECT id, result FROM jobs WHERE state IN ('queued','author','critic')").fetchall():
        partial = json.loads(result)
        partial['error'] = 'Сервер перезапущен. Автоматического повтора не было.'
        conn.execute("UPDATE jobs SET state='error', result=? WHERE id=?", (json.dumps(partial, ensure_ascii=False), job_id))
    conn.commit()
    conn.close()


init_db()


def build_agents():
    from agno.agent import Agent
    from agno.models.ollama import Ollama

    model = Ollama(
        id=MODEL_ID,
        host=OLLAMA_HOST,
        options={
            "num_ctx": 1024,
            "num_predict": 160,
            "temperature": 0.5,
            "top_p": 0.85,
            "repeat_penalty": 1.08,
        },
    )

    author = Agent(
        model=model,
        name="author",
        instructions=(
            "Ты — автор продукта Kavoikov&CO. "
            "Отвечай на русском. "
            "Главная цель: предложить один быстрый и полезный шаг, который реально улучшает продуктивность пользователя. "
            "Не придумывай огромные фичи и не расписывай архитектуру. "
            "Не говори о том, что ещё невозможно сделать. "
            "Дай 1 конкретный шаг: что сделать, зачем это полезно и как быстро проверить результат. "
            "Формат: 2 коротких предложения, максимум 50–80 слов. "
            "Это должна быть идея для реального пользователя, а не абстрактный план."
        ),
        additional_context=(
            "Ты работаешь в продукте, который помогает человеку быстро сохранять голосовые мысли, "
            "потом превращать их в заметки, задачи и план действий. "
            "Ты должен думать как практик: полезно, просто, понятно, быстро в проверке. "
            "Лучший результат — одна маленькая передовая идея, которую можно начать использовать сразу."
        ),
    )

    critic = Agent(
        model=model,
        name="critic",
        instructions=(
            "Ты — критик продукта Kavoikov&CO. "
            "Сначала проверь, что предложил автор, относительно реальной пользы и понятности. "
            "Не придумывай отсутствующие функции. "
            "Если ответ автора логичен, полезен и понятен — скажи, что явного недостатка нет. "
            "Если есть реальная проблема, назови только одно важное улучшение. "
            "Не спорь ради спора. Не выдумывай сложности. "
            "Отвечай коротко, на русском, 1-2 предложения."
        ),
        additional_context=(
            "Смотри на продукт через призму UX, повседневной пользы и скорости освоения. "
            "Если проблема неочевидна — честно скажи, что явного недостатка нет. "
            "Лучшее улучшение — то, которое реально повышает ценность и не усложняет интерфейс."
        ),
    )
    return author, critic


def get_session_context(session_id: str | None, prompt_idea: str, limit: int = 6):
    if not session_id:
        return f"Исходная идея: {prompt_idea}\n\n"

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    row = conn.execute(
        "SELECT id, idea FROM sessions WHERE id = ?",
        (session_id,),
    ).fetchone()
    if row is None:
        conn.close()
        return f"Исходная идея: {prompt_idea}\n\n"

    base_idea = row["idea"]
    recent = conn.execute(
        "SELECT role, content FROM messages WHERE session_id = ? ORDER BY created_at DESC, rowid DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()

    if not recent:
        return f"Исходная идея: {base_idea}\n\nТекущее продолжение: {prompt_idea}\n\n"

    history = "\n".join(
        f"{ {'author': 'Автор', 'critic': 'Критик', 'user': 'Пользователь'}.get(item['role'], item['role'])}: {item['content'][:450]}"
        for item in reversed(recent[:3])
    )
    return (
        f"Исходная идея: {base_idea}\n\n"
        f"Последние реплики в текущей сессии:\n{history}\n\n"
        f"Текущее продолжение: {prompt_idea}\n\n"
    )


def run_discussion(idea: str, session_id: str | None = None, progress=lambda stage, data: None):
    author, critic = build_agents()
    context_block = get_session_context(session_id, idea)

    author_prompt = (
        f"{context_block}"
        "Сформулируй один быстрый и практичный следующий шаг для этой идеи. "
        "Твоя задача — предложить действие, которое можно начать сразу и проверить в течение дня. "
        "Не придумывай сложную систему и не описывай весь продукт целиком. "
        "Сделай ответ полезным и понятным для обычного пользователя. "
        "Формат: 2 коротких предложения, без списка, без вводных слов, без лишней воды."
    )
    progress("author", {})
    author_started = time.perf_counter()
    author_result = author.run(author_prompt)
    author_seconds = time.perf_counter() - author_started
    author_content = sanitize_text(getattr(author_result, "content", "") or "")
    if not author_content:
        author_content = "Сделайте первый шаг максимально простым: зафиксируйте идею и проверьте, что она действительно решает одну реальную задачу."

    partial = {"author": {"content": author_content, "time_sec": round(author_seconds, 3)}}
    progress("critic", partial)
    critic_prompt = (
        f"{context_block}"
        f"Ответ автора: {author_content}\n\n"
        "Оцени этот ответ как критик продукта. "
        "Если ответ автора полезен, понятен и реалистичен — ответь: 'Явного недостатка нет'. "
        "Если есть реальная проблема, предложи одно конкретное улучшение. "
        "Не выдумывай функции и не спорь ради спора. "
        "Дай один короткий вывод на русском."
    )
    critic_started = time.perf_counter()
    critic_result = critic.run(critic_prompt)
    critic_seconds = time.perf_counter() - critic_started
    critic_content = sanitize_text(getattr(critic_result, "content", "") or "")
    if not critic_content:
        critic_content = "Явного недостатка нет. Ответ автора достаточно практичен и понятен для первого шага."

    return {
        "author": {"content": author_content, "time_sec": round(author_seconds, 3)},
        "critic": {"content": critic_content, "time_sec": round(critic_seconds, 3)},
    }


def save_discussion(idea: str, data: dict, session_id: str | None = None):
    now = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    conn = sqlite3.connect(DB_PATH)
    if session_id:
        existing = conn.execute(
            "SELECT id FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if existing is None:
            session_id = None

    if session_id is None:
        session_id = uuid.uuid4().hex
        conn.execute(
            "INSERT INTO sessions (id, idea, created_at) VALUES (?, ?, ?)",
            (session_id, idea, now),
        )

    conn.execute("INSERT INTO messages VALUES (?, ?, ?, ?, ?)",
                 (uuid.uuid4().hex, session_id, "user", idea, now))
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, session_id, "author", data["author"]["content"], now),
    )
    conn.execute(
        "INSERT INTO messages (id, session_id, role, content, created_at) VALUES (?, ?, ?, ?, ?)",
        (uuid.uuid4().hex, session_id, "critic", data["critic"]["content"], now),
    )
    conn.commit()
    conn.close()
    return session_id


def fetch_history():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    rows = conn.execute(
        "SELECT id, idea, created_at FROM sessions ORDER BY created_at DESC"
    ).fetchall()
    items = []
    for row in rows:
        msgs = conn.execute(
            "SELECT role, content, created_at FROM messages WHERE session_id = ? ORDER BY created_at ASC, rowid ASC",
            (row["id"],),
        ).fetchall()
        items.append({
            "id": row["id"],
            "idea": row["idea"],
            "created_at": row["created_at"],
            "messages": [
                {"role": msg["role"], "content": msg["content"], "created_at": msg["created_at"]}
                for msg in msgs
            ],
        })
    conn.close()
    return items


JOB_LOCK = threading.Lock()


def read_job(job_id):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT state, result FROM jobs WHERE id=?", (job_id,)).fetchone()
    return {"job_id": job_id, "state": row[0], **json.loads(row[1])} if row else None


def update_job(job_id, state, data):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("UPDATE jobs SET state=?, result=? WHERE id=?", (state, json.dumps(data, ensure_ascii=False), job_id))


def worker(job_id, idea, session_id):
    partial = {}
    def progress(state, data):
        partial.update(data)
        update_job(job_id, state, partial)
    try:
        result = run_discussion(idea, session_id, progress)
        sid = save_discussion(idea, result, session_id)
        update_job(job_id, "done", {**result, "session_id": sid})
    except Exception as exc:
        print("Discussion failed:", type(exc).__name__, flush=True)
        update_job(job_id, "error", {**partial, "error": "Модель не завершила ответ. Ответ Автора, если получен, сохранён. Проверьте Ollama и журнал сервера."})


class DiscussionHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT), **kwargs)

    def do_GET(self):
        path = urlparse(self.path).path
        if path == "/api/health":
            return self.send_json({"status": "ok"})
        if path == "/api/discussions":
            return self.send_json({"items": fetch_history()})
        if path.startswith("/api/jobs/"):
            job = read_job(path.rsplit("/", 1)[-1])
            return self.send_json(job or {"error": "Задание не найдено"}, 200 if job else 404)
        # Only explicit public assets, never SQLite backups or directory listings.
        if path not in ("/", "/index.html", "/sw.js", "/app.js", "/manifest.webmanifest", "/icon.svg", "/icon-180.png", "/icon-192.png", "/icon-512.png"):
            return self.send_error(404)
        super().do_GET()

    def do_HEAD(self):
        if urlparse(self.path).path not in ("/", "/index.html", "/sw.js", "/app.js", "/manifest.webmanifest", "/icon.svg", "/icon-180.png", "/icon-192.png", "/icon-512.png"):
            return self.send_error(404)
        super().do_HEAD()

    def do_POST(self):
        if urlparse(self.path).path != "/api/discussions":
            return self.send_error(404)
        # Browser requests must be same-origin; authentication stays at private Codespaces tunnel.
        origin = self.headers.get("Origin")
        if origin and urlparse(origin).netloc != self.headers.get("Host"):
            return self.send_json({"error": "Недопустимый источник"}, 403)
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 16000:
                raise ValueError()
            data = json.loads(self.rfile.read(length))
            idea = data.get("idea", "").strip()
            job_id = data.get("request_id", "")
            session_id = data.get("session_id") or None
            uuid.UUID(job_id)
            if not idea or len(idea) > 1200 or (session_id and not isinstance(session_id, str)):
                raise ValueError()
        except (ValueError, TypeError, AttributeError):
            return self.send_json({"error": "Нужна идея до 1200 символов и корректный идентификатор запроса"}, 400)
        payload = json.dumps([idea, session_id], ensure_ascii=False)
        with JOB_LOCK, sqlite3.connect(DB_PATH) as conn:
            previous = conn.execute("SELECT payload FROM jobs WHERE id=?", (job_id,)).fetchone()
            if previous:
                if previous[0] != payload:
                    return self.send_json({"error": "Идентификатор уже используется"}, 409)
                return self.send_json(read_job(job_id), 200)
            if session_id and not conn.execute("SELECT 1 FROM sessions WHERE id=?", (session_id,)).fetchone():
                return self.send_json({"error": "Сессия не найдена"}, 404)
            if conn.execute("SELECT 1 FROM jobs WHERE state IN ('queued','author','critic')").fetchone():
                return self.send_json({"error": "Команда уже отвечает. Дождитесь завершения."}, 409)
            conn.execute("INSERT INTO jobs VALUES (?, ?, 'queued', '{}')", (job_id, payload))
            conn.commit()
            threading.Thread(target=worker, args=(job_id, idea, session_id), daemon=True).start()
        return self.send_json({"job_id": job_id, "state": "queued"}, 202)

    def end_headers(self):
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
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
    httpd = ThreadingHTTPServer(("0.0.0.0", PORT), DiscussionHandler)
    print(f"Serving Kavoikov&CO on port {PORT}", flush=True)
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
