from __future__ import annotations

import streamlit as st
from ai.ollama_client import DEFAULT_OLLAMA_MODEL, OllamaUnavailable
from application.orchestrator import assess, generate_explanation
from domain.assessment import TESTS
from security.guardrails import UnsafeAIOutput


def _reset_test_defaults() -> None:
    test_info = TESTS[st.session_state["test_name"]]
    st.session_state["result"] = None
    st.session_state["unit"] = test_info["unit"]
    st.session_state["lower"] = float(test_info["example_range"][0])
    st.session_state["upper"] = float(test_info["example_range"][1])


st.set_page_config(page_title="LabLens | Lab Report Explainer", page_icon="🔬", layout="centered")
st.markdown(
    """
    <style>
        .block-container {max-width: 760px; padding-top: 2rem; padding-bottom: 3rem;}
        [data-testid="stCaptionContainer"] {color: #526173;}
    </style>
    """,
    unsafe_allow_html=True,
)

st.title("🔬 LabLens")
st.caption("A plain-language guide to the numbers on your lab report.")
st.caption("Educational only—not a diagnosis. Use your lab’s own reference interval.")

if "test_name" not in st.session_state:
    st.session_state["test_name"] = next(iter(TESTS))
    st.session_state["unit"] = TESTS[st.session_state["test_name"]]["unit"]
    st.session_state["lower"] = float(TESTS[st.session_state["test_name"]]["example_range"][0])
    st.session_state["upper"] = float(TESTS[st.session_state["test_name"]]["example_range"][1])

st.subheader("Your lab result")
test_name = st.selectbox(
    "Lab test",
    options=list(TESTS),
    key="test_name",
    on_change=_reset_test_defaults,
)
test_info = TESTS[test_name]
st.caption(test_info["what_it_measures"])

st.number_input(
    "Result",
    min_value=0.0,
    value=None,
    format="%.3f",
    step=0.1,
    key="result",
    placeholder="Enter the value from your report",
)
st.text_input("Unit shown on your report", key="unit")

st.markdown("**Reference interval on your report**")
lower_column, upper_column = st.columns(2)
with lower_column:
    st.number_input("Lower limit", min_value=0.0, format="%.3f", step=0.1, key="lower")
with upper_column:
    st.number_input("Upper limit", min_value=0.0, format="%.3f", step=0.1, key="upper")
st.caption(
    f"Prefilled values ({test_info['example_range'][0]:g}–{test_info['example_range'][1]:g} "
    f"{test_info['unit']}) are illustrative examples only. Replace them with the interval "
    "printed on your report."
)

current_input = (
    test_name,
    st.session_state.get("result"),
    st.session_state["unit"],
    st.session_state["lower"],
    st.session_state["upper"],
)
if st.session_state.get("assessment_input") != current_input:
    for key in ("assessment_input", "last_assessment", "validation_error", "ai_response", "ai_error"):
        st.session_state.pop(key, None)

if st.button("Explain my result", type="primary", use_container_width=True):
    assessment = assess(*current_input)
    st.session_state["assessment_input"] = current_input
    st.session_state.pop("ai_response", None)
    st.session_state.pop("ai_error", None)
    if "error" in assessment:
        st.session_state["last_assessment"] = None
        st.session_state["validation_error"] = assessment["error"]
    else:
        st.session_state["last_assessment"] = assessment
        st.session_state.pop("validation_error", None)

if st.session_state.get("validation_error"):
    st.error(st.session_state["validation_error"])

assessment = st.session_state.get("last_assessment")
if assessment and st.session_state.get("assessment_input") == current_input:
    st.divider()
    with st.container(border=True):
        st.subheader("Your comparison")
        if assessment["status"] == "Within supplied range":
            st.success(assessment["status"])
        else:
            st.warning(assessment["status"])
        st.metric("Your result", f"{assessment['result']:g} {assessment['unit']}".strip())
        st.write(assessment["interpretation"])
        st.markdown("**Questions to discuss with your clinician**")
        for question in assessment["questions"]:
            st.markdown(f"- {question}")

    st.markdown("**Want a simpler explanation?**")
    st.caption(
        "Optional local AI uses only the test, result, unit, and interval above. "
        "Its educational output may be inaccurate and cannot diagnose medical conditions."
    )
    with st.expander("Advanced settings"):
        ollama_model = st.text_input(
            "Ollama model",
            value=DEFAULT_OLLAMA_MODEL,
            key="ollama_model",
            help="Use a model already downloaded in Ollama.",
        )

    if st.button("Simplify with local AI"):
        with st.spinner("Asking your local Ollama model…"):
            try:
                st.session_state["ai_response"] = generate_explanation(
                    assessment,
                    model=st.session_state.get("ollama_model", DEFAULT_OLLAMA_MODEL),
                )
                st.session_state.pop("ai_error", None)
            except OllamaUnavailable as exc:
                st.session_state["ai_error"] = str(exc)
                st.session_state.pop("ai_response", None)
            except UnsafeAIOutput:
                st.session_state["ai_error"] = "blocked"
                st.session_state.pop("ai_response", None)

    if st.session_state.get("ai_response"):
        with st.container(border=True):
            st.markdown("**Simpler explanation**")
            st.write(st.session_state["ai_response"])

    if st.session_state.get("ai_error") not in (None, "blocked"):
        st.error(f"{st.session_state['ai_error']} Your standard comparison is still here.")
        with st.expander("Ollama setup help"):
            st.write(
                "Install Ollama, start its app, and download the selected model:"
            )
            st.code(
                f"ollama pull {st.session_state.get('ollama_model', DEFAULT_OLLAMA_MODEL)}",
                language="powershell",
            )
            st.caption("If the service is not already running, start it with `ollama serve`.")
    elif st.session_state.get("ai_error") == "blocked":
        st.error(
            "The local AI response did not pass safety checks. Your standard comparison "
            "is still available."
        )

with st.expander("Safety, privacy, and limitations"):
    st.markdown(
        """
        LabLens does not diagnose disease, estimate personal risk, or recommend medication
        or treatment. Reference intervals vary between laboratories and people; an
        in-range result does not guarantee health, and an out-of-range result is not a
        diagnosis. Use the interval printed on your report and discuss interpretation
        with a qualified clinician.

        The deterministic comparison runs in this app. Optional AI sends only the
        selected test, result, unit, and entered interval to Ollama at
        `127.0.0.1:11434`; no report or identifying details are requested, and there is
        no cloud fallback. AI output and automated safety checks can be inaccurate or
        incomplete, so treat the output as untrusted educational information.
        """
    )
