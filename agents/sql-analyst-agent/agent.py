import os
import sqlite3
import json
from dotenv import load_dotenv
from google import genai

load_dotenv()

DB_NAME = "company.db"
MODEL_NAME = "gemini-3.8-flash"

def init_mock_database():
    """Seeds an embedded SQLite database with realistic tables."""
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    
    cursor.execute("""
    CREATE TABLE IF NOT EXISTS employees (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        department TEXT NOT NULL,
        salary REAL NOT NULL,
        joined_date TEXT NOT NULL
    );
    """)

    cursor.execute("""
    CREATE TABLE IF NOT EXISTS projects (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        budget REAL NOT NULL,
        status TEXT NOT NULL
    );
    """)

    cursor.execute("SELECT COUNT(*) FROM employees;")
    if cursor.fetchone()[0] == 0:
        cursor.executemany("""
        INSERT INTO employees (name, department, salary, joined_date) VALUES (?, ?, ?, ?)
        """, [
            ("Alice Johnson", "Engineering", 115000, "2022-03-15"),
            ("Bob Smith", "Engineering", 95000, "2023-01-10"),
            ("Clara Oswald", "Product", 105000, "2021-06-01"),
            ("David Miller", "Marketing", 75000, "2023-08-20"),
            ("Elena Rostova", "Engineering", 125000, "2020-11-05")
        ])

        cursor.executemany("""
        INSERT INTO projects (name, budget, status) VALUES (?, ?, ?)
        """, [
            ("API Gateway Modernization", 45000, "Active"),
            ("Q4 Marketing Campaign", 15000, "Completed"),
            ("Data Pipeline Refactor", 30000, "Active")
        ])
        conn.commit()
    conn.close()

def get_schema_context() -> str:
    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    cursor.execute("SELECT sql FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    conn.close()
    return "\n".join([table[0] for table in tables if table[0]])

def execute_readonly_sql(query: str):
    """Executes SELECT queries safely and returns columns and row results."""
    clean_query = query.strip().rstrip(";")
    first_word = clean_query.split()[0].upper() if clean_query else ""
    if first_word not in ["SELECT", "WITH", "EXPLAIN"]:
        return {"error": "Security check failed: Only read-only queries are permitted."}

    conn = sqlite3.connect(DB_NAME)
    cursor = conn.cursor()
    try:
        cursor.execute(clean_query)
        columns = [description[0] for description in cursor.description] if cursor.description else []
        rows = cursor.fetchall()
        return {"columns": columns, "data": rows}
    except Exception as e:
        return {"error": str(e)}
    finally:
        conn.close()

def run_agent(question: str):
    api_key = os.getenv("GEMINI_API_KEY")
    if not api_key:
        print("[Error] GEMINI_API_KEY environment variable is missing.")
        return

    client = genai.Client(api_key=api_key)
    schema = get_schema_context()

    prompt = f"""
You are an expert SQL analyst. Given the SQLite database schema below, generate a valid SQL query to answer the user's question.

Schema:
{schema}

User Question: "{question}"

Rules:
1. Return ONLY pure SQLite SQL.
2. Do not enclose the query in markdown code blocks like ```sql.
3. Only use SELECT queries.
"""

    response = client.models.generate_content(
        model=MODEL_NAME,
        contents=prompt,
    )

    generated_sql = response.text.strip().replace("```sql", "").replace("```", "").strip()
    print(f"\n[Generated SQL]:\n  {generated_sql}\n")

    result = execute_readonly_sql(generated_sql)
    if "error" in result:
        print(f"[Execution Error]: {result['error']}")
        return

    summary_prompt = f"""
A user asked: "{question}"
Generated SQL: {generated_sql}
Database Output: {json.dumps(result)}

Summarize this result cleanly in natural, professional language.
"""
    summary = client.models.generate_content(
        model=MODEL_NAME,
        contents=summary_prompt,
    )

    print(f"[Analysis Result]:\n{summary.text}\n")

if __name__ == "__main__":
    init_mock_database()
    print("=== SQLite AI Analyst Agent Initialized ===")
    user_query = input("Ask a question about employees or projects (e.g. 'Who is the highest paid engineer?'): ")
    if not user_query.strip():
        user_query = "Who are the top 3 highest paid employees and what departments are they in?"
        print(f"Defaulting to: {user_query}")
    run_agent(user_query)