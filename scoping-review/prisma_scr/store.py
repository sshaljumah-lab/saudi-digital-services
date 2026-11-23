"""Project data store: a transparent JSON file of records plus an audit log."""

from __future__ import annotations

import hashlib
import json
import re
import unicodedata
from datetime import datetime, timezone
from pathlib import Path

RECORDS = "data/records.json"
SEARCH_LOG = "data/search_log.json"
AUDIT_LOG = "data/audit_log.jsonl"


def now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def normalize_doi(doi: str | None) -> str:
    if not doi:
        return ""
    doi = doi.strip().lower()
    doi = re.sub(r"^(https?://)?(dx\.)?doi\.org/", "", doi)
    doi = re.sub(r"^doi:\s*", "", doi)
    return doi.rstrip(".")


def normalize_title(title: str | None) -> str:
    if not title:
        return ""
    t = unicodedata.normalize("NFKD", title)
    t = "".join(c for c in t if not unicodedata.combining(c)).lower()
    t = re.sub(r"<[^>]+>", " ", t)
    t = re.sub(r"[^a-z0-9؀-ۿ]+", " ", t)
    return re.sub(r"\s+", " ", t).strip()


def make_record(*, title, abstract="", authors=None, year=None, doi="", venue="",
                source, url="", keywords=None, pub_type="", language="", source_id="") -> dict:
    year_int = None
    if year not in (None, ""):
        m = re.search(r"(1[89]|20)\d{2}", str(year))
        year_int = int(m.group(0)) if m else None
    rec = {
        "title": (title or "").strip(),
        "abstract": (abstract or "").strip(),
        "authors": [a.strip() for a in (authors or []) if a and a.strip()],
        "year": year_int,
        "doi": normalize_doi(doi),
        "venue": (venue or "").strip(),
        "url": url or "",
        "keywords": [k.strip() for k in (keywords or []) if k and k.strip()],
        "pub_type": pub_type or "",
        "language": language or "",
        "source": source,
        "source_id": source_id or "",
        "duplicate_of": None,
        "screening": {"ta": {}, "ft": {}},
        "ta_final": None,
        "ft_final": None,
        "ft_reason": None,
        "charting": {},
    }
    key = f"{source}|{rec['doi']}|{normalize_title(rec['title'])}|{year_int}"
    rec["id"] = "R" + hashlib.sha1(key.encode()).hexdigest()[:10]
    return rec


class Store:
    def __init__(self, project: Path):
        self.project = Path(project)
        self.path = self.project / RECORDS
        self.records: list[dict] = []
        if self.path.exists():
            self.records = json.loads(self.path.read_text(encoding="utf-8"))
        self._index = {r["id"]: r for r in self.records}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.records, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(self.path)

    def get(self, rid: str) -> dict | None:
        return self._index.get(rid)

    def add(self, recs: list[dict]) -> int:
        added = 0
        for r in recs:
            if r["id"] in self._index or not r["title"]:
                continue
            self.records.append(r)
            self._index[r["id"]] = r
            added += 1
        return added

    # --- views -----------------------------------------------------------
    def unique(self) -> list[dict]:
        return [r for r in self.records if not r.get("duplicate_of")]

    def ta_pool(self) -> list[dict]:
        return self.unique()

    def ft_pool(self) -> list[dict]:
        return [r for r in self.unique() if r.get("ta_final") == "include"]

    def included(self) -> list[dict]:
        return [r for r in self.unique() if r.get("ft_final") == "include"]

    # --- logs ------------------------------------------------------------
    def log_search(self, entry: dict) -> None:
        p = self.project / SEARCH_LOG
        log = json.loads(p.read_text(encoding="utf-8")) if p.exists() else []
        log.append(entry)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(log, ensure_ascii=False, indent=1), encoding="utf-8")

    def search_log(self) -> list[dict]:
        p = self.project / SEARCH_LOG
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else []

    def audit(self, action: str, **details) -> None:
        p = self.project / AUDIT_LOG
        p.parent.mkdir(parents=True, exist_ok=True)
        with p.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps({"time": now_iso(), "action": action, **details}, ensure_ascii=False) + "\n")
