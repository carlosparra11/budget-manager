"""Tests for Release 1. Each test states its expected output explicitly.

Run from the project root:  python -m pytest -v
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from budget_manager.cli import main
from budget_manager.models import Transaction
from budget_manager.services import BudgetService, ReadOnlyError
from budget_manager.storage import CsvStorage, StorageError, read_csv, write_csv
from budget_manager.validation import ValidationError, parse_transaction

SAMPLE = Path(__file__).resolve().parents[1] / "data" / "sample_transactions.csv"


def raw(**overrides):
    base = {"id": "T001", "date": "2026-09-04", "kind": "expense",
            "category": "food", "amount": "18.50", "currency": "EUR"}
    base.update(overrides)
    return base


@pytest.fixture
def service(tmp_path):
    return BudgetService(CsvStorage(tmp_path / "tx.csv"))


# ---------------------------------------------------------------- normal case
def test_normal_add_list_and_report(service):
    service.add({"date": "2026-09-01", "kind": "income", "category": "salary",
                 "amount": "2500.00", "currency": "EUR"})
    service.add({"date": "2026-09-04", "kind": "expense", "category": "food",
                 "amount": "18.50", "currency": "EUR"})
    service.add({"date": "2026-09-05", "kind": "expense", "category": "food",
                 "amount": "6.50", "currency": "EUR"})

    assert [t.id for t in service.all()] == ["T001", "T002", "T003"]
    eur = service.summarize()["EUR"]
    assert eur.income == 2500.00
    assert eur.expense == 25.00
    assert eur.balance == 2475.00
    assert eur.by_category == {"food": 25.00}


def test_parse_valid_row_builds_typed_transaction():
    tx = parse_transaction(raw())
    assert tx == Transaction("T001", date(2026, 9, 4), "expense", "food", 18.50, "EUR")


def test_whitespace_and_case_are_normalised_but_nothing_else():
    tx = parse_transaction(raw(kind=" Expense ", category=" FOOD", currency="eur"))
    assert (tx.kind, tx.category, tx.currency) == ("expense", "food", "EUR")


# ------------------------------------------------------------ boundary tests
@pytest.mark.parametrize("amount, ok", [
    ("0.01", True),          # smallest valid amount
    ("1000000.00", True),    # largest valid amount
    ("0", False),            # zero is not a transaction
    ("0.00", False),
    ("-12.00", False),       # negatives rejected at entry
    ("1000000.01", False),   # above the cap
    ("18.505", False),       # 3 decimals: ambiguous, not rounded silently
])
def test_amount_boundaries(amount, ok):
    if ok:
        assert parse_transaction(raw(amount=amount)).amount == float(amount)
    else:
        with pytest.raises(ValidationError):
            parse_transaction(raw(amount=amount))


def test_negative_amount_message_is_actionable():
    with pytest.raises(ValidationError) as exc:
        parse_transaction(raw(amount="-5"))
    assert exc.value.errors == ["amount must be > 0 (got -5); use kind=expense for money out"]


@pytest.mark.parametrize("value", ["2026-02-30", "04/09/2026", "2026-9-4", ""])
def test_invalid_dates_rejected(value):
    with pytest.raises(ValidationError):
        parse_transaction(raw(date=value))


def test_leap_day_is_valid():
    assert parse_transaction(raw(date="2028-02-29")).date == date(2028, 2, 29)


def test_unknown_category_policy_is_reject_not_remap():
    with pytest.raises(ValidationError) as exc:
        parse_transaction(raw(category="gadgets"))
    assert "not allowed for expense" in exc.value.errors[0]
    assert "food" in exc.value.errors[0]  # lists allowed values


def test_category_must_match_kind():
    with pytest.raises(ValidationError):
        parse_transaction(raw(kind="income", category="food"))


def test_all_errors_reported_at_once():
    with pytest.raises(ValidationError) as exc:
        parse_transaction(raw(kind="refund", amount="abc", currency="JPY"))
    assert len(exc.value.errors) == 3


# ----------------------------------------------------------- malformed files
def test_sample_file_reports_each_bad_row_with_its_number():
    result = read_csv(SAMPLE)
    assert len(result.transactions) == 7
    assert "Row 5: amount must be > 0 (got -12.00); use kind=expense for money out" in result.errors
    assert "Row 15: id T013 duplicates row 14" in result.errors
    assert any(e.startswith("Row 9: date '04/09/2026'") for e in result.errors)


def test_wrong_header_is_a_file_level_error(tmp_path):
    bad = tmp_path / "bad.csv"
    bad.write_text("id,date,amount\nT001,2026-09-04,10\n", encoding="utf-8")
    with pytest.raises(StorageError, match="missing column"):
        read_csv(bad)


def test_missing_file_means_empty_store(tmp_path):
    assert read_csv(tmp_path / "nope.csv").transactions == []


def test_file_with_bad_rows_is_read_only(tmp_path):
    path = tmp_path / "tx.csv"
    path.write_text(SAMPLE.read_text(encoding="utf-8"), encoding="utf-8")
    before = path.read_text(encoding="utf-8")
    svc = BudgetService(CsvStorage(path))
    assert svc.read_only
    with pytest.raises(ReadOnlyError):
        svc.add({"date": "2026-09-20", "kind": "expense", "category": "food",
                 "amount": "1.00", "currency": "EUR"})
    assert path.read_text(encoding="utf-8") == before  # nothing deleted


# ------------------------------------------------------ persistence round-trip
def test_save_then_load_round_trip(tmp_path):
    txs = [parse_transaction(raw()),
           parse_transaction(raw(id="T002", kind="income", category="salary",
                                 amount="100", currency="USD"))]
    path = tmp_path / "tx.csv"
    write_csv(path, txs)
    loaded = read_csv(path)
    assert loaded.errors == []
    assert loaded.transactions == txs


def test_added_transactions_survive_restart(tmp_path):
    path = tmp_path / "tx.csv"
    BudgetService(CsvStorage(path)).add(
        {"date": "2026-09-04", "kind": "expense", "category": "food",
         "amount": "18.50", "currency": "EUR"})
    reloaded = BudgetService(CsvStorage(path))
    assert [(t.id, t.amount) for t in reloaded.all()] == [("T001", 18.50)]


def test_rejected_add_does_not_touch_file(service):
    with pytest.raises(ValidationError):
        service.add({"date": "2026-09-04", "kind": "expense", "category": "food",
                     "amount": "-1", "currency": "EUR"})
    assert service.all() == []
    assert not service.storage.path.exists()


def test_import_assigns_fresh_ids_and_reports_errors(service):
    service.add({"date": "2026-08-31", "kind": "expense", "category": "food",
                 "amount": "3.00", "currency": "EUR"})
    result = service.import_csv(SAMPLE)
    assert len(result.added) == 7
    assert [t.id for t in service.all()][:3] == ["T001", "T002", "T003"]
    assert len({t.id for t in service.all()}) == 8  # no collisions
    assert result.errors  # bad rows reported, not swallowed


# ----------------------------------------------------- stretch: undo + persist
def test_undo_is_persisted_to_disk(tmp_path):
    path = tmp_path / "tx.csv"
    svc = BudgetService(CsvStorage(path))
    for amount in ("1.00", "2.00"):
        svc.add({"date": "2026-09-04", "kind": "expense", "category": "food",
                 "amount": amount, "currency": "EUR"})
    removed = svc.undo_last()
    assert removed.id == "T002"
    assert [t.id for t in read_csv(path).transactions] == ["T001"]


def test_undo_after_crash_and_reload(tmp_path):
    path = tmp_path / "tx.csv"
    svc = BudgetService(CsvStorage(path))
    svc.add({"date": "2026-09-04", "kind": "expense", "category": "food",
             "amount": "1.00", "currency": "EUR"})
    svc.add({"date": "2026-09-05", "kind": "income", "category": "gift",
             "amount": "9.00", "currency": "EUR"})
    del svc  # simulate a crash: no in-memory history survives

    fresh = BudgetService(CsvStorage(path))
    assert fresh.undo_last().id == "T002"
    assert [t.id for t in BudgetService(CsvStorage(path)).all()] == ["T001"]
    # the freed id is reused, so ids stay sequential
    assert fresh.next_id() == "T002"


def test_undo_on_empty_store_returns_none(service):
    assert service.undo_last() is None


def test_failed_save_leaves_memory_and_disk_consistent(tmp_path):
    class BrokenStorage(CsvStorage):
        def save(self, transactions):
            raise OSError("disk full")

    svc = BudgetService(BrokenStorage(tmp_path / "tx.csv"))
    with pytest.raises(OSError):
        svc.add({"date": "2026-09-04", "kind": "expense", "category": "food",
                 "amount": "1.00", "currency": "EUR"})
    assert svc.all() == []  # memory not changed when disk write failed


# --------------------------------------------------------------- CLI journey
def test_cli_end_to_end(tmp_path):
    f = str(tmp_path / "tx.csv")
    out: list[str] = []
    assert main(["--file", f, "add", "--kind", "expense", "--category", "food",
                 "--amount", "18.50", "--date", "2026-09-04"], out=out.append) == 0
    assert main(["--file", f, "add", "--kind", "expense", "--category", "food",
                 "--amount", "-3", "--date", "2026-09-04"], out=out.append) == 2
    assert "  - amount must be > 0 (got -3); use kind=expense for money out" in out
    out.clear()
    assert main(["--file", f, "report"], out=out.append) == 0
    assert "Expense:        18.50" in out[0]
    assert "Balance:       -18.50" in out[0]


def test_interactive_reprompts_on_bad_input(tmp_path):
    answers = iter(["1",            # menu: add
                    "expense",
                    "gadgets", "food",       # bad category, then good
                    "-5", "12.30",           # bad amount, then good
                    "",                      # currency default EUR
                    "2026-09-04",
                    "6"])                    # quit
    out: list[str] = []
    code = main(["--file", str(tmp_path / "tx.csv")],
                input_fn=lambda _prompt: next(answers), out=out.append)
    assert code == 0
    assert any("not allowed for expense" in line for line in out)
    assert any("amount must be > 0" in line for line in out)
    assert any(line.startswith("Saved T001: expense 12.30 EUR") for line in out)
