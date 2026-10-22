# What changed in LbelDB 2.0.0

**Author:** UnTenseUnJury
**Date:** 2026-10-23
**Version:** 0.2.0 (repository) / 1.0.0 (PyPI) → **2.0.0**

This release repairs the whole project and fixes the biggest problems in its
design, while keeping **how LbelDB works**: one table, plain module-level
functions (`ldb.init()`, `ldb.add_r()`, `ldb.store()`, `ldb.switch()`...)
and the same function names.

Every change below explains **what was wrong**, **why it happened** and
**what happens now**. Every fix has a test in `tests/test_ldb.py` (52 tests,
all passing).

---

## Contents

**Part A: Design improvements**
1. [Rows are picked by id](#1-rows-are-picked-by-id)
2. [Asking questions: `where()`](#2-asking-questions-where)
3. [Data is saved next to your script](#3-data-is-saved-next-to-your-script)
4. [Missing values are `None`](#4-missing-values-are-none)
5. [Saving: the guarantees come first](#5-saving-the-guarantees-come-first)
6. [The global state, tidied up](#6-the-global-state-tidied-up)

**Part B: Bug fixes**

7. [Critical bugs (lost data or a frozen program)](#7-critical-bugs-lost-data-or-a-frozen-program)
8. [Other bugs](#8-other-bugs)
9. [Smaller improvements](#9-smaller-improvements)

**Part C: Everything else**

10. [Behaviour changes that can affect old code](#10-behaviour-changes-that-can-affect-old-code)
11. [The console](#11-the-console)
12. [Packaging: the PyPI release was empty](#12-packaging-the-pypi-release-was-empty)
13. [Tests](#13-tests)
14. [Documentation](#14-documentation)
15. [Moving data saved by the old version](#15-moving-data-saved-by-the-old-version)
16. [Known limitations, and what was deliberately not changed](#16-known-limitations-and-what-was-deliberately-not-changed)
17. [Files changed](#17-files-changed)

---

# Part A: Design improvements

## 1. Rows are picked by id

**What was wrong:** rows were picked by **position** (row 0, row 1...).
Positions change every time you sort or delete, so code that worked
yesterday could quietly change the wrong row today:

```python
ldb.update_ri(1, 1, 95)    # "row 1" - but after sort_col() that's a different person
```

Ids existed, but they were renumbered after almost every change (`genid()`
was called automatically). So an id was really just "position + 10001" and
didn't help.

**Now:** every row is picked by its **id**, and a row keeps its id for its
whole life.

```python
alice = ldb.add_r(("alice", 90))     # add_r() returns the new id: 10001
ldb.sort_col("score")                # alice moves - her id doesn't
ldb.clear_r(10002)                   # deleting bob doesn't renumber anyone
ldb.update_ri(alice, "score", 95)    # always alice
```

- `update_r`, `update_ri`, `clear_r` and `return_r` take ids.
- `find()` returns `[id, column]`, so `ldb.update_ri(*ldb.find(85), 86)` works.
- `update_c()` also accepts a dict `{id: value}` to change only some rows.
- Ids are **never reused**. The last id handed out is saved in the file, so
  after deleting row 10002 and restarting, the next row is still 10003.
- Internally a dict maps each id to its row, so finding a row by id is
  instant, however big the table is.
- `genid()` still exists for when you *want* fresh numbers. Its docstring
  warns that it changes the ids.
- Wrong ids give a clear message: `There is no row with id 99999`, or
  `Rows are picked by their id (a whole number like 10001), got '10001'`.

Columns are still picked by **name** or by **position** among your own
columns (0 = the first label you created; the id column isn't counted).

## 2. Asking questions: `where()`

**What was wrong:** a database is mainly for questions like "who scored
over 80?", but LbelDB had no way to ask them. `find()` only returned the
first exact match, so you had to pull out columns and loop over them yourself.

**Now:** there is a new `where()` function:

```python
ldb.where("score", ">", 80)              # == != > >= < <=
ldb.where("name", "contains", "li")      # text (or list) contains it
ldb.where("score", "in", (85, 90))       # value is one of these
ldb.where("score", "==", None)           # rows with a missing score
ldb.where("id", ">=", 10002)             # the id column works too
ldb.where("name", lambda n: n.startswith("a"))   # your own test
```

- It returns **copies** of the matching rows (each starting with its id), in
  the table's current order.
- Comparisons that make no sense for a cell, like `None > 80` or
  `"text" > 1`, simply don't match. They don't crash. This matters because
  columns often hold mixed values.
- Wrong use gets a clear message: an unknown operator lists the valid ones,
  and a missing value shows an example.

## 3. Data is saved next to your script

**What was wrong:** `.ldbs` was created in the **current working
directory**, which is wherever the program was *started from*, not where the
script lives. Running `python game/game.py` from your home folder put the
data in your home folder, so the next run started from inside `game/`
"lost" it. Beginners run into this all the time, especially from IDEs.

**Now:** databases are saved in `.ldbs` **inside the folder of the script
you ran**, wherever you start it from.

- It works by looking up the file of the `__main__` module.
- In the interactive prompt or Jupyter there is no script, so the current
  folder is used.
- **A packaged app** (PyInstaller, cx_Freeze) keeps its data next to its
  `.exe`. Its script runs from a temporary folder that is deleted when the
  app closes, so without this rule a packaged game would lose its data every
  time it closed.
- **When the "script" isn't your own code,** the current folder is used.
  That covers tools like pytest (otherwise your data would land inside
  pytest's installation) and commands installed by pip (on Windows their
  `__main__` even lives *inside* an `.exe`, so saving would crash).
- `ldb.init("data")` picks another folder. A relative folder is also taken
  relative to your script, so it is just as reliable.
- `exportjson("ldb.json")` also puts relative file names next to your script.
- The console (`python -m ldb`) keeps its databases in the folder you start it
  from. "Next to the script" would mean inside the installed package there.

I tested this end to end: a script in `app/`, started from another folder
twice, saved and loaded `app/.ldbs/` both times.

## 4. Missing values are `None`

**What was wrong:** a missing value was stored as an empty text `""`, so you
couldn't tell "no value" apart from "the value is empty text".

**Now:** missing values are **`None`**, Python's own "nothing here".

- Rows that are too short are filled with `None`.
- New columns from `add_c()` are `None` in existing rows.
- `""` is a real value and stays `""`, even after saving and loading.
- `view()` shows `None` as a blank cell.
- `sort_col()` always puts `None` last, in both directions.
- `ldb.where("score", "==", None)` finds rows with a missing value.
- The saved file has `null`, and `exportjson()` writes `null`.

## 5. Saving: the guarantees come first

**What was wrong:** "no corruption" was the headline promise, but the
original file format (one value per line, appended to, overwritten in place)
was the easiest way to corrupt data. Nothing was actually behind the promise.

**Now** the guarantees are written down first (in the `store()` docstring and
the README), and each one has a mechanism and a test:

| Guarantee | How | Test |
|---|---|---|
| **All or nothing:** the file is always the complete previous save or the complete new one, even after a crash or power cut | Write to a temporary file → `fsync` → swap it in with `os.replace()` (one step). On Linux/macOS the folder is also synced, so the swap survives a power cut | `test_failed_save_keeps_the_previous_save` |
| **Always readable:** a save can't leave a file that `retrieve()` can't load | The new contents are read back and fully checked *before* they replace the old file | (checked on every save) |
| **One step back:** a missing or damaged file is recovered | The previous save is kept as `<name>.lbel.bak`. `retrieve()` loads it automatically and raises an `ldb.LdbWarning`. The damaged file is kept as `<name>.lbel.damaged`, out of the way of the next save | `test_a_damaged_file_is_replaced_by_the_backup_with_a_warning`, `test_an_interrupted_save_is_recovered_from_the_backup` |

**What can still go wrong** is also written down, rather than promised
away. If two programs save the same database, the last save wins.

Other details:

- If the file is damaged and there's no backup, `retrieve()` raises
  `LdbError` and **doesn't touch memory**. It only replaces your data once the
  whole file has been read and checked.
- A value that can't be saved (for example an open file) is rejected
  **when you add it**, not later when you call `store()`.
- On Windows, the swap retries a few times, because OneDrive, Dropbox or an
  antivirus can hold a file open for a moment.

## 6. The global state, tidied up

**What was wrong:** LbelDB remembered its database in many separate global
variables (`lbels`, `data`, `cols`, `idv`, `path`, `c_file`, `cd_file`,
`temp`, `is_inio`). Every function had to keep them all in step by hand,
and many bugs came from them getting out of step. For example, `store()`
set `cols = None` while `lbels` was emptied separately. Also, any code
could write `ldb.data.append(...)` and silently break the table.

**Now** the functions work exactly as before (`ldb.add_r(...)`,
`ldb.switch(...)`...), but inside:

- Everything LbelDB remembers lives in **one object** (`_State`): the
  database name, the folder, the labels, the rows, the id → row lookup and
  the last id. There is one place to look, and one `clear()` that resets
  the table.
- `cols` is no longer stored separately. It is always just `len(labels)`, so
  it can't be wrong.
- `ldb.lbels`, `ldb.data`, `ldb.cols`, `ldb.idv`, `ldb.path` and
  `ldb.current_db` still work for reading, but they return **copies** (using a
  module-level `__getattr__`). Changing a copy can't damage the database.
  The functions are the only way to make changes, so every change is checked.
- The temporary variables that lived in the global namespace (`temp`,
  `tempv`, `tempo`) are gone.

---

# Part B: Bug fixes

## 7. Critical bugs (lost data or a frozen program)

### 7.1 Saving and loading used each other's files

After `store()` and then `retrieve()`, the rows came back as column names
and the table was empty:

```
before store:   labels ['id','name','score']   rows [[10001,'alice',90], [10002,'bob',85]]
after retrieve: labels ['10001','alice','90','10002','bob','85']   rows []
```

**Why:** `store()` wrote the rows into the labels file (`dbs.lbell`) and
the labels into the data file (`dat.lbeld`), and `retrieve()` read them the
other way round.

**Now:** each database is one file, `.ldbs/<name>/<name>.lbel`, so the two
can't be mixed up.

### 7.2 Saving more than once kept adding copies of the data

**Why:** rows were written in append mode (`"a"`). **Now:** each save
replaces the file.

### 7.3 `retrieve()` added rows to the table instead of replacing it

**Why:** it appended to `data` without emptying it first, so calling it
twice gave every row twice. **Now:** it replaces what is in memory.

### 7.4 `exportjson()` froze every later save or load

**Why:** the "busy" flag `is_inio` was set to `True` and never reset, so
`store()` and `retrieve()` waited forever in `while is_inio: pass`, using
100% of a CPU core.

**Now:** a real lock (`threading.RLock`), used with `with`, so it is always
released. It guards every public function, which also makes LbelDB safe to
use from several threads.

### 7.5 After `store()`, you couldn't add rows any more

**Why:** `store()` emptied memory and set `cols = None`, and `add_r()` then
crashed comparing `None` with a number. **Now:** data stays in memory after
saving.

### 7.6 Values containing a line break broke the file

**Why:** one value per line, so `"line 1\nline 2"` became two values and
shifted everything after it. **Now:** JSON escapes line breaks.

### 7.7 Switching databases could wipe the one you left

**Why:** `switch()` always saved first, even when nothing had been loaded
yet, which overwrote the saved file with an empty table. **Now:** it only
saves if the current database has columns.

## 8. Other bugs

| # | Function | What was wrong | Why | Now |
|---|---|---|---|---|
| 8.1 | `clear_c` | Deleting any normal column raised "Index is invalid" | The check was backwards: `if inx >= 0: raise`. A list crashed, and that branch never removed the values from the rows | Works with a name, a position or a list, and removes the column from every row |
| 8.2 | `add_r` | A tuple, e.g. `add_r(("bob", 5))`, crashed | Tuples have no `.append()` | Lists and tuples both work |
| 8.3 | `add_r` | It changed the list you passed in | It padded and inserted into *your* list | It works on a copy |
| 8.4 | `view` | Always crashed without `tabulate` | It returned `{[lbels] + [data]}`, which puts lists in a set | A built-in table is drawn instead |
| 8.5 | `view` | Viewing could change the data | `temp = data` doesn't copy | `view()` only reads |
| 8.6 | `return_c` | A list of columns crashed | `lbels[inx]` ran before the list check, and every column went into the same list | One list per column |
| 8.7 | `update_r` | A bad row number damaged the labels | It removed `"id"` and only put it back if nothing failed | The labels are never touched |
| 8.8 | `update_r` | Rows with too many values were accepted | It checked `len(val) > cols`, but `cols` counts the id too | The limit is your number of columns |
| 8.9 | `update_c` | A single value only changed the first row | `data[0][inx] = val` | It fills the whole column |
| 8.10 | `init` | If `.ldbs` existed but `default` didn't, `default` was never created | Both `mkdir`s were in one `try` | `os.makedirs(..., exist_ok=True)` |
| 8.11 | `new` | One of the new database's files went into the *current* database's folder | It used `path` instead of the new folder | It creates the new database's own folder |
| 8.12 | `delete` | Deleting a database with files in it failed | `os.rmdir` only removes empty folders | `shutil.rmtree`. Deleting the database in use is refused |
| 8.13 | `switch` | Checking whether a database existed created its files as a side effect | It "checked" by opening the files in mode `"a"` | It checks that the folder exists without creating anything |
| 8.14 | `sort_col` | Mixed values (e.g. numbers and text) crashed | Python can't compare `5 < "a"` | Numbers first, then text, missing values last |
| 8.15 | `sort_col` | The docstring said "descending" | It sorted ascending | The docstring is fixed |
| 8.16 | all paths | Only worked properly on Windows | Paths were written as `".ldbs\\default"` | `os.path.join` everywhere |
| 8.17 | labels | Duplicate or empty labels, or a label called `"id"`, were accepted and broke lookups and `exportjson()` | No checks | Rejected with a clear message |

## 9. Smaller improvements

- **Types are kept.** The old format turned everything into text (`90` came
  back as `"90"`). Now `int`, `float`, `bool`, `None`, `str`, `list`,
  `tuple`, `set`, `frozenset`, `complex` and `dict` all come back as the
  same type.
- **The saved file is readable.** It is JSON with one row per line:
  ```json
  {"format": "LbelDB", "version": 2, "last_id": 10003, "labels": ["id", "name", "score"], "rows": [
    [10001, "alice", 95],
    [10002, "bob", 85],
    [10003, "carol", null]
  ]}
  ```
  `"version"` lets future releases recognise older files. A file from a
  newer LbelDB gives a clear "please upgrade" error.
- **Clear errors.** Every mistake raises `ldb.LdbError` with a message that
  says what went wrong (a subclass of `Exception`, so old `except Exception:`
  code still works):
  ```
  LdbError: There is no column named 'scroe'. Columns: ['name', 'score']
  LdbError: There is no row with id 99999
  ```
- **All or nothing for several items.** `clear_r([10001, 99999])` used to
  delete the first row and then crash. Now every id is checked first.
- **Safe database names.** Only letters, digits, `_` and `-` are allowed, so
  a name like `"../../Documents"` can't reach outside `.ldbs`.
- **Columns by name** work everywhere: `ldb.sort_col("score")`,
  `ldb.return_c("name")`.
- `add_r()` returns the new id. `exportjson()` returns the file's path.
  `return_r()` and `where()` return copies. `retrieve()` returns `True`
  when it loaded something and `False` when nothing was saved yet.

---

# Part C: Everything else

## 10. Behaviour changes that can affect old code

| Old behaviour | New behaviour | What to do |
|---|---|---|
| `update_r`, `update_ri`, `clear_r`, `return_r` took a row **position** | They take the row's **id** | Use the id from `add_r()`, `find()` or `where()` |
| `find()` returned `[position, column]` | Returns `[id, column]` | Use it directly: `ldb.update_ri(*ldb.find(85), 86)` |
| ids were renumbered after every sort/delete | ids stay with their row | Call `genid()` if you want renumbering |
| Missing values were `""` | Missing values are `None` | Check with `is None` instead of `== ""` |
| `.ldbs` was created in the current working directory | `.ldbs` is created next to your script | Move an old `.ldbs` folder next to your script, or use `ldb.init(folder)` |
| `store()` emptied memory | Data stays in memory | Call `clearall()` if you relied on that |
| `return_c(0)`, `sort_col(0)`, `update_c(0, …)`, `clear_c(0)` meant the **id column** | `0` is your **first** column | Subtract 1 from old positions, or use names |
| `retrieve()` raised an exception if nothing was saved | Returns `False` | `if not ldb.retrieve(): ldb.create(...)` |
| `delete()` printed "The file does not exist" | Raises `LdbError` | Catch `ldb.LdbError` if needed |
| `create()` with rows present silently mixed up the columns | Allowed only to rename (same number of labels) | Use `add_c()`/`clear_c()`, or `clearall()` first |
| Writing to `ldb.data` / `ldb.lbels` changed the database | They are read-only copies | Use the functions |
| Files `dbs.lbell` + `dat.lbeld` | One file, `<name>.lbel` (plus `.bak`) | See [section 15](#15-moving-data-saved-by-the-old-version) |

## 11. The console

`ldb/console.py` was rewritten. The old version crashed on most typing
mistakes, and several commands never worked:

| Old problem | Now |
|---|---|
| `view` and `find` printed nothing | Every result is printed |
| Everything was text, so `add_r bob 90` stored `"90"` | Values are read like Python: `90` is a number, `"90"` is text, `[1,2]` is a list |
| No way to type text with spaces | Quotes work: `add_r "Ada Lovelace" 36` |
| `clear_c`, `return_r`, `update_ri` crashed | Arguments are converted. Rows are picked by id, columns by name or position |
| `sort_col 1` sorted *backwards* | `sort_col score` ascending, `sort_col score desc` descending |
| Any mistake crashed the console | It prints `Error: …` and keeps running |
| Missing commands | Added `where` (e.g. `where score > 80`, shown as a table), `new`, `switch`, `delete` (asks for confirmation), `exportjson` and `help` |
| `import ldb.console` started the console immediately | Wrapped in `main()` |
| Ctrl+C / Ctrl+D crashed | They quit cleanly |
| Box-drawing table characters crashed it when output was redirected on Windows | Unprintable characters are shown as `?` instead |

Warnings (such as "loaded the backup") are shown as `Warning: …` lines.
Start it with `python -m ldb` (new `ldb/__main__.py`), or `ldb` after
`pip install`.

## 12. Packaging: the PyPI release was empty

I downloaded **LbelDB 1.0.0 from PyPI**. The wheel contains **only
metadata and no Python code**: there is no `ldb/` folder, and `top_level.txt`
is empty. So right now `pip install LbelDB` succeeds, but `import ldb`
fails. The `setup.py` that built it was in `.gitignore`, so it was never in
the repository.

**Now:** a `pyproject.toml` lists the package explicitly, adds the
`pip install "LbelDB[pretty]"` option (which also installs `tabulate`) and
an `ldb` command for the console, and names UnTenseUnJury as author. I
built it and checked that the wheel contains `ldb/__init__.py`,
`ldb/console.py` and `ldb/__main__.py`, then installed it into a clean
environment and ran it.

**It has not been uploaded to PyPI**; that is up to you:

```bash
pip install build twine
python -m build
python -m twine upload dist/*
```

After uploading, consider "yanking" 1.0.0 on PyPI so pip stops choosing the
empty release.

## 13. Tests

`tests/test_ldb.py` has 52 tests. Each test gets a fresh database state and
a temporary folder, so tests can't affect each other or your real data.
They cover:

- **ids:** finding, updating and deleting by id; ids surviving sorts,
  deletes and reloads; ids never being reused; clear errors for bad ids.
- **`where()`:** every operator, functions, `None`, mixed-type columns,
  bad input, and returning copies.
- **Location:** saving next to the script when started from another folder,
  `init(folder)`, `exportjson()`, the fallback for Jupyter/the prompt, packaged
  apps, pytest and pip-made commands.
- **`None`:** padding, `add_c()`, keeping `""` apart from `None`, sorting,
  `view()`.
- **Guarantees:** a failed save keeps the previous save, a damaged file is
  recovered from the backup with a warning, an interrupted save is
  recovered, and damaged-with-no-backup raises without touching memory.
- **State:** `ldb.data`/`ldb.lbels` are copies that can't break the table.
- Every bug in Part B, and the console.

```bash
pip install pytest tabulate
python -m pytest
```

## 14. Documentation

- **In the code:** both modules start with a header naming the author
  (`UnTenseUnJury`), the project link and the license. `ldb.__author__` and
  `ldb.__version__` are set. The module docstring has a full example and
  explains rows, ids, columns and where files are saved. Every function has
  a docstring with its parameters and return value. Comments explain the
  *why* of the tricky parts: the save steps, the backup, the Windows retry,
  the folder sync, the sort order, the JSON tags, the lock and the
  read-only views.
- **README.md:** a working example (its output is copied from a real run), ids
  and columns, `where()`, a table of every function, where data is saved,
  the save guarantees, the console and the tests. The old example used an
  undefined `scores` variable.
- **.gitignore:** also ignores `.ldbs/`, `ldb.json`, `__pycache__/`, build
  output and virtual environments.

## 15. Moving data saved by the old version

2.0.0 can't read the old `dbs.lbell` / `dat.lbeld` files directly. The old
version couldn't read them back correctly either (bug 7.1). Put this script
in the folder that contains the old `.ldbs` folder and run it. I tested it on
files made by the old code, started from another folder:

```python
# migrate_old.py - put this file in the folder that contains the old .ldbs folder
import os
import ldb

old = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".ldbs", "default")
with open(os.path.join(old, "dat.lbeld"), encoding="utf-8") as f:   # the old store() put the labels here...
    labels = f.read().splitlines()
with open(os.path.join(old, "dbs.lbell"), encoding="utf-8") as f:   # ...and the values here
    values = f.read().splitlines()

ldb.init()
ldb.create(labels[1:])                                              # skip the old "id" label
width = len(labels)
for start in range(0, len(values) - width + 1, width):
    ldb.add_r(values[start + 1:start + width])                      # skip the old id
ldb.store()
print(ldb.view())
```

Things to know about converted data:

- Every value comes back as **text** (`"90"`, not `90`), because the old
  format only stored text. Fix types with `update_c()` if needed.
- If the old `store()` ran several times, rows appear several times
  (bug 7.2). Remove extras with `clear_r()`.
- Values that contained a line break can't be recovered correctly (bug 7.6).

## 16. Known limitations, and what was deliberately not changed

**Kept as designed, on purpose:**

- **Module-level functions and one open database at a time.** This is how
  LbelDB is meant to work. Use `switch()` to move between databases.
- **The function names** (`add_r`, `update_ri`, `return_c`...).
- **Rows are lists** (id first, then the values), not dicts.
- **Saving is manual.** Nothing is saved until you call `store()`.

**Limitations:**

- If two programs save the same database, the last save wins.
- Every `store()` rewrites the whole file. That's fine for thousands of
  rows, but not meant for millions (use `sqlite3` for that).
- The backup goes one save back, not further.
- `view()` builds the whole table as text, so it is slow for very big tables.
- Needs Python 3.10 or newer (every version still maintained). The tests run
  automatically on Windows, macOS and Linux with Python 3.10-3.14 (see
  `.github/workflows/tests.yml`), with and without `tabulate`.

## 17. Files changed

| File | Change |
|---|---|
| `ldb/__init__.py` | Rows by id, `where()`, save next to the script, `None` for missing, save guarantees with backup and recovery, the state gathered into one object with read-only views, all bug fixes, comments and docstrings |
| `ldb/console.py` | Rewritten: ids, `where`, value parsing, quoting, help, errors and warnings, new commands, `main()` |
| `ldb/__main__.py` | **New:** `python -m ldb` opens the console |
| `tests/test_ldb.py` | **New:** 52 tests |
| `pyproject.toml` | **New:** packaging that includes the code; `ldb` command; `[pretty]` extra; Python 3.10+ |
| `.github/workflows/tests.yml` | **New:** runs the tests on Windows, macOS and Linux, Python 3.10-3.14 |
| `README.md` | Rewritten for 2.0.0 |
| `.gitignore` | Ignores databases, exports and build/test leftovers |
| `changed.md` | **New:** this file |
| `LICENSE` | Unchanged (Unlicense) |
