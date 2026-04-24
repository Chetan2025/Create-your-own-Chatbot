import requests
import streamlit as st


def render_auth(login_user_api_url: str, register_user_api_url: str):
    tab_login, tab_register = st.tabs(["Login", "Register"])

    with tab_login:
        st.subheader("Login your account")
        st.caption("create your own chatbot")
        login_username = st.text_input("Username", key="login_username")
        login_password = st.text_input("Password", type="password", key="login_password")

        if st.button("Login", key="login_btn"):
            if not login_username or not login_password:
                st.warning("wrong username or password")
            else:
                try:
                    resp = requests.post(
                        login_user_api_url,
                        json={"username": login_username, "password": login_password},
                        timeout=20,
                    )
                    if resp.ok:
                        payload = resp.json()
                        st.session_state.logged_in = True
                        st.session_state.username = payload.get("username", login_username)
                        st.session_state.page = "home"
                        chatbots = payload.get("chatbots") or []
                        st.session_state.user_chatbots = [bot for bot in chatbots if isinstance(bot, dict)]
                        active_chatbot = payload.get("active_chatbot") or {}
                        if active_chatbot:
                            st.session_state.chatbot_id = active_chatbot.get("chatbot_id")
                            st.session_state.api_key = active_chatbot.get("api_key", st.session_state.api_key)
                            st.session_state.chatbot_name = active_chatbot.get("name")
                            st.session_state.published = True
                            st.session_state.ready = True
                            st.session_state.pending_chatbot_id = None
                            st.session_state.pending_vector_db = None
                        elif st.session_state.user_chatbots:
                            fallback_bot = st.session_state.user_chatbots[0]
                            st.session_state.chatbot_id = fallback_bot.get("chatbot_id")
                            st.session_state.api_key = fallback_bot.get("api_key", st.session_state.api_key)
                            st.session_state.chatbot_name = fallback_bot.get("name")
                            st.session_state.published = True
                            st.session_state.ready = True
                        else:
                            st.session_state.chatbot_id = None
                            st.session_state.chatbot_name = None
                            st.session_state.published = False
                            st.session_state.ready = False
                        st.success("Login successful")
                        st.rerun()
                    else:
                        msg = resp.json().get("error", "Login failed")
                        st.error(msg)
                except requests.RequestException as err:
                    st.error(f"Login error: {err}")

    with tab_register:
        st.subheader("Create your account")
        st.caption("create your own chatbot")
        reg_username = st.text_input("New Username", key="reg_username")
        reg_password = st.text_input("New Password", type="password", key="reg_password")

        if st.button("Register", key="register_btn"):
            if not reg_username or not reg_password:
                st.warning("Please fill in all fields")
            else:
                try:
                    resp = requests.post(
                        register_user_api_url,
                        json={"username": reg_username, "password": reg_password},
                        timeout=20,
                    )
                    if resp.ok:
                        st.success("Register successful. Ab login karo.")
                    else:
                        msg = resp.json().get("error", "Registration failed")
                        st.error(msg)
                except requests.RequestException as err:
                    st.error(f"Register error: {err}")
