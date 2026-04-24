import json
import os
import tempfile
import uuid

import requests
import streamlit as st
from langchain_community.document_loaders import Docx2txtLoader, PyPDFLoader
from langchain_community.embeddings import HuggingFaceEmbeddings
from langchain_community.vectorstores import FAISS
from langchain_text_splitters import RecursiveCharacterTextSplitter
from state import reset_chatbot_creator_form


def render_chatbot_creator(api_url: str, register_api_url: str, project_root: str):
    st.caption(f"Logged in as: {st.session_state.username}")
    form_version = st.session_state.get("creator_form_version", 0)

    if st.button("Back to Home"):
        st.session_state.page = "home"
        reset_chatbot_creator_form()
        st.rerun()

    uploaded_files = st.file_uploader(
        "Upload multiple files",
        accept_multiple_files=True,
        key=f"file_uploader_{form_version}",
    )

    chatbot_name = st.text_input(
        "Chatbot Name (optional)",
        placeholder="e.g., My Company Bot",
        key=f"chatbot_name_input_{form_version}",
    )

    if st.button("Create Chatbot"):
        if uploaded_files and len(uploaded_files) > 0:
            all_docs = []
            st.session_state.published = False
            st.session_state.pending_chatbot_id = None
            st.session_state.pending_vector_db = None
            st.success(f"{len(uploaded_files)} files uploaded")
            st.write("Processing documents...")

            for file in uploaded_files:
                suffix = file.name.split(".")[-1].lower()

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
                st.error("No valid documents loaded. Please upload Document or DOCX files.")
                st.stop()

            splitter = RecursiveCharacterTextSplitter(
                chunk_size=500,
                chunk_overlap=50,
            )
            chunks = splitter.split_documents(all_docs)

            embeddings = HuggingFaceEmbeddings(
                model_name="sentence-transformers/all-MiniLM-L6-v2"
            )
            st.session_state.pending_vector_db = FAISS.from_documents(chunks, embeddings)
            st.session_state.pending_chatbot_id = str(uuid.uuid4())
            st.session_state.chatbot_name = chatbot_name if chatbot_name.strip() else f"Bot-{str(uuid.uuid4())[:8]}"
            st.session_state.ready = True

            st.success("Chatbot prepared")
            st.info(f"Naam: {st.session_state.chatbot_name}\nAb Done - Save Model click karo. Save ke baad hi database/backend me record jayega.")
        else:
            st.warning("Please upload files first")

    if st.session_state.ready:
        st.subheader("Chat with your documents")
        if st.session_state.published:
            st.caption(f"Using Chatbot ID: {st.session_state.chatbot_id}")
        else:
            st.caption("Model prepared but not saved yet")

        if not st.session_state.published:
            st.info("Test aur API info dekhne ke liye pehle Done - Save Model click karo.")

        c1, c2, c3 = st.columns([1, 2, 1])
        with c2:
            if st.button("Done - Save Model", use_container_width=True):
                if not st.session_state.pending_vector_db or not st.session_state.pending_chatbot_id:
                    st.error("Koi prepared model nahi mila. Pehle Create Chatbot karo.")
                else:
                    base_db_dir = os.path.join(project_root, "db", "users")
                    user_chatbots_dir = os.path.join(
                        base_db_dir,
                        st.session_state.username,
                        "chatbots",
                    )
                    db_dir = os.path.join(user_chatbots_dir, st.session_state.pending_chatbot_id)
                    os.makedirs(user_chatbots_dir, exist_ok=True)
                    st.session_state.pending_vector_db.save_local(db_dir)

                    try:
                        register_resp = requests.post(
                            register_api_url,
                            json={
                                "chatbot_id": st.session_state.pending_chatbot_id,
                                "api_key": st.session_state.api_key,
                                "name": st.session_state.chatbot_name,
                                "username": st.session_state.username,
                            },
                            timeout=30,
                        )
                        if not register_resp.ok:
                            st.error("Could not register chatbot ownership on backend")
                            st.stop()
                    except requests.RequestException as err:
                        st.error(f"Registration error: {err}")
                        st.stop()

                    st.session_state.chatbot_id = st.session_state.pending_chatbot_id
                    st.session_state.published = True
                    st.success("Congrats! Model saved successfully.")

                    new_bot = {
                        "chatbot_id": st.session_state.chatbot_id,
                        "api_key": st.session_state.api_key,
                        "name": st.session_state.chatbot_name,
                    }
                    existing = st.session_state.get("user_chatbots", [])
                    updated = [
                        bot
                        for bot in existing
                        if not (
                            isinstance(bot, dict)
                            and bot.get("chatbot_id") == st.session_state.chatbot_id
                        )
                    ]
                    updated.append(new_bot)
                    st.session_state.user_chatbots = updated

                    st.session_state.pending_vector_db = None
                    st.session_state.pending_chatbot_id = None

        if st.session_state.published:
            st.subheader("Test This Chatbot")
            test_query = st.text_input("Test query", key=f"test_query_{form_version}")

            if st.button("Run Test"):
                if test_query:
                    try:
                        response = requests.post(
                            api_url,
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

            query = st.text_input("Ask something...", key=f"user_query_{form_version}")

            if query:
                try:
                    response = requests.post(
                        api_url,
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

            st.subheader("API Integration Info")
            st.write(f"**Chatbot Name:** {st.session_state.chatbot_name}")
            st.write(f"**Chatbot ID:** {st.session_state.chatbot_id}")
            st.caption(f"Your API Key: {st.session_state.api_key}")
            st.write("Ab aap is API info ko website/app integration ke liye use kar sakte ho.")
            st.code(api_url, language="text")
            request_payload = {
                "chatbot_id": st.session_state.chatbot_id,
                "api_key": st.session_state.api_key,
                "query": "What is this document about?",
            }
            st.write("Example request body:")
            st.code(json.dumps(request_payload, indent=2), language="json")
