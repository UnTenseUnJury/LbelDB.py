import os
import json

tab = True
try:
    from tabulate import tabulate
except ModuleNotFoundError:
    tab = False

path = ".ldbs\\default"
c_file = "dbs.lbell"
cd_file = "dat.lbeld"

idv = 10000
temp = []
lbels = []
data = []
cols = 0
is_inio = False

default = [int, float, complex, str, list, tuple, set, bool]
sing = [int, float, complex, str, bool]


def init():
    try:
        os.mkdir(".ldbs")
        os.mkdir(path)
    except FileExistsError:
        pass
    open(os.path.join(path, c_file), "a").close()
    open(os.path.join(path, cd_file), "a").close()


def create(labels):
    """
    Creates the Headers or labels:
    To be run at the first run with init()
    """
    global lbels
    global cols
    global idv
    if not (type(labels) in default):
        raise Exception("Passed value is not a str or list or tuple")
    if type(labels) == str:
        labels = [labels]
    labels = list(labels)
    labels.insert(0, "id")
    lbels = list(labels)
    cols = len(lbels)


def add_c(arg: str or list or tuple):
    """
    Creates a column in the database
    """
    global lbels
    global data
    global cols
    if type(arg) in sing:
        lbels.append(arg)
        nol = 1
    else:
        for i in arg:
            lbels.append(i)
        nol = len(arg)
    for _ in range(nol):
        for i in range(len(data)):
            data[i].append("")
    cols = len(lbels)


def add_r(dat: tuple or list):
    """
    Adds a row to the database
    :note: An empty string => "" represents missing
    :return: None
    """
    global data
    global cols
    global idv
    if type(dat) in sing:
        dat = [dat]
        dat.insert(0, idv)
        data.append(dat)
    elif cols > len(dat):
        for i in range(cols - len(dat) - 1):
            dat.append("")
        idv += 1
        dat = list(dat)
        dat.insert(0, idv)
        data.append(dat)
    else:
        raise Exception("Number of columns exceed number of labels")
    genid()


def clear_r(inx):
    """
    Deletes the specified row or rows
    :param inx: Index of the row or rows to be deleted
    :return: None
    """
    global data
    if type(inx) == int:
        try:
            data.pop(int(inx))
        except IndexError:
            raise Exception("No rows present or specified index is out of range")
    else:
        inx = set(inx)
        inx = list(inx)
        inx.sort()
        inx.reverse()
        for x in inx:
            data.pop(int(x))
    genid()


def clear_c(inx: int or tuple or list):
    """
    Deletes the specified columns or columns
    :param inx: Index of the column or columns to be deleted
    :return: None
    """
    if inx >= 0:
        raise Exception("Index is invalid")
    else:
        global data
        global lbels
        global cols
        if type(inx) == int:
            lbels.pop(inx)
            for i in range(len(data)):
                data[i].pop(inx)
        else:
            for x in inx:
                lbels.pop(x)
        cols = len(lbels)


def clearall():
    """
    Deletes the database locally
    :note: Does not delete the files
    :return: None
    """
    global data
    global lbels
    global cols
    data = []
    lbels = []
    cols = 0


def view():
    """
    View the data base
    Better results if using Tabulate module but not necessary
    Note: Not to be used with intensive databases as it can be resource intensive
    :return: The string view of the db
    """
    global lbels
    global data
    global temp
    global cols
    if tab:
        temp = data
        for i in temp:
            if not len(i) == cols:
                for x in range(cols - len(i)):
                    temp[temp.index(i)].append("")
        return tabulate(temp, headers=lbels, tablefmt="fancy_grid")
    else:
        print("Module tabulate is a dependency. ModuleNotFound")
        return {[lbels] + [data]}


def return_r(inx: int or tuple or list):
    """
    Returns a requested row from the db
    :param inx: The row number
    :return: The requested row
    """
    if type(inx) == int:
        return data[inx]
    else:
        tempv = []
        for i in inx:
            tempv += [data[i]]
        return tempv


def return_c(inx: int or tuple or list):
    """
    Returns a requested column from the db
    :param inx: The column number
    :return: The requested column
    """
    global data
    tempo = []
    tempv = [lbels[inx]]
    if type(inx) == int:
        for i in range(len(data)):
            tempv.append(data[i][inx])
        return tempv
    else:
        for x in inx:
            for i in range(len(data)):
                tempv.append(data[i][x])
            tempo.append(tempv)
        return tempo


def genid():
    """
    Use only if ids generated a corrupt
    :return: None
    """
    global data
    global idv
    idv = 10000
    for i in range(len(data)):
        idv += 1
        data[i].pop(0)
        data[i].insert(0, idv)


def update_r(inx: int, val: list or tuple or set):
    """
    Updates the whole selected row
    :param inx: index of the row
    :param val: a list or tuple of the updated row
    :return: None
    """
    global data
    global cols
    global lbels
    lbels.pop(0)
    val = list(val)
    try:
        if len(val) > cols:
            raise Exception("no of columns in provided list too high")
        data[inx] = val
        data[inx].insert(0, "")
    except IndexError:
        raise Exception("Row number invalid")
    lbels.insert(0, "id")
    genid()


def update_c(inx: int, val):
    """
    Updates the whole selected row
    :param inx: index of the row
    :param val: a list or tuple of the updated row
    :return: None
    """
    global data
    global cols
    global lbels
    if type(val) in sing:
        data[0][inx] = val
    else:
        if len(data) == len(val):
            for x in range(len(data)):
                data[x][inx] = val[x]
        elif len(data) > len(val):
            raise Exception("Values too less")
        else:
            raise Exception("Too many values")
    genid()


def update_ri(inx_r: int, inx_o: int, val):
    """
    Updates a single item in a row
    :param inx_r: index of the row
    :param inx_o: index of the object
    :param val: the value of replaced object
    :return: None
    """
    global data
    data[inx_r][inx_o + 1] = val


def sort_col(index: int, reverse: bool = False):
    """
    Sorts the chosen column in descending order
    :param index: The index of the column
    :param reverse: Reverse = True or False
    :return: None
    """
    global lbels
    global data
    global cols
    data.sort(key=lambda x: x[index])
    if reverse:
        data.reverse()
    genid()


def find(value):
    """
    Find the index of a given value
    :param value: The value to be searched
    """
    global data
    for x in data:
        for y in x:
            if y == value:
                return [data.index(x), x.index(y)]


def exportjson():
    """
    Export the database as a JSON file
    :return: None
    """
    global is_inio
    while is_inio:
        pass
    is_inio = True

    res = {}
    for i in data:
        res[i[0]] = {}
        for j in range(cols):
            if j > 0:
                res[i[0]][lbels[j]] = i[j]

    with open("ldb.json", "w") as f:
        json.dump(res, f)


def retrieve():
    """
    Retrieves the database from the stored state
    :return: None
    """
    global is_inio
    global lbels
    global data
    global cols
    while True:
        if not is_inio:
            break
    is_inio = True
    with open(os.path.join(path, c_file), "r+") as l:
        lbels = [line.rstrip() for line in l]
    cols = len(lbels)
    file = open(os.path.join(path, cd_file), "r+")
    counter = 0
    content = file.read()
    colist = content.split("\n")
    for i in colist:
        if i:
            counter += 1
    file.close()
    with open(os.path.join(path, cd_file), "r+") as f:
        lines = list(f.read().splitlines())
        try:
            for a in range(int((counter / cols + 1))):
                global temp
                it = 1
                temp = []
                for i in lines:
                    temp.append(i)
                    if it == cols:
                        data.append(temp)
                        temp = []
                        for _ in range(cols):
                            lines.pop(0)
                        break
                    it += 1
        except ZeroDivisionError:
            raise Exception("Retrieved without adding data to DBs")
    is_inio = False


def store():
    """
    Stores the data in the db
    :Note: This clears everything from local memory and cant be retrieved without retrieve()
    :return: None
    """
    global is_inio
    global data
    global lbels
    global cols
    while is_inio:
        pass
    is_inio = True
    with open(os.path.join(path, c_file), "a") as d:
        for i in data:
            for x in i:
                d.write(str(x) + "\n")
        data = []

    with open(os.path.join(path, cd_file), "w") as f:
        for i in lbels:
            f.write(str(i) + "\n")
        lbels = []
        cols = None
    is_inio = False


def new(name: str):
    """
    Create new DB
    """
    try:
        os.mkdir(f".ldbs\\{name}")
        open(os.path.join(f".ldbs\\{name}", f"{name}.lbell"), "a").close()
        open(os.path.join(path, f"{name}.lbeld"), "a").close()
    except FileExistsError:
        raise Exception("Database already exists")


def delete(name: str):
    """
    Deletes the DB
    """
    if os.path.exists(f".ldbs\\{name}"):
        os.rmdir(f".ldbs\\{name}")
    else:
        print("The file does not exist")


def switch(name):
    """
    Switch to the required DB
    """
    global path
    global c_file
    global cd_file
    try:
        open(os.path.join(f".ldbs\\{name}", f"{name}.lbell"), "a").close()
        open(os.path.join(f".ldbs\\{name}", f"{name}.lbeld"), "a").close()
    except FileNotFoundError:
        raise Exception("DB doesn't exist")
    store()

    path = f".ldbs\\{name}"
    c_file = f"{name}.lbell"
    cd_file = f"{name}.lbeld"

    with open(os.path.join(path, c_file), "r") as d:
        nope = False
        if d.read() == "":
            nope = True

    if not nope:
        retrieve()
