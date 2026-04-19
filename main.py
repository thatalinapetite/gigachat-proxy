from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx, base64, time, os, uuid

app = FastAPI()
_cache = {"token": None, "exp": 0}
AUTH_KEY = os.environ["GC_AUTH_KEY"]
TG_TOKEN = os.environ.get("TG_TOKEN", "")
DIFY_KEY = os.environ.get("DIFY_KEY", "")

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

# GigaChat прокси
@app.post("/v1/{path:path}")
async def proxy(path: str, request: Request):
    body = await request.json()
    r = httpx.post(
        f"https://gigachat.devices.sberbank.ru/api/v1/{path}",
        headers={"Authorization": f"Bearer {get_token()}"},
        json=body, verify=False, timeout=60
    )
    return JSONResponse(r.json())

# Telegram webhook
@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()
    if "message" not in data:
        return {"ok": True}
    text = data["message"].get("text", "")
    chat_id = data["message"]["chat"]["id"]
    if not text:
        return {"ok": True}

    # Печатает...
    httpx.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendChatAction",
        json={"chat_id": chat_id, "action": "typing"}
    )

    # Спрашиваем Dify
    r = httpx.post(
        "https://api.dify.ai/v1/chat-messages",
        headers={"Authorization": f"Bearer {DIFY_KEY}"},
        json={
            "inputs": {},
            "query": text,
            "response_mode": "blocking",
            "user": str(chat_id)
        },
        timeout=60
    )
    answer = r.json().get("answer", "Произошла ошибка, попробуйте позже.")

    # Отвечаем
    httpx.post(
        f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage",
        json={
            "chat_id": chat_id,
            "text": answer,
            "reply_to_message_id": data["message"]["message_id"]
        }
    )
    return {"ok": True}
