#!/usr/bin/env python3
"""
DARIO Composite Memory Scoring — Weighted retrieval ranking (CrewAI-inspired).
================================================================================
Scores RAG results by: similarity*0.5 + recency*0.3 + importance*0.2
with hierarchical scoping (global → project → task).

Replaces raw similarity-only RAG search with multi-signal ranking.

Usage:
    from composite_memory_scoring import score_and_rank, MemoryScorer

    scorer = MemoryScorer(weights={"similarity": 0.5, "recency": 0.3, "importance": 0.2})
    ranked = scorer.rank(results, scope="project/mar-brasa")

    # Or standalone
    python composite_memory_scoring.py --query "brand positioning" --scope mar-brasa --json
"""

import json
import logging
import math
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

logging.basicConfig(level=logging.INFO, format="[%(levelname)s] %(message)s")
log = logging.getLogger("memory_scoring")

# Default weights
DEFAULT_WEIGHTS = {
    "similarity": 0.50,
    "recency": 0.30,
    "importance": 0.20,
}

# Importance keywords → boost
IMPORTANCE_KEYWORDS = {
    "critico": 1.0,
    "critical": 1.0,
    "decisao": 0.9,
    "decision": 0.9,
    "bloqueado": 0.8,
    "blocked": 0.8,
    "cliente": 0.7,
    "client": 0.7,
    "orcamento": 0.7,
    "budget": 0.7,
    "prazo": 0.6,
    "deadline": 0.6,
    "legal": 0.8,
    "contrato": 0.8,
    "contract": 0.8,
}

# Scope priority: more specific = higher boost
SCOPE_PRIORITY = {
    "task": 1.0,      # Exact task context
    "project": 0.8,   # Same project
    "client": 0.6,    # Same client
    "skill": 0.5,     # Same skill type
    "global": 0.3,    # General knowledge
}


@dataclass
class ScoredResult:
    """A RAG result with composite score."""
    content: str
    source: str = ""
    similarity: float = 0.0
    recency_score: float = 0.0
    importance_score: float = 0.0
    scope_boost: float = 0.0
    composite_score: float = 0.0
    metadata: dict = None

    def __post_init__(self):
        if self.metadata is None:
            self.metadata = {}


class MemoryScorer:
    """Composite memory scoring engine."""

    def __init__(self, weights: dict = None):
        self.weights = weights or DEFAULT_WEIGHTS.copy()

    def _calc_recency(self, timestamp: str = "", max_age_days: int = 90) -> float:
        """Calculate recency score (1.0 = just now, 0.0 = very old)."""
        if not timestamp:
            return 0.5  # Unknown age = middle score

        try:
            if isinstance(timestamp, (int, float)):
                created = datetime.fromtimestamp(timestamp, tz=timezone.utc)
            else:
                created = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))

            age_days = (datetime.now(timezone.utc) - created).days
            # Exponential decay: half-life of 30 days
            score = math.exp(-0.693 * age_days / 30)
            return max(0.0, min(1.0, score))
        except Exception:
            return 0.5

    def _calc_importance(self, content: str, source: str = "") -> float:
        """Calculate importance score based on content keywords."""
        if not content:
            return 0.3

        content_lower = content.lower()
        max_importance = 0.3  # Base importance

        for keyword, weight in IMPORTANCE_KEYWORDS.items():
            if keyword in content_lower:
                max_importance = max(max_importance, weight)

        return max_importance

    def _calc_scope_boost(self, result_scope: str, query_scope: str) -> float:
        """Calculate scope affinity boost."""
        if not query_scope or not result_scope:
            return SCOPE_PRIORITY.get("global", 0.3)

        # Exact match
        if result_scope == query_scope:
            return 1.0

        # Hierarchical match (e.g., result is project-level, query is task-level)
        if query_scope.startswith(result_scope):
            return 0.8

        return SCOPE_PRIORITY.get("global", 0.3)

    def score(self, result: dict, query_scope: str = "") -> ScoredResult:
        """Score a single RAG result."""
        content = result.get("content", result.get("text", result.get("chunk", "")))
        source = result.get("source", result.get("name", ""))
        similarity = result.get("similarity", result.get("score", 0.5))
        timestamp = result.get("created_at", result.get("timestamp", ""))
        result_scope = result.get("scope", result.get("collection", "global"))

        recency = self._calc_recency(timestamp)
        importance = self._calc_importance(content, source)
        scope_boost = self._calc_scope_boost(result_scope, query_scope)

        # Weighted composite
        composite = (
            similarity * self.weights["similarity"] +
            recency * self.weights["recency"] +
            importance * self.weights["importance"] +
            scope_boost * 0.1  # Small scope boost on top
        )

        return ScoredResult(
            content=content,
            source=source,
            similarity=round(similarity, 3),
            recency_score=round(recency, 3),
            importance_score=round(importance, 3),
            scope_boost=round(scope_boost, 3),
            composite_score=round(composite, 3),
            metadata=result.get("metadata", {}),
        )

    def rank(self, results: list[dict], query_scope: str = "", limit: int = 10) -> list[ScoredResult]:
        """Score and rank a list of RAG results."""
        scored = [self.score(r, query_scope) for r in results]
        scored.sort(key=lambda s: s.composite_score, reverse=True)
        return scored[:limit]

    def rank_and_trim(self, results: list[dict], query_scope: str = "",
                      token_budget: int = 4000, avg_tokens_per_chunk: int = 200) -> list[ScoredResult]:
        """Rank and trim to fit within token budget."""
        ranked = self.rank(results, query_scope, limit=50)

        # Trim to budget
        max_chunks = token_budget // avg_tokens_per_chunk
        return ranked[:max_chunks]


# Singleton
_scorer = MemoryScorer()

def get_scorer() -> MemoryScorer:
    return _scorer

def score_and_rank(results: list[dict], scope: str = "", limit: int = 10) -> list[dict]:
    """Convenience function: score, rank, return as dicts."""
    ranked = _scorer.rank(results, scope, limit)
    return [
        {
            "content": r.content,
            "source": r.source,
            "similarity": r.similarity,
            "recency": r.recency_score,
            "importance": r.importance_score,
            "scope_boost": r.scope_boost,
            "composite": r.composite_score,
        }
        for r in ranked
    ]


if __name__ == "__main__":
    print("=== Composite Memory Scoring ===\n")

    # Test data
    test_results = [
        {"content": "Brand positioning para restaurante critico deadline proximo", "similarity": 0.85, "created_at": "2026-05-05T10:00:00Z", "scope": "mar-brasa"},
        {"content": "SEO audit generico sem urgencia particular", "similarity": 0.90, "created_at": "2026-03-15T10:00:00Z", "scope": "global"},
        {"content": "Decisao de orcamento contrato cliente prioritario", "similarity": 0.75, "created_at": "2026-05-04T10:00:00Z", "scope": "mar-brasa"},
        {"content": "Tutorial sobre WordPress basico", "similarity": 0.70, "created_at": "2026-01-01T10:00:00Z", "scope": "global"},
    ]

    ranked = score_and_rank(test_results, scope="mar-brasa")
    print(f"Ranked {len(ranked)} results (scope: mar-brasa):\n")
    for i, r in enumerate(ranked):
        print(f"  {i+1}. composite={r['composite']:.3f} | sim={r['similarity']:.2f} rec={r['recency']:.2f} imp={r['importance']:.2f} scope={r['scope_boost']:.2f}")
        print(f"     {r['content'][:60]}...")
        print()
