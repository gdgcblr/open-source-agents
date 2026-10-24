"""
PDF Q&A Agent - Ask questions about any PDF using Google Gemini API.

Usage:
    python main.py path/to/your/file.pdf
    python main.py report.pdf --model gemini-1.5-pro
"""

import os
import sys
import argparse
import threading
import itertools
import time
from dotenv import load_dotenv

# Load environment variables from .env file
load_dotenv()


def spinner(stop_event: threading.Event, message: str = "Thinking"):
    """Show an animated spinner while waiting for API response."""
    for frame in itertools.cycle(["⠋", "⠙", "⠹", "⠸", "⠼", "⠴", "⠦", "⠧", "⠇", "⠏"]):
        if stop_event.is_set():
            break
        sys.stdout.write(f"\r{message}... {frame} ")
        sys.stdout.flush()
        time.sleep(0.1)
    sys.stdout.write("\r" + " " * 30 + "\r")  # clear the spinner line
    sys.stdout.flush()


def extract_text_from_pdf(pdf_path: str) -> str:
    """Extract all text content from a PDF file using pdfplumber."""
    try:
        import pdfplumber
    except ImportError:
        print("Error: pdfplumber is not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    text = ""
    with pdfplumber.open(pdf_path) as pdf:
        total_pages = len(pdf.pages)
        print(f"   Reading {total_pages} page(s)...")
        for i, page in enumerate(pdf.pages, 1):
            page_text = page.extract_text()
            if page_text:
                text += page_text + "\n"
    return text.strip()


def ask_gemini(client, model_name: str, pdf_text: str, question: str, chat_history: list) -> str:
    """Send a question about the PDF content to Gemini with conversation context."""
    history_text = ""
    if chat_history:
        history_text = "\nPrevious conversation:\n"
        for turn in chat_history[-4:]:
            history_text += f"Q: {turn['question']}\nA: {turn['answer']}\n\n"

    prompt = f"""You are a helpful assistant that answers questions based strictly on the provided PDF content.

Rules:
- Only use information from the PDF content below to answer.
- If the answer is not in the PDF, clearly say: "I could not find that information in this PDF."
- Be concise and accurate.
- Quote relevant sections when helpful.
{history_text}
--- PDF CONTENT START ---
{pdf_text[:20000]}
--- PDF CONTENT END ---

Question: {question}

Answer:"""

    # Retry up to 3 times on 503 / server errors
    max_retries = 3
    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(model=model_name, contents=prompt)
            return response.text.strip()
        except Exception as e:
            err = str(e)
            if "503" in err or "UNAVAILABLE" in err:
                wait = 5 * (attempt + 1)
                sys.stdout.write(f"\r  Model busy, retrying in {wait}s... ({attempt+1}/{max_retries})")
                sys.stdout.flush()
                time.sleep(wait)
            else:
                raise  # re-raise non-503 errors immediately
    raise Exception("Model is currently unavailable after 3 retries. Please try again in a moment.")


def main():
    parser = argparse.ArgumentParser(
        description="PDF Q&A Agent - Ask questions about any PDF using Google Gemini",
        epilog="Example: python main.py report.pdf"
    )
    parser.add_argument("pdf_path", help="Path to the PDF file you want to query")
    parser.add_argument(
        "--model",
        default="gemini-flash-latest",
        help="Gemini model to use (default: gemini-flash-latest)"
    )
    args = parser.parse_args()

    # Validate PDF path
    if not os.path.exists(args.pdf_path):
        print(f"Error: File not found: {args.pdf_path}")
        sys.exit(1)

    if not args.pdf_path.lower().endswith(".pdf"):
        print("Error: The file must be a PDF (.pdf extension required).")
        sys.exit(1)

    # Load API key
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("Error: GEMINI_API_KEY is not set.")
        print("  1. Copy .env.example to .env")
        print("  2. Add your key: GEMINI_API_KEY=your_key_here")
        print("  3. Get a free key at: https://aistudio.google.com/apikey")
        sys.exit(1)

    # Configure Gemini
    try:
        from google import genai
    except ImportError:
        print("Error: google-genai not installed. Run: pip install -r requirements.txt")
        sys.exit(1)

    client = genai.Client(api_key=api_key)

    # Load PDF
    print(f"\nLoading PDF: {args.pdf_path}")
    try:
        pdf_text = extract_text_from_pdf(args.pdf_path)
    except Exception as e:
        print(f"Error reading PDF: {e}")
        sys.exit(1)

    if not pdf_text:
        print("Error: No text could be extracted from this PDF.")
        print("  The PDF may be image-based or scanned (OCR not supported).")
        sys.exit(1)

    word_count = len(pdf_text.split())
    char_count = len(pdf_text)
    print(f"PDF loaded successfully! ({word_count:,} words, {char_count:,} characters)")

    if char_count > 30000:
        print("Note: Large PDF detected. Only the first ~30,000 characters will be sent per query.")

    print(f"\nModel: {args.model}")
    print("Ask any question about your PDF. Type 'quit' to exit.")
    print("=" * 60)

    chat_history = []

    while True:
        print()
        try:
            question = input("Your question: ").strip()
        except (KeyboardInterrupt, EOFError):
            print("\n\nGoodbye!")
            break

        if not question:
            print("  (Please enter a question)")
            continue

        if question.lower() in ("quit", "exit", "q", "bye"):
            print("Goodbye!")
            break

        stop_event = threading.Event()
        spin_thread = threading.Thread(target=spinner, args=(stop_event, "Thinking"))
        spin_thread.start()
        try:
            answer = ask_gemini(client, args.model, pdf_text, question, chat_history)
            stop_event.set()
            spin_thread.join()
            print(f"\nAnswer:\n{answer}")
            print("\n" + "-" * 60)
            chat_history.append({"question": question, "answer": answer})
        except Exception as e:
            stop_event.set()
            spin_thread.join()
            print(f"Error: {e}")
            print("  Check your API key and internet connection.")


if __name__ == "__main__":
    main()
