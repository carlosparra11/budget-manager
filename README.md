# Personal Budget Manager — Release 1

A command-line budget manager with a reliable core. You can add, list and report
transactions, save and load them from CSV, undo the last change, and import a CSV.
Every input is validated where it enters the system.

Standard library only. Python 3.10+ is required (developed on 3.13). Running the tests needs `pytest`.

## Setup

```bash
cd budget-manager
python -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install pytest
```

## Run

Run these from the project root, with `src` on the path:

```bash
export PYTHONPATH=src              # Windows PowerShell: $env:PYTHONPATH="src"
python -m budget_manager           # interactive menu (default)
```

Or use one-shot commands:

```bash
python -m budget_manager add --kind income  --category salary --amount 2500 --date 2026-09-01
python -m budget_manager add --kind expense --category food   --amount 18.50
python -m budget_manager list   --month 2026-09
python -m budget_manager report --kind expense
python -m budget_manager undo
python -m budget_manager import data/sample_transactions.csv
```

Data is stored in `data/transactions.csv` by default. Use `--file PATH` to pick a different file.
(If you'd rather not set `PYTHONPATH`, run `pip install -e .` and then the `budget` command.)

## Example session

```text
$ python -m budget_manager add --kind expense --category food --amount 18,50
Error: transaction rejected:
  - amount '18,50' uses a comma; use a dot for decimals, e.g. 18.50

$ python -m budget_manager report
=== EUR (2 transaction(s)) ===
  Income :      2500.00
  Expense:        18.50
  Balance:      2481.50
  Expenses by category:
    food               18.50  (100.0%)
```

## Test

```bash
python -m pytest -v
```

There are 33 tests, grouped as follows:
- **Normal path:** add → list → report, with exact totals.
- **Boundaries:** `0.01` and `1,000,000.00` are accepted. `0`, `-12`, `1,000,000.01` and `18.505` are rejected. A leap day is valid and `2026-02-30` is rejected.
- **Malformed input:** the sample file's bad rows each come back with their row number. A wrong header is a file-level error.
- **Persistence:** saving and reloading gives back the same data, transactions survive a restart, a rejected add leaves the file untouched, and a failed save leaves memory unchanged.
- **Undo (stretch):** undo is written to disk and still works after a crash and reload.
- **CLI:** an end-to-end journey, and interactive re-prompting after bad answers.

## Notebook

Open `notebooks/practice1_notebook.ipynb` (Jupyter or VS Code) and choose *Run All*. Each section states a prediction first, then asserts it. It runs in a temp folder, so your real data is never touched.

## Business rules (acceptance criteria)

| Rule | Example input | Result |
|---|---|---|
| Amount must be > 0 | `-12.00`, `0` | Rejected: "amount must be > 0" |
| Max 2 decimals, dot separator | `64.999`, `18,50` | Rejected (never rounded or reinterpreted) |
| Amount ≤ 1,000,000.00 | `1000000.01` | Rejected |
| Date is a real ISO date | `04/09/2026`, `2026-02-30` | Rejected |
| `kind` ∈ {expense, income} | `refund` | Rejected |
| Category is controlled vocabulary per kind | `gadgets`, or `food` as income | **Rejected, and the allowed list is shown** (the unknown-category policy) |
| Currency ∈ {EUR, USD, GBP} | `JPY` | Rejected |
| IDs unique, format `T001` | Two rows with `T013` | Second one rejected |
| Whitespace and case are trimmed | ` Food `, `eur` | Accepted as `food`, `EUR` |
| Reports never mix currencies | EUR + USD rows | One block per currency |
| A file with invalid rows is read-only | Edit `sample_transactions.csv` | Rows are listed; add/undo are blocked |

Allowed categories:
- **Expense:** food, housing, transport, utilities, health, entertainment, education, other.
- **Income:** salary, freelance, gift, other.

## Sample data

`data/sample_transactions.csv` has 18 rows. Seven are valid, and the rest each break one rule.
Run `python -m budget_manager import data/sample_transactions.csv` to see every rule fire with its row number.

## Project layout

```
src/budget_manager/
  models.py      Transaction schema + allowed values
  validation.py  boundary checks with actionable messages
  services.py    add / filter / summarise / undo / import
  storage.py     CSV load/save (atomic writes)
  cli.py         argparse + interactive menu, no business logic
tests/           pytest suite
notebooks/       practice1_notebook.ipynb (Think → Predict → Test evidence)
```

## Known limitations

- There is no currency conversion. Totals are reported separately for each currency.
- Undo only goes back one step at a time, always removing the **last row in the file**. There is no redo, and you can't undo an edit, because editing isn't supported yet.
- No edit or delete by ID yet.
- One user and one process. If two copies of the program write to the same file at once, the last write wins.
- The category and currency lists are hard-coded in `models.py`. They aren't configurable.
- Amounts are stored as `float`. That is fine at 2-decimal precision for these sizes, but `Decimal` would be safer (planned for Release 2).
