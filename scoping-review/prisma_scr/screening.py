"""Two-stage screening (title/abstract, full text) with independent reviewers,
agreement statistics, conflict reconciliation and an interactive terminal screener."""

from __future__ import annotations

import csv
import textwrap
from pathlib import Path

from .store import Store

STAGES = {"ta": "title/abstract", "ft": "full-text"}
VALID = {"include", "exclude", "maybe"}
ALIASES = {"i": "include", "y": "include", "yes": "include", "in": "include",
           "e": "exclude", "n": "exclude", "no": "exclude", "x": "exclude", "out": "exclude",
           "m": "maybe", "?": "maybe", "u": "maybe", "unsure": "maybe",
           "nr": "not_retrieved", "not retrieved": "not_retrieved"}


def norm_decision(v: str, stage: str) -> str | None:
    v = (v or "").strip().lower()
    if not v:
        return None
    v = ALIASES.get(v, v).replace(" ", "_")
    allowed = VALID | ({"not_retrieved"} if stage == "ft" else set())
    if v not in allowed:
        raise ValueError(f"invalid decision {v!r}; use one of {sorted(allowed)}")
    return v


def pool(store: Store, stage: str) -> list[dict]:
    return store.ta_pool() if stage == "ta" else store.ft_pool()


def priority_score(r: dict, terms: list[str]) -> int:
    text = f"{r['title']} {r['abstract']} {' '.join(r.get('keywords', []))}".lower()
    return sum(text.count(t.lower()) * (3 if t.lower() in r["title"].lower() else 1) for t in terms)


# ------------------------------------------------------------ CSV round-trip
DEFAULT_FLAG_TYPES = ["book-review", "editorial", "erratum", "letter", "paratext", "peer-review", "retraction"]


def flags(r: dict, protocol: dict) -> list[str]:
    """Advisory, rule-based flags shown to reviewers. They never set a decision."""
    elig = protocol.get("eligibility") or {}
    scr = protocol.get("screening") or {}
    out = []
    if r["title"].startswith("[No title"):
        out.append("No title in source record")
    years = elig.get("years")
    if years and r.get("year") and not (years[0] <= r["year"] <= years[1]):
        out.append(f"Outside {years[0]}-{years[1]}")
    langs = [l.lower() for l in elig.get("languages") or []]
    lang = (r.get("language") or "").lower()[:2]
    if langs and lang and lang not in langs:
        out.append(f"Language: {r['language']}")
    ftypes = scr.get("flag_types", DEFAULT_FLAG_TYPES)
    if (r.get("pub_type") or "").lower() in ftypes:
        out.append(f"Type: {r['pub_type']}")
    need = scr.get("required_any_terms") or []
    if need:
        text = f"{r['title']} {r['abstract']} {' '.join(r.get('keywords', []))}".lower()
        if not any(t.lower() in text for t in need):
            out.append("No focal term in title/abstract")
    return out


def export_sheet(store: Store, stage: str, reviewer: str, out: Path, terms: list[str],
                 protocol: dict | None = None, sample: int = 0, seed: int = 2026) -> int:
    """Write a screening sheet. Unflagged records come first, by priority score.
    With `sample`, write a reproducible random sample (same seed -> same records for every
    reviewer) for pilot/calibration screening."""
    import random
    protocol = protocol or {}
    recs = [r for r in pool(store, stage) if reviewer not in r["screening"][stage]]
    if sample:
        everyone = sorted(pool(store, stage), key=lambda r: r["id"])
        chosen = {r["id"] for r in random.Random(seed).sample(everyone, min(sample, len(everyone)))}
        recs = [r for r in recs if r["id"] in chosen]
    fl = {r["id"]: flags(r, protocol) for r in recs}
    recs.sort(key=lambda r: (bool(fl[r["id"]]), -priority_score(r, terms)))
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = ["id", "decision", "reason", "notes", "flags", "title", "year", "authors", "venue", "doi", "url", "abstract"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in recs:
            w.writerow({"id": r["id"], "decision": "", "reason": "", "notes": "", "flags": "; ".join(fl[r["id"]]),
                        "title": r["title"], "year": r["year"] or "", "authors": "; ".join(r["authors"][:6]),
                        "venue": r["venue"], "doi": r["doi"],
                        "url": r["url"] or (f"https://doi.org/{r['doi']}" if r["doi"] else ""),
                        "abstract": r["abstract"]})
    return len(recs)


def import_sheet(store: Store, stage: str, reviewer: str, path: Path, reasons: list[str]) -> tuple[int, list[str]]:
    n, problems = 0, []
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            rec = store.get((row.get("id") or "").strip())
            if rec is None:
                problems.append(f"line {line_no}: unknown id {row.get('id')!r}")
                continue
            try:
                d = norm_decision(row.get("decision", ""), stage)
            except ValueError as e:
                problems.append(f"line {line_no}: {e}")
                continue
            if d is None:
                continue
            reason = (row.get("reason") or "").strip()
            if stage == "ft" and d == "exclude" and not reason:
                problems.append(f"line {line_no}: full-text exclusion needs a reason ({rec['id']})")
                continue
            if stage == "ft" and d == "exclude" and reasons and reason not in reasons:
                # allow numeric shorthand: "2" -> second reason in protocol
                if reason.isdigit() and 1 <= int(reason) <= len(reasons):
                    reason = reasons[int(reason) - 1]
            rec["screening"][stage][reviewer] = {"decision": d, "reason": reason,
                                                 "notes": (row.get("notes") or "").strip()}
            n += 1
    return n, problems


# ------------------------------------------------------------ agreement
def cohen_kappa(pairs: list[tuple[str, str]]) -> float | None:
    if not pairs:
        return None
    cats = sorted({c for p in pairs for c in p})
    n = len(pairs)
    po = sum(a == b for a, b in pairs) / n
    pe = sum((sum(a == c for a, _ in pairs) / n) * (sum(b == c for _, b in pairs) / n) for c in cats)
    return 1.0 if pe == 1 else (po - pe) / (1 - pe)


def _binary(d: str) -> str:
    # 'maybe' advances at title/abstract stage, so it is treated as include for agreement.
    return "exclude" if d in ("exclude", "not_retrieved") else "include"


def reconcile(store: Store, stage: str, reviewers: list[str]) -> dict:
    """Set final decisions where reviewers agree; return stats and conflict list."""
    stats = {"stage": stage, "reviewers": reviewers, "complete": 0, "pending": 0,
             "agreed": 0, "conflicts": [], "kappa": None, "percent_agreement": None}
    pairs = []
    for r in pool(store, stage):
        dec = r["screening"][stage]
        final_key = f"{stage}_final"
        if "_adjudicated" in dec:
            stats["complete"] += 1
            continue
        if not all(rv in dec for rv in reviewers):
            stats["pending"] += 1
            r[final_key] = None
            continue
        stats["complete"] += 1
        ds = [dec[rv]["decision"] for rv in reviewers]
        if len(reviewers) >= 2:
            pairs.append((_binary(ds[0]), _binary(ds[1])))
        # At title/abstract, 'maybe' advances (counts as include); at full text every
        # reviewer must give the same definite decision.
        cats = {_binary(d) for d in ds} if stage == "ta" else set(ds)
        if len(cats) == 1 and "maybe" not in cats:
            stats["agreed"] += 1
            final = cats.pop()
            r[final_key] = final
            if stage == "ft":
                r["ft_reason"] = (dec[reviewers[0]].get("reason") or None) if final == "exclude" else None
        else:
            r[final_key] = None
            stats["conflicts"].append(r)
    if pairs:
        stats["kappa"] = cohen_kappa(pairs)
        stats["percent_agreement"] = sum(a == b for a, b in pairs) / len(pairs)
    return stats


def export_conflicts(stats: dict, reviewers: list[str], out: Path) -> None:
    stage = stats["stage"]
    cols = ["id", "final_decision", "reason"] + [f"{rv}_decision" for rv in reviewers] + \
           [f"{rv}_reason" for rv in reviewers] + ["title", "abstract"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in stats["conflicts"]:
            row = {"id": r["id"], "final_decision": "", "reason": "", "title": r["title"], "abstract": r["abstract"]}
            for rv in reviewers:
                d = r["screening"][stage].get(rv, {})
                row[f"{rv}_decision"] = d.get("decision", "")
                row[f"{rv}_reason"] = d.get("reason", "")
            w.writerow(row)


def import_adjudication(store: Store, stage: str, path: Path, reasons: list[str]) -> int:
    n = 0
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for row in csv.DictReader(fh):
            rec = store.get(row["id"].strip())
            d = norm_decision(row.get("final_decision", ""), stage)
            if rec is None or d is None:
                continue
            if d == "maybe":
                raise SystemExit(f"{rec['id']}: adjudicated decision must be include or exclude")
            reason = (row.get("reason") or "").strip()
            if reason.isdigit() and reasons and 1 <= int(reason) <= len(reasons):
                reason = reasons[int(reason) - 1]
            if stage == "ft" and d == "exclude" and not reason:
                raise SystemExit(f"{rec['id']}: full-text exclusion needs a reason")
            rec["screening"][stage]["_adjudicated"] = {"decision": d, "reason": reason}
            rec[f"{stage}_final"] = d
            if stage == "ft":
                rec["ft_reason"] = reason if d == "exclude" else None
            n += 1
    return n


# ------------------------------------------------------------ interactive
def interactive(store: Store, stage: str, reviewer: str, terms: list[str], reasons: list[str],
                criteria: dict, inp=input, out=print) -> int:
    todo = [r for r in pool(store, stage) if reviewer not in r["screening"][stage]]
    todo.sort(key=lambda r: -priority_score(r, terms))
    keys = "[i]nclude  [e]xclude  [m]aybe  [s]kip  [q]uit"
    if stage == "ft":
        keys = "[i]nclude  [e]xclude  [n]ot retrieved  [s]kip  [q]uit"
    out(f"\n{STAGES[stage].title()} screening as {reviewer}: {len(todo)} records to screen")
    out("Inclusion: " + " | ".join(criteria.get("inclusion", [])))
    out("Exclusion: " + " | ".join(criteria.get("exclusion", [])))
    done = 0
    for k, r in enumerate(todo, 1):
        out("\n" + "=" * 78)
        out(f"[{k}/{len(todo)}] {r['id']}  ({r['year'] or 'n.d.'})  {r['venue']}")
        out(textwrap.fill(r["title"], 78))
        if r["doi"]:
            out(f"https://doi.org/{r['doi']}")
        out("-" * 78)
        out(textwrap.fill(r["abstract"] or "(no abstract)", 78))
        while True:
            ans = inp(keys + " > ").strip().lower()
            if ans == "q":
                return done
            if ans == "s":
                break
            if stage == "ft" and ans == "n":
                ans = "not_retrieved"
            try:
                d = norm_decision(ans, stage)
            except ValueError:
                d = None
            if d is None or (stage == "ft" and d == "maybe"):
                out("  ? unrecognised key")
                continue
            reason = ""
            if stage == "ft" and d == "exclude":
                for i, rs in enumerate(reasons, 1):
                    out(f"   {i}. {rs}")
                choice = inp("  reason number (or text) > ").strip()
                reason = reasons[int(choice) - 1] if choice.isdigit() and 1 <= int(choice) <= len(reasons) else choice
                if not reason:
                    out("  a reason is required")
                    continue
            r["screening"][stage][reviewer] = {"decision": d, "reason": reason, "notes": ""}
            done += 1
            if done % 10 == 0:
                store.save()
            break
    return done
