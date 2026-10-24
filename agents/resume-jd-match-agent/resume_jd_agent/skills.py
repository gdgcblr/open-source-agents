"""Skill catalog, aliases, and keyword matching patterns.

Contains ~175 standard tech, product, data, and engineering management skills,
along with case-sensitive aliases, stopword sets, and pre-compiled regexes.
"""

import re

# Canonical skill -> extra spellings that should count as the same skill.
# Matching is case-insensitive and on word boundaries.
SKILLS: dict[str, list[str]] = {
    # Programming languages
    "python": [],
    "java": [],
    "javascript": ["js"],
    "typescript": [],
    "c++": ["cpp"],
    "c#": ["csharp"],
    "golang": [],
    "rust": [],
    "kotlin": [],
    "swift": [],
    "scala": [],
    "ruby": [],
    "php": [],
    "sql": [],
    "bash": ["shell scripting"],
    "html": ["html5"],
    "css": ["css3"],
    # Frameworks and libraries
    "react": ["react.js", "reactjs"],
    "angular": [],
    "vue": ["vue.js", "vuejs"],
    "next.js": ["nextjs"],
    "node.js": ["nodejs", "node"],
    "express": ["express.js"],
    "django": [],
    "flask": [],
    "fastapi": [],
    "spring boot": [],
    "graphql": [],
    "rest api": ["rest apis", "restful"],
    "grpc": [],
    "microservices": ["microservice"],
    "redux": [],
    "webpack": ["vite"],
    "jest": ["react testing library"],
    "cypress": ["playwright"],
    "responsive design": ["responsive web design", "responsive"],
    "accessibility": ["wcag", "a11y"],
    "design system": ["design systems", "component library"],
    "server-side rendering": ["ssr", "server-side", "server components"],
    "event-driven architecture": ["event-driven"],
    "rabbitmq": [],
    # Cloud and infrastructure
    "aws": ["amazon web services"],
    "gcp": ["google cloud", "google cloud platform"],
    "azure": [],
    "docker": [],
    "kubernetes": ["k8s"],
    "terraform": [],
    "ci/cd": ["cicd", "continuous integration", "continuous delivery"],
    "jenkins": [],
    "github actions": [],
    "linux": [],
    "serverless": [],
    "cloud run": [],
    "bigquery": [],
    "snowflake": [],
    "redshift": [],
    "databricks": [],
    "dynamodb": [],
    "infrastructure as code": ["infrastructure-as-code", "iac"],
    "helm": [],
    "ansible": [],
    "gitops": ["argo cd", "argocd", "flux"],
    "prometheus": [],
    "grafana": [],
    "opentelemetry": [],
    "elk stack": ["elk", "kibana", "logstash"],
    "incident response": ["incident management", "on-call", "postmortems"],
    "slos": ["slo", "slis", "sla"],
    "cloud cost optimization": ["cost optimization", "finops"],
    # Databases and data
    "postgresql": ["postgres"],
    "mysql": [],
    "mongodb": ["mongo"],
    "redis": [],
    "elasticsearch": [],
    "kafka": [],
    "spark": ["apache spark", "pyspark"],
    "airflow": [],
    "dbt": [],
    "etl": ["elt"],
    "data pipelines": ["data pipeline"],
    "data warehouse": ["data warehousing"],
    "data modeling": ["data modelling"],
    "data analysis": ["data analytics"],
    "data visualization": ["data visualisation"],
    "tableau": [],
    "power bi": ["powerbi"],
    "looker": [],
    "excel": ["microsoft excel"],
    "pandas": [],
    "numpy": [],
    "statistics": ["statistical analysis"],
    "a/b testing": ["ab testing", "a/b tests", "split testing", "experimentation"],
    "sql queries": [],
    "mixpanel": [],
    "amplitude": [],
    "google analytics": [],
    # AI / ML
    "machine learning": ["ml"],
    "deep learning": [],
    "nlp": ["natural language processing"],
    "llm": ["llms", "large language models", "large language model"],
    "generative ai": ["genai", "gen ai"],
    "prompt engineering": [],
    "rag": ["retrieval augmented generation", "retrieval-augmented generation"],
    "tensorflow": [],
    "pytorch": [],
    "scikit-learn": ["sklearn"],
    "computer vision": [],
    "mlops": [],
    "vertex ai": [],
    # Engineering practices
    "git": ["github", "gitlab"],
    "unit testing": ["unit tests"],
    "integration testing": ["integration tests"],
    "test automation": ["automated testing", "end-to-end testing", "end-to-end tests", "e2e", "e2e tests"],
    "code review": ["code reviews"],
    "system design": [],
    "distributed systems": [],
    "api design": [],
    "observability": ["monitoring"],
    "performance optimization": ["performance tuning"],
    "security": ["application security"],
    "devops": [],
    "sre": ["site reliability"],
    "mobile development": ["android", "ios"],
    # Product
    "product management": ["product manager"],
    "product strategy": [],
    "product roadmap": ["roadmap", "roadmaps", "roadmapping"],
    "product discovery": [],
    "product requirements": ["prd", "prds", "product requirements document"],
    "user stories": ["user story"],
    "user research": ["customer research", "customer interviews"],
    "ux": ["user experience"],
    "ui": ["user interface"],
    "wireframing": ["wireframes"],
    "prototyping": ["prototypes"],
    "figma": [],
    "go-to-market": ["gtm", "go to market"],
    "market research": [],
    "competitive analysis": [],
    "kpis": ["kpi"],
    "okrs": ["okr"],
    "metrics": [],
    "funnel analysis": ["conversion funnel"],
    "growth": ["growth strategy"],
    "retention": [],
    "monetization": ["pricing"],
    "b2b": [],
    "b2c": [],
    "saas": [],
    "api products": ["platform products"],
    "backlog management": ["backlog", "backlog prioritization"],
    "prioritization": ["prioritisation"],
    "feature launches": ["product launches", "launches"],
    # Process and management
    "agile": [],
    "scrum": [],
    "kanban": [],
    "jira": [],
    "confluence": [],
    "sprint planning": [],
    "project management": [],
    "program management": [],
    "stakeholder management": ["stakeholders"],
    "cross-functional collaboration": ["cross-functional", "cross functional"],
    "leadership": ["led"],
    "mentoring": ["mentored", "mentorship"],
    "people management": ["team management", "direct reports"],
    "recruiting": ["interviewing candidates"],
    "communication": [],
    "presentation": ["presentations"],
    "problem solving": ["problem-solving"],
    "decision making": ["decision-making"],
    "budgeting": ["budget management", "budget ownership"],
    "risk management": [],
    "vendor management": [],
    "customer success": [],
    "documentation": ["technical writing"],
}

# Aliases that are only a skill when written in capitals ("REST" vs. "the
# rest of"). These are matched case-sensitively against the original text.
CASE_SENSITIVE_ALIASES: dict[str, list[str]] = {
    "rest api": ["REST"],
    "typescript": ["TS"],
}

# Single words that commonly start capitalised sentences or headings and
# should never be treated as the start of a skill phrase.
_PHRASE_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "in", "on", "at", "to", "for",
    "with", "by", "we", "you", "our", "your", "i", "my", "this", "that",
    "about", "what", "who", "how", "why", "when", "experience", "skills",
    "education", "summary", "responsibilities", "requirements", "qualifications",
}

_CAP_PHRASE_RE = re.compile(r"\b([A-Z][a-zA-Z0-9+#.]*(?:[ \-][A-Z][a-zA-Z0-9+#.]*){1,3})\b")


def _variant_pattern(term: str) -> re.Pattern:
    """Builds a case-insensitive regex that matches a term on word boundaries."""
    return re.compile(r"(?<![a-z0-9])" + re.escape(term) + r"(?![a-z0-9])")


# Each entry is (variant, pattern). The plain-substring check on `variant` runs
# first and is ~10x cheaper than the regex, so most patterns never execute.
_SKILL_PATTERNS: list[tuple[str, list[tuple[str, re.Pattern]]]] = [
    (skill, [(v, _variant_pattern(v)) for v in [skill, *variants]])
    for skill, variants in SKILLS.items()
]

_CASE_SENSITIVE_PATTERNS: list[tuple[str, list[tuple[str, re.Pattern]]]] = [
    (
        skill,
        [(v, re.compile(r"(?<![A-Za-z0-9])" + re.escape(v) + r"(?![A-Za-z0-9])")) for v in variants],
    )
    for skill, variants in CASE_SENSITIVE_ALIASES.items()
]

# Words that are capitalised in JDs but are not skills (titles, perks, fillers).
_GENERIC_JD_WORDS = {
    "experience", "strong", "excellent", "working", "knowledge", "familiarity",
    "exposure", "hands-on", "years", "total", "including", "team", "teams",
    "product", "products", "platform", "platforms", "manager", "managers",
    "senior", "junior", "associate", "lead", "engineer", "engineers", "role",
    "company", "customers", "merchants", "users", "business", "competitive",
    "salary", "health", "insurance", "hybrid", "remote", "work", "setup",
    "degree", "computer", "science", "background", "former", "technical",
    "skills", "plus", "bonus", "qualifications", "offer", "annual", "learning",
    "budget", "culture", "certification", "sponsorship", "family", "esops",
    "sde", "pm", "apm", "ii", "iii", "iv", "qa", "vp",
}

_JD_WORD = r"[A-Z][A-Za-z0-9+#./-]*[A-Za-z0-9+#]|[A-Z]{2,}"
_JD_PHRASE_RE = re.compile(rf"(?<![\w./-])((?:{_JD_WORD})(?: (?:{_JD_WORD}))*)(?![\w])")
_SKILL_WORDS = {w for skill, variants in SKILLS.items() for v in [skill, *variants] for w in v.split()}
