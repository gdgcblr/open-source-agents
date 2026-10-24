
import os
from dotenv import load_dotenv
from langchain_ollama import ChatOllama
from langchain_core.prompts import PromptTemplate
from flask import Flask, request, jsonify, render_template

load_dotenv()
app = Flask(__name__)

llm = ChatOllama(
    model=os.getenv("OLLAMA_MODEL", "llama3.2:3b"),
    base_url=os.getenv("OLLAMA_BASE_URL", "http://localhost:11434"),
    temperature=0.7,
)

prompt = PromptTemplate.from_template(
    "You are an expert agricultural assistant helping farmers in Karnataka reduce post-harvest food loss. "
    "Please answer the following question clearly in Kannada: {question}"
)
chain = prompt | llm


@app.route('/')
def home():
    return render_template('index.html')


def extract_answer_text(payload):
    if payload is None:
        return ""
    if isinstance(payload, str):
        return payload.strip()
    if isinstance(payload, dict):
        for key in ("text", "answer", "content"):
            if key in payload:
                result = extract_answer_text(payload[key])
                if result:
                    return result
        return ""
    if isinstance(payload, list):
        parts = [extract_answer_text(item) for item in payload]
        return "\n".join(part for part in parts if part).strip()
    if hasattr(payload, "text"):
        return extract_answer_text(payload.text)
    if hasattr(payload, "content"):
        return extract_answer_text(payload.content)
    return str(payload).strip()


@app.route('/ask', methods=['GET', 'POST'])
def ask_assistant():
    if request.method == 'POST':
        data = request.get_json(silent=True) or {}
        question = data.get('question', '') if isinstance(data, dict) else ''
    else:
        question = request.args.get('question', '')

    if not question:
        return jsonify({"error": "No question provided. Use ?question=your_question in the browser."}), 400

    try:
        print(f"👉 Received question: {question}")
        print("⏳ Waiting for Ollama API to respond...")

        response = chain.invoke({"question": question})
        answer = extract_answer_text(response)

        if not answer:
            answer = str(response)

        print(f"✅ Response received: {answer[:120]}...")
        return jsonify({"answer": answer})
    except Exception as e:
        print(f"❌ Error occurred: {e}")
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🌾 Starting the Kannada Agri-Assistant...")
    print("🌐 Server URL: http://0.0.0.0:5000")
    app.run(host="0.0.0.0", port=5000, debug=False, use_reloader=False)