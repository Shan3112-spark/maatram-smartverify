"""Accuracy evaluation on the synthetic sample set (the catalogue asks for accuracy results).
Usage: python evaluate.py --samples samples --out results
"""
import argparse, json, time
from pathlib import Path

from validator import validate_application


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--samples", default="samples")
    ap.add_argument("--out", default="results")
    a = ap.parse_args()
    root, out = Path(a.samples), Path(a.out)
    out.mkdir(exist_ok=True)
    cases = json.loads((root / "manifest.json").read_text())

    rows, queue = [], []
    f_total = f_exact = 0
    for c in cases:
        t0 = time.time()
        rep, ex = validate_application(c["case_id"], c["entered"], (root / c["marksheet"]).read_bytes(),
                                       (root / c["photo"]).read_bytes())
        truth = c["truth"]
        sheet_t = truth["sheet_marks"]
        exact = sum(1 for s, v in sheet_t.items() if s in ex.marks and ex.marks[s].obtained == v)
        f_total += len(sheet_t); f_exact += exact
        # wrong-but-confident extractions are the dangerous ones
        silent_wrong = [s for s, m in ex.marks.items() if s in sheet_t and m.obtained != sheet_t[s]
                        and m.confidence >= 75 and not m.repaired]
        problems = truth["problems"]
        photo_bad = truth["photo_scenario"] != "good"
        photo_flag = any(k.status != "PASS" for k in rep.checks if k.group == "photo")
        sheet_problem = any(not p.startswith("photo:") for p in problems)
        sheet_flag = any(k.status != "PASS" for k in rep.checks if k.group == "marks")
        rows.append({"case": c["case_id"], "overall": rep.overall, "has_problem": bool(problems),
                     "flagged": rep.overall != "PASS", "sheet_problem": sheet_problem, "sheet_flag": sheet_flag,
                     "photo_bad": photo_bad, "photo_flag": photo_flag, "ocr_exact": exact, "ocr_total": len(sheet_t),
                     "silent_wrong": silent_wrong, "degradation": truth["degradation"], "problems": problems,
                     "secs": round(time.time() - t0, 1)})
        if rep.overall != "PASS":
            queue.append({"case": c["case_id"], "status": rep.overall, "reasons": rep.reasons,
                          "actual_problems": problems})

    n = len(rows)
    prob = [r for r in rows if r["has_problem"]]
    clean = [r for r in rows if not r["has_problem"]]
    sp = [r for r in rows if r["sheet_problem"]]
    sc = [r for r in rows if not r["sheet_problem"]]
    pb = [r for r in rows if r["photo_bad"]]
    pg = [r for r in rows if not r["photo_bad"]]
    pct = lambda x, y: round(100 * x / y, 1) if y else None
    by_level = {}
    for lv in ("clean", "mild", "moderate", "hard"):
        rr = [r for r in rows if r["degradation"] == lv]
        by_level[lv] = {"sheets": len(rr), "ocr_field_accuracy_%": pct(sum(r["ocr_exact"] for r in rr), sum(r["ocr_total"] for r in rr))}
    summary = {
        "applications": n,
        "ocr_field_accuracy_%": pct(f_exact, f_total),
        "ocr_by_scan_quality": by_level,
        "problem_cases_flagged_%  (recall; higher is better)": pct(sum(r["flagged"] for r in prob), len(prob)),
        "problem_cases_silently_passed (must be 0)": sum(not r["flagged"] for r in prob),
        "clean_cases_auto_passed_%": pct(sum(not r["flagged"] for r in clean), len(clean)),
        "clean_cases_sent_to_review": sum(r["flagged"] for r in clean),
        "sheet_problems_flagged_%": pct(sum(r["sheet_flag"] for r in sp), len(sp)),
        "sheet_false_alarms": sum(r["sheet_flag"] for r in sc),
        "bad_photos_rejected_%": pct(sum(r["photo_flag"] for r in pb), len(pb)),
        "good_photos_wrongly_rejected": sum(r["photo_flag"] for r in pg),
        "confident_but_wrong_extractions (must be 0)": sum(len(r["silent_wrong"]) for r in rows),
        "avg_seconds_per_application": round(sum(r["secs"] for r in rows) / n, 1),
    }
    (out / "summary.json").write_text(json.dumps(summary, indent=2))
    (out / "exception_queue.json").write_text(json.dumps(queue, indent=2))
    (out / "per_case.json").write_text(json.dumps(rows, indent=2))
    print(json.dumps(summary, indent=2))
    print(f"\n{len(queue)} applications routed to the exception queue -> {out}/exception_queue.json")
    for r in rows:
        if (r["has_problem"] and not r["flagged"]) or (not r["has_problem"] and r["flagged"]) or r["silent_wrong"]:
            print("  attention:", r["case"], r["degradation"], r["problems"], r["overall"], r["silent_wrong"])


if __name__ == "__main__":
    main()
