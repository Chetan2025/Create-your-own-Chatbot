import uuid
import streamlit as st


def init_session_state():
    if "ready" not in st.session_state:
        st.session_state.ready = False

    if "logged_in" not in st.session_state:
        st.session_state.logged_in = False

    if "username" not in st.session_state:
        st.session_state.username = None

    if "page" not in st.session_state:
        st.session_state.page = "home"

    if "chatbot_id" not in st.session_state:
        st.session_state.chatbot_id = None

    if "api_key" not in st.session_state:
        st.session_state.api_key = str(uuid.uuid4())

    if "published" not in st.session_state:
        st.session_state.published = False

    if "pending_chatbot_id" not in st.session_state:
        st.session_state.pending_chatbot_id = None

    if "pending_vector_db" not in st.session_state:
        st.session_state.pending_vector_db = None

    if "chatbot_name" not in st.session_state:
        st.session_state.chatbot_name = None

    if "user_chatbots" not in st.session_state:
        st.session_state.user_chatbots = []

    if "show_chatbot_info" not in st.session_state:
        st.session_state.show_chatbot_info = False

    if "creator_form_version" not in st.session_state:
        st.session_state.creator_form_version = 0


def reset_user_session():
    st.session_state.logged_in = False
    st.session_state.username = None
    st.session_state.page = "home"
    st.session_state.ready = False
    st.session_state.chatbot_id = None
    st.session_state.api_key = str(uuid.uuid4())
    st.session_state.published = False
    st.session_state.pending_chatbot_id = None
    st.session_state.pending_vector_db = None
    st.session_state.chatbot_name = None
    st.session_state.user_chatbots = []
    st.session_state.show_chatbot_info = False


def reset_chatbot_creator_form():
    """Clear chatbot creator form fields"""
    st.session_state.creator_form_version += 1
    st.session_state.ready = False
    st.session_state.pending_chatbot_id = None
    st.session_state.pending_vector_db = None
    st.session_state.published = False
