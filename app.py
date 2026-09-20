import streamlit as st
from agent import ask_agent

st.set_page_config(page_title="Order Status Agent", page_icon="📦")
st.title("📦 Order Status Agent")
st.caption("Ask about any sales order in the SAP sandbox — e.g. \"What's the status of order 1234?\"")

if "history" not in st.session_state:
    st.session_state.history = []       # full message log the agent needs
if "display" not in st.session_state:
    st.session_state.display = []       # simplified log for rendering

for role, text in st.session_state.display:
    with st.chat_message(role):
        st.write(text)

question = st.chat_input("Ask about a sales order…")
if question:
    st.session_state.display.append(("user", question))
    with st.chat_message("user"):
        st.write(question)

    with st.chat_message("assistant"):
        with st.spinner("Checking SAP…"):
            answer, st.session_state.history = ask_agent(question, st.session_state.history)
        st.write(answer)
    st.session_state.display.append(("assistant", answer))