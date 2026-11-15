"""The three demonstration scenarios.

Each scenario has:
- public metadata (title, description, code, request) served by /api/scenarios;
- a *script*: the outputs a deterministic, simulated model returns for each
  agent call, in order. The script is consumed by ``ScriptedProvider`` and is
  used (1) by the automated tests and (2) to record the Guided Demo
  workflows. The orchestration, routing, retries and events around those
  outputs are produced by the real LangGraph engine.
"""

from __future__ import annotations

from typing import Any

# --------------------------------------------------------------------------
# Scenario 1 — Fix a Python bug (shows the correction loop)
# --------------------------------------------------------------------------

BUG_CODE = '''def calculate_average(numbers):
    """Return the arithmetic mean of an iterable of numbers."""
    return sum(numbers) / len(numbers)
'''

BUG_REQUEST = (
    "calculate_average crashes on empty input. Fix it: the function must accept any "
    "iterable (lists, tuples, generators) and raise ValueError on empty input."
)

BUG_FIX_V1 = '''def calculate_average(numbers):
    """Return the arithmetic mean of an iterable of numbers."""
    if not numbers:
        raise ValueError("calculate_average() requires at least one number")
    return sum(numbers) / len(numbers)
'''

BUG_FIX_V2 = '''from collections.abc import Iterable


def calculate_average(numbers: Iterable[float]) -> float:
    """Return the arithmetic mean of an iterable of numbers.

    Raises:
        ValueError: if ``numbers`` is empty.
    """
    values = list(numbers)  # materialise once: generators can only be read once
    if not values:
        raise ValueError("calculate_average() requires at least one number")
    return sum(values) / len(values)
'''

BUG_TESTS = '''import math

import pytest

from solution import calculate_average


def test_list_of_ints():
    assert calculate_average([1, 2, 3, 4]) == 2.5


def test_single_value():
    assert calculate_average([7]) == 7


def test_floats():
    assert math.isclose(calculate_average([0.1, 0.2, 0.3]), 0.2)


def test_negative_numbers():
    assert calculate_average([-2, 2, -4, 4]) == 0


def test_tuple_input():
    assert calculate_average((10, 20)) == 15


def test_generator_input():
    assert calculate_average(x for x in [2, 4, 6]) == 4


def test_empty_list_raises():
    with pytest.raises(ValueError):
        calculate_average([])


def test_empty_generator_raises():
    with pytest.raises(ValueError):
        calculate_average(x for x in [])
'''

BUG_CASES = [
    {"name": "test_list_of_ints", "category": "nominal", "description": "Mean of a list of integers"},
    {"name": "test_single_value", "category": "edge", "description": "One element returns itself"},
    {"name": "test_floats", "category": "nominal", "description": "Float precision handled with isclose"},
    {"name": "test_negative_numbers", "category": "edge", "description": "Negative values cancel out"},
    {"name": "test_tuple_input", "category": "nominal", "description": "Tuples are accepted"},
    {"name": "test_generator_input", "category": "edge", "description": "Generators are accepted"},
    {"name": "test_empty_list_raises", "category": "error", "description": "Empty list raises ValueError"},
    {"name": "test_empty_generator_raises", "category": "error", "description": "Empty generator raises ValueError"},
]

BUG_SCRIPT: dict[str, list[dict[str, Any]]] = {
    "classifier": [
        {
            "task_type": "BUG_FIX",
            "confidence": 0.96,
            "reason": "The request reports a crash and asks for a behavioural fix with explicit requirements.",
            "subtasks": {
                "analyzer": "Locate the root cause of the crash and list every requirement the fix must satisfy.",
                "developer": "Patch calculate_average so it satisfies all requirements without changing its name.",
                "tester": "Write pytest cases for nominal, edge and error inputs, then check the patch against them.",
                "reviewer": "Verify the final patch matches the request and is safe to merge.",
            },
        }
    ],
    "analyzer": [
        {
            "summary": "Division by zero on empty input; len() also breaks the 'any iterable' requirement.",
            "issues": [
                {"title": "ZeroDivisionError on empty input", "severity": "high", "line": 3,
                 "detail": "len([]) is 0, so sum([]) / len([]) raises ZeroDivisionError instead of ValueError."},
                {"title": "len() is not defined for generators", "severity": "medium", "line": 3,
                 "detail": "The request requires generators; len(generator) raises TypeError, and sum() would consume the generator first."},
                {"title": "No type hints or documented exceptions", "severity": "low", "line": 1,
                 "detail": "The contract (accepted inputs, raised errors) is not visible to callers."},
            ],
            "recommendations": [
                "Materialise the iterable once (list(numbers)) before computing sum and length.",
                "Raise ValueError with a clear message when there are no values.",
                "Add type hints and document the raised exception.",
            ],
        }
    ],
    "developer": [
        {
            "summary": "Added an explicit empty-input guard that raises ValueError.",
            "code": BUG_FIX_V1,
            "changes": ["Raise ValueError when the input is empty"],
        },
        {
            "summary": "Materialise the iterable once, then validate and compute; generators now work.",
            "code": BUG_FIX_V2,
            "changes": [
                "Convert the input to a list once so generators can be measured",
                "Check emptiness on the materialised list (works for empty generators)",
                "Add type hints and document ValueError",
            ],
        },
    ],
    "tester": [
        {
            "summary": "8 cases generated. Static check: generator inputs still fail with this patch.",
            "test_code": BUG_TESTS,
            "cases": BUG_CASES,
            "validation": {
                "passed": False,
                "failing_cases": ["test_generator_input", "test_empty_generator_raises"],
                "issues": [
                    "A generator object is always truthy, so `if not numbers` never detects an empty generator.",
                    "sum(numbers) consumes the generator, then len(numbers) raises TypeError.",
                ],
            },
        },
        {
            "summary": "8 cases generated. Static check: all cases are expected to pass.",
            "test_code": BUG_TESTS,
            "cases": BUG_CASES,
            "validation": {"passed": True, "failing_cases": [], "issues": []},
        },
    ],
    "reviewer": [
        {
            "summary": "The patch meets every requirement in the request; approved.",
            "approved": True,
            "rubric": {"correctness": 9, "edge_cases": 9, "robustness": 9, "readability": 9},
            "findings": [
                "Empty input now raises ValueError with an explicit message.",
                "Lists, tuples and generators are supported by materialising once.",
                "Type hints and docstring document the contract.",
            ],
            "required_changes": [],
            "risks": ["list(numbers) copies the input: memory grows with very large iterables (acceptable here)."],
        }
    ],
}

# --------------------------------------------------------------------------
# Scenario 2 — Generate unit tests (Developer is not needed)
# --------------------------------------------------------------------------

SLUG_CODE = '''import re


def slugify(text: str, max_length: int = 50) -> str:
    """Convert text to a URL-friendly slug."""
    if max_length <= 0:
        raise ValueError("max_length must be positive")
    slug = text.lower().strip()
    slug = re.sub(r"[^a-z0-9\\s-]", "", slug)
    slug = re.sub(r"[\\s_-]+", "-", slug)
    slug = slug.strip("-")
    return slug[:max_length].rstrip("-")
'''

SLUG_REQUEST = "Generate a pytest suite for slugify covering nominal behaviour, edge cases and errors."

SLUG_TESTS_V1 = '''import pytest

from solution import slugify


def test_basic_sentence():
    assert slugify("Hello World") == "hello-world"


def test_punctuation_removed():
    assert slugify("Hello, World!") == "hello-world"


def test_collapses_whitespace():
    assert slugify("  many   spaces  here ") == "many-spaces-here"


def test_empty_string():
    assert slugify("") == ""


def test_invalid_max_length():
    with pytest.raises(ValueError):
        slugify("abc", max_length=0)
'''

SLUG_TESTS_V2 = SLUG_TESTS_V1 + '''

def test_symbols_only():
    assert slugify("!!!???") == ""


def test_underscores_are_dropped_not_converted():
    # The first regex deletes "_" before the separator regex can see it.
    assert slugify("snake_case_text") == "snakecasetext"


def test_accents_are_dropped():
    assert slugify("Café au lait") == "caf-au-lait"


def test_truncation_strips_trailing_hyphen():
    assert slugify("hello world", max_length=6) == "hello"


def test_repeated_hyphens_collapse():
    assert slugify("a -- b") == "a-b"


@pytest.mark.parametrize("bad", [0, -1])
def test_non_positive_max_length(bad):
    with pytest.raises(ValueError):
        slugify("abc", max_length=bad)
'''

SLUG_SCRIPT: dict[str, list[dict[str, Any]]] = {
    "classifier": [
        {
            "task_type": "TEST_GEN",
            "confidence": 0.98,
            "reason": "The user asks for a test suite; the code itself must not be modified.",
            "subtasks": {
                "analyzer": "Map the behaviour of slugify, including surprising edge cases.",
                "developer": "",
                "tester": "Write a pytest module that pins down that behaviour.",
                "reviewer": "Check coverage of the edge cases found by the Analyzer.",
            },
        }
    ],
    "analyzer": [
        {
            "summary": "Five behaviours to pin down; underscores and accents are silently deleted.",
            "issues": [
                {"title": "Underscores deleted instead of converted", "severity": "medium", "line": 9,
                 "detail": "[^a-z0-9\\s-] removes '_' before the separator regex runs, so '_' in [\\s_-] is dead code."},
                {"title": "Non-ASCII letters are dropped", "severity": "medium", "line": 9,
                 "detail": "'Café' becomes 'caf' because é is outside [a-z]."},
                {"title": "Truncation can end on a hyphen", "severity": "low", "line": 12,
                 "detail": "Handled by rstrip('-') after slicing; worth a regression test."},
                {"title": "max_length validation", "severity": "low", "line": 6,
                 "detail": "Zero and negative values raise ValueError."},
            ],
            "recommendations": [
                "Test underscores, accents, truncation on a hyphen and symbol-only input explicitly.",
                "Parametrise the invalid max_length cases.",
            ],
        }
    ],
    "tester": [
        {
            "summary": "5 tests covering the main path and the max_length error.",
            "test_code": SLUG_TESTS_V1,
            "cases": [
                {"name": "test_basic_sentence", "category": "nominal", "description": "Spaces become hyphens"},
                {"name": "test_punctuation_removed", "category": "nominal", "description": "Punctuation stripped"},
                {"name": "test_collapses_whitespace", "category": "edge", "description": "Runs of spaces collapse"},
                {"name": "test_empty_string", "category": "edge", "description": "Empty input"},
                {"name": "test_invalid_max_length", "category": "error", "description": "max_length=0 raises"},
            ],
            "validation": {"passed": True, "failing_cases": [], "issues": []},
        },
        {
            "summary": "11 tests: added the Analyzer's edge cases and parametrised errors.",
            "test_code": SLUG_TESTS_V2,
            "cases": [
                {"name": "test_basic_sentence", "category": "nominal", "description": "Spaces become hyphens"},
                {"name": "test_punctuation_removed", "category": "nominal", "description": "Punctuation stripped"},
                {"name": "test_collapses_whitespace", "category": "edge", "description": "Runs of spaces collapse"},
                {"name": "test_empty_string", "category": "edge", "description": "Empty input"},
                {"name": "test_invalid_max_length", "category": "error", "description": "max_length=0 raises"},
                {"name": "test_symbols_only", "category": "edge", "description": "Only symbols gives ''"},
                {"name": "test_underscores_are_dropped_not_converted", "category": "edge", "description": "Pins the underscore behaviour"},
                {"name": "test_accents_are_dropped", "category": "edge", "description": "Pins the accent behaviour"},
                {"name": "test_truncation_strips_trailing_hyphen", "category": "edge", "description": "No trailing hyphen after truncation"},
                {"name": "test_repeated_hyphens_collapse", "category": "edge", "description": "Hyphen runs collapse"},
                {"name": "test_non_positive_max_length", "category": "error", "description": "0 and -1 raise"},
            ],
            "validation": {"passed": True, "failing_cases": [], "issues": []},
        },
    ],
    "reviewer": [
        {
            "summary": "The tests are correct, but the edge cases found by the Analyzer are not covered.",
            "approved": True,
            "rubric": {"correctness": 9, "edge_cases": 5, "robustness": 7, "readability": 8},
            "findings": ["Main path is covered", "None of the four Analyzer edge cases is tested"],
            "required_changes": [
                "Add tests for underscores, accents and truncation ending on a hyphen.",
                "Add a symbol-only input case and parametrise invalid max_length values.",
            ],
            "risks": ["Silent data loss (underscores, accents) could regress unnoticed."],
        },
        {
            "summary": "The suite now pins every behaviour identified by the Analyzer; approved.",
            "approved": True,
            "rubric": {"correctness": 9, "edge_cases": 9, "robustness": 8, "readability": 9},
            "findings": ["11 focused tests", "Surprising behaviours are documented by tests"],
            "required_changes": [],
            "risks": ["Tests document current behaviour; accents/underscores may be a product bug worth a ticket."],
        },
    ],
}

# --------------------------------------------------------------------------
# Scenario 3 — Code review (Analyzer and Tester run in parallel)
# --------------------------------------------------------------------------

REVIEW_CODE = '''import sqlite3


def get_user_orders(db_path, user_id, statuses=[]):
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    query = "SELECT id, total, status FROM orders WHERE user_id = '%s'" % user_id
    if statuses:
        query += " AND status IN (%s)" % ",".join("'" + s + "'" for s in statuses)
    try:
        rows = cursor.execute(query).fetchall()
    except:
        rows = []
    total = 0
    for r in rows:
        total = total + r[1]
    return {"orders": rows, "total": total}
'''

REVIEW_REQUEST = "Review this function before it goes to production: quality, risks and testability."

REVIEW_TESTS = '''import sqlite3

import pytest

from solution import get_user_orders


@pytest.fixture
def db(tmp_path):
    path = tmp_path / "shop.db"
    conn = sqlite3.connect(path)
    conn.execute("CREATE TABLE orders (id INTEGER, user_id TEXT, total REAL, status TEXT)")
    conn.executemany(
        "INSERT INTO orders VALUES (?, ?, ?, ?)",
        [(1, "u1", 10.0, "paid"), (2, "u1", 5.5, "refunded"), (3, "u2", 99.0, "paid")],
    )
    conn.commit()
    conn.close()
    return str(path)


def test_total_for_user(db):
    assert get_user_orders(db, "u1")["total"] == 15.5


def test_status_filter(db):
    assert get_user_orders(db, "u1", ["paid"])["total"] == 10.0


def test_unknown_user(db):
    assert get_user_orders(db, "nobody") == {"orders": [], "total": 0}


def test_injection_payload_is_not_executed(db):
    result = get_user_orders(db, "x' OR '1'='1")
    assert result["orders"] == []  # currently FAILS: returns every order


def test_database_error_is_not_silenced(tmp_path):
    with pytest.raises(sqlite3.Error):
        get_user_orders(str(tmp_path / "missing.db"), "u1")  # currently returns []
'''

REVIEW_SCRIPT: dict[str, list[dict[str, Any]]] = {
    "classifier": [
        {
            "task_type": "CODE_REVIEW",
            "confidence": 0.95,
            "reason": "The user asks for an assessment, not a change: two independent reviews then a verdict.",
            "subtasks": {
                "analyzer": "Review quality, security and maintainability.",
                "developer": "",
                "tester": "Assess testability and list the edge cases a test suite must cover.",
                "reviewer": "Merge both reviews into a single prioritised verdict.",
            },
        }
    ],
    "analyzer": [
        {
            "summary": "Critical SQL injection plus resource leak and silenced errors.",
            "issues": [
                {"title": "SQL injection", "severity": "critical", "line": 7,
                 "detail": "user_id and statuses are interpolated into SQL. Use ? placeholders."},
                {"title": "Connection never closed", "severity": "high", "line": 5,
                 "detail": "sqlite3.connect without close/context manager leaks a handle per call."},
                {"title": "Bare except hides failures", "severity": "high", "line": 12,
                 "detail": "Any error (missing table, locked DB) is reported as 'no orders'."},
                {"title": "Mutable default argument", "severity": "low", "line": 4,
                 "detail": "statuses=[] is shared between calls; use None or a tuple."},
                {"title": "Money summed as floats", "severity": "medium", "line": 16,
                 "detail": "Use integer cents or Decimal for monetary totals."},
            ],
            "recommendations": [
                "Parameterise the query, including a generated IN (?, ?, ...) list.",
                "Use `with closing(sqlite3.connect(...))` and let database errors propagate.",
                "Compute the total in SQL (SUM(total)) or with Decimal.",
            ],
        }
    ],
    "tester": [
        {
            "summary": "Hard to test in isolation; 2 of 5 key cases would fail today.",
            "test_code": REVIEW_TESTS,
            "cases": [
                {"name": "test_total_for_user", "category": "nominal", "description": "Sum for one user"},
                {"name": "test_status_filter", "category": "nominal", "description": "Filter by status"},
                {"name": "test_unknown_user", "category": "edge", "description": "No rows"},
                {"name": "test_injection_payload_is_not_executed", "category": "error", "description": "Injection payload must not match rows"},
                {"name": "test_database_error_is_not_silenced", "category": "error", "description": "DB errors must surface"},
            ],
            "validation": {
                "passed": False,
                "failing_cases": ["test_injection_payload_is_not_executed", "test_database_error_is_not_silenced"],
                "issues": [
                    "The function opens its own connection: tests need a real file database (no injection of a connection).",
                    "Errors are swallowed, so failure modes cannot be asserted.",
                ],
            },
        }
    ],
    "reviewer": [
        {
            "summary": "Changes requested: not production-ready (1 critical, 2 high).",
            "approved": False,
            "rubric": {"correctness": 3, "edge_cases": 3, "robustness": 2, "readability": 6},
            "findings": [
                "Both reviews independently flag the error swallowing (Analyzer: bare except; Tester: unassertable failures).",
                "SQL injection is confirmed by a concrete failing test case.",
                "Design couples connection management, querying and aggregation.",
            ],
            "required_changes": [
                "Use parameterised queries for user_id and statuses (blocking).",
                "Close the connection with a context manager (blocking).",
                "Remove the bare except; let sqlite3.Error propagate or wrap it explicitly.",
                "Accept a connection (or repository) parameter so the function can be unit-tested.",
            ],
            "risks": ["Data exfiltration via user_id", "File-handle exhaustion under load", "Silent incorrect totals"],
        }
    ],
}

# --------------------------------------------------------------------------

SCENARIOS: dict[str, dict[str, Any]] = {
    "fix-bug": {
        "id": "fix-bug",
        "title": "Fix a Python Bug",
        "short_title": "Fix a Bug",
        "description": "A function crashes on empty input. Watch the agents analyse it, patch it, "
                       "catch a flawed first fix and loop back until the tests pass.",
        "task_type": "BUG_FIX",
        "highlights": ["4 agents", "Correction loop", "Conditional routing"],
        "code": BUG_CODE,
        "request": BUG_REQUEST,
        "script": BUG_SCRIPT,
    },
    "generate-tests": {
        "id": "generate-tests",
        "title": "Generate Unit Tests",
        "short_title": "Generate Tests",
        "description": "The orchestrator skips the Developer: no code change is needed. The Reviewer "
                       "sends the Tester back once to cover the edge cases the Analyzer found.",
        "task_type": "TEST_GEN",
        "highlights": ["3 of 4 agents", "Agent skipped", "Reviewer feedback loop"],
        "code": SLUG_CODE,
        "request": SLUG_REQUEST,
        "script": SLUG_SCRIPT,
    },
    "code-review": {
        "id": "code-review",
        "title": "Review My Code",
        "short_title": "Code Review",
        "description": "Two independent reviews run at the same time (quality and testability), "
                       "then the Reviewer merges them into a single verdict.",
        "task_type": "CODE_REVIEW",
        "highlights": ["Parallel execution", "Fan-out / fan-in", "Aggregated verdict"],
        "code": REVIEW_CODE,
        "request": REVIEW_REQUEST,
        "script": REVIEW_SCRIPT,
    },
}

SCENARIO_ORDER = ["fix-bug", "generate-tests", "code-review"]

# Step-by-step traces the scripted Tester produces for the cases it predicts will fail.
FAILING_TRACES = {
    "test_generator_input": (
        "numbers=<generator 2,4,6> -> `if not numbers` is False (generator objects are always truthy) "
        "-> sum(numbers)=12 consumes it -> len(numbers) on a generator",
        "returns 4", "raises TypeError: object of type 'generator' has no len()"),
    "test_empty_generator_raises": (
        "numbers=<empty generator> -> `if not numbers` is False -> sum(numbers)=0 -> len(numbers)",
        "raises ValueError", "raises TypeError, not ValueError"),
    "test_injection_payload_is_not_executed": (
        "user_id=\"x' OR '1'='1\" -> query becomes WHERE user_id = 'x' OR '1'='1' -> condition always true",
        "no rows", "returns all 3 orders"),
    "test_database_error_is_not_silenced": (
        "missing.db -> connect() creates an empty file -> execute() raises OperationalError (no such table) "
        "-> bare except sets rows=[]",
        "raises sqlite3.Error", "returns {'orders': [], 'total': 0}, no exception"),
}


def _split_tester(script: dict[str, list[dict[str, Any]]]) -> None:
    """Turn the single scripted Tester entries into the two-step format (write, then verify)."""
    write, verify = [], []
    for entry in script.pop("tester"):
        failing = set(entry["validation"]["failing_cases"])
        write.append({"summary": entry["summary"], "test_code": entry["test_code"], "cases": entry["cases"]})
        traces = []
        for case in entry["cases"]:
            if case["name"] in failing:
                trace, expected, predicted = FAILING_TRACES[case["name"]]
                traces.append({"case": case["name"], "trace": trace, "expected": expected,
                               "predicted": predicted, "passes": False})
            else:
                traces.append({"case": case["name"], "trace": f"Traced: {case['description'].lower()}.",
                               "expected": "assertion holds", "predicted": "assertion holds", "passes": True})
        verify.append({"traces": traces, "issues": entry["validation"]["issues"]})
    script["tester"] = write
    script["tester_verify"] = verify


for _scenario in SCENARIOS.values():
    _split_tester(_scenario["script"])


def public_scenarios() -> list[dict[str, Any]]:
    return [{k: v for k, v in SCENARIOS[s].items() if k != "script"} for s in SCENARIO_ORDER]
