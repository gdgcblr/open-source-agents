"""Codebase analyzer: scans repo structure, detects frameworks, extracts context."""

import os
import re
from pathlib import Path
from typing import Dict, List, Set, Tuple

from agentfeat.models.schemas import CodebaseSummary, FileContext
from agentfeat.utils.file_ops import get_file_tree, read_file_safe


class CodebaseAnalyzer:
    """Scans and analyzes target repository codebases to provide grounded context."""

    IGNORED_DIRS = {
        ".git", ".venv", "venv", "__pycache__", "node_modules",
        ".agentfeat_backup", ".pytest_cache", ".idea", ".vscode",
        "dist", "build", "coverage", ".next", ".nuxt", "target"
    }

    LANGUAGE_EXTENSIONS: Dict[str, str] = {
        ".py": "Python",
        ".ts": "TypeScript",
        ".tsx": "TypeScript (React)",
        ".js": "JavaScript",
        ".jsx": "JavaScript (React)",
        ".go": "Go",
        ".rs": "Rust",
        ".java": "Java",
        ".cpp": "C++",
        ".c": "C",
        ".rb": "Ruby",
        ".php": "PHP",
        ".sh": "Shell",
        ".html": "HTML",
        ".css": "CSS",
        ".json": "JSON",
        ".yaml": "YAML",
        ".yml": "YAML",
        ".toml": "TOML",
        ".md": "Markdown",
        ".sql": "SQL",
    }

    MANIFEST_PATTERNS = {
        "requirements.txt": "Python pip",
        "pyproject.toml": "Python PEP 621 / Poetry",
        "Pipfile": "Python Pipenv",
        "setup.py": "Python Setuptools",
        "package.json": "Node.js npm/yarn/pnpm",
        "go.mod": "Go Modules",
        "Cargo.toml": "Rust Cargo",
        "pom.xml": "Java Maven",
        "build.gradle": "Java Gradle",
    }

    def __init__(self, target_dir: Path) -> None:
        self.target_dir = target_dir.resolve()

    def analyze(self, feature_query: str = "") -> CodebaseSummary:
        """Scan the repository and return a structured summary."""
        languages: Set[str] = set()
        manifests: List[str] = []
        frameworks: Set[str] = set()
        all_candidate_files: List[Tuple[Path, str]] = []

        total_scanned = 0

        for root, dirs, files in os.walk(self.target_dir):
            # Prune ignored directories
            dirs[:] = [d for d in dirs if d not in self.IGNORED_DIRS and not d.startswith(".")]

            rel_root = Path(root).relative_to(self.target_dir)

            for file in files:
                if file.startswith("."):
                    continue

                total_scanned += 1
                file_path = Path(root) / file
                rel_path = (rel_root / file).as_posix() if str(rel_root) != "." else file

                # Detect manifests
                if file in self.MANIFEST_PATTERNS:
                    manifests.append(rel_path)

                # Detect language
                ext = file_path.suffix.lower()
                lang = self.LANGUAGE_EXTENSIONS.get(ext, "")
                if lang:
                    languages.add(lang)
                    all_candidate_files.append((file_path, rel_path))

        # Detect frameworks by inspecting manifests or imports
        frameworks = self._detect_frameworks(manifests)

        # Select most relevant files for the feature request
        relevant_file_contexts = self._select_relevant_files(
            all_candidate_files, feature_query, manifests
        )

        file_tree = get_file_tree(self.target_dir)

        return CodebaseSummary(
            root_path=str(self.target_dir),
            total_files=total_scanned,
            languages=sorted(list(languages)),
            frameworks=sorted(list(frameworks)),
            manifest_files=sorted(manifests),
            relevant_files=relevant_file_contexts,
            file_tree=file_tree,
        )

    def _detect_frameworks(self, manifests: List[str]) -> Set[str]:
        """Detect web/app frameworks from manifest contents."""
        detected = set()

        for rel_manifest in manifests:
            manifest_path = self.target_dir / rel_manifest
            content, _ = read_file_safe(manifest_path, max_bytes=50_000)
            content_lower = content.lower()

            patterns = {
                "fastapi": "FastAPI",
                "flask": "Flask",
                "django": "Django",
                "express": "Express",
                "react": "React",
                "next": "Next.js",
                "vue": "Vue.js",
                "google-genai": "Google GenAI SDK",
                "langchain": "LangChain",
                "crewai": "CrewAI",
                "torch": "PyTorch",
                "pytest": "pytest",
            }

            for needle, name in patterns.items():
                if re.search(rf"\b{needle}\b", content_lower):
                    detected.add(name)

        return detected

    def _select_relevant_files(
        self,
        candidates: List[Tuple[Path, str]],
        query: str,
        manifests: List[str],
        max_files: int = 8,
    ) -> List[FileContext]:
        """Rank and extract context from files most relevant to the feature query."""
        keywords = set(re.findall(r"\w+", query.lower())) if query else set()
        scored_files: List[Tuple[int, Path, str]] = []

        for full_path, rel_path in candidates:
            score = 0
            rel_lower = rel_path.lower()

            # Prioritize entry points and manifests
            if any(name in rel_lower for name in ["main", "app", "index", "cli", "server", "routes", "api"]):
                score += 5
            if rel_path in manifests:
                score += 4

            # Keyword matching against path
            for kw in keywords:
                if kw in rel_lower:
                    score += 10

            scored_files.append((score, full_path, rel_path))

        # Sort descending by score
        scored_files.sort(key=lambda x: x[0], reverse=True)
        selected = scored_files[:max_files]

        contexts = []
        for _, full_path, rel_path in selected:
            content, truncated = read_file_safe(full_path, max_bytes=8_000)
            ext = full_path.suffix.lower()
            lang = self.LANGUAGE_EXTENSIONS.get(ext, "Plain Text")
            contexts.append(
                FileContext(
                    path=rel_path,
                    size_bytes=full_path.stat().st_size if full_path.exists() else 0,
                    language=lang,
                    content=content,
                    is_truncated=truncated,
                )
            )

        return contexts
