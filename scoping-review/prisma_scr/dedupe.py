"""Duplicate detection: exact DOI match, then normalised title (+ year within 1) fuzzy match."""

from __future__ import annotations

from difflib import SequenceMatcher

from .store import normalize_title

SOURCE_PRIORITY = ["PubMed", "Scopus", "Web of Science", "OpenAlex", "Crossref"]


def _richness(r: dict) -> tuple:
    pri = SOURCE_PRIORITY.index(r["source"]) if r["source"] in SOURCE_PRIORITY else len(SOURCE_PRIORITY)
    return (bool(r.get("abstract")), bool(r.get("doi")), len(r.get("abstract", "")), -pri)


def find_duplicates(records: list[dict], threshold: float = 0.93) -> dict[str, str]:
    """Return {duplicate_id: kept_id}. The record with the richest metadata is kept."""
    live = [r for r in records if not r.get("duplicate_of")]
    parent = {r["id"]: r["id"] for r in live}

    def find(x):
        while parent[x] != x:
            parent[x] = parent[parent[x]]
            x = parent[x]
        return x

    def union(a, b):
        ra, rb = find(a), find(b)
        if ra != rb:
            parent[rb] = ra

    by_doi: dict[str, str] = {}
    for r in live:
        if r["doi"]:
            if r["doi"] in by_doi:
                union(by_doi[r["doi"]], r["id"])
            else:
                by_doi[r["doi"]] = r["id"]

    # Title blocking by first 3 tokens' initial characters keeps comparisons tractable.
    blocks: dict[str, list[dict]] = {}
    norm = {r["id"]: normalize_title(r["title"]) for r in live}
    for r in live:
        t = norm[r["id"]]
        if len(t) < 10:
            continue
        blocks.setdefault(t[:12], []).append(r)
    for group in blocks.values():
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                if a["doi"] and b["doi"] and a["doi"] != b["doi"]:
                    continue
                if a["year"] and b["year"] and abs(a["year"] - b["year"]) > 1:
                    continue
                ta, tb = norm[a["id"]], norm[b["id"]]
                if ta == tb or SequenceMatcher(None, ta, tb).ratio() >= threshold:
                    union(a["id"], b["id"])

    clusters: dict[str, list[dict]] = {}
    for r in live:
        clusters.setdefault(find(r["id"]), []).append(r)
    dupes = {}
    for members in clusters.values():
        if len(members) < 2:
            continue
        keep = max(members, key=_richness)
        for m in members:
            if m["id"] != keep["id"]:
                dupes[m["id"]] = keep["id"]
                # Merge useful metadata into the kept record.
                if not keep["abstract"] and m["abstract"]:
                    keep["abstract"] = m["abstract"]
                if not keep["doi"] and m["doi"]:
                    keep["doi"] = m["doi"]
                keep.setdefault("also_found_in", [])
                if m["source"] not in keep["also_found_in"] and m["source"] != keep["source"]:
                    keep["also_found_in"].append(m["source"])
    return dupes
