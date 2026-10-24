"""Local Streamlit chat UI for the issue triage assistant."""

from __future__ import annotations

import streamlit as st

from github_api import GitHubAPIError, fetch_public_issue, fetch_repository_labels
from triage import MOCK_RESULT, triage, validate_result


def render_result(result: dict) -> None:
    st.markdown(f"**{result['summary']}**")
    st.write(f"Issue type: `{result['issue_type']}`")
    st.markdown("**Maintainer guidance**")
    st.write(result["maintainer_guidance"])
    if result["readiness"] == "ready":
        st.success("Ready for maintainer review")
    else:
        st.warning("Needs more information")

    with st.expander("Missing information", expanded=bool(result["missing_information"])):
        if result["missing_information"]:
            for item in result["missing_information"]:
                st.markdown(f"- {item}")
        else:
            st.write("No missing details identified.")

    st.markdown("**Suggested labels**")
    if result["suggested_labels"]:
        st.write(" · ".join(f"`{label}`" for label in result["suggested_labels"]))
    else:
        st.write("No allowed labels suggested. Add this repository's labels in the sidebar.")

    if result["template_checks"]:
        st.markdown("**Issue template check**")
        for item in result["template_checks"]:
            icon = "✅" if item["status"] == "present" else "⚠️"
            st.write(f"{icon} {item['field']}: {item['status']}")

    with st.expander("Evidence from the issue", expanded=False):
        if result["evidence"]:
            for item in result["evidence"]:
                st.markdown(f"- **{item['field']}**: “{item['quote']}”")
        else:
            st.write("No exact supporting quotes were returned.")

    st.markdown("**Draft reply · review before posting**")
    st.info(result["draft_reply"] or "No reply draft returned.")


def analyze_issue(issue_text: str, host: str, model: str, labels: list[str], template_text: str, mock_mode: bool) -> dict:
    if mock_mode:
        return validate_result(MOCK_RESULT, issue_text, labels or ["bug", "needs-reproduction"])
    return triage(issue_text, host, model, labels, template_text)


def main() -> None:
    st.set_page_config(page_title="Issue Triage Assistant", page_icon="🔎", layout="centered")
    if "messages" not in st.session_state:
        st.session_state["messages"] = []
    st.title("GitHub Issue Triage Assistant")
    st.caption("Local-first issue triage. Suggestions are for maintainer review; nothing is posted or applied.")

    with st.sidebar:
        st.header("Configuration")
        input_source = st.radio("Issue source", ["Paste issue", "Public GitHub issue"])
        mock_mode = st.toggle("Use sample output", value=False, help="Preview the interface without ADK or Ollama.")
        model = st.text_input("Ollama model", value="llama3.2:3b", disabled=mock_mode)
        host = st.text_input("Ollama URL", value="http://localhost:11434", disabled=mock_mode)
        labels_text = st.text_area(
            "Repository labels (comma-separated)",
            value="bug,enhancement,question,documentation,needs-reproduction",
            height=90,
        )
        uploaded_template = st.file_uploader("Optional Markdown issue template", type=["md", "markdown"])
        github_url = ""
        github_submitted = False
        if input_source == "Public GitHub issue":
            with st.form("github_issue_form"):
                github_url = st.text_input(
                    "Public issue URL",
                    placeholder="https://github.com/owner/repo/issues/123",
                )
                github_submitted = st.form_submit_button("Fetch and triage issue", use_container_width=True)
            st.caption("Fetches a public issue and its repository labels using read-only GitHub API requests.")
        st.caption("Live triage sends issue text and the optional template to the configured Ollama endpoint.")
        if st.button("Clear conversation", use_container_width=True):
            st.session_state["messages"] = []
            st.rerun()

    if not st.session_state["messages"]:
        with st.chat_message("assistant"):
            st.write("Paste an issue or fetch one from a public GitHub repository. I’ll check whether it’s ready for triage and show the evidence behind my suggestions.")

    for message in st.session_state["messages"]:
        with st.chat_message(message["role"]):
            if message["role"] == "user":
                st.markdown(message["content"])
            elif "error" in message:
                st.error(message["error"])
            else:
                if message.get("notice"):
                    st.caption(message["notice"])
                render_result(message["result"])

    try:
        template_text = uploaded_template.getvalue().decode("utf-8") if uploaded_template else ""
        if input_source == "Paste issue":
            issue_text = st.chat_input("Paste the issue title and description…")
            if not issue_text:
                return
            labels = [label.strip() for label in labels_text.split(",") if label.strip()]
            display_text = issue_text
            st.session_state["messages"].append({"role": "user", "content": display_text})
            with st.spinner("Checking the issue with your local model… The first response may take a little longer while Ollama loads the model."):
                result = analyze_issue(issue_text, host, model, labels, template_text, mock_mode)
            st.session_state["messages"].append({"role": "assistant", "result": result})
            st.rerun()

        if github_submitted:
            with st.spinner("Fetching the public issue and repository labels, then checking it with your local model…"):
                issue = fetch_public_issue(github_url)
                issue_text = f"Title: {issue['title']}\n\n{issue['body']}".strip()
                labels_notice = None
                try:
                    labels = fetch_repository_labels(issue["owner"], issue["repo"])
                    if not labels:
                        labels = [label.strip() for label in labels_text.split(",") if label.strip()]
                        if labels:
                            labels_notice = "Repository returned no labels; used the labels entered in the sidebar."
                except GitHubAPIError as exc:
                    labels = [label.strip() for label in labels_text.split(",") if label.strip()]
                    labels_notice = f"Could not load repository labels; used sidebar labels instead. {exc}"
                issue_body = issue["body"] or "_(No description provided.)_"
                display_text = (
                    f"[{issue['owner']}/{issue['repo']}#{issue['number']}]({issue['url']})\n\n"
                    f"**{issue['title']}**\n\n{issue_body}"
                )
                result = analyze_issue(issue_text, host, model, labels, template_text, mock_mode)
            st.session_state["messages"].append({"role": "user", "content": display_text})
            st.session_state["messages"].append(
                {"role": "assistant", "result": result, "notice": labels_notice}
            )
            st.rerun()
    except (GitHubAPIError, UnicodeDecodeError, RuntimeError, OSError) as exc:
        if input_source == "Public GitHub issue" and github_submitted:
            st.session_state["messages"].append({"role": "user", "content": github_url})
        st.session_state["messages"].append({"role": "assistant", "error": str(exc)})
        st.rerun()


if __name__ == "__main__":
    main()
