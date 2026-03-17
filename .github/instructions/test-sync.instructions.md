---
description: "Enforce test synchronization after every code change. Use when modifying any src/ file — adding features, fixing bugs, refactoring. Covers test update rules, test run requirements, and iteration until green."
applyTo: "src/**/*.py"
---

# Test Synchronization — Project Convention

## Rule: Keep Tests in Sync With Code

After **every** modification to a file under `src/`, the corresponding unit test file must be updated in the same step — before the task is considered complete.

## Mapping: Source File → Test File

| Source file                                                 | Test file                                |
| ----------------------------------------------------------- | ---------------------------------------- |
| `src/PowerPlatform/Dataverse/extensions/sales_dashboard.py` | `tests/unit/test_sales_dashboard.py`     |
| `src/PowerPlatform/Dataverse/operations/records.py`         | `tests/unit/test_records_operations.py`  |
| `src/PowerPlatform/Dataverse/operations/query.py`           | `tests/unit/test_query_operations.py`    |
| `src/PowerPlatform/Dataverse/operations/tables.py`          | `tests/unit/test_tables_operations.py`   |
| `src/PowerPlatform/Dataverse/operations/files.py`           | `tests/unit/test_files_operations.py`    |
| `src/PowerPlatform/Dataverse/client.py`                     | `tests/unit/test_client.py`              |
| `src/PowerPlatform/Dataverse/core/_http.py`                 | `tests/unit/core/test_http_errors.py`    |
| `src/PowerPlatform/Dataverse/data/_odata.py`                | `tests/unit/data/test_odata_internal.py` |
| `src/PowerPlatform/Dataverse/data/_relationships.py`        | `tests/unit/data/test_relationships.py`  |

For new source files with no existing test file, create one at the matching path under `tests/unit/`.

## What Must Be Updated

- **New public method added** → add at least one test for the happy path and one for an edge case (e.g., empty input, wrong type).
- **Method signature changed** → update every test that calls that method.
- **Bug fixed** → add a regression test that fails before the fix and passes after.
- **Method deleted or renamed** → delete or rename its tests accordingly.
- **Behaviour change** (different return value, different exception) → update assertions in existing tests.

## How to Run Tests

Always use the virtual environment Python:

```powershell
.venv\Scripts\python.exe -m pytest tests/unit/test_<module>.py -v
```

To run the full suite:

```powershell
.venv\Scripts\python.exe -m pytest tests/ -v
```

## Required Outcome

The task is **not done** until:

1. All tests in the affected test file pass (`N passed`, 0 failed, 0 errors).
2. No previously passing tests in the rest of the suite are broken (run full suite when in doubt).

If a test fails, fix either the source code or the test (whichever is wrong) and re-run. Repeat until green.
