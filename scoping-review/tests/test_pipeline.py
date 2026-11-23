import csv
import json
from pathlib import Path

import pytest

from prisma_scr import cli, report
from prisma_scr.dedupe import find_duplicates
from prisma_scr.importers import import_file
from prisma_scr.screening import cohen_kappa
from prisma_scr.sources import _openalex_abstract, parse_pubmed_xml
from prisma_scr.store import Store, normalize_doi

FX = Path(__file__).parent / "fixtures"


def run(proj, *args):
    return cli.main(["-p", str(proj), *args])


def fill(path, decisions, reason_col=None):
    """Fill a screening CSV: decisions = {title_substring: (decision, reason)}; default include."""
    rows = list(csv.DictReader(path.open(encoding="utf-8-sig")))
    for row in rows:
        d, r = "include", ""
        for key, val in decisions.items():
            if key.lower() in row["title"].lower():
                d, r = val
        row["decision"], row["reason"] = d, r
    with path.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


# ------------------------------------------------------------- units
def test_parsers():
    scopus = import_file(FX / "scopus.csv", "Scopus")
    assert len(scopus) == 3 and scopus[0]["year"] == 2017
    assert scopus[0]["authors"][0] == "Alzahrani L."
    ris = import_file(FX / "wos.ris", "Web of Science")
    assert len(ris) == 3
    assert ris[0]["doi"] == "10.1016/j.ibusrev.2016.06.004"
    assert "Saudi Arabia and Jordan" in ris[1]["abstract"]  # continuation line joined
    assert ris[2]["pub_type"] == "proceedings-article"
    bib = import_file(FX / "handsearch.bib", "Hand search")
    assert bib[0]["title"].startswith("Tawakkalna app") and bib[0]["year"] == 2022
    pm = parse_pubmed_xml((FX / "pubmed.xml").read_text())
    assert pm[0]["doi"] == "10.2196/sehhaty" and pm[0]["authors"] == ["Alghamdi, Saad"]


def test_normalize_doi_and_openalex_abstract():
    assert normalize_doi("https://dx.doi.org/10.1/ABC.") == "10.1/abc"
    assert _openalex_abstract({"world": [1], "hello": [0]}) == "hello world"


def test_dedupe_doi_and_fuzzy_title():
    recs = import_file(FX / "scopus.csv", "Scopus") + import_file(FX / "wos.ris", "Web of Science")
    dupes = find_duplicates(recs)
    assert len(dupes) == 1  # Alzahrani 2017 appears in both
    kept = next(r for r in recs if r["id"] == next(iter(dupes.values())))
    assert "Alzahrani" in kept["authors"][0]


def test_kappa():
    assert cohen_kappa([("include", "include"), ("exclude", "exclude")]) == 1.0
    k = cohen_kappa([("include", "include"), ("include", "exclude"), ("exclude", "exclude"), ("exclude", "exclude")])
    assert 0 < k < 1


# ------------------------------------------------------------- end to end
def test_full_pipeline(tmp_path):
    proj = tmp_path / "review"
    run(proj, "init")
    run(proj, "import", str(FX / "scopus.csv"), "--source", "Scopus", "--date", "2026-11-01")
    run(proj, "import", str(FX / "wos.ris"), "--source", "Web of Science", "--date", "2026-11-01")
    run(proj, "import", str(FX / "handsearch.bib"), "--source", "Citation searching", "--kind", "other")
    run(proj, "dedupe", "--report")
    store = Store(proj)
    assert len(store.records) == 7 and len(store.unique()) == 6

    # Title/abstract: two reviewers, one disagreement on Absher.
    for rv, dec in (("R1", {"shopping": ("exclude", "")}),
                    ("R2", {"shopping": ("exclude", ""), "absher": ("exclude", "")})):
        run(proj, "screen", "export", "--stage", "ta", "--reviewer", rv)
        sheet = proj / "screening" / f"ta_{rv}.csv"
        fill(sheet, dec)
        run(proj, "screen", "import", str(sheet), "--stage", "ta", "--reviewer", rv)
    run(proj, "screen", "reconcile", "--stage", "ta")
    conflicts = proj / "screening" / "ta_conflicts.csv"
    rows = list(csv.DictReader(conflicts.open(encoding="utf-8-sig")))
    assert len(rows) == 1 and "Absher" in rows[0]["title"]
    rows[0]["final_decision"] = "include"
    with conflicts.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    run(proj, "screen", "resolve", str(conflicts), "--stage", "ta")
    stats = json.loads((proj / "data" / "screening_stats.json").read_text())
    assert stats["ta"]["kappa"] is not None

    # Full text: both agree; exclude Alshehri (reason 3), Al-Hujran not retrieved.
    ft = {"implementation of e-government": ("exclude", "3"), "imperative": ("not_retrieved", "")}
    for rv in ("R1", "R2"):
        run(proj, "screen", "export", "--stage", "ft", "--reviewer", rv)
        sheet = proj / "screening" / f"ft_{rv}.csv"
        fill(sheet, ft)
        run(proj, "screen", "import", str(sheet), "--stage", "ft", "--reviewer", rv)
    run(proj, "screen", "reconcile", "--stage", "ft")

    # Charting
    run(proj, "chart", "export")
    form = proj / "charting" / "charting_form.csv"
    rows = list(csv.DictReader(form.open(encoding="utf-8-sig")))
    assert len(rows) == 3
    for row in rows:
        row.update(study_design="survey", sector="interior", stakeholder_group="citizens", sample_size="250")
    with form.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)
    run(proj, "chart", "import", str(form))

    run(proj, "report")
    c = json.loads((proj / "output" / "flow_counts.json").read_text())
    assert c == {**c, "identified_total": 7, "duplicates": 1, "screened": 6, "ta_excluded": 1, "sought": 5,
                 "not_retrieved": 1, "assessed": 4, "ft_excluded": 1, "included": 3}
    assert c["ft_reasons"] == {"Wrong publication type": 1}
    assert report.check_consistency(c) == []
    svg = (proj / "output" / "prisma_flow.svg").read_text()
    assert svg.startswith("<svg") and "Sources of evidence included in review (n = 3)" in svg
    ms = (proj / "output" / "manuscript.md").read_text()
    assert "Cohen's κ" in ms and "3 sources of evidence were included" in ms
    assert "| survey | 3 (100%) |" in ms
    cl = (proj / "output" / "prisma_scr_checklist.md").read_text()
    assert cl.count("\n| ") >= 22


def test_ft_exclusion_requires_reason(tmp_path):
    proj = tmp_path / "r"
    run(proj, "init")
    run(proj, "import", str(FX / "wos.ris"), "--source", "WoS")
    store = Store(proj)
    for r in store.records:
        r["ta_final"] = "include"
    store.save()
    run(proj, "screen", "export", "--stage", "ft", "--reviewer", "R1")
    sheet = proj / "screening" / "ft_R1.csv"
    fill(sheet, {"": ("exclude", "")})
    run(proj, "screen", "import", str(sheet), "--stage", "ft", "--reviewer", "R1")
    assert all("R1" not in r["screening"]["ft"] for r in Store(proj).records)


def test_missing_protocol(tmp_path):
    with pytest.raises(SystemExit):
        run(tmp_path, "status")


def test_openalex_params_field():
    from prisma_scr.sources import openalex_params
    p = openalex_params("a AND b", [1990, 2026])
    assert p["filter"] == "title_and_abstract.search:a AND b,publication_year:1990-2026" and "search" not in p
    p = openalex_params("a", None, "fulltext")
    assert p["search"] == "a" and "filter" not in p
    with pytest.raises(ValueError):
        openalex_params("a", None, "body")


def test_identical_metadata_records_counted_as_duplicates(tmp_path):
    from prisma_scr.store import make_record
    s = Store(tmp_path)
    a = make_record(title="Same title here", year=2000, doi="10.1/x", source="OpenAlex", source_id="W1")
    b = make_record(title="Same title here", year=2000, doi="10.1/x", source="OpenAlex", source_id="W2")
    assert s.add([a, b]) == 2
    assert len(s.records) == 2 and len(s.unique()) == 1
    again = make_record(title="Same title here", year=2000, doi="10.1/x", source="OpenAlex", source_id="W1")
    assert s.add([again]) == 0  # re-import is a no-op


def test_flags_and_pilot_sample(tmp_path):
    import csv as _csv
    from prisma_scr.screening import flags
    proto = {"eligibility": {"years": [1990, 2026], "languages": ["en"]},
             "screening": {"required_any_terms": ["faulkner"]}}
    r = {"title": "A review", "abstract": "", "keywords": [], "year": 1985, "language": "fr", "pub_type": "book-review"}
    f = flags(r, proto)
    assert "Outside 1990-2026" in f and "Language: fr" in f and "Type: book-review" in f
    assert "No focal term in title/abstract" in f
    proj = tmp_path / "p"
    run(proj, "init")
    run(proj, "import", str(FX / "scopus.csv"), str(FX / "wos.ris"), "--source", "X")
    for rv in ("R1", "R2"):
        run(proj, "screen", "export", "--stage", "ta", "--reviewer", rv, "--sample", "3")
    ids = [[row["id"] for row in _csv.DictReader((proj / "screening" / f"ta_pilot_{rv}.csv").open(encoding="utf-8-sig"))]
           for rv in ("R1", "R2")]
    assert len(ids[0]) == 3 and sorted(ids[0]) == sorted(ids[1])


def test_protocol_document(tmp_path):
    proj = tmp_path / "p"
    run(proj, "init")
    run(proj, "import", str(FX / "wos.ris"), "--source", "WoS")
    run(proj, "protocol")
    md = (proj / "output" / "protocol_registration.md").read_text()
    assert "## 5. Eligibility criteria" in md and "Records identified to date: 3" in md
