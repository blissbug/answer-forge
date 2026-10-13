from app.services.evaluation import end_to_end_metrics, retrieval_metrics


def test_retrieval_metrics_keep_rank_quality_separate() -> None:
    metrics = retrieval_metrics([["a", "b"], ["c", "d"]], [{"a"}, {"d"}])
    assert metrics == {"recall_at_1": 0.5, "recall_at_3": 1.0, "recall_at_5": 1.0, "mrr": 0.75}


def test_end_to_end_metrics_measure_grounding_and_abstention() -> None:
    metrics = end_to_end_metrics([
        {"evidence_status_correct": True, "abstention_correct": True, "expected_source_found": True, "citations_correct": True, "unsupported_claim_count": 0, "material_claim_count": 2},
        {"evidence_status_correct": False, "abstention_correct": True, "expected_source_found": False, "citations_correct": False, "unsupported_claim_count": 1, "material_claim_count": 2},
    ])
    assert metrics["evidence_status_accuracy"] == 0.5
    assert metrics["abstention_accuracy"] == 1.0
    assert metrics["expected_source_recall"] == 0.5
    assert metrics["unsupported_claim_rate"] == 0.25
    assert metrics["citation_correctness"] == 0.5
