#ollama run mistral
# to stop the model : taskkill /IM ollama.exe /F
# run the streamlit : # python -m  streamlit run main.py
# uvicorn backend.app:app --reload


import streamlit as st
import tempfile
import uuid
import os
import json
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
import requests

API_URL = "http://127.0.0.1:8000/api/chat"
REGISTER_API_URL = "http://127.0.0.1:8000/api/register-chatbot"
PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))

st.title("📄 PDF Chatbot")

# ✅ session state init
if "ready" not in st.session_state:
    st.session_state.ready = False

if "chatbot_id" not in st.session_state:
    st.session_state.chatbot_id = None

if "api_key" not in st.session_state:
    st.session_state.api_key = str(uuid.uuid4())

st.caption(f"Your API Key: {st.session_state.api_key}")


# 📂 File uploader
uploaded_files = st.file_uploader(
    "Upload multiple files",
    accept_multiple_files=True
)

# 🚀 Create chatbot button
if st.button("Create Chatbot"):

    if uploaded_files and len(uploaded_files) > 0:

        all_docs = []

        st.success(f"{len(uploaded_files)} files uploaded ✅")
        st.write("⏳ Processing documents...")

        for file in uploaded_files:
            suffix = file.name.split(".")[-1]

            with tempfile.NamedTemporaryFile(delete=False, suffix=f".{suffix}") as tmp_file:
                tmp_file.write(file.read())
                temp_path = tmp_file.name

            if suffix == "pdf":
                loader = PyPDFLoader(temp_path)
            elif suffix == "docx":
                loader = Docx2txtLoader(temp_path)
            else:
                st.warning(f"Unsupported file: {file.name}")
                continue
                
            

            docs = loader.load()
            all_docs.extend(docs)
        if not all_docs:
            st.error("No valid documents loaded. Please upload PDF or DOCX files.")
            st.stop()

        # ✂️ Chunking
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=500,
            chunk_overlap=50
        )

        chunks = splitter.split_documents(all_docs)

        # 🔢 Embeddings
        embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )

        # 🗃️ Vector DB
        vector_db = FAISS.from_documents(chunks, embeddings)

        chatbot_id = str(uuid.uuid4())
        base_db_dir = os.path.join(PROJECT_ROOT, "db")
        db_dir = os.path.join(base_db_dir, chatbot_id)
        os.makedirs(base_db_dir, exist_ok=True)
        vector_db.save_local(db_dir)

        try:
            register_resp = requests.post(
                REGISTER_API_URL,
                json={
                    "chatbot_id": chatbot_id,
                    "api_key": st.session_state.api_key,
                },
                timeout=30,
            )
            if not register_resp.ok:
                st.error("Could not register chatbot ownership on backend")
                st.stop()
        except requests.RequestException as err:
            st.error(f"Registration error: {err}")
            st.stop()

        # ✅ SAVE CHATBOT ID IN SESSION
        st.session_state.chatbot_id = chatbot_id
        st.session_state.ready = True

        st.success("Chatbot ready ✅")
        st.info(f"Chatbot ID: {chatbot_id}")

    else:
        st.warning("Please upload files first!")


# 💬 Chat section
if st.session_state.ready:

    st.subheader("💬 Chat with your documents")
    st.caption(f"Using Chatbot ID: {st.session_state.chatbot_id}")

    with st.expander("🔌 API Integration Info", expanded=True):
        st.write("Use these values in another system or website to call this chatbot.")
        st.code(API_URL, language="text")
        request_payload = {
            "chatbot_id": st.session_state.chatbot_id,
            "api_key": st.session_state.api_key,
            "query": "What is this document about?",
        }
        st.write("Example request body:")
        st.code(json.dumps(request_payload, indent=2), language="json")
        #------------------------------------
        st.write("Example JavaScript fetch:")
        st.code(
            f'''fetch("{API_URL}", {{
                method: "POST",
                headers: {{ "Content-Type": "application/json" }},
                body: JSON.stringify({json.dumps(request_payload, indent=2)})
                }})''',
                language="javascript",
            )
        #------------------------------------
        st.write("Example Python (requests):")
        st.code(
            f'''import requests
                url = "{API_URL}"
                payload = {json.dumps(request_payload, indent=2)}

                response = requests.post(url, json=payload, timeout=60)
                print(response.status_code)
                print(response.json())
            ''',
            language="python",
        )
        #------------------------------------
        st.write("Example Python (urllib):")
        st.code(
            f'''import json
                from urllib.request import Request, urlopen

                url = "{API_URL}"
                payload = {json.dumps(request_payload, indent=2)}
                data = json.dumps(payload).encode("utf-8")

                req = Request(
                    url,
                    data=data,
                    headers={{"Content-Type": "application/json"}},
                    method="POST",
                )

                with urlopen(req, timeout=60) as resp:
                    body = resp.read().decode("utf-8")
                    print(resp.status)
                    print(body)
            ''',
            language="python",
        )

    st.subheader("🧪 Test This Chatbot")
    test_query = st.text_input("Test query", key="test_query")

    if st.button("Run Test"):
        if test_query:
            try:
                response = requests.post(
                    API_URL,
                    json={
                        "query": test_query,
                        "chatbot_id": st.session_state.chatbot_id,
                        "api_key": st.session_state.api_key,
                    },
                    timeout=60,
                )

                if response.ok:
                    payload = response.json()
                    st.success("Test successful")
                    st.write(payload.get("response", "No response received"))
                else:
                    error_msg = f"Test failed: {response.status_code}"
                    try:
                        payload = response.json()
                        if payload.get("error"):
                            error_msg = f"{error_msg} - {payload['error']}"
                    except ValueError:
                        pass
                    st.error(error_msg)
            except requests.RequestException as err:
                st.error(f"Test request error: {err}")
        else:
            st.warning("Enter a test query first")

    query = st.text_input("Ask something...", key="user_query")

    if query:
        try:
            response = requests.post(
                API_URL,
                json={
                    "query": query,
                    "chatbot_id": st.session_state.chatbot_id,
                    "api_key": st.session_state.api_key,
                },
                timeout=60,
            )

            if response.ok:
                payload = response.json()
                answer = payload.get("response")

                if answer:
                    st.markdown("### Answer")
                    st.write(answer)
                else:
                    st.error(payload.get("error", "No response received from API"))
            else:
                error_msg = f"Backend API failed: {response.status_code}"
                try:
                    payload = response.json()
                    if payload.get("error"):
                        error_msg = f"{error_msg} - {payload['error']}"
                except ValueError:
                    pass
                st.error(error_msg)

        except requests.RequestException as err:
            st.error(f"API integration error: {err}")

