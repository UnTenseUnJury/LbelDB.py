# =============================================================================
#  Tests for LbelDB.   Run them with:   python -m pytest
#  Author: UnTenseUnJury
# =============================================================================
import io
import json
import os
import sys
import sysconfig
import types

import pytest

import ldb
import ldb.console as console

REAL_SCRIPT_FOLDER = ldb._script_folder


@pytest.fixture(autouse=True)
def fresh_db(tmp_path, monkeypatch):
    """
    Give every test an empty database. Its "script folder" is a temporary
    folder, so nothing is ever written next to pytest or into your project.
    """
    monkeypatch.setattr(ldb, "_db", ldb._State())     # all of ldb's memory, reset
    monkeypatch.setattr(ldb, "_script_folder", lambda: str(tmp_path))
    monkeypatch.chdir(tmp_path)
    ldb.init()


def make_scores():
    ldb.create(("name", "score"))
    ldb.add_r(("alice", 90))
    ldb.add_r(("bob", 85))


def saved_file(tmp_path, name="default"):
    return os.path.join(str(tmp_path), ".ldbs", name, name + ".lbel")


def reload_from_disk():
    ldb.clearall()
    assert ldb.retrieve() is True


# --- rows are picked by id (#1) ----------------------------------------------

def test_add_r_returns_the_id_and_rows_are_found_by_it():
    ldb.create(("name", "score"))
    alice = ldb.add_r(("alice", 90))
    bob = ldb.add_r(("bob", 85))
    assert (alice, bob) == (10001, 10002)
    assert ldb.return_r(bob) == [10002, "bob", 85]
    assert ldb.return_r([bob, alice]) == [[10002, "bob", 85], [10001, "alice", 90]]


def test_ids_keep_pointing_at_the_same_row_after_sorting_and_deleting():
    make_scores()
    carol = ldb.add_r(("carol", 70))
    ldb.sort_col("score")
    ldb.clear_r(10001)
    ldb.update_ri(carol, "score", 75)          # still carol, wherever she moved
    assert ldb.return_r(carol) == [10003, "carol", 75]
    assert ldb.data == [[10003, "carol", 75], [10002, "bob", 85]]


def test_update_r_and_update_ri_by_id():
    make_scores()
    ldb.update_r(10002, ("bobby",))
    ldb.update_ri(10001, "score", 95)
    ldb.update_ri(10001, 0, "Alice")           # columns still work by position too
    assert ldb.data == [[10001, "Alice", 95], [10002, "bobby", None]]


def test_unknown_ids_raise_and_change_nothing():
    make_scores()
    for bad in [99999, 0, "10001", True, 1.5]:
        with pytest.raises(ldb.LdbError):
            ldb.return_r(bad)
    with pytest.raises(ldb.LdbError):
        ldb.clear_r([10001, 99999])            # one bad id -> nothing deleted
    assert len(ldb.data) == 2


def test_clear_r_several_rows_and_ids_are_not_reused():
    ldb.create("letter")
    ids = [ldb.add_r(letter) for letter in "abcd"]
    ldb.clear_r({ids[0], ids[2]})
    assert ldb.data == [[10002, "b"], [10004, "d"]]
    assert ldb.add_r("e") == 10005


def test_ids_continue_after_saving_and_loading(tmp_path):
    make_scores()
    ldb.clear_r(10002)
    ldb.store()
    reload_from_disk()
    assert ldb.add_r(("carol", 70)) == 10003   # 10002 is never reused


def test_genid_renumbers():
    make_scores()
    ldb.sort_col("score")
    ldb.genid()
    assert ldb.data == [[10001, "bob", 85], [10002, "alice", 90]]
    assert ldb.return_r(10001) == [10001, "bob", 85]


def test_update_c_with_one_value_a_list_or_a_dict_of_ids():
    make_scores()
    ldb.update_c("score", 0)
    assert ldb.return_c("score") == ["score", 0, 0]
    ldb.update_c("score", [1, 2])               # one per row, top to bottom
    assert ldb.return_c("score") == ["score", 1, 2]
    ldb.update_c("score", {10002: 50})          # only bob changes
    assert ldb.return_c("score") == ["score", 1, 50]
    with pytest.raises(ldb.LdbError):
        ldb.update_c("score", {99999: 1})
    with pytest.raises(ldb.LdbError):
        ldb.update_c("score", [1, 2, 3])


def test_find_returns_an_id_and_a_column():
    make_scores()
    assert ldb.find(85) == [10002, 1]
    ldb.update_ri(*ldb.find(85), 86)
    assert ldb.return_r(10002) == [10002, "bob", 86]
    assert ldb.find("nobody") is None
    assert ldb.find(10001) is None              # ids are not searched


def test_the_id_column_can_be_read_but_not_changed():
    make_scores()
    assert ldb.return_c("id") == ["id", 10001, 10002]
    with pytest.raises(ldb.LdbError):
        ldb.update_c("id", 5)
    with pytest.raises(ldb.LdbError):
        ldb.clear_c("id")


# --- where() (#2) ------------------------------------------------------------

def test_where_with_operators():
    make_scores()
    ldb.add_r(("carol", None))
    assert ldb.where("score", ">", 86) == [[10001, "alice", 90]]
    assert ldb.where("score", "<=", 90) == [[10001, "alice", 90], [10002, "bob", 85]]
    assert ldb.where("name", "==", "bob") == [[10002, "bob", 85]]
    assert ldb.where("name", "!=", "bob") == [[10001, "alice", 90], [10003, "carol", None]]
    assert ldb.where("name", "contains", "li") == [[10001, "alice", 90]]
    assert ldb.where("score", "in", (85, None)) == [[10002, "bob", 85], [10003, "carol", None]]
    assert ldb.where("score", "==", None) == [[10003, "carol", None]]
    assert ldb.where("id", ">=", 10002) == [[10002, "bob", 85], [10003, "carol", None]]
    assert ldb.where("score", ">", 1000) == []


def test_where_with_a_function():
    make_scores()
    assert ldb.where("name", lambda name: name.startswith("b")) == [[10002, "bob", 85]]


def test_where_does_not_crash_on_mixed_values():
    ldb.create("v")
    for value in [5, "text", None, [1, 2]]:
        ldb.add_r([value])
    assert ldb.where("v", ">", 1) == [[10001, 5]]          # "text" > 1 just doesn't match
    assert ldb.where("v", "contains", 2) == [[10004, [1, 2]]]


def test_where_rejects_bad_input():
    make_scores()
    with pytest.raises(ldb.LdbError):
        ldb.where("score", "=>", 1)             # unknown operator
    with pytest.raises(ldb.LdbError):
        ldb.where("score", ">")                 # no value
    with pytest.raises(ldb.LdbError):
        ldb.where("score", lambda s: True, 5)   # function and value
    with pytest.raises(ldb.LdbError):
        ldb.where("nope", "==", 1)              # unknown column


def test_where_returns_copies():
    make_scores()
    ldb.where("name", "==", "bob")[0][1] = "changed"
    assert ldb.return_r(10002) == [10002, "bob", 85]


# --- saved next to the script (#7) -------------------------------------------

def test_databases_are_saved_next_to_the_script_not_the_current_folder(tmp_path, monkeypatch):
    elsewhere = tmp_path / "somewhere_else"
    elsewhere.mkdir()
    monkeypatch.chdir(elsewhere)                # program started from another folder
    make_scores()
    ldb.store()
    assert os.path.exists(saved_file(tmp_path))
    assert not os.path.exists(elsewhere / ".ldbs")


def test_init_with_a_folder(tmp_path):
    ldb.init("data")                            # relative -> next to the script
    make_scores()
    ldb.store()
    assert os.path.exists(tmp_path / "data" / "default" / "default.lbel")


def test_exportjson_goes_next_to_the_script(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path / ".ldbs")
    make_scores()
    ldb.add_r(("carol", None))
    path = ldb.exportjson()
    assert path == str(tmp_path / "ldb.json")
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["10003"] == {"name": "carol", "score": None}


def test_script_folder_is_the_folder_of_the_main_file(tmp_path, monkeypatch):
    (tmp_path / "game").mkdir()
    fake_main = types.ModuleType("__main__")
    fake_main.__file__ = str(tmp_path / "game" / "my_game.py")
    monkeypatch.setitem(sys.modules, "__main__", fake_main)
    assert REAL_SCRIPT_FOLDER() == str(tmp_path / "game")


def test_script_folder_falls_back_to_the_current_folder(tmp_path, monkeypatch):
    monkeypatch.setitem(sys.modules, "__main__", types.ModuleType("__main__"))   # like Jupyter
    assert REAL_SCRIPT_FOLDER() == os.getcwd()


def fake_main_file(monkeypatch, path):
    fake_main = types.ModuleType("__main__")
    fake_main.__file__ = str(path)
    monkeypatch.setitem(sys.modules, "__main__", fake_main)


def test_a_packaged_app_keeps_its_data_next_to_the_exe(tmp_path, monkeypatch):
    # PyInstaller runs the script from a temp folder that is deleted on exit
    fake_main_file(monkeypatch, tmp_path / "_MEI12345" / "game.py")
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "executable", str(tmp_path / "dist" / "game.exe"))
    assert REAL_SCRIPT_FOLDER() == str(tmp_path / "dist")


def test_installed_tools_like_pytest_are_not_treated_as_your_script(monkeypatch):
    fake_main_file(monkeypatch, os.path.join(os.path.dirname(pytest.__file__), "__main__.py"))
    assert REAL_SCRIPT_FOLDER() == os.getcwd()


def test_a_pip_made_command_is_not_treated_as_your_script(tmp_path, monkeypatch):
    launcher = tmp_path / "mygame.exe"          # on Windows __main__ lives inside the .exe
    launcher.write_bytes(b"")
    fake_main_file(monkeypatch, launcher / "__main__.py")
    assert REAL_SCRIPT_FOLDER() == os.getcwd()
    fake_main_file(monkeypatch, os.path.join(sysconfig.get_paths()["scripts"], "mygame"))
    assert REAL_SCRIPT_FOLDER() == os.getcwd()  # Linux/macOS: a script in the bin folder


# --- None means missing (#8) -------------------------------------------------

def test_missing_values_are_none_and_empty_text_is_kept():
    ldb.create(("a", "b", "c"))
    ldb.add_r(["x"])
    ldb.add_r(["", "y"])
    ldb.add_c("d")
    assert ldb.data == [[10001, "x", None, None, None], [10002, "", "y", None, None]]
    ldb.store()
    reload_from_disk()
    assert ldb.return_r(10002) == [10002, "", "y", None, None]   # "" stays "", None stays None


def test_sort_puts_missing_values_last_and_handles_mixed_types():
    ldb.create("v")
    for value in [3, "b", None, 1.5, "a", "", 10]:
        ldb.add_r([value])
    ldb.sort_col("v")
    assert [row[1] for row in ldb.data] == [1.5, 3, 10, "", "a", "b", None]
    ldb.sort_col("v", reverse=True)
    assert [row[1] for row in ldb.data] == ["b", "a", "", 10, 3, 1.5, None]


def test_view_shows_missing_values_as_blank(monkeypatch):
    make_scores()
    ldb.add_r(("carol",))
    monkeypatch.setattr(ldb, "tabulate", None)
    assert "None" not in ldb.view()


def test_view_with_tabulate():
    pytest.importorskip("tabulate")             # skipped when tabulate isn't installed
    make_scores()
    ldb.add_r(("carol",))
    table = ldb.view()
    assert "╒" in table and "alice" in table    # tabulate's fancy_grid style
    assert "None" not in table                  # missing values are blank here too


# --- saving and its guarantees (#9) ------------------------------------------

def test_store_then_retrieve_gives_back_the_same_table():
    make_scores()
    ldb.store()
    reload_from_disk()
    assert ldb.lbels == ["id", "name", "score"]
    assert ldb.data == [[10001, "alice", 90], [10002, "bob", 85]]


def test_value_types_survive_a_round_trip():
    values = [42, 3.5, True, None, "", "two\nlines", [1, [2]], (1, 2), {1, 2},
              frozenset({3}), 2 + 3j, {"a": 1, 2: (3,)}]
    ldb.create([f"c{i}" for i in range(len(values))])
    ldb.add_r(values)
    ldb.store()
    reload_from_disk()
    row = ldb.return_r(10001)[1:]
    assert row == values
    assert [type(v) for v in row] == [type(v) for v in values]


def test_store_keeps_the_data_in_memory_and_overwrites_the_file():
    make_scores()
    ldb.store()
    ldb.add_r(("carol", 70))
    ldb.store()
    reload_from_disk()
    assert len(ldb.data) == 3


def test_retrieve_with_nothing_saved_returns_false():
    assert ldb.retrieve() is False
    assert ldb.data == []


def test_the_previous_save_is_kept_as_a_backup(tmp_path):
    make_scores()
    ldb.store()
    ldb.add_r(("carol", 70))
    ldb.store()
    with open(saved_file(tmp_path) + ".bak", encoding="utf-8") as f:
        assert len(json.load(f)["rows"]) == 2   # the save before the last one


def test_failed_save_keeps_the_previous_save(tmp_path, monkeypatch):
    make_scores()
    ldb.store()
    with open(saved_file(tmp_path), encoding="utf-8") as f:
        before = f.read()
    ldb.add_r(("carol", 70))

    def broken_fsync(fd):
        raise OSError("disk unplugged")

    real_fsync = os.fsync
    monkeypatch.setattr(os, "fsync", broken_fsync)
    with pytest.raises(OSError):
        ldb.store()
    monkeypatch.setattr(os, "fsync", real_fsync)

    with open(saved_file(tmp_path), encoding="utf-8") as f:
        assert f.read() == before
    assert sorted(os.listdir(os.path.dirname(saved_file(tmp_path)))) == ["default.lbel"]


def test_a_damaged_file_is_replaced_by_the_backup_with_a_warning(tmp_path):
    make_scores()
    ldb.store()
    ldb.add_r(("carol", 70))
    ldb.store()
    with open(saved_file(tmp_path), "w", encoding="utf-8") as f:
        f.write('{"format": "LbelDB", "rows": [[10001, "ali')   # damaged
    ldb.clearall()
    with pytest.warns(ldb.LdbWarning, match="damaged"):
        assert ldb.retrieve() is True
    assert len(ldb.data) == 2                   # the previous save
    assert os.path.exists(saved_file(tmp_path) + ".damaged")
    ldb.store()                                 # saving again works normally
    reload_from_disk()
    assert len(ldb.data) == 2


def test_an_interrupted_save_is_recovered_from_the_backup(tmp_path):
    make_scores()
    ldb.store()
    ldb.store()
    os.remove(saved_file(tmp_path))             # as if the program stopped mid-save
    ldb.clearall()
    with pytest.warns(ldb.LdbWarning, match="missing"):
        assert ldb.retrieve() is True
    assert len(ldb.data) == 2


def test_damaged_file_and_no_backup_raises_and_leaves_memory_alone(tmp_path):
    make_scores()
    ldb.store()
    with open(saved_file(tmp_path), "w", encoding="utf-8") as f:
        f.write("{not json")
    with pytest.raises(ldb.LdbError):
        ldb.retrieve()
    assert len(ldb.data) == 2


def test_saved_file_is_readable_json_with_one_row_per_line(tmp_path):
    make_scores()
    ldb.store()
    with open(saved_file(tmp_path), encoding="utf-8") as f:
        text = f.read()
    assert '  [10001, "alice", 90],\n' in text
    saved = json.loads(text)
    assert saved["labels"] == ["id", "name", "score"]


def test_exportjson_then_store_does_not_hang():
    make_scores()
    ldb.exportjson()
    ldb.store()


# --- the tidied-up state -----------------------------------------------------

def test_reading_the_state_gives_copies_that_cannot_break_it():
    make_scores()
    ldb.data[0][1] = "changed"
    ldb.lbels.append("oops")
    assert ldb.data[0] == [10001, "alice", 90]
    assert ldb.lbels == ["id", "name", "score"]
    assert (ldb.cols, ldb.idv, ldb.current_db) == (3, 10002, "default")


def test_unknown_module_attributes_still_raise():
    with pytest.raises(AttributeError):
        ldb.no_such_thing


# --- columns -----------------------------------------------------------------

def test_create_rejects_bad_labels():
    for bad in [("a", "a"), ("id",), ("",), ()]:
        with pytest.raises(ldb.LdbError):
            ldb.create(bad)


def test_create_can_rename_but_not_resize_when_rows_exist():
    make_scores()
    ldb.create(("player", "points"))
    assert ldb.lbels == ["id", "player", "points"]
    with pytest.raises(ldb.LdbError):
        ldb.create(("only_one",))


def test_add_c_and_clear_c():
    make_scores()
    ldb.add_c(["age", "city"])
    assert ldb.return_r(10001) == [10001, "alice", 90, None, None]
    ldb.clear_c(["name", -1])
    assert ldb.lbels == ["id", "score", "age"]
    assert ldb.return_r(10001) == [10001, 90, None]


def test_add_r_checks_its_values():
    with pytest.raises(ldb.LdbError):
        ldb.add_r(("x",))                       # no columns yet
    make_scores()
    with pytest.raises(ldb.LdbError):
        ldb.add_r(("carol", 70, "extra"))
    with pytest.raises(ldb.LdbError):
        ldb.add_r(("carol", object()))          # can't be saved
    values = ["dave"]
    ldb.add_r(values)
    assert values == ["dave"]                   # the caller's list isn't changed


# --- several databases -------------------------------------------------------

def test_new_switch_and_delete(tmp_path):
    make_scores()
    ldb.new("other")
    ldb.switch("other")                         # saves "default" first
    assert ldb.current_db == "other"
    assert ldb.data == []
    ldb.create("x")
    ldb.add_r(1)
    ldb.store()
    ldb.switch("default")
    assert ldb.return_c("name") == ["name", "alice", "bob"]
    with pytest.raises(ldb.LdbError):
        ldb.delete("default")                   # it's the one in use
    ldb.delete("other")
    assert not os.path.exists(tmp_path / ".ldbs" / "other")


def test_switching_with_nothing_loaded_does_not_wipe_the_saved_file():
    make_scores()
    ldb.store()
    ldb.clearall()
    ldb.new("other")
    ldb.switch("other")
    ldb.switch("default")
    assert len(ldb.data) == 2


def test_bad_database_names():
    for bad in ["../evil", "a/b", "a\\b", "", "a b", "..", 5]:
        with pytest.raises(ldb.LdbError):
            ldb.new(bad)
    with pytest.raises(ldb.LdbError):
        ldb.switch("nope")


# --- console -----------------------------------------------------------------

def test_console_commands():
    outputs = [console.run_command(line) for line in [
        "create name score",
        'add_r "Ada Lovelace" 36',
        "add_r Bob 41",
        "update_ri 10002 score 42",
        "sort_col score desc",
        "find 42",
        "where score > 40",
        "clear_r 99999",
        "nonsense",
        "update_ri 10001",
    ]]
    assert ldb.data == [[10002, "Bob", 42], [10001, "Ada Lovelace", 36]]
    assert outputs[1] == "Added row 10001"
    assert outputs[5] == "Found in row 10002, column 1"
    assert "Bob" in outputs[6] and "Ada" not in outputs[6]
    assert outputs[7].startswith("Error:")
    assert outputs[8].startswith("Unknown command")
    assert outputs[9].startswith("Usage:")


def test_console_quotes_keep_numbers_as_text():
    console.run_command("create code")
    console.run_command('add_r "007"')
    assert ldb.data == [[10001, "007"]]


def test_console_shows_warnings(tmp_path):
    make_scores()
    ldb.store()
    ldb.store()
    os.remove(saved_file(tmp_path))
    assert console.run_command("retrieve").startswith("Warning:")


def test_console_main_uses_the_current_folder(tmp_path, monkeypatch):
    start = tmp_path / "start"
    start.mkdir()
    monkeypatch.chdir(start)
    lines = iter(["add_c a", "add_r 1", "view", "store", "exit"])
    monkeypatch.setattr("builtins.input", lambda prompt="": next(lines))
    console.main()
    assert os.path.exists(start / ".ldbs" / "default" / "default.lbel")


def test_console_output_survives_a_terminal_that_cant_show_the_table(monkeypatch):
    fake = io.TextIOWrapper(io.BytesIO(), encoding="cp1252")
    monkeypatch.setattr(sys, "stdout", fake)
    console._show("╒═══╕ table")     # used to crash with UnicodeEncodeError
    fake.flush()
    assert fake.buffer.getvalue().startswith(b"????? table")
