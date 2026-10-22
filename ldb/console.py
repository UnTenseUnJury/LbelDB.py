# =============================================================================
#  LbelDB interactive console
#
#  Author  : UnTenseUnJury
#  Project : https://github.com/UnTenseUnJury/LbelDB.py
#
#  Start it with:   python -m ldb      (or just:  ldb   after pip install)
# =============================================================================
"""A small command prompt for trying LbelDB without writing a program."""

import ast
import os
import shlex
import sys
import warnings

import ldb

HELP = """\
Rows are picked by their id (10001, 10002, ...). Columns are picked by name
or by position (0 = first column you created; the id column isn't counted).

  create <label> ...             set the column names
  add_c <label> ...              add columns
  add_r <value> ...              add a row (shows its new id)
  update_r <id> <value> ...      replace a whole row
  update_c <col> <value> ...     replace a column (one value fills every row)
  update_ri <id> <col> <value>   change one value
  clear_r <id> ...               delete rows
  clear_c <col> ...              delete columns
  clearall                       empty the database in memory
  view                           show the table
  return_r <id> ...              show rows
  return_c <col> ...             show columns
  find <value>                   find the first cell with this value
  where <col> <op> <value>       show matching rows, e.g.  where score > 80
                                 (ops: == != > >= < <= contains in)
  sort_col <col> [desc]          sort the rows by a column
  genid                          renumber the ids 10001, 10002, ... (changes ids!)
  store / retrieve               save to / load from the file
  exportjson [file]              export to a JSON file (default: ldb.json)
  new / switch / delete <name>   manage several databases
  help                           show this text
  exit                           quit (this does NOT save - run store first)

Values are read like Python: 42 and 4.2 are numbers, True/False/None work,
and [1,2] is a list (no spaces inside). Anything else is text. Use quotes for
text with spaces, or to keep a number as text:  add_r "Ada Lovelace" "007"
Databases are kept in the .ldbs folder inside the folder you started from.
"""


def _value(token):
    """Read a typed word as a Python value: '42' -> 42, '"42"' -> '42', 'bob' -> 'bob'."""
    try:
        return ast.literal_eval(token)
    except (ValueError, SyntaxError, TypeError, MemoryError, RecursionError):
        return token


def _values(tokens):
    return [_value(token) for token in tokens]


def _id(token):
    """Read a row id, which must be a whole number."""
    try:
        return int(token)
    except ValueError:
        raise ldb.LdbError(f"A row id must be a whole number like 10001, got {token!r}") from None


def _one_value(tokens):
    """Several words without quotes count as one text: Ada Lovelace -> 'Ada Lovelace'."""
    return _value(tokens[0]) if len(tokens) == 1 else " ".join(tokens)


def _table(rows):
    """Show some rows as a table with the column names on top."""
    if not rows:
        return "No rows."
    return ldb._format_table(ldb.lbels, rows)


def _update_c(args):
    # one value -> fill every row; several values -> one per row, top to bottom
    ldb.update_c(_value(args[0]), _value(args[1]) if len(args) == 2 else _values(args[1:]))


def _return_r(args):
    return _table(ldb.return_r([_id(a) for a in args]))


def _return_c(args):
    columns = _values(args)
    return ldb.return_c(columns[0] if len(columns) == 1 else columns)


def _find(args):
    found = ldb.find(_one_value(args))
    return "Not found." if found is None else f"Found in row {found[0]}, column {found[1]}"


def _where(args):
    return _table(ldb.where(_value(args[0]), args[1].lower(), _one_value(args[2:])))


def _sort_col(args):
    reverse = len(args) > 1 and args[1].lower() in ("desc", "reverse")
    ldb.sort_col(_value(args[0]), reverse)


def _delete(args):
    # Deleting can't be undone, so ask first.
    answer = input(f"Permanently delete the database {args[0]!r}? [y/N] ")
    if answer.strip().lower() not in ("y", "yes"):
        return "Cancelled."
    ldb.delete(args[0])
    return f"Deleted {args[0]!r}."


# command name -> (minimum number of arguments, usage text, what to run).
# Whatever the action returns (if not None) is printed.
COMMANDS = {
    "help":       (0, "help", lambda a: HELP),
    "init":       (0, "init", lambda a: ldb.init()),
    "create":     (1, "create <label> ...", lambda a: ldb.create(_values(a))),
    "add_c":      (1, "add_c <label> ...", lambda a: ldb.add_c(_values(a))),
    "add_r":      (1, "add_r <value> ...", lambda a: f"Added row {ldb.add_r(_values(a))}"),
    "update_r":   (2, "update_r <id> <value> ...", lambda a: ldb.update_r(_id(a[0]), _values(a[1:]))),
    "update_c":   (2, "update_c <col> <value> ...", _update_c),
    "update_ri":  (3, "update_ri <id> <col> <value>",
                   lambda a: ldb.update_ri(_id(a[0]), _value(a[1]), _one_value(a[2:]))),
    "clear_r":    (1, "clear_r <id> ...", lambda a: ldb.clear_r([_id(x) for x in a])),
    "clear_c":    (1, "clear_c <col> ...", lambda a: ldb.clear_c(_values(a))),
    "clearall":   (0, "clearall", lambda a: ldb.clearall()),
    "view":       (0, "view", lambda a: ldb.view()),
    "return_r":   (1, "return_r <id> ...", _return_r),
    "return_c":   (1, "return_c <col> ...", _return_c),
    "find":       (1, "find <value>", _find),
    "where":      (3, "where <col> <op> <value>", _where),
    "sort_col":   (1, "sort_col <col> [desc]", _sort_col),
    "genid":      (0, "genid", lambda a: ldb.genid()),
    "store":      (0, "store", lambda a: ldb.store() or "Saved."),
    "retrieve":   (0, "retrieve", lambda a: "Loaded." if ldb.retrieve() else "Nothing saved yet."),
    "exportjson": (0, "exportjson [file]", lambda a: f"Exported to {ldb.exportjson(*a[:1])}"),
    "new":        (1, "new <name>", lambda a: ldb.new(a[0]) or f"Created database {a[0]!r}."),
    "switch":     (1, "switch <name>", lambda a: ldb.switch(a[0]) or f"Now using {a[0]!r}."),
    "delete":     (1, "delete <name>", _delete),
}


def run_command(line):
    """
    Run one line typed in the console.
    :return: the text to show, or None if there is nothing to show
    """
    try:
        # posix=False keeps the quotes, so '"42"' can stay text in _value().
        words = shlex.split(line, posix=False)
    except ValueError as error:          # e.g. a quote that is never closed
        return f"Error: {error}"
    if not words:
        return None
    name, args = words[0].lower(), words[1:]
    if name not in COMMANDS:
        return f"Unknown command {name!r}. Type 'help' to see the commands."
    min_args, usage, action = COMMANDS[name]
    if len(args) < min_args:
        return f"Usage: {usage}"
    # Collect LdbWarnings (e.g. "loaded the backup") to show them neatly.
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always", ldb.LdbWarning)
        try:
            result = action(args)
        except (ldb.LdbError, OSError) as error:
            # Show the problem and keep the console running instead of crashing.
            result = f"Error: {error}"
    lines = [f"Warning: {w.message}" for w in caught]
    if result is not None:
        lines.append(str(result))
    return "\n".join(lines) or None


def _show(text):
    """
    print() that can't crash. The table from view() uses box-drawing
    characters, which some terminals can't display (e.g. Windows when the
    output is redirected to a file). Those characters are shown as "?" instead.
    """
    try:
        print(text)
    except UnicodeEncodeError:
        encoding = getattr(sys.stdout, "encoding", None) or "ascii"
        print(text.encode(encoding, "replace").decode(encoding))


def main():
    """Start the console and keep reading commands until 'exit'."""
    print(f"LbelDB {ldb.__version__} console by {ldb.__author__} - type 'help' for the commands")
    # The console keeps its databases where you started it, not next to the
    # ldb package itself (which is what "next to the script" would mean here).
    ldb.init(os.path.join(os.getcwd(), ldb.ROOT))
    while True:
        try:
            line = input("LDB > ")
        except (EOFError, KeyboardInterrupt):    # Ctrl+D / Ctrl+Z / Ctrl+C
            print()
            break
        if line.strip().lower() in ("exit", "quit"):
            break
        output = run_command(line)
        if output:
            _show(output)


if __name__ == "__main__":
    main()
