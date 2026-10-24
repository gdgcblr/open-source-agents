"""
Configuration management for CodeLens.

Loads settings from environment variables (via .env file)
and provides a single Config object used across all modules.
"""

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv


@dataclass
class Config:
    """Central configuration for CodeLens."""

    gemini_api_key: str = ""
    gemini_model: str = "gemini-3.8-flash"
    output_dir: str = "./docs_output"
    log_level: str = "INFO"
    max_file_size: int = 524288  # 512KB

    # Directories and files to always skip during scanning
    ignore_dirs: set = field(default_factory=lambda: {
        ".git", "node_modules", "__pycache__", ".venv", "venv", "env",
        ".env", ".idea", ".vscode", ".vs", "dist", "build", "target",
        ".tox", ".mypy_cache", ".pytest_cache", ".coverage", "htmlcov",
        ".eggs", ".gradle", ".mvn", "vendor", "Pods",
        ".next", ".nuxt", ".output", ".cache", ".parcel-cache",
        "docs_output",  # Skip our own output directory
    })

    # Files to always skip during scanning
    ignore_files: set = field(default_factory=lambda: {
        ".DS_Store", "Thumbs.db", ".gitkeep",
        "package-lock.json", "yarn.lock", "poetry.lock",
        "Pipfile.lock", "pnpm-lock.yaml", "composer.lock",
        "Gemfile.lock", "Cargo.lock",
    })

    # File extensions to treat as source code
    source_extensions: dict = field(default_factory=lambda: {
        ".py": "python",
        ".js": "javascript",
        ".ts": "typescript",
        ".jsx": "javascript",
        ".tsx": "typescript",
        ".go": "go",
        ".rs": "rust",
        ".java": "java",
        ".rb": "ruby",
        ".php": "php",
        ".c": "c",
        ".cpp": "cpp",
        ".h": "c",
        ".hpp": "cpp",
        ".cs": "csharp",
        ".swift": "swift",
        ".kt": "kotlin",
        ".scala": "scala",
        ".sh": "shell",
        ".bash": "shell",
        ".ps1": "powershell",
        ".vue": "vue",
        ".svelte": "svelte",
    })

    # File extensions for config/data files (scanned but analyzed differently)
    config_extensions: dict = field(default_factory=lambda: {
        ".yaml": "yaml",
        ".yml": "yaml",
        ".json": "json",
        ".toml": "toml",
        ".ini": "ini",
        ".cfg": "ini",
        ".xml": "xml",
        ".env.example": "dotenv",
        ".dockerfile": "dockerfile",
        ".proto": "protobuf",
        ".graphql": "graphql",
    })

    # File extensions for documentation files
    doc_extensions: dict = field(default_factory=lambda: {
        ".md": "markdown",
        ".rst": "restructuredtext",
        ".txt": "text",
        ".html": "html",
        ".css": "css",
        ".scss": "scss",
    })


PLACEHOLDER_API_KEY = "your_gemini_api_key_here"


def load_config(env_path: str = None) -> Config:
    """
    Load configuration from .env file and environment variables.

    Searches for .env in:
    1. Explicit env_path (if provided)
    2. Current working directory
    3. Tool package root directory
    """
    if env_path and Path(env_path).exists():
        load_dotenv(dotenv_path=env_path)
    else:
        # Check current working directory
        cwd_env = Path.cwd() / ".env"
        # Check tool root directory
        tool_env = Path(__file__).resolve().parent.parent / ".env"

        if cwd_env.exists():
            load_dotenv(dotenv_path=cwd_env)
        elif tool_env.exists():
            load_dotenv(dotenv_path=tool_env)
        else:
            load_dotenv()

    config = Config(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.8-flash"),
        output_dir=os.getenv("OUTPUT_DIR", "./docs_output"),
        log_level=os.getenv("LOG_LEVEL", "INFO"),
        max_file_size=int(os.getenv("MAX_FILE_SIZE", "524288")),
    )

    return config


def validate_config(config: Config) -> list[str]:
    """
    Validate the configuration and return a list of error messages.
    Returns an empty list if all checks pass.
    """
    errors = []

    if not config.gemini_api_key or config.gemini_api_key == PLACEHOLDER_API_KEY:
        errors.append(
            "GEMINI_API_KEY is not set. "
            "Get your free API key from: https://aistudio.google.com/apikey "
            "and add it to your .env file."
        )

    return errors
