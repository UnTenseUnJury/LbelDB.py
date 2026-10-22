# =============================================================================
#  LbelDB  -  a small, beginner-friendly database for Python
#
#  Author  : UnTenseUnJury
#  Project : https://github.com/UnTenseUnJury/LbelDB.py
#  License : The Unlicense (public domain) - see the LICENSE file
# =============================================================================
"""
LbelDB (imported as ``ldb``) keeps one table in memory and saves it to a
readable text file::

    import ldb

    ldb.init()                           # prepares .ldbs next to your script
    if not ldb.retrieve():               # load the saved table, if there is one
        ldb.create(("name", "score"))    # first run: make the columns

    alice = ldb.add_r(("alice", 90))     # add_r() gives back the new row's id
    ldb.add_r(("bob", 85))
    ldb.update_ri(alice, "score", 95)    # rows by id, columns by name

    print(ldb.where("score", ">", 80))   # ask the table a question
    print(ldb.view())                    # show the whole table
    ldb.store()                          # save

How the table is laid out
-------------------------
* The column names are the "labels". The first one is always "id"; LbelDB
  adds and manages that column for you.
* Every row is a list: its id first, then one value per label.
  A missing value is ``None``.

How rows and columns are picked
-------------------------------
* A row is picked by its **id** (10001, 10002, ...). A row keeps its id for
  its whole life, so sorting or deleting other rows can never make your code
  point at the wrong row. add_r() returns the id; find() and where() find ids.
* A column is picked by its **name** ("score"), or by its position among
  your own columns (0 = the first label you created; the id isn't counted).

Where things are saved
----------------------
In ``.ldbs/<name>/<name>.lbel``, inside the folder of the script you ran -
not whatever folder you happened to start it from. (In the interactive
prompt or Jupyter there is no script, so the current folder is used.)
``init(folder=...)`` picks another place. What a save guarantees is
explained in store().
"""

import copy
import functools
import io
import json
import operator
import os
import re
import shutil
import sys
import sysconfig
import tempfile
import threading
import time
import warnings

try:
    # tabulate is optional - it only makes view() look nicer.
    from tabulate import tabulate
except ImportError:
    tabulate = None

__author__ = "UnTenseUnJury"
__version__ = "2.0.0"

__all__ = [
    "LdbError", "LdbWarning",
    "init", "create", "add_c", "add_r", "clear_r", "clear_c", "clearall",
    "view", "return_r", "return_c", "genid", "update_r", "update_c",
    "update_ri", "sort_col", "find", "where", "exportjson", "retrieve",
    "store", "new", "delete", "switch",
]

# -----------------------------------------------------------------------------
# Settings
# -----------------------------------------------------------------------------
ROOT = ".ldbs"            # folder that holds every database
DEFAULT_DB = "default"    # database in use until switch() is called
FILE_EXT = ".lbel"        # extension of a saved database
BACKUP_EXT = ".bak"       # the previous save:   default.lbel.bak
DAMAGED_EXT = ".damaged"  # a file that couldn't be read is moved aside to this
FIRST_ID = 10001          # id given to the very first row
FORMAT_VERSION = 2        # increase whenever the layout of the file changes

# Database names may only use letters, digits, "_" and "-", so a name can
# never point outside the .ldbs folder (like "../../Documents").
_NAME_RE = re.compile(r"[\w-]+")

# Arguments of these types mean "several values" (e.g. several cells for
# add_r()). Anything else counts as one single value.
_MANY = (list, tuple)
# Arguments that list several ids or columns may also be a set or a range.
_SEVERAL = (list, tuple, set, frozenset, range)

# The operators where() understands, and what each one checks.
_OPERATORS = {
    "==": operator.eq,
    "!=": operator.ne,
    ">": operator.gt,
    ">=": operator.ge,
    "<": operator.lt,
    "<=": operator.le,
    "contains": lambda cell, value: value in cell,   # "li" in "alice"
    "in": lambda cell, value: cell in value,         # 85 in (85, 90)
}

# Marks "no value given", for arguments where None is a real value.
_NOTHING = object()


class LdbError(Exception):
    """
    Raised when LbelDB is used the wrong way (unknown id, unknown column,
    unknown database...). It is a subclass of Exception, so
    ``except Exception`` still catches it.
    """


class LdbWarning(UserWarning):
    """
    Shown when LbelDB fixed a problem by itself, e.g. it loaded the backup
    because the saved file was damaged. Your program keeps running.
    """


# -----------------------------------------------------------------------------
# The state of the open database
#
# Everything LbelDB remembers lives in ONE object, ``_db``, instead of being
# spread over many global variables that had to be kept in step by hand.
# Old code that reads ``ldb.data`` or ``ldb.lbels`` still works: see
# __getattr__ at the bottom of this file.
# -----------------------------------------------------------------------------
class _State:
    """Everything LbelDB remembers about the database that is open now."""

    def __init__(self):
        self.name = DEFAULT_DB      # name of the open database
        self.root = None            # folder chosen with init(folder=...), if any
        self.labels = []            # column names; labels[0] == "id" after create()
        self.rows = []              # the rows, in display order; row[0] is the id
        self.by_id = {}             # id -> row, so a row is found instantly by its id
        self.last_id = FIRST_ID - 1 # last id handed out; the next row gets last_id + 1

    def clear(self):
        """Forget the table (but not which database is open or where)."""
        self.labels, self.rows, self.by_id = [], [], {}
        self.last_id = FIRST_ID - 1

    def root_folder(self):
        """The folder holding every database: .ldbs next to your script by default."""
        return self.root or _resolve(ROOT)

    def folder(self, name=None):
        """Folder of the database ``name`` (default: the open one)."""
        return os.path.join(self.root_folder(), name or self.name)

    def file(self):
        """Full path of the open database's file."""
        return os.path.join(self.folder(), self.name + FILE_EXT)


_db = _State()

# One lock guards every public function, so two threads can't change the
# database (or its file) at the same moment. It is re-entrant (an RLock)
# because some functions call others, e.g. switch() calls store().
_lock = threading.RLock()


def _locked(func):
    """Decorator: run ``func`` while holding the lock."""
    @functools.wraps(func)
    def wrapper(*args, **kwargs):
        with _lock:
            return func(*args, **kwargs)
    return wrapper


# -----------------------------------------------------------------------------
# Small helpers used by the public functions below
# -----------------------------------------------------------------------------
def _as_list(value):
    """Copy a list/tuple into a new list; wrap any other value in a list."""
    return list(value) if isinstance(value, _MANY) else [value]


def _as_several(value):
    """Like _as_list(), but sets and ranges also count as several values."""
    return list(value) if isinstance(value, _SEVERAL) else [value]


def _require_labels():
    """Stop with a clear message if create() hasn't been called yet."""
    if not _db.labels:
        raise LdbError("The database has no columns yet. Call create() "
                       "first, or retrieve() a saved database.")


def _row(row_id):
    """Find a row by its id (the row itself, not a copy)."""
    if isinstance(row_id, bool) or not isinstance(row_id, int):
        raise LdbError(f"Rows are picked by their id (a whole number like {FIRST_ID}), got {row_id!r}")
    try:
        return _db.by_id[row_id]
    except KeyError:
        raise LdbError(f"There is no row with id {row_id}") from None


def _col(column, allow_id=False):
    """
    Turn a column (label name or position) into its position inside a row.
    Rows store the id first, so the user's column 0 is position 1 in a row.
    :param allow_id: True for functions that only *read* the column, which
                     may then use the id column too, e.g. sort_col("id")
    """
    _require_labels()
    if isinstance(column, str):
        if column == "id":
            if allow_id:
                return 0
            raise LdbError("The id column is managed by LbelDB and can't be changed")
        if column in _db.labels:
            return _db.labels.index(column)
        raise LdbError(f"There is no column named {column!r}. Columns: {_db.labels[1:]}")
    if isinstance(column, bool) or not isinstance(column, int):
        raise LdbError(f"A column must be a label name (str) or a position (int), got {column!r}")
    count = len(_db.labels) - 1            # number of user columns (no id)
    position = column + count if column < 0 else column
    if not 0 <= position < count:
        raise LdbError(f"Column {column} is out of range: there are {count} column(s)")
    return position + 1                    # skip over the id


def _clean_labels(new_labels, taken):
    """
    Check new column names and return them as text.
    :param new_labels: the names that were asked for
    :param taken: names already in use (a name can't be used twice)
    """
    cleaned = []
    for label in new_labels:
        if isinstance(label, bool) or not isinstance(label, (str, int, float)):
            raise LdbError(f"A label must be text (or a number), got {label!r}")
        label = str(label)
        if not label:
            raise LdbError("A label can't be empty")
        if label == "id":
            raise LdbError('"id" is reserved: LbelDB adds the id column itself')
        if label in taken or label in cleaned:
            raise LdbError(f"The label {label!r} is used twice")
        cleaned.append(label)
    return cleaned


def _check_savable(value):
    """Fail right away (rather than later in store()) if a value can't be saved."""
    _encode(value)


def _fit_row(values):
    """Check a row's values and fill the missing ones at the end with None."""
    count = len(_db.labels) - 1
    if len(values) > count:
        raise LdbError(f"Got {len(values)} value(s), but the database only has {count} column(s)")
    for value in values:
        _check_savable(value)
    return values + [None] * (count - len(values))


def _sort_key(value):
    """
    Sort key that works on mixed columns. Python can't compare 5 < "abc",
    so numbers are put first (in number order) and everything else after
    them (in alphabetical order of its text).
    """
    if isinstance(value, (int, float)):    # bool counts as a number too
        return (0, value, "")
    return (1, 0, str(value))


def _format_table(headers, rows):
    """Draw rows as a text table, with tabulate if it is installed."""
    if tabulate is not None:
        return tabulate(rows, headers=headers, tablefmt="fancy_grid")   # shows None as blank
    return _plain_table(headers, rows)


def _plain_table(headers, rows):
    """
    Draw a simple text table, used when tabulate isn't installed:

        +-------+-------+
        | id    | name  |
        +-------+-------+
        | 10001 | alice |
        +-------+-------+
    """
    def show(cell):
        # Missing values show as blank, and line breaks as "\n" so a value
        # can't break the table's layout.
        return "" if cell is None else str(cell).replace("\n", "\\n")

    text = [[show(cell) for cell in row] for row in [headers] + list(rows)]
    widths = [max(len(row[i]) for row in text) for i in range(len(headers))]
    border = "+" + "+".join("-" * (width + 2) for width in widths) + "+"

    def line(row):
        return "| " + " | ".join(cell.ljust(width) for cell, width in zip(row, widths)) + " |"

    out = [border, line(text[0]), border]
    out += [line(row) for row in text[1:]]
    if rows:
        out.append(border)
    return "\n".join(out)


# -----------------------------------------------------------------------------
# Turning values into JSON and back
#
# JSON only knows text, numbers, true/false, null, lists and objects with
# text keys. Other common Python types are saved as small tagged objects so
# they come back as the same type after retrieve(), for example
#     (1, 2)  ->  {"__tuple__": [1, 2]}
# -----------------------------------------------------------------------------
def _encode(value):
    """Convert ``value`` into something json can write."""
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    if isinstance(value, list):
        return [_encode(item) for item in value]
    if isinstance(value, tuple):
        return {"__tuple__": [_encode(item) for item in value]}
    if isinstance(value, frozenset):
        return {"__frozenset__": [_encode(item) for item in value]}
    if isinstance(value, set):
        return {"__set__": [_encode(item) for item in value]}
    if isinstance(value, complex):
        return {"__complex__": [value.real, value.imag]}
    if isinstance(value, dict):
        # saved as [key, value] pairs, so the keys don't have to be text
        return {"__dict__": [[_encode(k), _encode(v)] for k, v in value.items()]}
    raise LdbError(f"LbelDB can't save a value of type {type(value).__name__}: {value!r}")


def _decode(value):
    """Undo _encode(): rebuild tuples, sets, complex numbers and dicts."""
    if isinstance(value, list):
        return [_decode(item) for item in value]
    if isinstance(value, dict):
        if len(value) != 1:
            raise ValueError(f"unexpected object {value!r}")
        (tag, items), = value.items()
        if tag == "__tuple__":
            return tuple(_decode(item) for item in items)
        if tag == "__set__":
            return {_decode(item) for item in items}
        if tag == "__frozenset__":
            return frozenset(_decode(item) for item in items)
        if tag == "__complex__":
            return complex(items[0], items[1])
        if tag == "__dict__":
            return {_decode(k): _decode(v) for k, v in items}
        raise ValueError(f"unknown tag {tag!r}")
    return value


def _plain(value):
    """
    Convert a value for exportjson(). That file is meant for other programs,
    so it uses plain JSON only: tuples and sets become lists, and complex
    numbers become text.
    """
    if isinstance(value, (list, tuple, set, frozenset)):
        return [_plain(item) for item in value]
    if isinstance(value, dict):
        return {str(k): _plain(v) for k, v in value.items()}
    if isinstance(value, complex):
        return str(value)
    return value


def _parse(saved):
    """
    Check the contents of a saved file and return (labels, rows, last_id).
    Raises ValueError/KeyError/TypeError/IndexError if anything is wrong.
    """
    if not isinstance(saved, dict) or saved.get("format") != "LbelDB":
        raise ValueError("it is not an LbelDB file")
    if saved.get("version", 0) > FORMAT_VERSION:
        raise ValueError("it was saved by a newer version of LbelDB - please upgrade")
    labels = saved["labels"]
    if (not isinstance(labels, list) or (labels and labels[0] != "id")
            or not all(isinstance(label, str) and label for label in labels)
            or len(set(labels)) != len(labels)):
        raise ValueError("its column names are damaged")
    rows = [_decode(row) for row in saved["rows"]]
    for row in rows:
        if (not isinstance(row, list) or len(row) != len(labels)
                or isinstance(row[0], bool) or not isinstance(row[0], int)):
            raise ValueError("a row doesn't match the column names")
    ids = [row[0] for row in rows]
    if len(set(ids)) != len(ids):
        raise ValueError("two rows have the same id")
    last_id = max([saved.get("last_id", FIRST_ID - 1)] + ids)
    return labels, rows, last_id


# -----------------------------------------------------------------------------
# Files
# -----------------------------------------------------------------------------
def _script_folder():
    """
    The folder of the program you started (``python my_game.py`` ->
    the folder of my_game.py). When that isn't a sensible place for data,
    see the cases below, the current folder is used instead.
    """
    # A packaged app (PyInstaller, cx_Freeze...): keep the data next to the
    # .exe. Its script runs from a temporary folder that is deleted when the
    # app closes, so saving there would lose everything.
    if getattr(sys, "frozen", False):
        return os.path.dirname(os.path.abspath(sys.executable))
    main_file = getattr(sys.modules.get("__main__"), "__file__", None)
    if main_file:
        folder = os.path.dirname(os.path.abspath(main_file))
        # Skip "scripts" that aren't your own code: an installed tool such as
        # pytest, or a command made by pip (on Windows its __main__ even lives
        # *inside* an .exe file, so its "folder" isn't a folder at all).
        if os.path.isdir(folder) and not _is_installed_code(folder):
            return folder
    # The interactive prompt, Jupyter, or one of the cases above.
    return os.getcwd()


def _is_installed_code(folder):
    """True if ``folder`` is where Python keeps installed packages or commands."""
    places = []
    schemes = [None]
    try:
        schemes.append(sysconfig.get_preferred_scheme("user"))   # Python 3.10+
    except AttributeError:
        schemes.append(f"{os.name}_user")
    for scheme in schemes:
        try:
            paths = sysconfig.get_paths(scheme) if scheme else sysconfig.get_paths()
        except KeyError:
            continue
        places += [paths.get("purelib"), paths.get("platlib"), paths.get("scripts")]
    folder = os.path.normcase(os.path.abspath(folder))
    for place in filter(None, places):
        place = os.path.normcase(os.path.abspath(place))
        if folder == place or folder.startswith(place + os.sep):
            return True
    return False


def _resolve(path):
    """
    Turn a path into a full path. A relative path is taken relative to your
    script's folder, so your files are found no matter which folder the
    program is started from.
    """
    return os.path.abspath(os.path.join(_script_folder(), os.fspath(path)))


def _check_name(name):
    """Make sure a database name is safe to use as a folder name."""
    if not isinstance(name, str) or not _NAME_RE.fullmatch(name):
        raise LdbError(f"Invalid database name {name!r}: use only letters, digits, '_' and '-'")


def _write_atomically(file_path, text, backup_path=None):
    """
    Write ``text`` to ``file_path`` without ever leaving a half-written file:

    1. write everything to a temporary file in the same folder,
    2. force it onto the disk (fsync),
    3. if asked, turn the current file into the backup,
    4. swap the temporary file into place with os.replace(). That swap
       happens in one step: the file is either the old one or the new one.

    If anything fails, the temporary file is thrown away.
    """
    folder = os.path.dirname(file_path)
    os.makedirs(folder, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(dir=folder, prefix=".ldb-", suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as tmp:
            tmp.write(text)
            tmp.flush()
            os.fsync(tmp.fileno())
        if backup_path and os.path.exists(file_path):
            # If the program stops right after this line, the file is missing
            # but the backup is complete - and retrieve() falls back to it.
            _replace(file_path, backup_path)
        _replace(tmp_path, file_path)
    except BaseException:
        try:
            os.remove(tmp_path)
        except OSError:
            pass
        raise
    _fsync_folder(folder)


def _replace(src, dst, attempts=5):
    """
    os.replace() with a few retries. On Windows, antivirus or sync tools
    (OneDrive, Dropbox...) can keep a file open for a moment, which makes
    os.replace() fail with PermissionError. A short wait usually fixes it.
    """
    for attempt in range(attempts):
        try:
            os.replace(src, dst)
            return
        except PermissionError:
            if attempt == attempts - 1:
                raise
            time.sleep(0.05 * (attempt + 1))


def _fsync_folder(folder):
    """
    On Linux and macOS, a renamed file only survives a power cut once its
    folder has been synced too. (Windows can't do this and doesn't need it.)
    """
    if os.name == "nt":
        return
    try:
        fd = os.open(folder, os.O_RDONLY)
    except OSError:
        return
    try:
        os.fsync(fd)
    except OSError:
        pass
    finally:
        os.close(fd)


def _load(file_path):
    """Read and check a saved file. Raises LdbError if it can't be used."""
    try:
        with io.open(file_path, "r", encoding="utf-8") as f:
            return _parse(json.load(f))
    except (OSError, ValueError, KeyError, TypeError, IndexError, AttributeError) as error:
        raise LdbError(f"Could not read {file_path}: {error}") from error


def _use(labels, rows, last_id):
    """Put a loaded table into memory."""
    _db.labels, _db.rows, _db.last_id = labels, rows, last_id
    _db.by_id = {row[0]: row for row in rows}


# -----------------------------------------------------------------------------
# Creating the database and its columns
# -----------------------------------------------------------------------------
@_locked
def init(folder=None):
    """
    Prepares the folder of the current database.
    Safe to call every time your program starts - it never deletes anything.
    :param folder: where to keep your databases. Default: a ".ldbs" folder
                   next to your script. A relative folder is also taken
                   relative to your script, e.g.  ldb.init("data")
    :return: None
    """
    if folder is not None:
        _db.root = _resolve(folder)
    os.makedirs(_db.folder(), exist_ok=True)


@_locked
def create(labels):
    """
    Creates the headers (labels / column names) of the database.
    The "id" column is added automatically as the first column.

    If the database already has rows, create() can only *rename* the columns,
    so it must get as many labels as there are columns. (Use add_c() or
    clear_c() to change the number of columns, or clearall() to start over.)

    :param labels: one label (str) or a list/tuple of labels
    :return: None
    """
    new_labels = _clean_labels(_as_list(labels), taken=[])
    if not new_labels:
        raise LdbError("create() needs at least one label")
    if _db.rows and len(new_labels) != len(_db.labels) - 1:
        raise LdbError(
            f"The database already has rows with {len(_db.labels) - 1} column(s), but "
            f"create() got {len(new_labels)} label(s). Use add_c()/clear_c() to change "
            "the columns, or clearall() to start over."
        )
    _db.labels = ["id"] + new_labels


@_locked
def add_c(arg):
    """
    Adds one or more columns at the end. Existing rows get None (missing) there.
    If the database has no columns yet, this works just like create().
    :param arg: one label (str) or a list/tuple of labels
    :return: None
    """
    if not _db.labels:
        create(arg)
        return
    new_labels = _clean_labels(_as_list(arg), taken=_db.labels[1:])
    _db.labels.extend(new_labels)
    for row in _db.rows:
        row.extend([None] * len(new_labels))


# -----------------------------------------------------------------------------
# Adding and removing rows / columns
# -----------------------------------------------------------------------------
@_locked
def add_r(dat):
    """
    Adds a row at the end of the database and gives it a new id.
    :param dat: the row's values in column order, as a list or tuple.
                A single value is fine too (it goes in the first column).
                Missing values at the end become None.
    :note: To store a list *inside* one cell, wrap it: add_r(["bob", [1, 2]])
    :return: the id of the new row - keep it to change the row later
    """
    _require_labels()
    values = _fit_row(_as_list(dat))
    _db.last_id += 1
    row = [_db.last_id] + values
    _db.rows.append(row)
    _db.by_id[row[0]] = row
    return row[0]


@_locked
def clear_r(row_id):
    """
    Deletes the specified row or rows. The other rows keep their ids.
    :param row_id: a row's id, or a list/tuple/set of ids
    :return: None
    """
    # Check every id before deleting anything, so one bad id doesn't leave
    # the job half done.
    ids = {_row(i)[0] for i in _as_several(row_id)}
    _db.rows[:] = [row for row in _db.rows if row[0] not in ids]
    for i in ids:
        del _db.by_id[i]


@_locked
def clear_c(inx):
    """
    Deletes the specified column or columns, from the labels and every row.
    :param inx: a column (name or position), or a list/tuple of them
    :return: None
    """
    positions = {_col(c) for c in _as_several(inx)}
    for position in sorted(positions, reverse=True):
        del _db.labels[position]
        for row in _db.rows:
            del row[position]


@_locked
def clearall():
    """
    Empties the database in memory (labels, rows and the id counter).
    :note: Does not touch the saved file - call store() afterwards if you
           want the file emptied too.
    :return: None
    """
    _db.clear()


# -----------------------------------------------------------------------------
# Reading the database
# -----------------------------------------------------------------------------
@_locked
def view():
    """
    Returns the database as a table you can print:   print(ldb.view())
    Uses the "tabulate" package for a nicer table when it is installed
    (pip install tabulate), otherwise a simple built-in layout.
    Missing values (None) show as blank cells.
    :note: Builds the whole table as text, so it's slow for huge databases.
    :return: the table as a str
    """
    if not _db.labels:
        return "(empty database: no columns yet)"
    return _format_table(_db.labels, _db.rows)


@_locked
def return_r(row_id):
    """
    Returns a copy of the requested row or rows (the id is the first item).
    Changing the copy doesn't change the database - use update_r() for that.
    :param row_id: a row's id, or a list/tuple/set of ids
    :return: one row (a list) for one id, otherwise a list of rows
    """
    if isinstance(row_id, _SEVERAL):
        return [list(_row(i)) for i in row_id]
    return list(_row(row_id))


@_locked
def return_c(inx):
    """
    Returns the requested column or columns, top to bottom. Each column is a
    list that starts with its label, e.g.  return_c("score") -> ["score", 90, 85]
    The id column can be read too:  return_c("id")
    :param inx: a column (name or position), or a list/tuple of them
    :return: one column for one column, otherwise a list of columns
    """
    def column(c):
        position = _col(c, allow_id=True)
        return [_db.labels[position]] + [row[position] for row in _db.rows]

    if isinstance(inx, _SEVERAL):
        return [column(c) for c in inx]
    return column(inx)


@_locked
def find(value):
    """
    Finds the first cell equal to ``value``. ids are not searched.
    :param value: the value to look for
    :return: [row id, column position], ready for the other functions, e.g.
             ldb.update_ri(*ldb.find(85), 86)  -  or None if not found
    """
    for row in _db.rows:
        for c, cell in enumerate(row[1:]):
            if cell == value:
                return [row[0], c]
    return None


@_locked
def where(column, op, value=_NOTHING):
    """
    Returns every row where ``column`` matches, in the table's order:

        ldb.where("score", ">", 80)           # == != > >= < <=
        ldb.where("name", "contains", "li")   # text (or list) contains it
        ldb.where("score", "in", (85, 90))    # value is one of these
        ldb.where("score", "==", None)        # rows with a missing score
        ldb.where("score", lambda s: s is not None and s % 2 == 0)   # your own test

    A comparison that makes no sense for a cell (like None > 80) just
    doesn't match - it doesn't crash.
    :param column: the column (name or position); "id" works too
    :param op: one of the operators above, or a function that gets the
               cell's value and returns True for rows to keep
    :param value: what to compare with (not used with a function)
    :return: a list of rows (copies), each starting with its id
    """
    position = _col(column, allow_id=True)
    if callable(op):
        if value is not _NOTHING:
            raise LdbError("Give where() either an operator and a value, or a function - not both")
        return [list(row) for row in _db.rows if op(row[position])]

    if op not in _OPERATORS:
        raise LdbError(f"Unknown operator {op!r}. Use one of: {', '.join(_OPERATORS)}")
    if value is _NOTHING:
        raise LdbError(f"where() needs a value to compare with, e.g. where({column!r}, {op!r}, 10)")
    compare = _OPERATORS[op]

    def matches(cell):
        try:
            return bool(compare(cell, value))
        except TypeError:          # e.g. None > 80, or 5 contains "a"
            return False

    return [list(row) for row in _db.rows if matches(row[position])]


# -----------------------------------------------------------------------------
# Changing values
# -----------------------------------------------------------------------------
@_locked
def genid():
    """
    Renumbers every row's id in the current order: 10001, 10002, ...
    :note: This CHANGES the ids, so any id your program kept (for example
           from add_r()) points at a different row afterwards. ids are never
           renumbered automatically - only call this when you want that.
    :return: None
    """
    _db.last_id = FIRST_ID - 1
    for row in _db.rows:
        _db.last_id += 1
        row[0] = _db.last_id
    _db.by_id = {row[0]: row for row in _db.rows}


@_locked
def update_r(row_id, val):
    """
    Replaces all the values of one row. The row keeps its id.
    :param row_id: the row's id
    :param val: the new values as a list or tuple (missing ones become None)
    :return: None
    """
    row = _row(row_id)
    row[1:] = _fit_row(_as_list(val))


@_locked
def update_c(inx, val):
    """
    Replaces the values of one column.
    :param inx: the column (name or position)
    :param val: one of:
                - a single value: put in every row
                - a list/tuple: one value per row, top to bottom
                - a dict {id: value}: only those rows change
    :return: None
    """
    position = _col(inx)
    if isinstance(val, dict):
        changes = {_row(row_id)[0]: value for row_id, value in val.items()}
    elif isinstance(val, _MANY):
        if len(val) != len(_db.rows):
            raise LdbError(f"Got {len(val)} value(s) for {len(_db.rows)} row(s)")
        changes = {row[0]: value for row, value in zip(_db.rows, val)}
    else:
        # A separate copy per row, so changing one cell's set/dict later
        # doesn't change the others too.
        changes = {row[0]: copy.deepcopy(val) for row in _db.rows}
    for value in changes.values():
        _check_savable(value)
    for row_id, value in changes.items():
        _db.by_id[row_id][position] = value


@_locked
def update_ri(row_id, inx_o, val):
    """
    Updates a single value.
    :param row_id: the row's id
    :param inx_o: the column (name or position)
    :param val: the new value
    :return: None
    """
    row = _row(row_id)
    column = _col(inx_o)
    _check_savable(val)
    row[column] = val


@_locked
def sort_col(index, reverse=False):
    """
    Sorts the rows by one column. Rows keep their ids.
    Numbers come first (smallest to biggest), then other values in
    alphabetical order. Missing values (None) always go last.
    :param index: the column (name or position); "id" works too
    :param reverse: True to sort from biggest to smallest
    :return: None
    """
    position = _col(index, allow_id=True)
    filled = [row for row in _db.rows if row[position] is not None]
    missing = [row for row in _db.rows if row[position] is None]
    filled.sort(key=lambda row: _sort_key(row[position]), reverse=reverse)
    _db.rows[:] = filled + missing


# -----------------------------------------------------------------------------
# Saving and loading
# -----------------------------------------------------------------------------
@_locked
def exportjson(filename="ldb.json"):
    """
    Exports the database in memory to a JSON file that other programs can read:
        {"10001": {"name": "alice", "score": 90}, ...}
    Missing values become null, tuples and sets become lists, and complex
    numbers become text, because plain JSON has no such types.
    (store() keeps the exact types.)
    :param filename: where to write it; a relative name is put next to your script
    :return: the full path of the file
    """
    target = _resolve(filename)
    result = {}
    for row in _db.rows:
        result[str(row[0])] = {label: _plain(value) for label, value in zip(_db.labels[1:], row[1:])}
    _write_atomically(target, json.dumps(result, ensure_ascii=False, indent=2) + "\n")
    return target


@_locked
def store():
    """
    Saves the database to its file (.ldbs/<name>/<name>.lbel).
    Everything stays in memory, so you can keep working after saving.

    What a save guarantees:
    1. All or nothing - the file always holds either the complete previous
       save or the complete new one, never a mix, even if the program
       crashes or the power goes out in the middle of saving.
    2. Always readable - the new contents are read back and checked BEFORE
       they replace the old file, so a save can't leave a file that
       retrieve() can't load.
    3. One step back - the previous save is kept as <name>.lbel.bak.
       If the file is ever missing or damaged, retrieve() loads the backup
       instead and warns you (LdbWarning).

    Not guaranteed: if two programs save the same database, the last save
    wins and the other program's changes are lost.
    :return: None
    """
    # The file is a normal JSON object, written by hand with one row per
    # line so it stays easy to read in a text editor:
    #   {"format": "LbelDB", "version": 2, "last_id": 10002, "labels": [...], "rows": [
    #     [10001, "alice", 90],
    #     [10002, "bob", null]
    #   ]}
    header = json.dumps({"format": "LbelDB", "version": FORMAT_VERSION,
                         "last_id": _db.last_id, "labels": _db.labels}, ensure_ascii=False)
    rows = ",\n".join("  " + json.dumps(_encode(row), ensure_ascii=False) for row in _db.rows)
    # header[:-1] drops the header's closing "}" so "rows" becomes its last key.
    text = header[:-1] + ', "rows": [\n' + rows + "\n]}\n"

    _parse(json.loads(text))     # guarantee 2: check it reads back before writing it
    _write_atomically(_db.file(), text, backup_path=_db.file() + BACKUP_EXT)


@_locked
def retrieve():
    """
    Loads the saved database from its file, replacing what is in memory.
    If the file is missing or damaged, the backup from the previous save is
    loaded instead and an LdbWarning tells you so. A damaged file is kept
    as <name>.lbel.damaged so you can look at it.
    :return: True if a saved database was loaded,
             False if nothing has been saved yet (memory is left as it is)
    """
    main = _db.file()
    backup = main + BACKUP_EXT
    if not os.path.exists(main) and not os.path.exists(backup):
        return False

    problem = None
    if os.path.exists(main):
        try:
            _use(*_load(main))
            return True
        except LdbError as error:
            problem = error
        if not os.path.exists(backup):
            raise problem

    # The main file is damaged, or missing because a save was interrupted:
    # fall back to the backup of the previous save.
    try:
        loaded = _load(backup)
    except LdbError as error:
        raise LdbError(f"{main} is {'damaged' if problem else 'missing'} and its backup "
                       f"can't be read either: {error}") from error
    if problem:
        damaged = main + DAMAGED_EXT
        _replace(main, damaged)    # keep it for inspection, out of store()'s way
        message = (f"{main} was damaged ({problem}). Loaded the backup of the previous "
                   f"save instead; the damaged file was kept as {damaged}")
    else:
        message = (f"{main} was missing (was a save interrupted?). "
                   "Loaded the backup of the previous save instead")
    _use(*loaded)
    warnings.warn(message, LdbWarning, stacklevel=3)
    return True


# -----------------------------------------------------------------------------
# Several databases
# -----------------------------------------------------------------------------
@_locked
def new(name):
    """
    Creates a new, empty database (it does not switch to it - use switch()).
    :param name: letters, digits, "_" and "-" only
    :return: None
    """
    _check_name(name)
    folder = _db.folder(name)
    if os.path.exists(folder):
        raise LdbError(f"The database {name!r} already exists")
    os.makedirs(folder)


@_locked
def delete(name):
    """
    Permanently deletes the saved database ``name`` (its whole folder,
    including the backup). The database in use can't be deleted -
    switch() to another one first.
    :param name: the database's name
    :return: None
    """
    _check_name(name)
    if name == _db.name:
        raise LdbError(f"{name!r} is the database in use; switch() to another one before deleting it")
    folder = _db.folder(name)
    if not os.path.isdir(folder):
        raise LdbError(f"The database {name!r} does not exist")
    shutil.rmtree(folder)


@_locked
def switch(name):
    """
    Saves the current database, then loads the database ``name``.
    The current database is only saved if it has columns, so switching right
    after your program starts (before retrieve()) can't overwrite its saved
    file with an empty table.
    :param name: a database made with new(), or "default"
    :return: None
    """
    _check_name(name)
    if name == _db.name:
        return
    if not os.path.isdir(_db.folder(name)):
        raise LdbError(f"The database {name!r} does not exist - create it with new({name!r})")
    if _db.labels:
        store()
    _db.name = name
    _db.clear()
    retrieve()


# -----------------------------------------------------------------------------
# Read-only views for code that looks at the state directly
# -----------------------------------------------------------------------------
def __getattr__(name):
    """
    Lets older code keep reading ``ldb.lbels``, ``ldb.data``, ``ldb.cols``,
    ``ldb.idv``, ``ldb.path`` and ``ldb.current_db``.
    They are COPIES, so changing them can't damage the database (which used
    to be easy). Use the functions above to make changes.
    """
    with _lock:
        if name == "lbels":
            return list(_db.labels)
        if name == "data":
            return [list(row) for row in _db.rows]
        if name == "cols":
            return len(_db.labels)
        if name == "idv":
            return _db.last_id
        if name == "path":
            return _db.folder()
        if name == "current_db":
            return _db.name
    raise AttributeError(f"module 'ldb' has no attribute {name!r}")
