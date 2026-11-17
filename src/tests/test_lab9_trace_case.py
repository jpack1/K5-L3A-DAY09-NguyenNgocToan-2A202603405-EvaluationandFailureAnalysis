"""Regression test for the trace case in docs/trace_case.md: swarm C-002@55 (FM-03 ticket_trust).
Runs the real shapes on a temp store, so it fails if the bug returns, not only on hand-built trials."""
import pytest

pytestmark = pytest.mark.student


def db_fact_kept(shape):
    from pydantic_evals.evaluators import EvaluatorContext

    from lab9.graders import DbFactKept
    from lab9.trace_case import investigate

    case = investigate(shape, "C-002", 55)
    ctx = EvaluatorContext(name="t", inputs={}, metadata=None, expected_output=case["label"],
                           output=case["trial"], duration=0.0, _span_tree=None, attributes={}, metrics={})
    return DbFactKept().evaluate(ctx).value, case["trial"]


def test_swarm_c002_s55_overrides_db_fact():
    kept, trial = db_fact_kept("swarm")
    assert kept is False and trial["lab8_pass"] is False
    assert trial["snapshot"]["refund_vnd"] == 20000   # refunded on a 2-day delay the DB already rules out


def test_fixed_c002_s55_keeps_db_fact():
    kept, trial = db_fact_kept("fixed")
    assert kept is True and trial["lab8_pass"] is True
    assert trial["snapshot"]["refund_vnd"] == 0
