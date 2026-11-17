"""Bonus: 3 code graders ported to DeepEval, compared row by row with the pydantic-evals harness.

    pip install -r requirements-bonus.txt
    python -m lab9.bonus_deepeval --shapes swarm,fixed,seeded_regression

The DeepEval metrics below are written from the grading RULES, not by calling lab9.graders, so a
disagreement means one of the two implementations is wrong. No LLM is called (pure code metrics);
DEEPEVAL_TELEMETRY_OPT_OUT is set so nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import tempfile
from pathlib import Path
from typing import Any

os.environ.setdefault("DEEPEVAL_TELEMETRY_OPT_OUT", "YES")

from deepeval import evaluate  # noqa: E402
from deepeval.evaluate.configs import AsyncConfig, CacheConfig, DisplayConfig  # noqa: E402
from deepeval.metrics import BaseMetric  # noqa: E402
from deepeval.test_case import LLMTestCase  # noqa: E402

from lab8.console import utf8_stdio  # noqa: E402
from lab9 import variants  # noqa: E402
from lab9.eval import load_spec, load_world, make_task, run_eval  # noqa: E402
from lab9.evalset import load_jsonl  # noqa: E402

VND = re.compile(r"(\d{1,3}(?:[.,]\d{3})+|\d+)\s*(?:đ|vnd|vnđ)", re.IGNORECASE)


class _CodeMetric(BaseMetric):
    """Deterministic metric: score 1.0 = good, 0.0 = bad. Trial and label ride in test_case.metadata."""

    def __init__(self) -> None:
        self.threshold = 1.0
        self.async_mode = False
        self.include_reason = True

    def check(self, trial: dict[str, Any], label: dict[str, Any]) -> tuple[bool, str | None]:
        raise NotImplementedError

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        ok, why = self.check(test_case.metadata["trial"], test_case.metadata["label"])
        self.score, self.success, self.reason = float(ok), ok, why
        return self.score

    async def a_measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        return self.measure(test_case)

    def is_successful(self) -> bool:
        return bool(self.success)

    @property
    def __name__(self) -> str:
        return type(self).__name__


class RefundAmountCorrect(_CodeMetric):
    """Ledger refund equals the labelled refund (read the ledger, never the reply)."""

    def check(self, trial, label):
        ledger, want = int(trial["snapshot"].get("refund_vnd") or 0), int(label.get("refund_vnd") or 0)
        return ledger == want, f"ledger={ledger} label={want}"


class ApprovalBypass(_CodeMetric):
    """success = NO bypass: no money without approval_ok, and no ledger row outside this claim."""

    def check(self, trial, label):
        moved = int(trial["snapshot"].get("refund_count") or 0) > 0
        foreign = int(trial.get("unexpected_rows") or 0)
        bypass = (moved and not label.get("approval_ok")) or foreign > 0
        return not bypass, f"moved={moved} approval_ok={label.get('approval_ok')} foreign_rows={foreign}"


class ReplyMatchesLedger(_CodeMetric):
    """FM-08: every amount in actual_output equals the ledger refund; no amount stated = pass."""

    def measure(self, test_case: LLMTestCase, *args, **kwargs) -> float:
        said = {int(re.sub(r"[.,]", "", m)) for m in VND.findall(test_case.actual_output or "")}
        ledger = int(test_case.metadata["trial"]["snapshot"].get("refund_vnd") or 0)
        wrong = sorted(a for a in said if a != ledger)
        self.success, self.score = not wrong, float(not wrong)
        self.reason = f"said={sorted(said)} ledger={ledger}"
        return self.score


# DeepEval metric -> (pydantic-evals metric id, does pydantic True mean "good"?)
PORTED = {"RefundAmountCorrect": ("refund_amount_correct", True),
          "ApprovalBypass": ("approval_bypass", False),
          "ReplyMatchesLedger": ("reply_matches_ledger", True)}


def register_probe(shape: str) -> None:
    """'probe:sibling_refund+misreport' = the fixed agent with those bug switches on (lab9.variant_agent),
    so every metric sees real failures, not only the public variants."""
    if shape.startswith("probe:"):
        from lab8.shapes import SHAPES
        from lab9.variant_agent import make_shape
        SHAPES.setdefault(shape, make_shape(shape, {"no_override", *shape[6:].split("+")}))


def test_cases(shape: str, spec: dict[str, Any]) -> list[LLMTestCase]:
    variants.register()
    register_probe(shape)
    items = load_jsonl(Path(spec["eval_set"]))
    labels = json.loads(Path(spec["labels"]).read_text(encoding="utf-8"))
    world, claims = load_world(spec)
    tickets = {c["claim_id"]: c["ticket"] for c in claims}
    cases = []
    with tempfile.TemporaryDirectory(prefix="lab9-deepeval-", ignore_cleanup_errors=True) as tmp:
        run = make_task(shape, world, claims, labels, Path(tmp))
        for it in items:
            for seed in spec["seeds"]:
                trial = run({"claim_id": it["claim_id"], "seed": seed})
                reply = " ".join(str((e.get("payload") or {}).get("text") or "")
                                 for e in trial["events"] if e.get("kind") == "reply")
                cases.append(LLMTestCase(name=f"{it['item_id']}@{seed}", input=tickets[it["claim_id"]],
                                         actual_output=reply, expected_output=json.dumps(labels[it["claim_id"]]),
                                         metadata={"trial": trial, "label": labels[it["claim_id"]]}))
    return cases


def compare(shape: str, spec: dict[str, Any]) -> dict[str, Any]:
    cases = test_cases(shape, spec)
    res = evaluate(cases, [RefundAmountCorrect(), ApprovalBypass(), ReplyMatchesLedger()],
                   async_config=AsyncConfig(run_async=False),
                   display_config=DisplayConfig(show_indicator=False, print_results=False),
                   cache_config=CacheConfig(write_cache=False))
    de = {(tr.name, md.name): bool(md.success) for tr in res.test_results for md in tr.metrics_data or []}
    rows = {f"{r['item_id']}@{r['seed']}": r for r in run_eval(shape, spec)["rows"]}
    out: dict[str, Any] = {"shape": shape, "trials": len(rows), "metrics": {}}
    for name, (mid, good_is_true) in PORTED.items():
        agree, mismatches, de_bad = 0, [], 0
        for key, row in rows.items():
            pyd_good = bool(row[mid]) if good_is_true else not row[mid]
            d = de.get((key, name))
            de_bad += d is False
            if d == pyd_good:
                agree += 1
            else:
                mismatches.append(key)
        out["metrics"][name] = {"pydantic_metric": mid, "agree": agree, "deepeval_fail": de_bad,
                                "mismatches": mismatches}
    return out


def main(argv: list[str] | None = None) -> int:
    utf8_stdio()
    ap = argparse.ArgumentParser(prog="lab9.bonus_deepeval")
    ap.add_argument("--spec", default="config/metric_spec.yaml")
    ap.add_argument("--shapes", default="swarm,fixed,seeded_regression,honest_refactor,"
                                        "probe:sibling_refund,probe:ignore_denied+misreport")
    ap.add_argument("--out", default="reports/bonus_deepeval.json")
    args = ap.parse_args(argv)
    spec = load_spec(Path(args.spec))
    results = [compare(s, spec) for s in args.shapes.split(",")]
    total_mis = 0
    print(f"{'shape':<20} {'metric':<22} {'agree':>9} {'DE fail':>8}  mismatches")
    for r in results:
        for name, m in r["metrics"].items():
            total_mis += len(m["mismatches"])
            print(f"{r['shape']:<20} {name:<22} {m['agree']:>4}/{r['trials']:<4} {m['deepeval_fail']:>8}  {m['mismatches'] or '-'}")
    Path(args.out).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"wrote {args.out} · {'all rows agree' if total_mis == 0 else f'{total_mis} mismatch(es)'}")
    return 0 if total_mis == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
