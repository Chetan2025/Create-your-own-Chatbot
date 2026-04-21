# Create Your Own Chatbot

A document-aware chatbot project built with:
- FastAPI backend
- Streamlit frontend
- FAISS vector store
- Hugging Face sentence embeddings
- Ollama (Mistral) for LLM responses

## Features
- Upload PDF and DOCX files
- Auto chunking and embedding generation
- Per-chatbot vector index storage
- API key based chatbot ownership check
- Ask questions from uploaded document context
- Async backend endpoint for better concurrent request handling

## Project Structure

```text
backend/
  app.py                # FastAPI API server
frentend/
  main.py               # Streamlit UI
requirements.txt        # Python dependencies
db/
  chatbots.json         # Chatbot ownership map (runtime)
  <chatbot-id>/         # FAISS index folders (runtime)
```

## Prerequisites
- Python 3.10+
- Ollama installed and running locally
- Mistral model available in Ollama

## Setup

1. Create and activate virtual environment:

```powershell
python -m venv venv
& ".\\venv\\Scripts\\Activate.ps1"
```

2. Install dependencies:

```powershell
pip install -r requirements.txt
```

3. Start Ollama model in another terminal:

```powershell
ollama run mistral
```

## Run

Open 2 terminals in project root.

1. Start backend:

```powershell
& ".\\venv\\Scripts\\Activate.ps1"
uvicorn backend.app:app --reload
```

2. Start frontend:

```powershell
& ".\\venv\\Scripts\\Activate.ps1"
streamlit run frentend\\main.py
```

## API Endpoints

### Register Chatbot
`POST /api/register-chatbot`

Request body:

```json
{
  "chatbot_id": "string",
  "api_key": "string"
}
```

### Chat
`POST /api/chat`

Request body:

```json
{
  "query": "What is this document about?",
  "chatbot_id": "string",
  "api_key": "string"
}
```

## Notes
- Keep the generated API key private.
- The `db/` content is runtime data and should not be committed.
- If model response is slow, keep Ollama warm and reduce prompt/query size.

## License
For personal and educational use.
