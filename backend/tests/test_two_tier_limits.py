import pytest

from app.knowledge.ingestion import replace_source_chunks
from app.knowledge.retrieval import search_case_and_global_knowledge
from app.models import ExperimentCase, KnowledgeSource, RetrievalResult


@pytest.mark.parametrize("top_k", [1, 2, 3, 5, 8])
def test_two_tier_context_and_trace_respect_top_k(db, top_k):
    case = ExperimentCase(title="Retrieval case", goal="Test", cavity_type="linear")
    db.add(case)
    db.flush()
    for index in range(8):
        source = KnowledgeSource(case_id=case.id if index >= 5 else None,
                                 title=f"Mirror record {index}", source_type="attachment" if index >= 5 else "global_attachment")
        db.add(source)
        replace_source_chunks(db, source, "Mirror alignment measurement protocol")
    db.commit()
    run, results = search_case_and_global_knowledge(db, query="Mirror alignment measurement", case_id=case.id, top_k=top_k)
    db.flush()
    assert len(results) == top_k
    assert db.query(RetrievalResult).filter_by(retrieval_run_id=run.id).count() == top_k
    assert [result.rank for result in results] == list(range(1, top_k + 1))
    if top_k >= 2:
        assert {result.scope for result in results} == {"global", "case"}
