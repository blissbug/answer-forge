"""Small, dependency-free evaluation helpers for curated agent fixtures."""

from collections.abc import Iterable


def retrieval_metrics(rankings: Iterable[list[str]], expected_sources: Iterable[set[str]]) -> dict[str, float]:
    """Compute retrieval-only Recall@k and MRR from source identifiers."""
    pairs = list(zip(rankings, expected_sources, strict=True))
    if not pairs:
        return {"recall_at_1": 0.0, "recall_at_3": 0.0, "recall_at_5": 0.0, "mrr": 0.0}

    def recall_at(k: int) -> float:
        return sum(bool(set(ranking[:k]) & expected) for ranking, expected in pairs) / len(pairs)

    reciprocal_ranks = []
    for ranking, expected in pairs:
        rank = next((index + 1 for index, source in enumerate(ranking) if source in expected), None)
        reciprocal_ranks.append(1 / rank if rank else 0.0)
    return {"recall_at_1": recall_at(1), "recall_at_3": recall_at(3), "recall_at_5": recall_at(5), "mrr": sum(reciprocal_ranks) / len(reciprocal_ranks)}


def end_to_end_metrics(results: Iterable[dict[str, object]]) -> dict[str, float]:
    """Score grounded outcomes without mixing them into retrieval quality."""
    rows = list(results)
    if not rows:
        return {"evidence_status_accuracy": 0.0, "abstention_accuracy": 0.0, "expected_source_recall": 0.0, "unsupported_claim_rate": 0.0, "citation_correctness": 0.0}

    def average(key: str) -> float:
        return sum(bool(row.get(key)) for row in rows) / len(rows)

    unsupported = sum(int(row.get("unsupported_claim_count", 0)) for row in rows)
    claims = sum(int(row.get("material_claim_count", 0)) for row in rows)
    return {
        "evidence_status_accuracy": average("evidence_status_correct"),
        "abstention_accuracy": average("abstention_correct"),
        "expected_source_recall": average("expected_source_found"),
        "unsupported_claim_rate": unsupported / claims if claims else 0.0,
        "citation_correctness": average("citations_correct"),
    }
