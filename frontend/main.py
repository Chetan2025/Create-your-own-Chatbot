import os

import streamlit as st
from dotenv import load_dotenv

from auth_page import render_auth
from chatbot_page import render_chatbot_creator
from home_page import render_home
from state import init_session_state

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

load_dotenv()

BACKEND_URL = os.getenv("BACKEND_URL", "http://127.0.0.1:8000").rstrip("/")
API_URL = f"{BACKEND_URL}/api/chat"
REGISTER_API_URL = f"{BACKEND_URL}/api/register-chatbot"
REGISTER_USER_API_URL = f"{BACKEND_URL}/api/register-user"
LOGIN_USER_API_URL = f"{BACKEND_URL}/api/login-user"
USAGE_REPORT_API_URL = f"{BACKEND_URL}/api/usage-report"
USAGE_CLEAR_API_URL = f"{BACKEND_URL}/api/usage-clear"
DELETE_CHATBOT_API_URL = f"{BACKEND_URL}/api/delete-chatbot"

st.title("Document Chatbot")
init_session_state()

if not st.session_state.logged_in:
    render_auth(
        login_user_api_url=LOGIN_USER_API_URL,
        register_user_api_url=REGISTER_USER_API_URL,
    )
elif st.session_state.page == "home":
    render_home(
        usage_report_api_url=USAGE_REPORT_API_URL,
        usage_clear_api_url=USAGE_CLEAR_API_URL,
        delete_chatbot_api_url=DELETE_CHATBOT_API_URL,
    )
else:
    render_chatbot_creator(
        api_url=API_URL,
        register_api_url=REGISTER_API_URL,
        project_root=PROJECT_ROOT,
    )

