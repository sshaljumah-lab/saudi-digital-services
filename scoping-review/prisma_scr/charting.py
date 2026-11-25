"""Data charting (extraction) of included sources and descriptive synthesis."""

from __future__ import annotations

import csv
from collections import Counter
from pathlib import Path

from .store import Store

BASE_COLS = ["id", "first_author", "year", "title", "venue", "doi", "country"]


def export_form(store: Store, fields: list[dict], out: Path, reviewer: str = "") -> int:
    out.parent.mkdir(parents=True, exist_ok=True)
    cols = BASE_COLS + [f["name"] for f in fields] + ["charted_by", "verified_by"]
    with out.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.DictWriter(fh, fieldnames=cols)
        w.writeheader()
        for r in sorted(store.included(), key=lambda r: (r["year"] or 0, r["title"])):
            row = {"id": r["id"], "first_author": (r["authors"] or [""])[0], "year": r["year"] or "",
                   "title": r["title"], "venue": r["venue"], "doi": r["doi"],
                   "country": r["charting"].get("country", ""), "charted_by": r["charting"].get("charted_by", reviewer),
                   "verified_by": r["charting"].get("verified_by", "")}
            for f in fields:
                row[f["name"]] = r["charting"].get(f["name"], "")
            w.writerow(row)
    # A codebook sheet next to the form documents allowed values (PRISMA-ScR item 11).
    book = out.with_name(out.stem + "_codebook.csv")
    with book.open("w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh)
        w.writerow(["field", "type", "allowed_values"])
        for f in fields:
            w.writerow([f["name"], f.get("type", "text"), " | ".join(f.get("options", []))])
    return len(store.included())


def import_form(store: Store, fields: list[dict], path: Path) -> tuple[int, list[str]]:
    n, problems = 0, []
    spec = {f["name"]: f for f in fields}
    with path.open(newline="", encoding="utf-8-sig") as fh:
        for line_no, row in enumerate(csv.DictReader(fh), start=2):
            rec = store.get((row.get("id") or "").strip())
            if rec is None:
                problems.append(f"line {line_no}: unknown id")
                continue
            for name, val in row.items():
                if name in BASE_COLS and name != "country":
                    continue
                val = (val or "").strip()
                f = spec.get(name)
                if f and val:
                    if f.get("type") == "category" and f.get("options"):
                        vals = [v.strip() for v in val.split(";")]
                        bad = [v for v in vals if v not in f["options"]]
                        if bad:
                            problems.append(f"line {line_no}: {name}={bad} not in {f['options']}")
                    if f.get("type") == "number":
                        try:
                            float(val.replace(",", ""))
                        except ValueError:
                            problems.append(f"line {line_no}: {name}={val!r} is not a number")
                rec["charting"][name] = val
            n += 1
    return n, problems


def summarise(store: Store, fields: list[dict]) -> dict:
    inc = store.included()
    out = {"n": len(inc), "by_year": Counter(r["year"] for r in inc if r["year"]),
           "by_type": Counter(r["pub_type"] or "unknown" for r in inc), "fields": {}}
    for f in fields:
        vals = [r["charting"].get(f["name"], "") for r in inc]
        if f.get("type") == "category":
            c = Counter()
            for v in vals:
                for part in (v.split(";") if v else ["not reported"]):
                    c[part.strip() or "not reported"] += 1
            out["fields"][f["name"]] = {"type": "category", "counts": c}
        elif f.get("type") == "number":
            nums = []
            for v in vals:
                try:
                    nums.append(float(str(v).replace(",", "")))
                except ValueError:
                    pass
            if nums:
                nums.sort()
                mid = len(nums) // 2
                median = nums[mid] if len(nums) % 2 else (nums[mid - 1] + nums[mid]) / 2
                out["fields"][f["name"]] = {"type": "number", "n": len(nums), "min": nums[0],
                                            "max": nums[-1], "median": median}
            else:
                out["fields"][f["name"]] = {"type": "number", "n": 0}
        else:
            out["fields"][f["name"]] = {"type": "text", "reported": sum(bool(v) for v in vals)}
    return out
