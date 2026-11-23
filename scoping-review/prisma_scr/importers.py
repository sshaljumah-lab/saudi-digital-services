"""Import database exports: RIS, BibTeX, CSV (Scopus / generic) and Web of Science tab-delimited."""

from __future__ import annotations

import csv
import io
import re
from pathlib import Path

from .store import make_record

# ---------------------------------------------------------------- RIS
RIS_LINE = re.compile(r"^([A-Z][A-Z0-9])  -\s?(.*)$")


def parse_ris(text: str, source: str) -> list[dict]:
    recs, cur = [], {}
    last_tag = None
    for raw in text.splitlines():
        line = raw.rstrip("\r")
        m = RIS_LINE.match(line)
        if not m:
            if last_tag and line.strip():
                cur.setdefault(last_tag, [""])[-1] += " " + line.strip()
            continue
        tag, val = m.group(1), m.group(2).strip()
        last_tag = tag
        if tag == "ER":
            if cur:
                recs.append(_ris_to_record(cur, source))
            cur, last_tag = {}, None
            continue
        cur.setdefault(tag, []).append(val)
    if cur:
        recs.append(_ris_to_record(cur, source))
    return recs


RIS_TYPES = {"JOUR": "journal-article", "CONF": "proceedings-article", "CPAPER": "proceedings-article",
             "RPRT": "report", "THES": "dissertation", "BOOK": "book", "CHAP": "book-chapter",
             "GEN": "other", "ELEC": "web-page"}


def _first(d, *tags):
    for t in tags:
        if d.get(t):
            return d[t][0]
    return ""


def _ris_to_record(d: dict, source: str) -> dict:
    return make_record(
        title=_first(d, "TI", "T1", "CT"),
        abstract=" ".join(d.get("AB", []) or d.get("N2", [])),
        authors=d.get("AU", []) + d.get("A1", []),
        year=_first(d, "PY", "Y1", "DA"),
        doi=_first(d, "DO"),
        venue=_first(d, "T2", "JO", "JF", "J2", "BT"),
        url=_first(d, "UR"),
        keywords=d.get("KW", []),
        pub_type=RIS_TYPES.get(_first(d, "TY"), _first(d, "TY").lower()),
        language=_first(d, "LA"),
        source=source,
        source_id=_first(d, "AN", "ID"),
    )


# ---------------------------------------------------------------- BibTeX
def _read_braced(text: str, i: int) -> tuple[str, int]:
    """text[i] is '{' or '"'; return content and index after closing delimiter."""
    opener = text[i]
    if opener == '"':
        j = i + 1
        while j < len(text) and not (text[j] == '"' and text[j - 1] != "\\"):
            j += 1
        return text[i + 1:j], j + 1
    depth, j = 0, i
    while j < len(text):
        if text[j] == "{":
            depth += 1
        elif text[j] == "}":
            depth -= 1
            if depth == 0:
                return text[i + 1:j], j + 1
        j += 1
    return text[i + 1:], len(text)


def parse_bibtex(text: str, source: str) -> list[dict]:
    recs = []
    for m in re.finditer(r"@(\w+)\s*\{", text):
        etype = m.group(1).lower()
        if etype in ("comment", "string", "preamble"):
            continue
        body, _ = _read_braced(text, m.end() - 1)
        key, _, rest = body.partition(",")
        fields, i = {}, 0
        while i < len(rest):
            fm = re.compile(r"\s*([\w-]+)\s*=\s*").match(rest, i)
            if not fm:
                i += 1
                continue
            name, i = fm.group(1).lower(), fm.end()
            if i < len(rest) and rest[i] in '{"':
                val, i = _read_braced(rest, i)
            else:
                vm = re.compile(r"[^,]*").match(rest, i)
                val, i = vm.group(0), vm.end()
            fields[name] = re.sub(r"\s+", " ", val.replace("{", "").replace("}", "")).strip()
        authors = [a.strip() for a in re.split(r"\s+and\s+", fields.get("author", "")) if a.strip()]
        type_map = {"article": "journal-article", "inproceedings": "proceedings-article",
                    "conference": "proceedings-article", "phdthesis": "dissertation",
                    "mastersthesis": "dissertation", "techreport": "report", "book": "book",
                    "incollection": "book-chapter"}
        recs.append(make_record(
            title=fields.get("title", ""), abstract=fields.get("abstract", ""), authors=authors,
            year=fields.get("year", ""), doi=fields.get("doi", ""),
            venue=fields.get("journal") or fields.get("booktitle", ""), url=fields.get("url", ""),
            keywords=re.split(r"[;,]", fields.get("keywords", "")), pub_type=type_map.get(etype, etype),
            language=fields.get("language", ""), source=source, source_id=key.strip(),
        ))
    return recs


# ---------------------------------------------------------------- CSV / WoS
COLUMN_ALIASES = {
    "title": ["title", "article title", "document title", "ti"],
    "abstract": ["abstract", "ab"],
    "authors": ["authors", "author", "author full names", "au", "af"],
    "year": ["year", "publication year", "py", "pubyear", "date"],
    "doi": ["doi", "di"],
    "venue": ["source title", "journal", "publication title", "venue", "so", "source"],
    "url": ["link", "url"],
    "keywords": ["author keywords", "keywords", "de", "index keywords"],
    "pub_type": ["document type", "type", "dt"],
    "language": ["language of original document", "language", "la"],
    "source_id": ["eid", "ut (unique wos id)", "ut", "pmid", "accession number"],
}


def _colmap(headers: list[str]) -> dict:
    low = {h.strip().lower().lstrip("﻿"): h for h in headers}
    out = {}
    for field, aliases in COLUMN_ALIASES.items():
        for a in aliases:
            if a in low:
                out[field] = low[a]
                break
    return out


def parse_table(text: str, source: str, delimiter: str | None = None) -> list[dict]:
    if delimiter is None:
        sample = text[:4096]
        delimiter = "\t" if sample.count("\t") > sample.count(",") else ","
    reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
    cmap = _colmap(reader.fieldnames or [])
    if "title" not in cmap:
        raise SystemExit(f"Could not find a title column. Columns: {reader.fieldnames}")
    recs = []
    for row in reader:
        g = lambda f: (row.get(cmap[f]) or "") if f in cmap else ""  # noqa: E731
        authors_raw = g("authors")
        authors = re.split(r";|\s{2,}", authors_raw) if ";" in authors_raw else (
            re.split(r",\s(?=[A-Z][a-z]+,)", authors_raw) if authors_raw else [])
        recs.append(make_record(
            title=g("title"), abstract=g("abstract"), authors=authors, year=g("year"), doi=g("doi"),
            venue=g("venue"), url=g("url"), keywords=re.split(r";", g("keywords")),
            pub_type=g("pub_type").lower(), language=g("language"), source=source, source_id=g("source_id"),
        ))
    return recs


def import_file(path: Path, source: str) -> list[dict]:
    text = Path(path).read_text(encoding="utf-8-sig", errors="replace")
    ext = Path(path).suffix.lower()
    if ext in (".ris", ".nbib") or re.search(r"^TY  -", text, re.M):
        return parse_ris(text, source)
    if ext in (".bib", ".bibtex") or re.search(r"^\s*@\w+\s*\{", text, re.M):
        return parse_bibtex(text, source)
    if ext in (".csv", ".tsv", ".txt"):
        return parse_table(text, source, "\t" if ext in (".tsv", ".txt") else None)
    raise SystemExit(f"Unsupported file type: {path}")
