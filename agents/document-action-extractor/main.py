import csv
from pathlib import Path

from extractor import extract_actions

BASE_DIR = Path(__file__).parent
SAMPLE_FILE = BASE_DIR / "sample_document.txt"
OUTPUT_FILE = BASE_DIR / "actions.csv"

FIELDS = ["task", "owner", "deadline", "priority", "evidence"]

# Fixed sample results make the demo reproducible and API-independent.
DEMO_ACTIONS = [
    {
        "task": "Prepare the presentation slides",
        "owner": "Priya",
        "deadline": "October 28",
        "priority": "Not specified",
        "evidence": "Priya will prepare the presentation slides by October 28.",
    },
    {
        "task": "Finish API testing",
        "owner": "Rahul",
        "deadline": "October 26",
        "priority": "Not specified",
        "evidence": "Rahul must finish API testing by October 26.",
    },
    {
        "task": "Submit the project proposal",
        "owner": "The team",
        "deadline": "October 30",
        "priority": "Not specified",
        "evidence": "The team should submit the project proposal by October 30.",
    },
    {
        "task": "Review the budget",
        "owner": "Not specified",
        "deadline": "Next Monday (date not resolved)",
        "priority": "Not specified",
        "evidence": "We will review the budget next Monday.",
    },
]


def print_actions(actions):
    if not actions:
        print("\nNo action items found.")
        return

    for number, action in enumerate(actions, start=1):
        print(f"\n{number}. {action['task']}")
        print(f"   Owner:    {action['owner']}")
        print(f"   Deadline: {action['deadline']}")
        print(f"   Priority: {action['priority']}")
        print(f"   Evidence: {action['evidence']}")


def export_csv(actions):
    with OUTPUT_FILE.open("w", newline="", encoding="utf-8") as file:
        writer = csv.DictWriter(file, fieldnames=FIELDS)
        writer.writeheader()
        writer.writerows(actions)
    print(f"Saved {len(actions)} action items to {OUTPUT_FILE}")


def main():
    print("\n=== AI Document Action Extractor ===")
    print("1. Offline demo (no API key required)")
    print("2. Extract sample notes using Gemini")
    print("3. Paste your own text and use Gemini")

    choice = input("Choose (1/2/3): ").strip()

    if choice == "1":
        print("\nRunning deterministic demo — no API call is made.")
        actions = DEMO_ACTIONS
    elif choice in {"2", "3"}:
        if choice == "2":
            document = SAMPLE_FILE.read_text(encoding="utf-8")
        else:
            print("Paste your text. Enter a line containing END when finished:")
            lines = []
            while True:
                try:
                    line = input()
                except EOFError:
                    break
                if line.strip() == "END":
                    break
                lines.append(line)
            document = "\n".join(lines)

        if not document.strip():
            print("No document text provided.")
            return

        try:
            actions = extract_actions(document)
        except Exception as exc:
            print(f"\nExtraction failed: {exc}")
            print("Check your local .env file, API key, internet, and model.")
            return
    else:
        print("Invalid choice.")
        return

    print_actions(actions)
    save = input("\nExport results to actions.csv? (y/n): ").strip().lower()
    if save == "y":
        export_csv(actions)


if __name__ == "__main__":
    main()
