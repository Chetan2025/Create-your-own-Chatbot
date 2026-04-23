import streamlit as st
import requests

from state import reset_chatbot_creator_form, reset_user_session


def _sync_selected_chatbot(chatbot_id: str):
    chatbots = st.session_state.get("user_chatbots", [])
    for bot in chatbots:
        if isinstance(bot, dict) and bot.get("chatbot_id") == chatbot_id:
            st.session_state.chatbot_id = bot.get("chatbot_id")
            st.session_state.chatbot_name = bot.get("name")
            st.session_state.api_key = bot.get("api_key", st.session_state.api_key)
            st.session_state.ready = True
            st.session_state.published = True
            return


def _fetch_usage(usage_report_api_url: str, chatbot_id: str, api_key: str):
    try:
        resp = requests.post(
            usage_report_api_url,
            json={"chatbot_id": chatbot_id, "api_key": api_key},
            timeout=20,
        )
    except requests.RequestException as err:
        return None, f"Report error: {err}"

    if not resp.ok:
        try:
            return None, resp.json().get("error", "Could not fetch usage report")
        except ValueError:
            return None, "Could not fetch usage report"

    return resp.json(), None


def _render_usage_metrics(data: dict):
    c1, c2, c3 = st.columns(3)
    c1.metric("Last 24 Hours", data.get("last_24_hours_calls", 0))
    c2.metric("Last 7 Days", data.get("last_7_days_calls", 0))
    c3.metric("Total Calls", data.get("total_calls", 0))


def render_home(
    usage_report_api_url: str,
    usage_clear_api_url: str,
    delete_chatbot_api_url: str,
):
    st.success(f"Welcome {st.session_state.username}")
    st.write("Apne chatbots ka table dekho. Kisi pe click karo details aur usage report dekhne ke liye.")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("Open Chatbot Creator", use_container_width=True):
            reset_chatbot_creator_form()
            st.session_state.page = "creator"
            st.rerun()

    with col2:
        if st.button("Logout", use_container_width=True):
            reset_user_session()
            st.rerun()

    st.divider()
    st.subheader("📊 Your Chatbots")

    chatbots = [bot for bot in st.session_state.get("user_chatbots", []) if isinstance(bot, dict)]
    st.session_state.user_chatbots = chatbots

    if not chatbots:
        st.info("There are no chatbots yet. Please create one to see usage reports and other details here.")
        return

    valid_ids = [bot.get("chatbot_id") for bot in chatbots if bot.get("chatbot_id")]
    if st.session_state.chatbot_id not in valid_ids and valid_ids:
        _sync_selected_chatbot(valid_ids[0])

    # Display all chatbots in a table-like interface with click capability
    st.markdown("### All Chatbots")
    
    # Create header
    header_cols = st.columns([1.8, 0.8, 0.8, 0.8, 1])
    with header_cols[0]:
        st.markdown("**Bot Name**")
    with header_cols[1]:
        st.markdown("**Bot ID**")
    with header_cols[2]:
        st.markdown("**Created**")
    with header_cols[3]:
        st.markdown("**Status**")
    with header_cols[4]:
        st.markdown("**Action**")
    
    st.divider()
    
    for bot in chatbots:
        chatbot_id = bot.get("chatbot_id")
        bot_name = bot.get("name", "Unnamed Bot")
        created_at = bot.get("created_at", "-")
        
        row_cols = st.columns([1.8, 0.8, 0.8, 0.8, 1])
        
        with row_cols[0]:
            st.write(bot_name)
        with row_cols[1]:
            st.caption(chatbot_id[:8] if chatbot_id else "-")
        with row_cols[2]:
            st.caption(created_at)
        with row_cols[3]:
            st.caption("✅ Active")
        with row_cols[4]:
            if st.button("View", key=f"view_{chatbot_id}", use_container_width=True):
                _sync_selected_chatbot(chatbot_id)
                st.session_state.selected_bot_detail = chatbot_id
                st.rerun()
    
    st.divider()
    
    # Show detailed view for selected chatbot
    if hasattr(st.session_state, 'selected_bot_detail') and st.session_state.selected_bot_detail:
        selected_id = st.session_state.selected_bot_detail
        selected_bot = next((bot for bot in chatbots if bot.get("chatbot_id") == selected_id), None)
        
        if selected_bot:
            st.subheader(f"📋 {selected_bot.get('name', 'Unnamed Bot')} Details")
            
            detail_cols = st.columns(3)
            
            with detail_cols[0]:
                st.metric("Bot Name", selected_bot.get("name", "N/A"))
            with detail_cols[1]:
                st.metric("Bot ID", selected_bot.get("chatbot_id", "N/A")[:16])
            with detail_cols[2]:
                st.metric("Created", selected_bot.get("created_at", "N/A"))
            
            st.write("**Full Details:**")
            st.json(selected_bot)
            
            # Usage Report Section
            st.subheader("📈 Usage Report")
            if st.button("📊 Fetch Usage Report", use_container_width=True, key=f"fetch_usage_{selected_id}"):
                data, error = _fetch_usage(
                    usage_report_api_url=usage_report_api_url,
                    chatbot_id=selected_id,
                    api_key=selected_bot.get("api_key"),
                )
                if error:
                    st.error(error)
                else:
                    _render_usage_metrics(data)
            
            # Action buttons
            action_col1, action_col2, action_col3 = st.columns(3)
            
            with action_col1:
                if st.button("Clear Usage", use_container_width=True, key=f"clear_{selected_id}"):
                    try:
                        resp = requests.delete(
                            usage_clear_api_url,
                            json={
                                "chatbot_id": selected_id,
                                "api_key": selected_bot.get("api_key"),
                            },
                            timeout=20,
                        )
                        if resp.ok:
                            st.success("Usage records cleared")
                        else:
                            msg = resp.json().get("error", "Could not clear usage")
                            st.error(msg)
                    except requests.RequestException as err:
                        st.error(f"Clear error: {err}")
            
            with action_col2:
                if st.button("Close Detail View", use_container_width=True, key=f"close_{selected_id}"):
                    st.session_state.selected_bot_detail = None
                    st.rerun()
            
            with action_col3:
                confirm_delete = st.checkbox(
                    "Confirm delete",
                    key=f"confirm_delete_{selected_id}",
                )
                if st.button("Delete Bot", use_container_width=True, key=f"delete_{selected_id}"):
                    if not confirm_delete:
                        st.warning("Delete se pehle confirmation tick karo.")
                    else:
                        try:
                            resp = requests.delete(
                                delete_chatbot_api_url,
                                json={
                                    "chatbot_id": selected_id,
                                    "api_key": selected_bot.get("api_key"),
                                },
                                timeout=20,
                            )
                            if resp.ok:
                                remaining = [
                                    bot
                                    for bot in st.session_state.user_chatbots
                                    if not (
                                        isinstance(bot, dict)
                                        and bot.get("chatbot_id") == selected_id
                                    )
                                ]
                                st.session_state.user_chatbots = remaining
                                st.session_state.selected_bot_detail = None

                                if remaining:
                                    _sync_selected_chatbot(remaining[0].get("chatbot_id"))
                                else:
                                    st.session_state.ready = False
                                    st.session_state.chatbot_id = None
                                    st.session_state.chatbot_name = None
                                    st.session_state.published = False

                                st.success("Chatbot deleted successfully")
                                st.rerun()
                            else:
                                msg = resp.json().get("error", "Could not delete chatbot")
                                st.error(msg)
                        except requests.RequestException as err:
                            st.error(f"Delete error: {err}")


