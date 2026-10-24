import argparse
import os
import sys
import logging
from pathlib import Path

import requests
from dotenv import load_dotenv

# Optional LLM imports – import lazily inside functions to avoid unnecessary dependencies if not used.

def setup_logging(level: str = "info"):
    numeric = getattr(logging, level.upper(), logging.INFO)
    logging.basicConfig(level=numeric, format="[%(levelname)s] %(message)s")

def parse_args():
    parser = argparse.ArgumentParser(description="Generate an automated PR review comment.")
    parser.add_argument("--pr", required=True, help="Full URL of the GitHub pull request, e.g. https://github.com/owner/repo/pull/42")
    parser.add_argument("--model", help="Model identifier (default from env MODEL_NAME)")
    parser.add_argument("--max-tokens", type=int, default=1024, help="Maximum tokens for the LLM response")
    parser.add_argument("--dry-run", action="store_true", help="Print the generated comment but do not post to GitHub")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    return parser.parse_args()

def extract_repo_info(pr_url: str):
    """Return (owner, repo, number) from a GitHub PR URL.
    Example: https://github.com/owner/repo/pull/42 -> (owner, repo, 42)
    """
    try:
        parts = pr_url.rstrip("/").split("/")
        number = int(parts[-1])
        repo = parts[-2]
        owner = parts[-3]
        return owner, repo, number
    except Exception as e:
        logging.error(f"Failed to parse PR URL '{pr_url}': {e}")
        sys.exit(1)

def fetch_pr_diff(owner: str, repo: str, number: int, token: str) -> str:
    """Fetch the unified diff for the given PR via GitHub API.
    Returns the diff as a string.
    """
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3.diff"}
    url = f"https://api.github.com/repos/{owner}/{repo}/pulls/{number}"  # GitHub returns diff if Accept header set
    resp = requests.get(url, headers=headers)
    if resp.status_code != 200:
        logging.error(f"GitHub API error {resp.status_code}: {resp.text}")
        sys.exit(1)
    return resp.text

def build_prompt(diff: str) -> str:
    """Construct a concise system/user prompt for the LLM.
    The prompt asks the model to act as a code reviewer.
    """
    prompt = (
        "You are an experienced software reviewer. Given the following Git diff, "
        "identify potential issues such as style problems, security concerns, missing tests, "
        "documentation gaps, or code smells. Produce a short markdown list of actionable review comments. "
        "Do not mention the diff itself, only the findings.\n\n"
        f"Diff:\n{diff}\n"
    )
    return prompt

def call_gemini(prompt: str, model_name: str, max_tokens: int) -> str:
    try:
        import google.generativeai as genai
    except ImportError:
        logging.error("google-generativeai not installed. Install via 'pip install google-generativeai'.")
        sys.exit(1)
    api_key = os.getenv("API_KEY")
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel(model_name)
    response = model.generate_content(
        prompt,
        generation_config=genai.types.GenerationConfig(
            max_output_tokens=max_tokens,
            temperature=0.7,
        ),
    )
    return response.text.strip()

def call_openai(prompt: str, model_name: str, max_tokens: int) -> str:
    try:
        import openai
    except ImportError:
        logging.error("openai package not installed. Install via 'pip install openai'.")
        sys.exit(1)
    api_key = os.getenv("API_KEY")
    openai.api_key = api_key
    resp = openai.ChatCompletion.create(
        model=model_name,
        messages=[{"role": "system", "content": "You are a helpful code reviewer."},
                  {"role": "user", "content": prompt}],
        max_tokens=max_tokens,
        temperature=0.7,
    )
    return resp.choices[0].message.content.strip()

def generate_review(diff: str, model_name: str, max_tokens: int) -> str:
    prompt = build_prompt(diff)
    if model_name.lower().startswith("gemini"):
        return call_gemini(prompt, model_name, max_tokens)
    else:
        # Assume OpenAI compatible model name
        return call_openai(prompt, model_name, max_tokens)

def post_review_comment(owner: str, repo: str, number: int, token: str, comment: str):
    url = f"https://api.github.com/repos/{owner}/{repo}/issues/{number}/comments"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github.v3+json"}
    payload = {"body": comment}
    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 201:
        logging.error(f"Failed to post comment: {resp.status_code} {resp.text}")
    else:
        logging.info("Comment posted successfully.")

def main():
    args = parse_args()
    if args.verbose:
        setup_logging("debug")
    else:
        setup_logging(os.getenv("LOG_LEVEL", "info"))

    load_dotenv()  # loads .env if present
    github_token = os.getenv("GITHUB_TOKEN")
    if not github_token:
        logging.error("GITHUB_TOKEN not set in environment.")
        sys.exit(1)
    model_name = args.model or os.getenv("MODEL_NAME", "gemini-1.5-flash")

    owner, repo, number = extract_repo_info(args.pr)
    logging.info(f"Fetching diff for {owner}/{repo} PR #{number} …")
    diff = fetch_pr_diff(owner, repo, number, github_token)
    if not diff.strip():
        logging.warning("Empty diff returned – nothing to review.")
        sys.exit(0)

    logging.info("Generating review …")
    review = generate_review(diff, model_name, args.max_tokens)
    markdown_comment = f"**Automated Review**\n\n{review}\n\n*Generated by PR Review Assistant using {model_name}.*"

    if args.dry_run:
        print("--- Generated Comment (dry‑run) ---\n")
        print(markdown_comment)
    else:
        logging.info("Posting comment to GitHub …")
        post_review_comment(owner, repo, number, github_token, markdown_comment)

if __name__ == "__main__":
    main()

