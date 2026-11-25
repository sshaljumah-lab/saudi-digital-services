"""Live database searches via public APIs: OpenAlex, Crossref and PubMed (E-utilities).

These need internet access. Set PRISMA_SCR_MAILTO to an email address to be
placed in the APIs' "polite pool" (recommended by OpenAlex and Crossref).
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from .store import make_record

UA = "prisma-scr/1.0 (scoping review tool)"


def _get(url: str, retries: int = 4) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    for attempt in range(retries):
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                return resp.read()
        except Exception:  # network error / 429 / 5xx: back off and retry
            if attempt == retries - 1:
                raise
            time.sleep(2 ** attempt)
    raise RuntimeError("unreachable")


def _mailto() -> str:
    return os.environ.get("PRISMA_SCR_MAILTO", "")


# ---------------------------------------------------------------- OpenAlex
def _openalex_abstract(inv: dict | None) -> str:
    if not inv:
        return ""
    pos = [(i, w) for w, idxs in inv.items() for i in idxs]
    return " ".join(w for _, w in sorted(pos))


OPENALEX_FIELDS = {"title_and_abstract", "title", "abstract", "fulltext"}


def openalex_params(query: str, years=None, field: str = "title_and_abstract") -> dict:
    """Build OpenAlex /works parameters. `field` limits where the boolean query is matched;
    'fulltext' uses the general `search` parameter (title, abstract and full text)."""
    if field not in OPENALEX_FIELDS:
        raise ValueError(f"openalex field must be one of {sorted(OPENALEX_FIELDS)}")
    params = {"per-page": "200", "cursor": "*"}
    filters = []
    if field == "fulltext":
        params["search"] = query
    else:
        filters.append(f"{field}.search:{query}")
    if years:
        filters.append(f"publication_year:{years[0]}-{years[1]}")
    if filters:
        params["filter"] = ",".join(filters)
    return params


def search_openalex(query: str, max_results: int, years=None, progress=print,
                    field: str = "title_and_abstract") -> list[dict]:
    """Page through OpenAlex results. Without an API key OpenAlex only allows numbered
    pages (up to 10,000 results); with OPENALEX_API_KEY set, cursor paging is used."""
    params = openalex_params(query, years, field)
    params["sort"] = "publication_date:desc"   # stable order across numbered pages
    if _mailto():
        params["mailto"] = _mailto()
    key = os.environ.get("OPENALEX_API_KEY", "")
    if key:
        params["api_key"] = key
    else:
        params.pop("cursor", None)
        params["page"] = 1
    out, seen = [], set()
    while len(out) < max_results:
        data = json.loads(_get("https://api.openalex.org/works?" + urllib.parse.urlencode(params)))
        results = data.get("results", [])
        for w in results:
            if w.get("id") in seen:
                continue
            seen.add(w.get("id"))
            out.append(make_record(
                title=w.get("title") or w.get("display_name") or "",
                abstract=_openalex_abstract(w.get("abstract_inverted_index")),
                authors=[a["author"]["display_name"] for a in w.get("authorships", []) if a.get("author")],
                year=w.get("publication_year"), doi=w.get("doi") or "",
                venue=((w.get("primary_location") or {}).get("source") or {}).get("display_name", ""),
                url=(w.get("primary_location") or {}).get("landing_page_url") or w.get("id", ""),
                keywords=[k.get("display_name", "") for k in w.get("keywords", [])],
                pub_type=w.get("type", ""), language=w.get("language") or "",
                source="OpenAlex", source_id=w.get("id", ""),
            ))
        total = data.get("meta", {}).get("count", 0)
        progress(f"  OpenAlex: {len(out)} / {total}")
        if not results:
            break
        if key:
            cursor = data.get("meta", {}).get("next_cursor")
            if not cursor:
                break
            params["cursor"] = cursor
        else:
            if params["page"] * int(params["per-page"]) >= min(total, 10000):
                break
            params["page"] += 1
        time.sleep(0.2)
    return out[:max_results]


# ---------------------------------------------------------------- Crossref
def search_crossref(query: str, max_results: int, years=None, progress=print) -> list[dict]:
    params = {"query.bibliographic": query, "rows": "200", "cursor": "*"}
    if years:
        params["filter"] = f"from-pub-date:{years[0]},until-pub-date:{years[1]}"
    if _mailto():
        params["mailto"] = _mailto()
    out = []
    while len(out) < max_results:
        data = json.loads(_get("https://api.crossref.org/works?" + urllib.parse.urlencode(params)))["message"]
        for it in data.get("items", []):
            date = (it.get("issued") or {}).get("date-parts", [[None]])[0][0]
            out.append(make_record(
                title=(it.get("title") or [""])[0],
                abstract=re.sub(r"<[^>]+>", " ", it.get("abstract", "")),
                authors=[f"{a.get('family', '')}, {a.get('given', '')}".strip(", ") for a in it.get("author", [])],
                year=date, doi=it.get("DOI", ""), venue=(it.get("container-title") or [""])[0],
                url=it.get("URL", ""), keywords=it.get("subject", []), pub_type=it.get("type", ""),
                language=it.get("language", ""), source="Crossref", source_id=it.get("DOI", ""),
            ))
        progress(f"  Crossref: {len(out)} / {data.get('total-results', '?')}")
        if not data.get("items") or not data.get("next-cursor"):
            break
        params["cursor"] = data["next-cursor"]
    return out[:max_results]


# ---------------------------------------------------------------- PubMed
EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"


def search_pubmed(query: str, max_results: int, years=None, progress=print) -> list[dict]:
    term = query
    if years:
        term += f" AND ({years[0]}:{years[1]}[dp])"
    p = {"db": "pubmed", "term": term, "retmax": str(max_results), "retmode": "json"}
    ids = json.loads(_get(EUTILS + "esearch.fcgi?" + urllib.parse.urlencode(p)))["esearchresult"]["idlist"]
    out = []
    for i in range(0, len(ids), 200):
        chunk = ids[i:i + 200]
        xml = _get(EUTILS + "efetch.fcgi?" + urllib.parse.urlencode(
            {"db": "pubmed", "id": ",".join(chunk), "retmode": "xml"}))
        out.extend(parse_pubmed_xml(xml))
        progress(f"  PubMed: {len(out)} / {len(ids)}")
        time.sleep(0.4)  # stay under 3 requests/second without an API key
    return out


def parse_pubmed_xml(xml: bytes | str) -> list[dict]:
    root = ET.fromstring(xml)
    out = []
    for art in root.iter("PubmedArticle"):
        a = art.find(".//Article")
        if a is None:
            continue
        doi = next((e.text for e in art.iter("ArticleId") if e.get("IdType") == "doi"), "")
        year = (a.findtext(".//JournalIssue/PubDate/Year")
                or a.findtext(".//JournalIssue/PubDate/MedlineDate") or "")
        authors = [f"{au.findtext('LastName', '')}, {au.findtext('ForeName', '')}".strip(", ")
                   for au in a.findall(".//AuthorList/Author")]
        pmid = art.findtext(".//PMID", "")
        out.append(make_record(
            title="".join(a.find("ArticleTitle").itertext()) if a.find("ArticleTitle") is not None else "",
            abstract=" ".join("".join(t.itertext()) for t in a.findall(".//Abstract/AbstractText")),
            authors=authors, year=year, doi=doi, venue=a.findtext(".//Journal/Title", ""),
            url=f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/",
            keywords=[k.text or "" for k in art.iter("Keyword")],
            pub_type="journal-article", language=a.findtext("Language", ""),
            source="PubMed", source_id=pmid,
        ))
    return out


ENGINES = {"openalex": search_openalex, "crossref": search_crossref, "pubmed": search_pubmed}
DISPLAY = {"openalex": "OpenAlex", "crossref": "Crossref", "pubmed": "PubMed"}
