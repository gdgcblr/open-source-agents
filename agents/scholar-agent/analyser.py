import os
from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from agents.scholar_agent.schemas import ResearchPaperArtifacts

SYSTEM_PROMPT = """You are a Principal AI Systems Engineer and Research Scientist.
Analyze the provided excerpts of a technical paper or whitepaper.

Produce:
1. Executive Summary: Core motivation, problem formulation, and key contributions.
2. Key Insights: 3 to 5 deep systems/algorithmic takeaways.
3. Tradeoffs & Limitations: Hardware bounds, KV-cache scaling, latency overheads, or failure cases.
4. Comparative Table: A clean benchmark or taxonomy table from the paper's experiments.
5. Mermaid Diagram: A valid Mermaid.js flowchart (starting with `flowchart TD` or `graph TD`) depicting the system architecture.

Adhere strictly to the requested JSON schema.
"""

class PaperAnalyzer:
    def __init__(self, model_name: str = "gpt-4o-mini", api_key: str = None, base_url: str = None):
        key = api_key or os.getenv("OPENAI_API_KEY") or os.getenv("GROQ_API_KEY", "EMPTY")
        url = base_url or os.getenv("OPENAI_BASE_URL", None)

        self.llm = ChatOpenAI(
            model=model_name,
            temperature=0.1,
            api_key=key,
            base_url=url
        ).with_structured_output(ResearchPaperArtifacts)

        self.prompt = ChatPromptTemplate.from_messages([
            ("system", SYSTEM_PROMPT),
            ("user", "Retrieved Paper Context:\n\n{context}\n\nPerform full structured analysis.")
        ])
        self.chain = self.prompt | self.llm

    def run(self, context: str) -> ResearchPaperArtifacts:
        return self.chain.invoke({"context": context})