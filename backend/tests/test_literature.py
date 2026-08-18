# -*- coding: utf-8 -*-
"""Literature search: parsers against recorded payloads, dedup invariants,
honesty of the three statuses, and all three entry paths (standalone endpoint,
case module, agent task + chat routing).

No test here touches the network: real-source parsers eat recorded fixtures
through the monkeypatched HTTP seams; everything end-to-end runs on the mock
source (conftest sets LITERATURE_PROVIDERS=mock).
"""
import pytest

from app.literature import providers as prov
from app.literature.records import PaperRecord, dedup_records, normalize_doi, to_bibtex
from app.literature.service import run_literature_search


# --- parsers against recorded payloads ----------------------------------------

OPENALEX_FIXTURE = {
    "results": [
        {
            "display_name": "Passively Q-switched Nd:YAG laser",
            "publication_year": 2018,
            "cited_by_count": 42,
            "doi": "https://doi.org/10.1000/test.1",
            "ids": {"openalex": "https://openalex.org/W1"},
            "primary_location": {"source": {"display_name": "Optics Letters"}},
            "best_oa_location": {"pdf_url": "https://example.org/paper.pdf"},
            "authorships": [
                {"author": {"display_name": "Alice Zhang"}},
                {"author": {"display_name": "Bob Li"}},
            ],
            # Deliberately out of order: reconstruction must sort by position.
            "abstract_inverted_index": {"laser": [2], "A": [0], "Q-switched": [1]},
        }
    ]
}

ARXIV_FIXTURE = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <id>http://arxiv.org/abs/1901.00001v2</id>
    <title>Thermal lensing in  diode-pumped
      lasers</title>
    <summary>  We measure thermal
      lensing.  </summary>
    <published>2019-01-01T00:00:00Z</published>
    <author><name>Carol Wu</name></author>
    <author><name>Dave Chen</name></author>
    <link title="pdf" href="http://arxiv.org/pdf/1901.00001v2" rel="related"/>
  </entry>
</feed>
"""


def test_openalex_parser_reads_the_recorded_payload(monkeypatch):
    monkeypatch.setattr(prov, "_http_get_json", lambda url, params, timeout_s: OPENALEX_FIXTURE)
    records = prov.OpenAlexProvider().search("q", max_results=10, year_from=None,
                                             sort="relevance", timeout_s=1)
    assert len(records) == 1
    paper = records[0]
    assert paper.title == "Passively Q-switched Nd:YAG laser"
    assert paper.venue == "Optics Letters"
    assert paper.cited_by == 42
    assert paper.pdf_url == "https://example.org/paper.pdf"
    assert paper.authors == ["Alice Zhang", "Bob Li"]
    assert paper.abstract == "A Q-switched laser", "inverted index must be re-ordered by position"


def test_arxiv_parser_reads_namespaced_atom(monkeypatch):
    monkeypatch.setattr(prov, "_http_get_text", lambda url, params, timeout_s: ARXIV_FIXTURE)
    records = prov.ArxivProvider().search("q", max_results=10, year_from=None,
                                          sort="relevance", timeout_s=1)
    assert len(records) == 1
    paper = records[0]
    assert paper.title == "Thermal lensing in diode-pumped lasers", "whitespace must be collapsed"
    assert paper.arxiv_id == "1901.00001v2"
    assert paper.year == 2019
    assert paper.pdf_url == "http://arxiv.org/pdf/1901.00001v2"
    assert paper.venue is None, "a preprint has no journal; inventing one would be a lie"
    assert paper.abstract == "We measure thermal lensing."


# --- dedup invariants ---------------------------------------------------------

def test_doi_case_and_prefix_variants_collapse():
    a = PaperRecord(title="Same paper", doi="https://doi.org/10.1000/X.1", source="openalex",
                    cited_by=10)
    b = PaperRecord(title="Same Paper!", doi="10.1000/x.1", source="arxiv",
                    arxiv_id="2001.1", pdf_url="p.pdf")
    merged = dedup_records([a, b])
    assert len(merged) == 1
    # The merge keeps the richer base and absorbs the other's fields.
    assert merged[0].cited_by == 10
    assert merged[0].arxiv_id == "2001.1"
    assert merged[0].pdf_url == "p.pdf"


def test_doiless_records_collapse_on_normalized_title():
    a = PaperRecord(title="Thermal Lensing, in Nd:YAG.", source="arxiv")
    b = PaperRecord(title="thermal lensing in nd:yag", source="openalex", year=2020)
    merged = dedup_records([a, b])
    assert len(merged) == 1
    assert merged[0].year == 2020


def test_different_papers_stay_apart():
    a = PaperRecord(title="Paper A", doi="10.1/a")
    b = PaperRecord(title="Paper B", doi="10.1/b")
    assert len(dedup_records([a, b])) == 2


def test_normalize_doi():
    assert normalize_doi("HTTPS://DOI.ORG/10.1000/AbC") == "10.1000/abc"
    assert normalize_doi("doi:10.1/x") == "10.1/x"
    assert normalize_doi(None) is None


def test_bibtex_has_the_identifying_fields():
    entry = to_bibtex(PaperRecord(title="T {x}", authors=["Alice Zhang"], year=2020,
                                  venue="OL", doi="10.1/x"))
    assert "@article{zhang2020" in entry
    assert "doi = {10.1/x}" in entry
    assert "{" not in entry.split("title = ")[1].split("\n")[0].replace("{T x},", "")


# --- service honesty ----------------------------------------------------------

class _Boom:
    name = "boom"

    def search(self, *args, **kwargs):
        raise TimeoutError("simulated network failure")


def test_all_sources_failing_is_a_failure_not_an_empty_success(monkeypatch):
    monkeypatch.setattr(prov, "build_providers", lambda csv=None: ([_Boom()], []))
    import app.literature.service as service
    monkeypatch.setattr(service, "build_providers", lambda csv=None: ([_Boom()], []))
    result = run_literature_search({"query": "anything"})
    assert result["status"] == "failed"
    assert "检索失败" in result["message"]


def test_one_source_failing_keeps_the_other_and_says_so(monkeypatch):
    import app.literature.service as service
    good = prov.MockProvider()
    monkeypatch.setattr(service, "build_providers", lambda csv=None: ([good, _Boom()], []))
    result = run_literature_search({"query": "laser"})
    assert result["status"] == "completed"
    assert result["papers"], "the healthy source's records must survive"
    assert any("boom" in err for err in result["source_errors"])


def test_no_query_anywhere_is_needs_input_in_chinese():
    result = run_literature_search({}, case_params=None, goal=None)
    assert result["status"] == "needs_input"
    assert "检索关键词" in result["message"]


def test_query_falls_back_to_the_chat_sentence():
    result = run_literature_search({}, goal="帮我找几篇LBO相位匹配的论文")
    assert result["status"] == "completed"
    assert result["query_source"] == "goal"
    assert "LBO" in result["query"]
    assert "帮我" not in result["query"] and "论文" not in result["query"]


def test_query_falls_back_to_case_physics():
    case = {"title": "1064 案例", "goal": "", "parameters":
            {"laser_wavelength_nm": 1064, "nonlinear_crystal": "LBO"}}
    result = run_literature_search({}, case_params=case)
    assert result["status"] == "completed"
    assert result["query_source"] == "case"
    assert "1064" in result["query"] and "LBO" in result["query"]


def test_max_results_is_hard_capped():
    result = run_literature_search({"query": "x", "max_results": 9999})
    assert len(result["papers"]) <= 50


def test_dedup_runs_in_the_service():
    """The mock source deliberately returns a DOI duplicate pair."""
    result = run_literature_search({"query": "x"})
    dois = [p["doi"] and p["doi"].lower().replace("https://doi.org/", "")
            for p in result["papers"] if p["doi"]]
    assert len(dois) == len(set(dois))


def test_result_carries_the_full_text_disclaimer():
    result = run_literature_search({"query": "x"})
    assert "未读取" in result["disclaimer"]
    assert result["bibliography"], "readable citation lines feed the RAG chunks"


# --- REST: standalone endpoint + case module ----------------------------------

def _make_case(client, parameters=None):
    resp = client.post("/api/cases", json={
        "title": "文献检索测试", "cavity_type": "linear", "goal": "找参考文献",
        "parameters": parameters or {},
    })
    assert resp.status_code in (200, 201), resp.text
    return resp.json()["id"]


def test_standalone_endpoint_searches_without_a_case(client):
    resp = client.post("/api/literature/search", json={"query": "Nd:YAG Q-switching"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "completed"
    assert body["papers"]
    assert body["papers"][0]["bibtex"].startswith("@")


def test_module_create_and_run(client):
    case_id = _make_case(client)
    module = client.post(f"/api/cases/{case_id}/modules",
                         json={"module_type": "literature_search"}).json()
    run = client.post(f"/api/cases/modules/{module['id']}/run",
                      json={"config_json": {"query": "thermal lensing"}})
    assert run.status_code == 200, run.text
    result = run.json()["result_json"]
    assert result["status"] == "completed"
    assert run.json()["result_json"].get("papers")
    assert "generated_content_id" in result, "module results must archive as generated content"


def test_unknown_module_type_is_still_rejected(client):
    case_id = _make_case(client)
    resp = client.post(f"/api/cases/{case_id}/modules", json={"module_type": "nonsense"})
    assert resp.status_code == 422


# --- agent task + chat routing ------------------------------------------------

def test_agent_task_runs_the_search_tool(client):
    case_id = _make_case(client)
    task = client.post("/api/agent/tasks", json={
        "case_id": case_id, "goal": "帮我找几篇关于LBO相位匹配的文献", "mode": "literature_search",
    })
    assert task.status_code in (200, 201), task.text
    body = task.json()
    tool_names = [c["tool_name"] for c in body["tool_calls"]]
    assert "search_literature" in tool_names
    search = next(c for c in body["tool_calls"] if c["tool_name"] == "search_literature")
    assert search["status"] == "completed"
    assert "LBO" in search["output_json"]["query"], "the chat sentence must seed the query"
    assert body["final_content_id"], "the result must be archived"


def test_chat_routes_literature_over_the_physics_topic_it_mentions(client):
    """Pins the position-first decision: the sentence also contains 相位匹配."""
    case_id = _make_case(client)
    resp = client.post("/api/agent/chat", json={
        "case_id": case_id, "message": "帮我找几篇关于LBO相位匹配的文献",
    })
    assert resp.status_code == 200, resp.text
    assert resp.json()["routed_mode"] == "literature_search"


def test_chat_routes_the_fused_verb(client):
    case_id = _make_case(client)
    resp = client.post("/api/agent/chat", json={
        "case_id": case_id, "message": "帮我检索文献,主题是被动调Q",
    })
    assert resp.json()["routed_mode"] == "literature_search"


def test_chat_without_intent_stays_chat(client):
    case_id = _make_case(client)
    resp = client.post("/api/agent/chat", json={
        "case_id": case_id, "message": "文献综述有什么写作技巧",
    })
    assert resp.json()["routed_mode"] == "chat"


@pytest.mark.parametrize("message,mode", [
    ("帮我设计一个谐振腔，算一下腔长和束腰", "cavity_design"),
    ("帮我算LBO的相位匹配角", "phase_match"),
    ("生成实验报告", "report"),
    ("谐振腔是什么原理？", "chat"),
])
def test_existing_routes_are_unchanged(client, message, mode):
    case_id = _make_case(client)
    resp = client.post("/api/agent/chat", json={"case_id": case_id, "message": message})
    assert resp.json()["routed_mode"] == mode


# --- RAG closes the loop ------------------------------------------------------

def test_found_papers_become_searchable_case_knowledge(client):
    case_id = _make_case(client)
    task = client.post("/api/agent/tasks", json={
        "case_id": case_id, "goal": "查文献 passive Q-switching", "mode": "literature_search",
    })
    assert task.status_code in (200, 201)

    hits = client.post("/api/knowledge/search", json={
        "query": "Passive Q-switching mode locking review", "case_id": case_id, "top_k": 5,
    })
    assert hits.status_code == 200, hits.text
    texts = " ".join(r.get("snippet", "") for r in hits.json()["results"])
    assert "Q-switching" in texts, "archived literature results must be retrievable"
