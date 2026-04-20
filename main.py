from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx, time, os, uuid

app = FastAPI()
_cache = {"token": None, "exp": 0}
AUTH_KEY = os.environ["GC_AUTH_KEY"]
TG_TOKEN = os.environ.get("TG_TOKEN", "")
DIFY_KEY = os.environ.get("DIFY_KEY", "")

conversations = {}

def get_token():
    if time.time() < _cache["exp"] - 60:
        return _cache["token"]
    r = httpx.post(
        "https://ngw.devices.sberbank.ru:9443/api/v2/oauth",
        headers={
            "Authorization": f"Basic {AUTH_KEY}",
            "RqUID": str(uuid.uuid4()),
            "Content-Type": "application/x-www-form-urlencoded"
        },
        data={"scope": "GIGACHAT_API_PERS"},
        verify=False
    )
    data = r.json()
    _cache["token"] = data["access_token"]
    _cache["exp"] = data["expires_at"] / 1000
    return _cache["token"]

def send_message(chat_id, text):
    return httpx.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    ).json()

def edit_message(chat_id, message_id, text):
    httpx.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/editMessageText",
        json={"chat_id": chat_id, "message_id": message_id, "text": text}
    )

def send_typing(chat_id):
    httpx.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"}
    )

@app.post("/v1/{path:path}")
async def proxy(path: str, request: Request):
    body = await request.json()
    r = httpx.post(
        f"https://gigachat.devices.sberbank.ru/api/v1/{path}",
        headers={"Authorization": f"Bearer {get_token()}"},
        json=body, verify=False, timeout=60
    )
    return JSONResponse(r.json())

@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" not in data:
        return {"ok": True}

    text = data["message"].get("text", "")
    chat_id = data["message"]["chat"]["id"]
    user_id = str(chat_id)

    if not text:
        return {"ok": True}

    # /start
    if text == "/start":
        conversations.pop(user_id, None)
        send_message(chat_id,
            "Добрый день! Я Лара — HR-ассистент компании ТехКорп.\n\n"
            "Помогу разобраться с вопросами по:\n"
            "📅 Отпускам — оформление, сроки, разделение\n"
            "🏥 ДМС — покрытие, как воспользоваться\n"
            "✈️ Командировкам — суточные, лимиты, отчётность\n\n"
            "Просто напишите свой вопрос!\n\n"
            "📋 /help — список тем\n"
            "📞 /contacts — контакты HR\n"
            "🔄 /reset — сбросить диалог"
        )
        return {"ok": True}

    # /help
    if text == "/help":
        send_message(chat_id,
            "Я могу помочь с:\n\n"
            "📅 Отпуск:\n"
            "— Сколько дней отпуска положено?\n"
            "— Как оформить отпуск?\n"
            "— Можно разделить отпуск?\n\n"
            "🏥 ДМС:\n"
            "— Что покрывает страховка?\n"
            "— Как записаться к врачу?\n\n"
            "✈️ Командировки:\n"
            "— Какие суточные?\n"
            "— Лимиты на гостиницу?\n\n"
            "🔄 /reset — сбросить историю диалога\n"
            "📞 /contacts — контакты HR-отдела"
        )
        return {"ok": True}

    # /reset
    if text == "/reset":
        conversations.pop(user_id, None)
        send_message(chat_id, "🔄 История диалога сброшена. Начнём заново!")
        return {"ok": True}

    # /contacts
    if text == "/contacts":
        send_message(chat_id,
            "📞 Контакты HR-отдела ТехКорп:\n\n"
            "📧 Email: hr@techcorp.ru\n"
            "☎️ Телефон: 101 (внутренний)\n"
            "🕐 Режим работы: пн-пт 9:00-18:00"
        )
        return {"ok": True}

    # Обычное сообщение
    send_typing(chat_id)

    # Индикатор загрузки
    loading = send_message(chat_id, "⏳ Ищу в регламенте...")
    loading_id = loading["result"]["message_id"]

    conv_id = conversations.get(user_id, "")

    try:
        r = httpx.post(
            "https://api.dify.ai/v1/chat-messages",
            headers={"Authorization": f"Bearer {DIFY_KEY}"},
            json={
                "inputs": {},
                "query": text,
                "response_mode": "blocking",
                "conversation_id": conv_id,
                "user": f"tg_{user_id}"
            },
            timeout=60
        )
        result = r.json()
        answer = result.get("answer", "Извините, не удалось обработать запрос. Обратитесь: hr@techcorp.ru / тел. 101.")

        new_conv_id = result.get("conversation_id", "")
        if new_conv_id:
            conversations[user_id] = new_conv_id

    except Exception:
        answer = "Извините, не удалось обработать запрос. Попробуйте позже или обратитесь: hr@techcorp.ru / тел. 101."

    # Заменяем индикатор на ответ
    edit_message(chat_id, loading_id, answer)
    return {"ok": True}
