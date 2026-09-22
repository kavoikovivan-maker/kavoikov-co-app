# K&C Telegram Agent

Telegram-бот K&C.agent использует Telegram Bot API и Groq.

## Переменные окружения

Создайте локальный `.env`:

- `TELEGRAM_BOT_TOKEN`
- `GROQ_API_KEY`
- необязательно `GROQ_MODEL`

Никогда не коммитьте настоящий `.env` с секретами.

## Запуск

```bash
python3 -m pip install -r requirements.txt
python3 bot.py
```

Команды Telegram:

- `/start` — проверка подключения
- `/reset` — очистить контекст чата
