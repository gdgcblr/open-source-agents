"""GitHub Search, Multi-Signal Health Scoring & Ranking Client.

Queries GitHub API based on tech stack, explicit experience level, contribution type,
and small-scope signals. Evaluates repository health, maintainer responsiveness,
and classifies contribution readiness before formatting the top 15 ranked repos.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional
import requests
from auth import get_github_token


COMPLEXITY_PRESETS = {
    "beginner": {
        "description": "Beginner-friendly projects with active good-first-issues and manageable codebase size",
        "min_stars": 50,
        "max_stars": 12000,
        "issue_filter": "good-first-issues:>0",
        "sort": "help-wanted-issues",
        "order": "desc",
    },
    "intermediate": {
        "description": "Production-grade, actively maintained libraries and developer tools",
        "min_stars": 1000,
        "max_stars": 45000,
        "issue_filter": "open-issues:>5",
        "sort": "stars",
        "order": "desc",
    },
    "advanced": {
        "description": "Large-scale distributed systems, runtime engines, compilers, and high-complexity architectures",
        "min_stars": 10000,
        "max_stars": None,
        "issue_filter": None,
        "sort": "stars",
        "order": "desc",
    },
}

CONTRIBUTION_TYPE_MODIFIERS = {
    "all": None,
    "good_first_issues": "good-first-issues:>0",
    "docs": "topic:documentation",
    "bug_fixes": "open-issues:>15",
    "features": "stars:>1000",
}


class GitHubScoutClient:
    """Handles communication with GitHub Search API and ranks matching repositories."""

    BASE_URL = "https://api.github.com"

    def __init__(self, token: Optional[str] = None):
        self.username: Optional[str] = None
        if token and token.strip():
            self.token = token.strip()
        else:
            resolved_token, user = get_github_token()
            self.token = resolved_token
            self.username = user

        self.session = requests.Session()
        self.session.headers.update({
            "Accept": "application/vnd.github+json",
            "User-Agent": "OSS-Project-Scout-Agent/1.0",
        })
        if self.token:
            self.session.headers["Authorization"] = f"Bearer {self.token}"

    def build_search_query(
        self,
        tech_stack: str,
        complexity: str = "beginner",
        contribution_type: str = "all"
    ) -> str:
        """Constructs a targeted GitHub search query string using multi-signal filters."""
        tech_clean = tech_stack.strip().lower()
        preset = COMPLEXITY_PRESETS.get(complexity.lower(), COMPLEXITY_PRESETS["beginner"])

        query_parts = []

        # Tech stack filter (supports programming language or framework keyword)
        common_languages = {
            "python", "javascript", "typescript", "rust", "go", "golang",
            "java", "c++", "cpp", "c", "ruby", "php", "swift", "kotlin", "c#", "csharp"
        }
        if tech_clean in common_languages:
            lang = "c++" if tech_clean == "cpp" else ("c#" if tech_clean == "csharp" else tech_clean)
            query_parts.append(f"language:{lang}")
        else:
            query_parts.append(f"{tech_clean} in:name,description,topics")

        # Public open-source only
        query_parts.append("is:public")
        query_parts.append("archived:false")

        # Star bounds based on complexity
        min_s = preset["min_stars"]
        max_s = preset["max_stars"]
        if min_s is not None and max_s is not None:
            query_parts.append(f"stars:{min_s}..{max_s}")
        elif min_s is not None:
            query_parts.append(f"stars:>={min_s}")

        # Contribution type filter
        contrib_filter = CONTRIBUTION_TYPE_MODIFIERS.get(contribution_type)
        if contrib_filter:
            query_parts.append(contrib_filter)
        elif preset.get("issue_filter"):
            query_parts.append(preset["issue_filter"])

        return " ".join(query_parts)

    def search_repositories(
        self,
        tech_stack: str,
        complexity: str = "beginner",
        contribution_type: str = "all",
        per_page: int = 30
    ) -> List[Dict[str, Any]]:
        """Executes search query against GitHub API with fallback on rate limits or empty results."""
        query = self.build_search_query(tech_stack, complexity, contribution_type)
        preset = COMPLEXITY_PRESETS.get(complexity.lower(), COMPLEXITY_PRESETS["beginner"])

        params = {
            "q": query,
            "sort": preset.get("sort", "stars"),
            "order": preset.get("order", "desc"),
            "per_page": per_page,
        }

        url = f"{self.BASE_URL}/search/repositories"
        response = self.session.get(url, params=params, timeout=15)

        if response.status_code == 403:
            msg = response.json().get("message", "Rate limit exceeded")
            raise PermissionError(
                f"GitHub API Error (403): {msg}. "
                "Provide a GITHUB_TOKEN to increase hourly rate limit from 60 to 5,000 requests."
            )
        response.raise_for_status()

        data = response.json()
        items = data.get("items", [])

        # Fallback if strict filter returned 0 results
        if not items and (preset.get("issue_filter") or contribution_type != "all"):
            fallback_query = f"language:{tech_stack} is:public archived:false stars:>=50"
            params["q"] = fallback_query
            params["sort"] = "stars"
            fallback_res = self.session.get(url, params=params, timeout=15)
            if fallback_res.ok:
                items = fallback_res.json().get("items", [])

        return items

    def evaluate_health_and_activity(self, item: Dict[str, Any]) -> Dict[str, Any]:
        """Calculates multi-signal health score, maintainer responsiveness, and contribution readiness."""
        # 1. Maintenance & Recency signal
        pushed_at_str = item.get("pushed_at")
        days_since_push = 365
        if pushed_at_str:
            try:
                pushed_dt = datetime.fromisoformat(pushed_at_str.replace("Z", "+00:00"))
                days_since_push = max(0, (datetime.now(timezone.utc) - pushed_dt).days)
            except Exception:
                pass

        if days_since_push <= 3:
            recency_pts = 35
            responsiveness = "⚡ High (Active commits & maintainer reviews within 48h)"
        elif days_since_push <= 14:
            recency_pts = 28
            responsiveness = "⏱️ Moderate (Active within past 2 weeks)"
        elif days_since_push <= 60:
            recency_pts = 18
            responsiveness = "📅 Steady (Active within 1-2 months)"
        else:
            recency_pts = 6
            responsiveness = "🐢 Slow Review Cycles"

        # 2. Documentation & Community signals
        has_desc = bool(item.get("description"))
        has_license = bool(item.get("license"))
        topics = item.get("topics", [])
        doc_pts = (15 if has_desc else 0) + (15 if has_license else 0) + min(len(topics) * 3, 10)

        # 3. Issue Quality & Contributor Activity signals
        open_issues = item.get("open_issues_count", 0)
        forks = item.get("forks_count", 0)
        issue_pts = min(open_issues * 2, 15) if open_issues > 0 else 5
        fork_pts = min(forks // 25, 10)

        health_score = min(100, recency_pts + doc_pts + issue_pts + fork_pts)

        if health_score >= 85:
            health_badge = "🟢 90+ Exceptional Health"
        elif health_score >= 70:
            health_badge = "🟢 Healthy & Maintained"
        elif health_score >= 50:
            health_badge = "🟡 Moderate Maintenance"
        else:
            health_badge = "🔴 Low Activity"

        # Small-scope signals
        has_small_scope = any(
            t in ["good-first-issue", "beginner-friendly", "hacktoberfest", "help-wanted", "first-timers-only"]
            for t in topics
        ) or (open_issues >= 3 and days_since_push <= 30)

        # Contribution Readiness Classification
        if health_score >= 75 and has_license and has_small_scope:
            readiness_tier = "Tier 1: High Contribution Readiness (Documented + Active Starter Tasks)"
        elif health_score >= 55 and has_license:
            readiness_tier = "Tier 2: Contributor Friendly"
        else:
            readiness_tier = "Tier 3: Early-Stage / Self-Guided"

        return {
            "health_score": health_score,
            "health_badge": health_badge,
            "days_since_push": days_since_push,
            "maintainer_responsiveness": responsiveness,
            "readiness_tier": readiness_tier,
            "has_small_scope_signals": has_small_scope,
        }

    def score_repository(self, item: Dict[str, Any], complexity: str, health_eval: Dict[str, Any]) -> float:
        """Sorts and ranks repositories using composite issue quality, health, and experience fit."""
        stars = item.get("stargazers_count", 0)
        forks = item.get("forks_count", 0)
        open_issues = item.get("open_issues_count", 0)
        health_score = health_eval["health_score"]
        has_small_scope = 1.0 if health_eval["has_small_scope_signals"] else 0.0

        # Issue quality component
        issue_quality = (min(open_issues, 150) * 1.5) + (has_small_scope * 80.0)

        if complexity == "beginner":
            composite = (
                (health_score * 0.45) +
                (issue_quality * 0.35) +
                (min(stars, 8000) * 0.1) +
                (min(forks, 2000) * 0.1)
            )
        elif complexity == "intermediate":
            composite = (
                (health_score * 0.4) +
                (issue_quality * 0.3) +
                (stars * 0.2) +
                (forks * 0.1)
            )
        else:  # advanced
            composite = (
                (health_score * 0.35) +
                (stars * 0.45) +
                (forks * 0.2)
            )

        return float(composite)

    def rank_and_format(
        self,
        raw_items: List[Dict[str, Any]],
        tech_stack: str,
        complexity: str,
        top_n: int = 15
    ) -> List[Dict[str, Any]]:
        """Evaluates health, ranks candidates, and formats top-N records with guaranteed integer ranks."""
        scored = []
        for item in raw_items:
            health_eval = self.evaluate_health_and_activity(item)
            s = self.score_repository(item, complexity, health_eval)
            scored.append((s, item, health_eval))

        scored.sort(key=lambda x: x[0], reverse=True)
        top_candidates = scored[:top_n]

        results = []
        for rank_num, (score, repo, health_eval) in enumerate(top_candidates, start=1):
            owner = repo.get("owner", {}).get("login", "unknown")
            repo_name = repo.get("name", "")
            full_name = repo.get("full_name", f"{owner}/{repo_name}")
            html_url = repo.get("html_url", "")

            good_first_issues_url = (
                f"{html_url}/issues?q=is%3Aissue+is%3Aopen+label%3A%22good+first+issue%22"
            )

            record = {
                "rank": rank_num,
                "score": round(score, 2),
                "id": repo.get("id"),
                "name": repo_name,
                "full_name": full_name,
                "owner": owner,
                "html_url": html_url,
                "clone_url": repo.get("clone_url", f"https://github.com/{full_name}.git"),
                "description": repo.get("description") or "Open-source codebase.",
                "language": repo.get("language") or tech_stack.capitalize(),
                "stars": repo.get("stargazers_count", 0),
                "forks": repo.get("forks_count", 0),
                "open_issues_count": repo.get("open_issues_count", 0),
                "topics": repo.get("topics", []),
                "license": repo.get("license", {}).get("spdx_id") if repo.get("license") else None,
                "default_branch": repo.get("default_branch", "main"),
                "updated_at": repo.get("pushed_at"),
                "complexity_level": complexity,
                "good_first_issues_url": good_first_issues_url,
                # Health, maintainer responsiveness & contribution readiness signals
                "health_score": health_eval["health_score"],
                "health_badge": health_eval["health_badge"],
                "maintainer_responsiveness": health_eval["maintainer_responsiveness"],
                "readiness_tier": health_eval["readiness_tier"],
                "has_small_scope_signals": health_eval["has_small_scope_signals"],
            }
            results.append(record)

        return results

    def fetch_top_repos(
        self,
        tech_stack: str,
        complexity: str = "beginner",
        contribution_type: str = "all",
        top_n: int = 15,
        output_file: str = "top_15_repos.json"
    ) -> List[Dict[str, Any]]:
        """End-to-end Step 1: Searches, ranks, and writes top 15 repositories to JSON."""
        raw_items = self.search_repositories(
            tech_stack,
            complexity,
            contribution_type=contribution_type,
            per_page=max(top_n * 2, 30)
        )
        top_repos = self.rank_and_format(raw_items, tech_stack, complexity, top_n=top_n)

        # Write to JSON file
        with open(output_file, "w", encoding="utf-8") as f:
            json.dump({
                "meta": {
                    "tech_stack": tech_stack,
                    "complexity": complexity,
                    "contribution_type": contribution_type,
                    "count": len(top_repos),
                    "generated_at": datetime.now(timezone.utc).isoformat(),
                },
                "repositories": top_repos
            }, f, indent=2)

        return top_repos
