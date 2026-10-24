import json
import os
from pathlib import Path

import google.generativeai as genai
import pandas as pd

from datasets import Dataset
from ragas import evaluate
from ragas.llms import llm_factory
from ragas.metrics import Faithfulness


PROJECT_ROOT = Path(__file__).resolve().parents[1]
DATASET_PATH = PROJECT_ROOT / "evals" / "accessibility_cases.json"
RESULTS_DIR = PROJECT_ROOT / "evals" / "results"


def load_cases():
    with open(DATASET_PATH, "r", encoding="utf-8") as file:
        return json.load(file)


def generate_candidate_response(case, client):
    """Generate a candidate response for this evaluation case."""

    prompt = f"""
You are AccessAble AI, an accessibility review assistant.

Use only the supplied evidence.
Do not invent measurements or claim that a screenshot proves
keyboard or screen-reader behavior.

User request:
{case["user_input"]}

Evidence context:
{json.dumps(case["evidence_context"], indent=2)}

Expected behavior:
{json.dumps(case["expected_behavior"], indent=2)}

Write a concise accessibility assessment.
"""

    response = client.generate_content(prompt)
    return response.text


def main():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise RuntimeError(
            "GOOGLE_API_KEY is missing. Configure it in your environment."
        )

    genai.configure(api_key=api_key)

    judge_client = genai.GenerativeModel("gemini-2.0-flash")
    judge_llm = llm_factory(
        "gemini-2.0-flash",
        provider="google",
        client=judge_client,
    )

    cases = load_cases()
    responses = []

    # Generate candidate answers for the evaluation cases.
    # This is a baseline harness; it does not invoke the ADK agent yet.
    for case in cases:
        candidate = generate_candidate_response(case, judge_client)

        responses.append(
            {
                "case_id": case["case_id"],
                "user_input": case["user_input"],
                "response": candidate,
                "contexts": case["evidence_context"],
                "expected_behavior": case["expected_behavior"],
            }
        )

    dataset = Dataset.from_list(
        [
            {
                "user_input": item["user_input"],
                "response": item["response"],
                "retrieved_contexts": item["contexts"],
            }
            for item in responses
        ]
    )

    # Faithfulness checks whether claims in the response are
    # supported by the supplied evidence.
    results = evaluate(
        dataset=dataset,
        metrics=[Faithfulness(llm=judge_llm)],
    )

    RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path = RESULTS_DIR / "ragas_scores.csv"

    results_df = results.to_pandas()
    results_df.insert(
        0,
        "case_id",
        [item["case_id"] for item in responses],
    )
    results_df["response"] = [
        item["response"] for item in responses
    ]

    results_df.to_csv(output_path, index=False)

    print("\nRAGAS evaluation completed.")
    print(results_df.to_string(index=False))
    print(f"\nResults saved to: {output_path}")


if __name__ == "__main__":
    main()
