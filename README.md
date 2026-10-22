[![tests](https://github.com/UnTenseUnJury/LbelDB.py/actions/workflows/tests.yml/badge.svg)](https://github.com/UnTenseUnJury/LbelDB.py/actions/workflows/tests.yml)
[![PyPI](https://img.shields.io/pypi/v/LbelDB)](https://pypi.org/project/LbelDB/)
[![Python](https://img.shields.io/pypi/pyversions/LbelDB)](https://pypi.org/project/LbelDB/)
[![License: Unlicense](https://img.shields.io/badge/license-Unlicense-lightgreen.svg)](http://unlicense.org/)

# LbelDB.py

> **A small, text-based database for Python. Easy to use. Made for beginners.**

*By [UnTenseUnJury](https://github.com/UnTenseUnJury)*

LbelDB keeps a table in memory and saves it to a plain text file next to
your script. No server, no SQL, no setup.

## Installation

```bash
pip install LbelDB            # the library
pip install "LbelDB[pretty]"  # ...plus `tabulate` for nicer tables in view()
```

## Usage

```python
import ldb

ldb.init()                           # prepares .ldbs next to your script
if not ldb.retrieve():               # load the saved table, if there is one
    ldb.create(("name", "score"))    # first run: make the columns

alice = ldb.add_r(("alice", 90))     # add_r() gives back the new row's id
ldb.add_r(("bob", 85))
ldb.add_r(("carol",))                # carol's score is missing (None)

ldb.update_ri(alice, "score", 95)    # rows by id, columns by name

print(ldb.where("score", ">", 80))   # [[10001, 'alice', 95], [10002, 'bob', 85]]
print(ldb.view())                    # show the whole table

ldb.store()                          # save
```

```
╒═══════╤════════╤═════════╕
│    id │ name   │   score │
╞═══════╪════════╪═════════╡
│ 10001 │ alice  │      95 │
├───────┼────────┼─────────┤
│ 10002 │ bob    │      85 │
├───────┼────────┼─────────┤
│ 10003 │ carol  │         │
╘═══════╧════════╧═════════╛
```

### Rows, columns and ids

- **Rows are picked by their id.** Every row gets one (10001, 10002, ...)
  and keeps it forever, so sorting or deleting other rows never makes your
  code point at the wrong row. `add_r()` returns the id; `find()` and
  `where()` find ids for you.
- **Columns are picked by name** (`"score"`), or by position among *your*
  columns (`0` is the first label you created; the id column isn't counted).
- **Missing values are `None`.** Rows that are too short are filled with
  `None`, and `view()` shows them as blank cells. An empty text `""` is a real
  value and stays `""`.

### Asking questions with `where()`

```python
ldb.where("score", ">", 80)              # == != > >= < <=
ldb.where("name", "contains", "li")      # text (or list) contains it
ldb.where("score", "in", (85, 90))       # value is one of these
ldb.where("score", "==", None)           # rows with a missing score
ldb.where("name", lambda n: n.startswith("a"))   # your own test
```

Each call returns the matching rows (each one starting with its id), in the
table's order. A comparison that makes no sense for a cell, like `None > 80`,
just doesn't match. It doesn't crash.

### All functions

| Function | What it does |
| --- | --- |
| `init(folder=None)` | Prepare the database folder (default: `.ldbs` next to your script) |
| `create(labels)` | Set the column names |
| `add_c(labels)` | Add columns |
| `add_r(values)` | Add a row; returns its id |
| `update_r(id, values)` | Replace a whole row |
| `update_c(col, values)` | Replace a column: one value for every row, a list (top to bottom), or a dict `{id: value}` |
| `update_ri(id, col, value)` | Change one value |
| `clear_r(ids)` / `clear_c(cols)` | Delete rows / columns |
| `clearall()` | Empty the database in memory |
| `view()` | The table as text, for `print()` |
| `return_r(ids)` / `return_c(cols)` | Get rows / columns |
| `find(value)` | `[id, column]` of the first match, or `None` |
| `where(col, op, value)` | Every row that matches |
| `sort_col(col, reverse=False)` | Sort the rows by a column (missing values last) |
| `genid()` | Renumber the ids 10001, 10002, ... (this changes them!) |
| `store()` / `retrieve()` | Save / load (`retrieve()` returns `False` if nothing was saved yet) |
| `exportjson(filename="ldb.json")` | Export to a plain JSON file |
| `new(name)` / `switch(name)` / `delete(name)` | Work with several databases |

Every mistake (unknown id, unknown column, unknown database...) raises
`ldb.LdbError` with a message explaining what went wrong.

`ldb.lbels`, `ldb.data`, `ldb.cols` and `ldb.idv` can still be read, but they
are copies. Use the functions above to change the database.

Values can be text, numbers, `True`/`False`, `None`, lists, tuples, sets,
dicts and complex numbers. They come back from `retrieve()` with the same type.

### Where is my data?

In `.ldbs/<name>/<name>.lbel`, inside **the folder of your script**, no
matter which folder you start the program from. A program packaged with
PyInstaller keeps its data next to its `.exe`. In the interactive prompt,
Jupyter or pytest, the current folder is used. To keep it somewhere else,
use `ldb.init("my_data_folder")`.

The file is JSON with one row per line, so you can open it in any text editor.

### What a save guarantees

1. **All or nothing.** The file always holds either the complete previous
   save or the complete new one, never a mix, even if your program crashes
   or the power goes out while it is saving.
2. **Always readable.** A save is read back and checked *before* it replaces
   the old file.
3. **One step back.** The previous save is kept as `<name>.lbel.bak`. If the
   file is ever missing or damaged, `retrieve()` loads the backup instead and
   warns you (`ldb.LdbWarning`). The damaged file is kept as
   `<name>.lbel.damaged` so you can look at it.

**Not guaranteed:** if two programs save the same database, the last save
wins.

### Console

Try LbelDB without writing a program:

```bash
ldb               # after pip install
python -m ldb     # or from a clone of this repository
```

Type `help` in the console to see the commands. The console keeps its
databases in the folder you start it from.

## Running the tests

```bash
pip install pytest tabulate
python -m pytest
```

## Contributing

Pull requests are welcome. For major changes, please open an issue first to
discuss what you would like to change. Please add or update tests in `tests/`.

See [changed.md](changed.md) for what changed in 2.0.0.

## License

[Unlicense](https://choosealicense.com/licenses/unlicense/) - author: UnTenseUnJury
