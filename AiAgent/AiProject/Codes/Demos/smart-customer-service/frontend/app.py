# frontend/app.py
import streamlit as st
import requests
import uuid
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

API_BASE_URL = "http://localhost:8000"

def init_session():
    if "user_id" not in st.session_state:
        st.session_state.user_id = str(uuid.uuid4())
    if "messages" not in st.session_state:
        st.session_state.messages = [
            {"role": "assistant", "content": "您好！我是智能客服，请问有什么可以帮您？"}
        ]

def send_message(message):
    st.session_state.messages.append({"role": "user", "content": message})
    logger.info("发送聊天请求: user_id=%s, message=%s", st.session_state.user_id, message)

    try:
        response = requests.post(
            f"{API_BASE_URL}/chat",
            json={"user_id": st.session_state.user_id, "message": message}
        )
        logger.info("收到聊天响应: status_code=%s", response.status_code)
        response.raise_for_status()
        data = response.json()
        logger.info("聊天响应内容: %s", data.get("response"))
        st.session_state.messages.append({"role": "assistant", "content": data["response"]})
    except requests.HTTPError as e:
        # FastAPI includes the actual exception in ``detail``; showing it
        # makes backend configuration failures diagnosable from the UI.
        detail = e.response.json().get("detail", e.response.text)
        logger.exception("聊天请求返回 HTTP 错误: status_code=%s, detail=%s", e.response.status_code, detail)
        st.session_state.messages.append({"role": "assistant", "content": f"抱歉，服务暂时不可用：{detail}"})
    except Exception as e:
        logger.exception("聊天请求失败")
        st.session_state.messages.append({"role": "assistant", "content": f"抱歉，服务暂时不可用：{str(e)}"})

def main():
    st.title("智能客服系统")
    
    init_session()
    
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.write(msg["content"])
    
    if prompt := st.chat_input("请输入您的问题..."):
        send_message(prompt)
        st.rerun()

if __name__ == "__main__":
    main()
