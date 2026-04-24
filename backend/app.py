from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import os
import json
import hashlib
import threading
import shutil
from datetime import datetime, timedelta, timezone
from typing import Optional

from dotenv import load_dotenv
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

app = FastAPI()
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_ROOT = os.path.join(PROJECT_ROOT, "db")
USERS_FILE = os.path.join(DB_ROOT, "users.json")
USAGE_FILE = os.path.join(DB_ROOT, "usage.json")
USER_DATA_ROOT = os.path.join(DB_ROOT, "users")

load_dotenv()

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))
MAX_CONTEXT_CHARS = int(os.getenv("MAX_CONTEXT_CHARS", "3000"))
MAX_FALLBACK_CONTEXT_CHARS = int(os.getenv("MAX_FALLBACK_CONTEXT_CHARS", "1200"))
AUTH_LOCK = threading.Lock()

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


def user_root_path(username: str) -> str:
    return os.path.join(USER_DATA_ROOT, username)


def user_chatbots_root_path(username: str) -> str:
    return os.path.join(user_root_path(username), "chatbots")


def chatbot_vector_path(username: str, chatbot_id: str) -> str:
    return os.path.join(user_chatbots_root_path(username), chatbot_id)


def normalize_chatbot(chatbot) -> Optional[dict]:
    if not isinstance(chatbot, dict):
        return None

    chatbot_id = str(chatbot.get("chatbot_id", "")).strip()
    api_key = str(chatbot.get("api_key", "")).strip()
    if not chatbot_id or not api_key:
        return None

    created_at = chatbot.get("created_at")
    if not created_at:
        created_at = datetime.now(timezone.utc).isoformat()

    return {
        "chatbot_id": chatbot_id,
        "api_key": api_key,
        "name": str(chatbot.get("name") or "Unnamed Bot"),
        "created_at": created_at,
    }


def normalize_user_record(record) -> tuple[dict, bool]:
    changed = False

    if not isinstance(record, dict):
        return {
            "password_hash": "",
            "chatbots": [],
            "active_chatbot_id": None,
        }, True

    normalized = {
        "password_hash": str(record.get("password_hash") or ""),
        "chatbots": [],
        "active_chatbot_id": record.get("active_chatbot_id"),
    }

    raw_chatbots = record.get("chatbots")
    if isinstance(raw_chatbots, list):
        for bot in raw_chatbots:
            clean_bot = normalize_chatbot(bot)
            if clean_bot:
                normalized["chatbots"].append(clean_bot)

    legacy_chatbot = record.get("chatbot")
    legacy_clean = normalize_chatbot(legacy_chatbot)
    if legacy_clean and not any(
        bot.get("chatbot_id") == legacy_clean["chatbot_id"]
        for bot in normalized["chatbots"]
    ):
        normalized["chatbots"].append(legacy_clean)
        changed = True

    if normalized["active_chatbot_id"] and not any(
        bot.get("chatbot_id") == normalized["active_chatbot_id"]
        for bot in normalized["chatbots"]
    ):
        normalized["active_chatbot_id"] = None
        changed = True

    if not normalized["active_chatbot_id"] and normalized["chatbots"]:
        normalized["active_chatbot_id"] = normalized["chatbots"][-1]["chatbot_id"]
        changed = True

    expected_keys = {"password_hash", "chatbots", "active_chatbot_id"}
    if set(record.keys()) != expected_keys:
        changed = True

    return normalized, changed


def load_users():
    if not os.path.exists(USERS_FILE):
        return {}

    try:
        with open(USERS_FILE, "r", encoding="utf-8") as f:
            users = json.load(f)
    except Exception:
        return {}

    if not isinstance(users, dict):
        return {}

    changed = False
    for username, record in users.items():
        normalized, record_changed = normalize_user_record(record)
        users[username] = normalized
        if record_changed:
            changed = True

    if changed:
        save_users(users)

    return users


def save_users(users):
    os.makedirs(DB_ROOT, exist_ok=True)
    with open(USERS_FILE, "w", encoding="utf-8") as f:
        json.dump(users, f, indent=4)
        f.write("\n")


def get_user_chatbots(users, username: str) -> list[dict]:
    user = users.get(username, {})
    if not isinstance(user, dict):
        return []

    chatbots = user.get("chatbots", [])
    return [bot for bot in chatbots if isinstance(bot, dict)]


def get_user_active_chatbot(users, username: str):
    user = users.get(username, {})
    if not isinstance(user, dict):
        return None

    active_id = user.get("active_chatbot_id")
    for chatbot in get_user_chatbots(users, username):
        if chatbot.get("chatbot_id") == active_id:
            return chatbot

    chatbots = get_user_chatbots(users, username)
    if chatbots:
        return chatbots[0]

    return None


def find_chatbot_owner(users, chatbot_id: str):
    for username, user in users.items():
        if not isinstance(user, dict):
            continue

        for chatbot in get_user_chatbots(users, username):
            if chatbot.get("chatbot_id") == chatbot_id:
                return username, chatbot

    return None, None


def resolve_chatbot_vector_path(username: str, chatbot_id: str) -> Optional[str]:
    organized_path = chatbot_vector_path(username, chatbot_id)
    if os.path.exists(organized_path):
        return organized_path

    legacy_path = os.path.join(DB_ROOT, chatbot_id)
    if os.path.exists(legacy_path):
        return legacy_path

    return None


def ensure_user_chatbot_folder(username: str, chatbot_id: str):
    os.makedirs(user_chatbots_root_path(username), exist_ok=True)

    target_path = chatbot_vector_path(username, chatbot_id)
    legacy_path = os.path.join(DB_ROOT, chatbot_id)

    if os.path.exists(target_path):
        return

    if os.path.exists(legacy_path):
        shutil.move(legacy_path, target_path)
        return

    os.makedirs(target_path, exist_ok=True)


def load_usage():
    if not os.path.exists(USAGE_FILE):
        return {}

    try:
        with open(USAGE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_usage(usage):
    os.makedirs(DB_ROOT, exist_ok=True)
    with open(USAGE_FILE, "w", encoding="utf-8") as f:
        json.dump(usage, f, indent=4)
        f.write("\n")


def verify_chatbot_access(chatbot_id: str, api_key: str):
    users = load_users()
    owner_username, owner = find_chatbot_owner(users, chatbot_id)

    if not owner:
        return False, JSONResponse(
            status_code=404,
            content={"error": "Invalid chatbot_id"},
        ), None, None

    if owner.get("api_key") != api_key:
        return False, JSONResponse(
            status_code=403,
            content={"error": "Unauthorized: invalid api_key for this chatbot"},
        ), None, None

    return True, None, owner_username, owner


def log_api_call(chatbot_id: str):
    usage = load_usage()
    records = usage.get(chatbot_id, [])
    records.append(datetime.now(timezone.utc).isoformat())
    usage[chatbot_id] = records
    save_usage(usage)


def trim_context(text: str, limit: int) -> str:
    clean_text = " ".join(text.split())
    if len(clean_text) <= limit:
        return clean_text
    return clean_text[:limit].rsplit(" ", 1)[0]


def build_prompt(context: str, question: str) -> str:
    return f"""
    You are a strict AI assistant.

    Rules:
    - Answer only from the context
    - If not found say "I don't know"
    - Keep answer clear and short

    Context:
    {context}

    Question:
    {question}
    """


async def call_ollama(prompt: str):
    async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
        return await client.post(
            OLLAMA_URL,
            json={
                "model": "mistral:latest",
                "prompt": prompt,
                "stream": False,
                "keep_alive": "10m",
                "options": {
                    "temperature": 0.2,
                    "num_ctx": 2048,
                },
            },
        )


class Message(BaseModel):
    query: str
    chatbot_id: str
    api_key: str


class ChatbotRegistration(BaseModel):
    chatbot_id: str
    api_key: str
    name: str = "Unnamed Bot"
    username: str = ""


class UserRegister(BaseModel):
    username: str
    password: str


class UserLogin(BaseModel):
    username: str
    password: str


class UsageManage(BaseModel):
    chatbot_id: str
    api_key: str


def password_hash(raw_password: str) -> str:
    return hashlib.sha256(raw_password.encode("utf-8")).hexdigest()


@app.post("/api/register-user")
async def register_user(data: UserRegister):
    username = data.username.strip()
    if len(username) < 3:
        return JSONResponse(
            status_code=400,
            content={"error": "Username must be at least 3 characters"},
        )
    if len(data.password) < 4:
        return JSONResponse(
            status_code=400,
            content={"error": "Password must be at least 4 characters"},
        )

    with AUTH_LOCK:
        users = load_users()
        if username in users:
            return JSONResponse(
                status_code=409,
                content={"error": "Username already exists"},
            )

        users[username] = {
            "password_hash": password_hash(data.password),
            "chatbots": [],
            "active_chatbot_id": None,
        }
        save_users(users)

    os.makedirs(user_chatbots_root_path(username), exist_ok=True)

    return {"ok": True, "username": username}


@app.post("/api/login-user")
async def login_user(data: UserLogin):
    username = data.username.strip()
    users = load_users()
    user = users.get(username)

    if not user:
        return JSONResponse(
            status_code=404,
            content={"error": "User not found"},
        )

    if user.get("password_hash") != password_hash(data.password):
        return JSONResponse(
            status_code=401,
            content={"error": "Invalid password"},
        )

    active_chatbot = get_user_active_chatbot(users, username)
    chatbots = get_user_chatbots(users, username)

    return {
        "ok": True,
        "username": username,
        "active_chatbot": active_chatbot,
        "chatbots": chatbots,
    }

# connects to db and registers chatbot ownership in database db
@app.post("/api/register-chatbot")
async def register_chatbot(data: ChatbotRegistration):
    os.makedirs(DB_ROOT, exist_ok=True)
    created_at = datetime.now(timezone.utc).isoformat()

    username = data.username.strip()
    if not username:
        return JSONResponse(
            status_code=400,
            content={"error": "username is required"},
        )

    users = load_users()
    user = users.get(username)
    if user is None:
        users[username] = {
            "password_hash": "",
            "chatbots": [],
            "active_chatbot_id": None,
        }
        user = users[username]

    owner_username, _ = find_chatbot_owner(users, data.chatbot_id)
    if owner_username and owner_username != username:
        return JSONResponse(
            status_code=409,
            content={"error": "chatbot_id already registered by another user"},
        )

    chatbots = get_user_chatbots(users, username)
    chatbot_payload = {
        "chatbot_id": data.chatbot_id,
        "api_key": data.api_key,
        "name": data.name,
        "created_at": created_at,
    }

    updated = False
    for index, bot in enumerate(chatbots):
        if bot.get("chatbot_id") == data.chatbot_id:
            chatbots[index] = {
                **bot,
                "api_key": data.api_key,
                "name": data.name,
            }
            updated = True
            break

    if not updated:
        chatbots.append(chatbot_payload)

    users[username]["chatbots"] = chatbots
    users[username]["active_chatbot_id"] = data.chatbot_id
    save_users(users)

    ensure_user_chatbot_folder(username, data.chatbot_id)

    return {"ok": True, "name": data.name, "chatbot_id": data.chatbot_id}

# this is main logic for handling client queries
@app.post("/api/chat")  
async def chat(data: Message):
    ok, error_response, owner_username, _ = verify_chatbot_access(data.chatbot_id, data.api_key)
    if not ok:
        return error_response

    db_path = resolve_chatbot_vector_path(owner_username, data.chatbot_id)

    if not db_path or not os.path.exists(db_path):
        return JSONResponse(
            status_code=404,
            content={"error": "Invalid chatbot_id or chatbot not found"},
        )

    try:
        vector_db = FAISS.load_local(
            db_path,
            embeddings,
            allow_dangerous_deserialization=True,
        )
    except Exception as e:
        return JSONResponse(
            status_code=400,
            content={"error": f"Failed to load chatbot DB: {str(e)}"},
        )

    retriever = vector_db.as_retriever(search_kwargs={"k": 3})
    docs = retriever.invoke(data.query)
    raw_context = "\n\n".join([doc.page_content for doc in docs])
    context = trim_context(raw_context, MAX_CONTEXT_CHARS)
    log_api_call(data.chatbot_id)

    prompt = build_prompt(context, data.query)

    try:
        response = await call_ollama(prompt)
        if response.status_code != 200:
            fallback_context = trim_context(raw_context, MAX_FALLBACK_CONTEXT_CHARS)
            if fallback_context != context:
                fallback_response = await call_ollama(build_prompt(fallback_context, data.query))
                if fallback_response.status_code == 200:
                    fallback_result = fallback_response.json()
                    fallback_answer = fallback_result.get("response", "No response")
                    return {"response": fallback_answer}

                fallback_error = fallback_response.text.strip()
                if not fallback_error:
                    fallback_error = f"Ollama returned HTTP {fallback_response.status_code}"
                return JSONResponse(
                    status_code=502,
                    content={"error": fallback_error},
                )

            error_text = response.text.strip()
            if not error_text:
                error_text = f"Ollama returned HTTP {response.status_code}"
            return JSONResponse(
                status_code=502,
                content={"error": error_text},
            )

        result = response.json()
        answer = result.get("response", "No response")
        return {"response": answer}

    except httpx.TimeoutException:
        return JSONResponse(
            status_code=504,
            content={
                "error": (
                    f"LLM timeout after {OLLAMA_TIMEOUT}s. "
                    "Try again, reduce query size, or keep Ollama model warm."
                )
            },
        )

    except httpx.RequestError as e:
        return JSONResponse(
            status_code=503,
            content={"error": f"LLM service unavailable (Ollama): {str(e)}"},
        )

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": f"Error: {str(e)}"},
        )


@app.post("/api/generate")
async def generate_compat(data: Message):
    return await chat(data)


@app.post("/api/usage-report")
async def usage_report(data: UsageManage):
    ok, error_response, _, _ = verify_chatbot_access(data.chatbot_id, data.api_key)
    if not ok:
        return error_response

    usage = load_usage()
    records = usage.get(data.chatbot_id, [])

    now = datetime.now(timezone.utc)
    last_24h_cutoff = now - timedelta(hours=24)
    last_7d_cutoff = now - timedelta(days=7)

    last_24h = 0
    last_7d = 0

    for ts in records:
        try:
            dt = datetime.fromisoformat(ts)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if dt >= last_24h_cutoff:
                last_24h += 1
            if dt >= last_7d_cutoff:
                last_7d += 1
        except Exception:
            continue

    return {
        "chatbot_id": data.chatbot_id,
        "last_24_hours_calls": last_24h,
        "last_7_days_calls": last_7d,
        "total_calls": len(records),
    }


@app.delete("/api/usage-clear")
async def clear_usage(data: UsageManage):
    ok, error_response, _, _ = verify_chatbot_access(data.chatbot_id, data.api_key)
    if not ok:
        return error_response

    usage = load_usage()
    deleted_count = len(usage.get(data.chatbot_id, []))

    if data.chatbot_id in usage:
        del usage[data.chatbot_id]
        save_usage(usage)

    return {
        "ok": True,
        "chatbot_id": data.chatbot_id,
        "deleted_records": deleted_count,
    }


@app.delete("/api/delete-chatbot")
async def delete_chatbot(data: UsageManage):
    ok, error_response, owner_username, _ = verify_chatbot_access(data.chatbot_id, data.api_key)
    if not ok:
        return error_response

    organized_path = chatbot_vector_path(owner_username, data.chatbot_id)
    legacy_path = os.path.join(DB_ROOT, data.chatbot_id)

    if os.path.exists(organized_path):
        shutil.rmtree(organized_path, ignore_errors=True)

    if os.path.exists(legacy_path):
        shutil.rmtree(legacy_path, ignore_errors=True)

    usage = load_usage()
    if data.chatbot_id in usage:
        del usage[data.chatbot_id]
        save_usage(usage)

    users = load_users()
    if owner_username:
        chatbots = [
            bot
            for bot in get_user_chatbots(users, owner_username)
            if bot.get("chatbot_id") != data.chatbot_id
        ]
        users[owner_username]["chatbots"] = chatbots

        active_chatbot_id = users[owner_username].get("active_chatbot_id")
        if active_chatbot_id == data.chatbot_id:
            users[owner_username]["active_chatbot_id"] = (
                chatbots[0].get("chatbot_id") if chatbots else None
            )

        save_users(users)

    return {
        "ok": True,
        "chatbot_id": data.chatbot_id,
        "message": "Chatbot and records deleted from backend",
    }