
from __future__ import annotations

import io
import json
import zipfile
from pathlib import PurePosixPath

import streamlit as st
from guardian import analyze_project, render_markdown_report
from ai_explainer import explain_findings


st.set_page_config(
    page_title="OpenSource Guardian",
    page_icon="🛡️",
    layout="wide",
)

st.title("🛡️ OpenSource Guardian")
st.subheader("Open-source contribution readiness checker")

st.write(
    "Inspect a project archive for documentation gaps, missing configuration "
    "templates, dependency issues, and common accidental-secret patterns—"
    "before sharing it on GitHub."
)

st.info(
    "Privacy-first MVP: analysis runs locally in this Streamlit process. "
    "The optional AI explanation feature is not required. This is a best-effort "
    "checklist, not a security audit or a guarantee that a project is safe."
)

with st.expander("What does this tool check?"):
    st.markdown(
        "- Repository basics: README, license, contribution guide, ignore rules\n"
        "- Python project setup: dependency file and test presence\n"
        "- Documentation: installation, usage, configuration, and examples\n"
        "- Configuration hygiene: `.env.example` and `.gitignore` coverage\n"
        "- Common secret patterns in eligible text files\n"
        "- A weighted readiness score with actionable findings"
    )

uploaded = st.file_uploader(
    "Upload your project as a ZIP file",
    type=["zip"],
)

if uploaded:
    try:
        with zipfile.ZipFile(io.BytesIO(uploaded.getvalue())) as zf:
            files_map: dict[str, str] = {}
            total_size = 0

            for info in zf.infolist():
                if info.is_dir():
                    continue

                # Ignore absolute paths, traversal paths, and oversized files.
                path = PurePosixPath(info.filename)

                if (
                    path.is_absolute()
                    or ".." in path.parts
                    or info.file_size > 1_000_000
                ):
                    continue

                total_size += info.file_size

                if total_size > 10_000_000:
                    st.error(
                        "Archive is too large to scan. Keep extracted file "
                        "contents under 10 MB."
                    )
                    st.stop()

                name = str(path)

                if name.startswith("__MACOSX/") or "/.git/" in f"/{name}/":
                    continue

                raw = zf.read(info)

                try:
                    files_map[name] = raw.decode("utf-8")
                except UnicodeDecodeError:
                    # Binary files are deliberately not inspected.
                    continue

        if not files_map:
            st.error("No readable text files found in this ZIP.")
            st.stop()

    except zipfile.BadZipFile:
        st.error("This file is not a valid ZIP archive.")
        st.stop()

    st.success(f"Loaded {len(files_map)} readable text files.")

    report = analyze_project(files_map)

    col1, col2, col3, col4 = st.columns(4)

    col1.metric("Readiness score", f"{report['score']}/100")
    col2.metric("Checks passed", report["passed"])
    col3.metric("Needs attention", report["attention"])
    col4.metric("High-priority findings", report["high"])

    st.progress(report["score"] / 100)

    st.caption(
        "The score reflects checklist coverage only. It is not a measure "
        "of overall code quality or security."
    )

    st.markdown("### Findings")

    severity_filter = st.multiselect(
        "Filter by severity",
        ["High", "Medium", "Low", "Info"],
        default=["High", "Medium", "Low", "Info"],
    )

    findings = [
        finding
        for finding in report["findings"]
        if finding["severity"] in severity_filter
    ]

    if not findings:
        st.success("No findings in the selected severity levels.")

    for finding in findings:
        title = (
            f"{finding['severity']} · "
            f"{finding['status']} · "
            f"{finding['title']}"
        )

        with st.expander(
            title,
            expanded=finding["severity"] == "High",
        ):
            st.write(finding["details"])

            st.markdown(
                f"**Suggested action:** {finding['recommendation']}"
            )

            if finding.get("evidence"):
                st.code(finding["evidence"], language="text")

    st.markdown("### File inventory")

    st.write(
        ", ".join(f"`{path}`" for path in report["inventory"])
        or "No files detected."
    )

    markdown = render_markdown_report(report)

    st.download_button(
        "Download Markdown report",
        data=markdown,
        file_name="opensource-guardian-report.md",
        mime="text/markdown",
    )

    st.download_button(
        "Download JSON report",
        data=json.dumps(report, indent=2),
        file_name="opensource-guardian-report.json",
        mime="application/json",
    )

    # Gemini AI explanation
    st.markdown("### AI explanation")

    st.caption(
        "Gemini explains the checklist findings and recommends what to fix "
        "first. Only summarized findings are sent when you request an "
        "explanation."
    )

    if st.button("Generate AI explanation"):
        with st.spinner("Generating explanation with Gemini..."):
            explanation = explain_findings(report)
            st.session_state["guardian_ai_explanation"] = explanation

    if st.session_state.get("guardian_ai_explanation"):
        st.markdown(
            st.session_state["guardian_ai_explanation"]
        )

        st.download_button(
            "Download AI explanation",
            data=st.session_state["guardian_ai_explanation"],
            file_name="opensource-guardian-ai-explanation.md",
            mime="text/markdown",
        )

    with st.expander("How the score is calculated"):
        st.write(
            "Each checklist item has a weight. Passing a check earns its "
            "weight; missing or failed checks do not. Informational checks "
            "do not affect the score. Findings are heuristics and may need "
            "human review."
        )