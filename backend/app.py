from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx
import os
import json
import asyncio
from langchain_community.vectorstores import FAISS
from langchain_community.embeddings import HuggingFaceEmbeddings

app = FastAPI()
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DB_ROOT = os.path.join(PROJECT_ROOT, "db")
INDEX_FILE = os.path.join(DB_ROOT, "chatbots.json")
OLLAMA_URL = os.getenv("OLLAMA_URL", "http://localhost:11434/api/generate")
OLLAMA_TIMEOUT = int(os.getenv("OLLAMA_TIMEOUT", "180"))

embeddings = HuggingFaceEmbeddings(
    model_name="sentence-transformers/all-MiniLM-L6-v2"
)


def load_index():
    if not os.path.exists(INDEX_FILE):
        return {}

    try:
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


class Message(BaseModel):
    query: str
    chatbot_id: str
    api_key: str


class ChatbotRegistration(BaseModel):
    chatbot_id: str
    api_key: str

# connects to db and registers chatbot ownership in database db
@app.post("/api/register-chatbot")
async def register_chatbot(data: ChatbotRegistration):
    os.makedirs(DB_ROOT, exist_ok=True)
    index = load_index()
    index[data.chatbot_id] = {"api_key": data.api_key}
    # add in db - chatbots.json file
    with open(INDEX_FILE, "w", encoding="utf-8") as f: 
        json.dump(index, f, indent=4)
        f.write("\n")

    return {"ok": True}

# this is main logic for handling client queries
@app.post("/api/chat")  
async def chat(data: Message):
    index = load_index()
    owner = index.get(data.chatbot_id)

    if not owner:
        return JSONResponse(
            status_code=404,
            content={"error": "Invalid chatbot_id"},
        )

    if owner.get("api_key") != data.api_key:
        return JSONResponse(
            status_code=403,
            content={"error": "Unauthorized: invalid api_key for this chatbot"},
        )

    db_path = os.path.join(DB_ROOT, data.chatbot_id)

    if not os.path.exists(db_path):
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
    context = "\n\n".join([doc.page_content for doc in docs])

    prompt = f"""
    You are a strict AI assistant.

    Rules:
    - Answer only from the context
    - If not found say "I don't know"
    - Keep answer clear

    Context:
    {context}

    Question:
    {data.query}
    """

    try:
        async with httpx.AsyncClient(timeout=OLLAMA_TIMEOUT) as client:
            response = await client.post(
                OLLAMA_URL,
                json={
                    "model": "mistral",
                    "prompt": prompt,
                    "stream": False
                },
            )
            response.raise_for_status()
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
def generate_compat(data: Message):
    return chat(data)