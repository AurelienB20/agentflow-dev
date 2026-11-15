"""Parser-based checks: deterministic, never execute the code."""

from app.scenarios import BUG_CODE, BUG_FIX_V1, BUG_FIX_V2, REVIEW_CODE, SLUG_CODE
from app.services.static_checks import analyze, public_names, collect_test_names


def rules(code):
    return [f["rule"] for f in analyze(code)["findings"]]


def test_division_by_len_flagged_only_without_guard():
    assert rules(BUG_CODE) == ["division-by-len"]
    assert rules(BUG_FIX_V1) == []  # guarded by `if not numbers: raise`
    assert rules(BUG_FIX_V2) == []


def test_review_code_findings():
    assert set(rules(REVIEW_CODE)) == {"mutable-default", "resource-leak", "sql-injection", "bare-except"}


def test_clean_code_has_no_findings():
    assert rules(SLUG_CODE) == []


def test_syntax_error_is_reported():
    report = analyze("def f(:\n  pass\n")
    assert report["syntax_ok"] is False and "line 1" in report["syntax_error"]


def test_pyflakes_undefined_name():
    assert "pyflakes" in rules("def f():\n    return y\n")


def test_eval_and_fstring_sql():
    code = 'def q(c, x):\n    eval(x)\n    c.execute(f"SELECT * FROM t WHERE id = {x}")\n'
    assert {"dangerous-call", "sql-injection"} <= set(rules(code))


def test_with_statement_is_not_a_leak():
    assert "resource-leak" not in rules("def f(p):\n    with open(p) as fh:\n        return fh.read()\n")


def test_name_helpers():
    assert public_names(BUG_FIX_V2) == {"calculate_average"}
    assert collect_test_names("def test_a():\n    pass\ndef helper():\n    pass\n") == {"test_a"}
