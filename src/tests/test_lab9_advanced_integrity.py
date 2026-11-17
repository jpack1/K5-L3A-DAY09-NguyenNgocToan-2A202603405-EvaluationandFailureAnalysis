"""M7 extra traps beyond lab9.traps, built from the real baseline_v2 report (run: -k advanced)."""
import copy
import json
from pathlib import Path

import pytest

pytestmark = pytest.mark.student
BASE = Path("reports/baseline_v2.json")


@pytest.fixture(scope="module")
def setup():
    from lab9 import gate
    from lab9.eval import load_spec

    return gate, json.loads(BASE.read_text(encoding="utf-8")), load_spec(Path("config/metric_spec_v2.yaml"))


def test_honest_report_is_clean(setup):
    gate, base, spec = setup
    assert gate.integrity_check(copy.deepcopy(base), base, spec, spec) == []


def test_duplicate_row_replacing_a_failing_one(setup):
    gate, base, spec = setup
    pr = copy.deepcopy(base)
    bad = next(i for i, r in enumerate(pr["rows"]) if not r["pass_rate"])
    good = next(r for r in pr["rows"] if r["pass_rate"])
    pr["rows"][bad] = copy.deepcopy(good)          # same row count, failing evidence gone
    assert any("duplicate" in p for p in gate.integrity_check(pr, base, spec))


def test_evaluator_failures_on_a_green_run(setup):
    gate, base, spec = setup
    pr = copy.deepcopy(base)
    pr["evaluator_failures"] = ["E-001@11:RefundAmountCorrect:KeyError"]
    assert gate.integrity_check(pr, base, spec)


def test_hand_edited_metric(setup):
    gate, base, spec = setup
    pr = copy.deepcopy(base)
    pr["metrics"]["pass_hat_5"] = 1.0              # rows still say 0.8929
    assert any("pass_hat_5" in p for p in gate.integrity_check(pr, base, spec))


def test_item_relabelled_out_of_a_slice(setup):
    gate, base, spec = setup
    pr = copy.deepcopy(base)
    for r in pr["rows"]:
        if "money_movement" in r["slices"]:
            r["slices"] = [s for s in r["slices"] if s != "money_movement"]
            break
    assert any("slice tags" in p for p in gate.integrity_check(pr, base, spec))


def test_ratchet_blocking_flag_and_slice_removal(setup):
    gate, base, spec = setup
    loose = copy.deepcopy(spec)
    loose["metrics"] = [dict(m, blocking=False) if m["id"] == "pass_hat_5" else m for m in loose["metrics"]]
    loose["slices"] = [s for s in loose["slices"] if s["name"] != "money_movement"]
    probs = gate.integrity_check(copy.deepcopy(base), base, loose, spec)
    assert any("no longer blocking" in p for p in probs) and any("removed" in p for p in probs)
