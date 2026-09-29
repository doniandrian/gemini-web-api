import os
import time
import uuid
import json
import asyncio
from typing import Any
from contextlib import asynccontextmanager
from dotenv import load_dotenv
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse, StreamingResponse
from gemini_webapi import GeminiClient

# Muat variabel dari .env jika ada
load_dotenv()

# Cookie sesi Gemini Pro (bisa lewat file .env atau langsung di sini)
PSID = os.getenv("GEMINI_SECURE_1PSID", "").strip()
PSIDTS = os.getenv("GEMINI_SECURE_1PSIDTS", "").strip()
DEFAULT_MODEL = os.getenv("DEFAULT_MODEL", "gemini-pro").strip()

client: GeminiClient | None = None
is_client_ready: bool = False


async def ensure_client() -> GeminiClient:
    """Memastikan client GeminiClient sudah terinisialisasi secara asynchronous."""
    global client, is_client_ready
    if is_client_ready and client:
        return client

    # Muat ulang .env jika sebelumnya kosong
    load_dotenv(override=True)
    psid = os.getenv("GEMINI_SECURE_1PSID", "").strip() or PSID
    psidts = os.getenv("GEMINI_SECURE_1PSIDTS", "").strip() or PSIDTS

    if not psid or psid.startswith("ISI_"):
        raise HTTPException(
            status_code=401,
            detail=(
                "Cookie GEMINI_SECURE_1PSID belum diisi! Silakan salin cookie __Secure-1PSID "
                "dan __Secure-1PSIDTS dari https://gemini.google.com ke file .env"
            ),
        )

    try:
        client = GeminiClient(secure_1psid=psid, secure_1psidts=psidts or None)
        # client.init() wajib di-await karena bersifat async
        await client.init(timeout=60, auto_refresh=True)
        is_client_ready = True
        return client
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Gagal menginisialisasi GeminiClient: {str(e)}",
        )


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Siklus hidup aplikasi FastAPI: inisialisasi saat start, close saat shutdown."""
    global client, is_client_ready
    psid = os.getenv("GEMINI_SECURE_1PSID", "").strip() or PSID
    if not psid or psid.startswith("ISI_"):
        print("[PERINGATAN] Cookie GEMINI_SECURE_1PSID belum diisi di .env!")
        print("[PETUNJUK] Masukkan cookie __Secure-1PSID dan __Secure-1PSIDTS di file .env.")
    else:
        try:
            print("[INFO] Menginisialisasi GeminiClient...")
            await ensure_client()
            print("[INFO] GeminiClient BERHASIL diinisialisasi!")
            models = client.list_models() if client else []
            if models:
                names = [m.model_name for m in models]
                print(f"[INFO] Model Gemini yang tersedia di akun ini: {names}")
        except Exception as e:
            print(f"[ERROR] Gagal inisialisasi Gemini saat startup: {e}")
            print("[PETUNJUK] Server tetap berjalan. Anda bisa memperbaiki cookie di .env lalu coba lagi.")

    yield

    if client:
        try:
            await client.close()
        except Exception:
            pass


app = FastAPI(
    title="Gemini WebAPI OpenAI-Compatible Server",
    description="Bridge Gemini Web ke format OpenAI API (kompatibel dengan Hermes, Chat UI, dll.)",
    lifespan=lifespan,
)


def format_messages(messages: list[dict[str, Any]]) -> str:
    """Format daftar percakapan OpenAI (system, user, assistant) menjadi prompt yang utuh."""
    if not messages:
        return ""

    # Jika hanya ada satu pesan user, kirim langsung
    if len(messages) == 1 and messages[0].get("role") == "user":
        content = messages[0].get("content", "")
        if isinstance(content, list):
            return " ".join(
                [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            )
        return str(content)

    formatted_parts = []
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if isinstance(content, list):
            content = " ".join(
                [c.get("text", "") for c in content if isinstance(c, dict) and c.get("type") == "text"]
            )
        else:
            content = str(content)

        if role == "system":
            formatted_parts.append(f"[System Instructions]\n{content}\n")
        elif role == "user":
            formatted_parts.append(f"User: {content}")
        elif role == "assistant":
            formatted_parts.append(f"Assistant: {content}")
        else:
            formatted_parts.append(f"{role.capitalize()}: {content}")

    return "\n\n".join(formatted_parts)


def resolve_model(requested_model: str | None, gemini: GeminiClient) -> str | None:
    """Mencari model yang cocok di akun Gemini.
    Secara default memilih Gemini Pro sesuai langganan pengguna, kecuali diminta Flash/Lite.
    """
    model_name = (requested_model or DEFAULT_MODEL or "gemini-pro").lower().strip()
    available_registry = getattr(gemini, "_model_registry", {})

    if not available_registry:
        return "gemini-pro"

    # Jika klien secara spesifik meminta model flash / lite
    if "flash" in model_name or "lite" in model_name:
        for m in available_registry.values():
            if "flash" in m.model_name.lower():
                return m.model_name

    # 1. Cek kecocokan langsung dari nama model, display name, atau aliases
    for m in available_registry.values():
        if (
            m.model_name.lower() == model_name
            or m.display_name.lower() == model_name
            or m.model_id.lower() == model_name
            or model_name in m.aliases
        ):
            return m.model_name

    # 2. Utamakan model Pro (karena akun berlangganan Gemini Pro / Advanced)
    for m in available_registry.values():
        if "pro" in m.model_name.lower():
            return m.model_name

    return "gemini-pro"


async def stream_chat_generator(prompt: str, model_arg: str | None, gemini: GeminiClient, chat_id: str, model_name: str):
    """Generator Server-Sent Events (SSE) untuk streaming response standar OpenAI."""
    created = int(time.time())

    # Initial chunk
    first_chunk = {
        "id": chat_id,
        "object": "chat.completion.chunk",
        "created": created,
        "model": model_name,
        "choices": [{
            "index": 0,
            "delta": {"role": "assistant", "content": ""},
            "finish_reason": None,
        }],
    }
    yield f"data: {json.dumps(first_chunk)}\n\n"

    try:
        # temporary=True agar tidak mengotori riwayat chat di gemini.google.com
        async for chunk in gemini.generate_content_stream(prompt, model=model_arg, temporary=True):
            delta = chunk.text_delta or ""
            if delta:
                chunk_data = {
                    "id": chat_id,
                    "object": "chat.completion.chunk",
                    "created": created,
                    "model": model_name,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta},
                        "finish_reason": None,
                    }],
                }
                yield f"data: {json.dumps(chunk_data)}\n\n"

        # Final stop chunk
        stop_chunk = {
            "id": chat_id,
            "object": "chat.completion.chunk",
            "created": created,
            "model": model_name,
            "choices": [{
                "index": 0,
                "delta": {},
                "finish_reason": "stop",
            }],
        }
        yield f"data: {json.dumps(stop_chunk)}\n\n"
        yield "data: [DONE]\n\n"
    except Exception as e:
        err = {"error": {"message": str(e), "type": "gemini_error"}}
        yield f"data: {json.dumps(err)}\n\n"
        yield "data: [DONE]\n\n"


@app.get("/")
async def root():
    return {
        "status": "online",
        "service": "Gemini WebAPI to OpenAI Bridge",
        "is_ready": is_client_ready,
        "default_model": DEFAULT_MODEL,
        "endpoints": {
            "chat_completions": "/v1/chat/completions",
            "models": "/v1/models",
        },
    }


@app.get("/v1/models")
async def list_models():
    """Endpoint /v1/models agar tools seperti Hermes mengenali model yang tersedia."""
    gemini = await ensure_client()
    models = gemini.list_models() or []
    data = []
    for m in models:
        data.append({
            "id": m.model_name,
            "object": "model",
            "created": 1700000000,
            "owned_by": "google",
            "display_name": m.display_name,
        })
    if not data:
        data.append({
            "id": "gemini-pro",
            "object": "model",
            "created": 1700000000,
            "owned_by": "google",
            "display_name": "Gemini Pro",
        })
    return JSONResponse({"object": "list", "data": data})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    data = await request.json()
    messages = data.get("messages", [])
    requested_model = data.get("model")
    stream = data.get("stream", False)

    # Format percakapan lengkap dari Hermes
    prompt = format_messages(messages)
    if not prompt:
        raise HTTPException(status_code=400, detail="Tidak ada pesan (messages) yang dikirim.")

    # Pastikan client aktif
    gemini = await ensure_client()

    # Pilih model (prioritas Gemini Pro dari akun langganan)
    model_arg = resolve_model(requested_model, gemini)
    chat_id = f"chatcmpl-{uuid.uuid4().hex[:12]}"
    model_name_for_response = model_arg or requested_model or DEFAULT_MODEL

    # Jika Hermes meminta streaming
    if stream:
        return StreamingResponse(
            stream_chat_generator(prompt, model_arg, gemini, chat_id, model_name_for_response),
            media_type="text/event-stream",
        )

    # Jika non-streaming: generate_content wajib di-await!
    response = await gemini.generate_content(prompt, model=model_arg, temporary=True)

    content_text = response.text or ""

    # Bungkus balik dalam format OpenAI API agar Hermes paham
    return JSONResponse({
        "id": chat_id,
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model_name_for_response,
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content_text,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": len(prompt.split()),
            "completion_tokens": len(content_text.split()),
            "total_tokens": len(prompt.split()) + len(content_text.split()),
        },
    })


if __name__ == "__main__":
    host = os.getenv("HOST", "127.0.0.1")
    port = int(os.getenv("PORT", 8000))
    print(f"[INFO] Menjalankan server di http://{host}:{port}")
    uvicorn.run("geminiwebapi:app", host=host, port=port, reload=False)