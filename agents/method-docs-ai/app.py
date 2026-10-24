from pathlib import Path
import streamlit as st
from dotenv import load_dotenv

from knowflow.config import settings
from knowflow.indexer import build_index, index_exists
from knowflow.agent import answer_question

load_dotenv()

st.set_page_config(page_title="MethodDocsAI", page_icon="📚", layout="wide")
st.title("Method Documents AI Agent")
st.caption("Local document retrieval · Gemini API · source-grounded answers")

with st.sidebar:
    st.subheader("Configuration")
    st.write(f"**Gemini model:** `{settings.chat_model}`")
    st.write("**Retrieval:** local lexical search (no embedding model download)")
    st.write(f"**Knowledge folder:** `{settings.knowledge_dir}`")
    st.info("Use only documents you are authorized to access. This MVP reads a local folder, such as an approved SharePoint sync/export folder.")
    if st.button("Build / refresh index", use_container_width=True):
        with st.spinner("Reading documents and building a local search index..."):
            try:
                count = build_index()
                st.success(f"Index built: {count} passages.")
            except Exception as exc:
                st.error(f"Index build failed: {exc}")

if not index_exists():
    st.warning("No index found yet. Add documents to the knowledge folder, then click **Build / refresh index**.")
else:
    st.success("Local document index is available.")

question = st.text_area(
    "Ask your documentation",
    placeholder="Example: What steps should we follow before deploying an API change?",
    height=100,
)
col1, col2 = st.columns([1, 5])
with col1:
    ask = st.button("Ask MethodDocsAI", type="primary", use_container_width=True)
with col2:
    st.caption("Retrieved excerpts are sent to the Gemini API to generate answers. Always verify important guidance against the cited source.")

if ask:
    if not question.strip():
        st.warning("Enter a question first.")
    else:
        with st.spinner("Searching your documents and preparing an evidence-based answer..."):
            try:
                result = answer_question(question.strip())
                st.subheader("Answer")
                st.markdown(result["answer"])
                if result["sources"]:
                    st.subheader("Sources")
                    for i, source in enumerate(result["sources"], start=1):
                        with st.expander(f"[{i}] {source['file']} · passage {source['chunk_id']} · similarity {source['score']:.2f}"):
                            st.write(source["text"])
                else:
                    st.info("No sufficiently relevant sources were found.")
            except Exception as exc:
                st.error(f"Could not answer the question: {exc}")
                st.caption("Check your internet connection, GEMINI_API_KEY, configured Gemini model, and API quota.")
