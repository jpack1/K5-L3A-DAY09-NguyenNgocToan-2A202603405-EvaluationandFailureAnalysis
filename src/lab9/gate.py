"""CI gate: compare a PR eval report with the main-branch baseline using the metric spec.

    python -m lab9.gate --pr reports/eval_workflow.json --baseline reports/baseline_v1.json

exit 0 = merge, exit 1 = blocked. Safety metrics: max 0, no averaging away.
Capability metrics: meet the floor AND the paired CI of (PR - main) is not entirely below 0.
Thresholds may only get stricter on the same eval-set version (ratchet).
"""

from __future__ import annotations

import argparse
import json
import math
from pathlib import Path

from lab8.console import utf8_stdio
from lab9 import stats
from lab9.eval import SPEC, load_spec, per_item


def integrity_check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> list[str]:
    """M7 (Expert): refuse to compare reports that cannot be trusted. Return a list of problems
    (empty = trustworthy). A gate that passes a broken report is worse than no gate.
    Must catch at least:
      - any metric value in pr["metrics"] that is NaN or inf
      - len(pr["rows"]) != manifest items x len(manifest seeds)   (dropped / duplicated rows)
      - the (item_id, seed) set of PR differs from the baseline's (cherry-picked seeds/items)
      - pr["evaluator_failures"] non-empty, or a row whose value for a graded spec metric is
        None (a crashed grader silently scores as "missing" and drops out of the mean)
      - base_spec given and a threshold in spec is LOOSER than in base_spec for the same
        eval-set version (ratchet: max may not rise, min may not fall, a blocking metric may
        not become non-blocking, a metric may not disappear; the same for spec["slices"],
        including dropping no_significant_drop)
      - an item's slice tags in PR rows differ from the baseline's (relabelling an item out of a
        slice hides its regression from the slice gate)"""
    from lab9.eval import aggregate
    from lab9.graders import GRADERS

    problems: list[str] = []
    rows = pr.get("rows") or []
    man = pr.get("manifest") or {}

    # 1. NaN / inf metric values (nan < min is False, so a naive gate lets them through).
    problems += [f"metric {k} is {v}" for k, v in (pr.get("metrics") or {}).items()
                 if isinstance(v, float) and not math.isfinite(v)]

    # 2. Row count and duplicates: every item x seed exactly once.
    want = (man.get("items") or 0) * len(man.get("seeds") or [])
    if len(rows) != want:
        problems.append(f"{len(rows)} rows, manifest says {man.get('items')} items x {len(man.get('seeds') or [])} seeds = {want}")
    keys = [(r.get("item_id"), r.get("seed")) for r in rows]
    dups = sorted({k for k in keys if keys.count(k) > 1}, key=str)
    if dups:
        problems.append(f"duplicate (item, seed) rows: {dups[:5]}")

    # 3. Same (item, seed) set and same seeds as the baseline (no cherry-picking).
    base_keys = {(r.get("item_id"), r.get("seed")) for r in base.get("rows") or []}
    if set(keys) != base_keys:
        miss, extra = base_keys - set(keys), set(keys) - base_keys
        problems.append(f"(item, seed) set differs from baseline: {len(miss)} missing, {len(extra)} extra")
    if sorted(man.get("seeds") or []) != sorted((base.get("manifest") or {}).get("seeds") or []):
        problems.append(f"seeds {man.get('seeds')} != baseline seeds {(base.get('manifest') or {}).get('seeds')}")

    # 4. Crashed graders: reported failures, or a graded metric that is None on some row.
    if pr.get("evaluator_failures"):
        problems.append(f"{len(pr['evaluator_failures'])} evaluator failure(s): {pr['evaluator_failures'][:2]}")
    graded = [m["id"] for m in spec.get("metrics", []) if m["id"] in GRADERS]
    for mid in graded:
        missing = sum(1 for r in rows if r.get(mid) is None)
        if missing:
            problems.append(f"{missing} row(s) have no value for graded metric {mid}")

    # 5. Hand-edited metrics: the reported numbers must be what the rows add up to.
    if rows:
        row_ids = [m for m in graded if all(m in r for r in rows)]
        has_cost = all("cost" in r for r in rows)
        recomputed = aggregate([{"cost": 0.0, **r} for r in rows], row_ids, k_values=spec.get("pass_k", []))
        for k, v in recomputed.items():
            got = (pr.get("metrics") or {}).get(k)
            if k == "cost_per_success" and not has_cost:
                continue
            if isinstance(got, (int, float)) and math.isfinite(got) and v is not None and abs(got - v) > 1e-3:
                problems.append(f"metric {k}={got} but rows give {v}")

    # 6. Slice tags must match the baseline's (relabelling an item hides it from the slice gate).
    def tags(rep: dict) -> dict:
        out: dict = {}
        for r in rep.get("rows") or []:
            out.setdefault(r.get("item_id"), set()).add(tuple(sorted(r.get("slices") or [])))
        return out
    pt, bt = tags(pr), tags(base)
    relabelled = sorted(i for i in pt if i in bt and pt[i] != bt[i])
    if relabelled:
        problems.append(f"slice tags differ from baseline for {relabelled[:5]}")

    # 7. Ratchet: on the same eval-set version, the PR spec may only be as strict or stricter.
    if base_spec is not None and spec.get("eval_set_version") == base_spec.get("eval_set_version"):
        problems += [f"ratchet: {p}" for p in _looser(base_spec, spec)]
    return problems


def _looser(old: dict, new: dict) -> list[str]:
    """Ways `new` is laxer than `old`: a lower min, a higher max / max_increase, a dropped
    no_significant_drop or blocking flag, a missing metric or slice."""
    out: list[str] = []

    def cmp(name: str, o: dict, n: dict | None, th_o: dict, th_n: dict) -> None:
        if n is None:
            out.append(f"{name} removed")
            return
        if "min" in th_o and th_n.get("min", float("-inf")) < th_o["min"]:
            out.append(f"{name} min {th_o['min']} -> {th_n.get('min')}")
        for k in ("max", "max_increase"):
            if k in th_o and th_n.get(k, float("inf")) > th_o[k]:
                out.append(f"{name} {k} {th_o[k]} -> {th_n.get(k)}")
        if th_o.get("no_significant_drop") and not th_n.get("no_significant_drop"):
            out.append(f"{name} no_significant_drop dropped")
        if o.get("blocking") and not n.get("blocking"):
            out.append(f"{name} no longer blocking")

    new_m = {m["id"]: m for m in new.get("metrics") or []}
    for m in old.get("metrics") or []:
        n = new_m.get(m["id"])
        cmp(f"metric {m['id']}", m, n, m.get("threshold") or {}, (n or {}).get("threshold") or {})
    new_s = {(s["name"], s["metric"]): s for s in new.get("slices") or []}
    for s in old.get("slices") or []:
        n = new_s.get((s["name"], s["metric"]))
        cmp(f"slice {s['name']}/{s['metric']}", s, n, s, n or {})
    return out


def slice_check(pr: dict, base: dict, spec: dict) -> tuple[list[str], list[str]]:
    """M5 (Advanced): an average can hide a regression on a small, important slice.
    For each entry of spec["slices"] ({"name", "metric", "min"?, "no_significant_drop"?, "blocking"}):
      - value = mean of per_item(pr, metric, slice_name=name)
      - fail if below "min", or if no_significant_drop and the paired CI over the slice's items
        lies entirely below 0
    Return (blocked ids like "slice:money_movement/pass_rate", report lines)."""
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for s in spec.get("slices") or []:
        name, metric = s["name"], s["metric"]
        a, b = per_item(pr, metric, slice_name=name), per_item(base, metric, slice_name=name)
        val = round(sum(a.values()) / len(a), 4) if a else None
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"   # an empty slice cannot vouch for anything
        elif "min" in s and val < s["min"]:
            verdict = "fail"
        keys = sorted(set(a) & set(b))
        if s.get("no_significant_drop") and keys:
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027),
                                               confidence=bs.get("confidence", 0.95))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        sid = f"slice:{name}/{metric}"
        if verdict != "ok" and s.get("blocking"):
            blocked.append(sid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if s.get("blocking") else "warn")
        th = {k: s[k] for k in ("min", "no_significant_drop") if k in s}
        lines.append(f"  {sid:<40} {val!s:<8} n={len(a):<3} {json.dumps(th):<36} {note:<28} {label}")
    return blocked, lines


def check(pr: dict, base: dict, spec: dict, base_spec: dict | None = None) -> tuple[list[str], list[str]]:
    if pr["manifest"]["eval_set_sha"] != base["manifest"]["eval_set_sha"]:
        return ["eval_set_sha"], ["  EVAL SET differs from the baseline's: re-run the baseline on the same eval set"]
    problems = integrity_check(pr, base, spec, base_spec)
    if problems:
        return ["integrity"], [f"  INTEGRITY {p}" for p in problems]
    blocked, lines = [], []
    bs = spec.get("bootstrap", {})
    for m in spec["metrics"]:
        mid, th, val = m["id"], m.get("threshold", {}), pr["metrics"].get(m["id"])
        verdict, note = "ok", ""
        if val is None:
            verdict = "missing"
        elif "max" in th and val > th["max"]:
            verdict = "fail"
        elif "min" in th and val < th["min"]:
            verdict = "fail"
        elif "max_increase" in th and base["metrics"].get(mid):
            if val > base["metrics"][mid] * (1 + th["max_increase"]):
                verdict = "fail"
        if th.get("no_significant_drop") and val is not None:
            a, b = per_item(pr, mid), per_item(base, mid)
            keys = sorted(set(a) & set(b))
            d, lo, hi = stats.paired_bootstrap([a[k] for k in keys], [b[k] for k in keys],
                                               n_resamples=bs.get("n_resamples", 1000), rng=bs.get("rng", 2027))
            note = f"Δ {d:+.3f} CI [{lo:+.3f}, {hi:+.3f}]"
            if hi < 0:
                verdict = "fail"
        if verdict != "ok" and m.get("blocking"):
            blocked.append(mid)
        label = {"ok": "ok", "missing": "MISSING"}.get(verdict, "BLOCK" if m.get("blocking") else "warn")
        lines.append(f"  {mid:<22} {val!s:<8} {json.dumps(th):<40} {note:<28} {label}")
    if spec.get("slices"):
        sb, sl = slice_check(pr, base, spec)
        blocked += sb
        lines += sl
    return blocked, lines


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.gate")
    ap.add_argument("--pr", required=True)
    ap.add_argument("--baseline", required=True)
    ap.add_argument("--spec", default=str(SPEC))
    ap.add_argument("--base-spec", help="metric spec on main, for the ratchet check (M7)")
    args = ap.parse_args(argv)
    pr = json.loads(Path(args.pr).read_text(encoding="utf-8"))
    base = json.loads(Path(args.baseline).read_text(encoding="utf-8"))
    base_spec = load_spec(Path(args.base_spec)) if args.base_spec else None
    blocked, lines = check(pr, base, load_spec(Path(args.spec)), base_spec)
    print(f"gate: PR {pr['run_id']} vs main {base['run_id']} · eval set {pr['manifest']['eval_set_sha']}")
    print("\n".join(lines))
    if blocked:
        print(f"exit 1 — blocked: {', '.join(blocked)}")
        return 1
    print("exit 0 — merge")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
