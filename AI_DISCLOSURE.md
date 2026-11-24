# AI Disclosure

## Tool used

- **Claude** (Anthropic), used as a coding assistant during Practice 1.

## What was AI-generated

The AI assistant drafted most of the first version of this project. I then reviewed, ran and tested it.

| Part of the project | AI involvement |
|---|---|
| `src/budget_manager/models.py` | Drafted with AI: transaction schema and allowed values |
| `src/budget_manager/validation.py` | Drafted with AI: boundary checks and error messages |
| `src/budget_manager/services.py` | Drafted with AI: add / filter / summarise / undo / import |
| `src/budget_manager/storage.py` | Drafted with AI: CSV load/save with atomic writes |
| `src/budget_manager/cli.py` | Drafted with AI: argparse commands and interactive menu |
| `tests/test_budget_manager.py` | Drafted with AI: 33 pytest tests |
| `data/sample_transactions.csv` | Drafted with AI: 18 rows that trigger both valid and invalid cases |
| `notebooks/practice1_notebook.ipynb` | Drafted with AI: Think → Predict → Test evidence |
| `README.md`, `DESIGN.md` | Drafted with AI, then edited by me |

## Why I used AI

- **Speed within the sprint.** The practice is a 40-minute implementation sprint. Using AI for the first draft let me spend my time on the business rules, the boundary cases and verifying the behaviour, rather than on boilerplate.
- **Coverage of edge cases.** I used the assistant to suggest boundary inputs (leap days, `18,50` with a comma, `1000000.01`, duplicate IDs) that I then turned into explicit predictions and assertions.
- **Learning the structure.** Seeing a layered layout (CLI → service → validation/models → storage) helped me understand why separating responsibilities makes each part testable on its own.

## How I verified the AI output

- I ran every notebook cell and the full test suite (`python -m pytest -v`, 33 tests passing).
- For each behaviour I wrote down the expected result **before** running it and asserted it, so "it ran" became "it's verified".
- I checked the business decisions against the brief, in particular:
  - unknown categories are **rejected with the allowed list**, not silently mapped to `other`;
  - a data file with invalid rows opens **read-only**, so saving never silently deletes the user's rows;
  - undo is written to disk and still works after a crash and reload.
- Review caught a real bug: the duplicate-ID check originally compared only *valid* rows, so a second `T013` slipped through when the first `T013` was itself invalid. The check now runs on the raw ID before validation.

## Responsibility

I understand the code in this repository and can explain any part of it. All design decisions and the final submission are my responsibility.
