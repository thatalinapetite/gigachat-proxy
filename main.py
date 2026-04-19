from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
import httpx, time, os, uuid

app = FastAPI()
_cache = {"token": None, "exp": 0}
AUTH_KEY = os.environ["GC_AUTH_KEY"]

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

@app.post("/v1/{path:path}")
async def proxy(path: str, request: Request):
    body = await request.json()
    r = httpx.post(
        f"https://gigachat.devices.sberbank.ru/api/v1/{path}",
        headers={"Authorization": f"Bearer {get_token()}"},
        json=body,
        verify=False,
        timeout=60
    )
    return JSONResponse(r.json())
