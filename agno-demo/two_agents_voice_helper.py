import time
from agno.agent import Agent
from agno.models.ollama import Ollama

OLLAMA_HOST = "http://127.0.0.1:11434"
MODEL_ID = "qwen2.5:1.5b"

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

author_agent = Agent(
    model=model,
    name="author",
    instructions=(
        "Ты — автор продукта Kavoikov&CO. "
        "Отвечай на русском. "
        "Дай один конкретный шаг, который можно начать уже сегодня. "
        "Не описывай весь продукт целиком. "
        "Не выдумывай крупные фичи. "
        "Сделай ответ коротким, понятным и полезным для реального пользователя."
    ),
    additional_context=(
        "Ты создаёшь идею для продукта, который помогает сохранять голосовые мысли, "
        "превращать их в заметки и задачи, и поддерживать ясность в работе. "
        "Лучший ответ — это полезный, маленький, проверяемый шаг, который реально решает повседневную проблему."
    ),
)

critic_agent = Agent(
    model=model,
    name="critic",
    instructions=(
        "Ты — критик продукта Kavoikov&CO. "
        "Оцени идею конструктивно, коротко и на русском. "
        "Если идея полезна и понятна, скажи: 'Явного недостатка нет'. "
        "Если есть реальная проблема, предложи одно конкретное улучшение."
    ),
    additional_context=(
        "Смотри на идею через призму UX, полезности и простоты. "
        "Не придумывай отсутствующие функции и не спорь ради спора. "
        "Лучшее улучшение — то, что сразу повышает ценность продукта без лишней сложности."
    ),
)

def run_with_timer(label: str, agent: Agent, prompt: str):
    start = time.perf_counter()
    result = agent.run(prompt)
    elapsed = time.perf_counter() - start
    print(f"[{label}] STATUS: {result.status}")
    print(f"[{label}] TIME_SEC: {elapsed:.3f}")
    print(f"[{label}] RESPONSE: {result.content}")
    print("-" * 80)
    return result, elapsed

author_prompt = (
    "Предложи одну идею Telegram-помощника для сохранения голосовых мыслей. "
    "Сделай решение простым, полезным и понятным для обычного пользователя."
)
author_response, author_time = run_with_timer("AUTHOR", author_agent, author_prompt)

critic_prompt = (
    f"Вот идея автора: {author_response.content}\n\n"
    "Как критик, оцени эту идею и предложи одно улучшение, которое сделает её лучше. "
    "Отвечай коротко и по делу."
)
critic_response, critic_time = run_with_timer("CRITIC", critic_agent, critic_prompt)

print(f"AUTHOR_TIME_SEC: {author_time:.3f}")
print(f"CRITIC_TIME_SEC: {critic_time:.3f}")
