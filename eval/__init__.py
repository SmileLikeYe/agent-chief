"""Eval harness (SPEC v3.1 Step 25).

CAPABILITY evals (eval/golden.jsonl, ~200 cases) measure judge quality — the
number is allowed to move and should be reported. REGRESSION evals (the demo
24) must stay at 100% and are wired into CI via tests/test_eval.py.
"""
