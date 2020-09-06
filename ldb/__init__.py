tab = True
try:
    from tabulate import tabulate
except ModuleNotFoundError:
    tab = False

idv = 10000
temp = []
lbels = []
data = []
cols = 0
is_inio = False


def init():
    """
    Creates the required files
    Should be run for initialization
    Can be run anytime
    :return: None
    """
    open("dbs.lbel", "a").close()
    open("dat.lbel", "a").close()


def create(labels: str or list or tuple):
    """
    Creates the Headers or labels:
    To be run at the first run with init()
    :param labels: A str, list or tuple of the the headers or labels
    """
    global lbels
    global cols
    global idv

    if not (type(labels) in [str, list, tuple]):
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
    :param arg: A str, list or tuple of the labels
    """
    global lbels
    global data
    global cols
    if type(arg) in [int, bool, str]:
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
    note: An empty string => "" represents missing
    """
    global data
    global cols
    global idv
    if type(dat) in [int, str, bool]:
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
    :param inx: index of the row or rows to be deleted
    """
    global data
    if type(inx) == int:
        try:
            data.pop(inx)
        except IndexError:
            raise Exception("No rows present or specified index is out of range")
    else:
        inx = set(inx)
        inx = list(inx)
        inx.sort()
        inx.reverse()
        for x in inx:
            data.pop(x)
    genid()


def clear_c(inx: int or tuple or list):
    """
    Deletes the specified columns or columns
    :param inx: index of the column or columns to be deleted
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
        :note: does not delete the files
        """
    global data
    global lbels
    global cols
    data = []
    lbels = []
    cols = 0


def store():
    """
    Stores the data in the db
    :Note: This clears everything from local memory and cant be retrieved without retrieve()
    """
    global is_inio
    global data
    global lbels
    global cols
    while True:
        if not is_inio:
            break
    is_inio = True
    with open("dat.lbel", "a") as d:
        for i in data:
            for x in i:
                d.write(str(x) + "\n")
        data = []

    with open("dbs.lbel", "w") as f:
        for i in lbels:
            f.write(str(i) + "\n")
        lbels = []
        cols = None
    is_inio = False


def retrieve():
    """
    Retrieves the database from the stored state
    """
    global is_inio
    global lbels
    global data
    global cols
    while True:
        if not is_inio:
            break
    is_inio = True
    with open("dbs.lbel", "r+") as l:
        lbels = [line.rstrip() for line in l]
    cols = len(lbels)
    file = open("dat.lbel", "r+")
    counter = 0
    content = file.read()
    colist = content.split("\n")
    for i in colist:
        if i:
            counter += 1
    file.close()
    with open("dat.lbel", "r+") as f:
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


def view():
    """
    View the data base
    Better results if using Tabulate module but not necessary
    Note: Not to be used with intensive databases as it can be resource intensive
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
        print(tabulate(temp, headers=lbels, tablefmt="fancy_grid"))
    else:
        print("Module tabulate is a dependency. ModuleNotFound")
        print(lbels)
        for x in data:
            print(x)


def return_r(inx: int or tuple or list):
    """
    Returns a requested row from the db
    :param inx: The row number
    :return: The requested row
    """
    if inx:
        return data[inx]
    else:
        temp = []
        for i in inx:
            temp += i
        return temp


def return_rs(inx: list or tuple):
    """
    Returns the requested rows from the db
    :param inx: list or tuple: The row numbers
    :return: The requested rows
    """
    global data
    inx = list(inx)
    tempc = []
    for x in inx:
        tempc.append(list(data[x]))
    return tempc


def return_c(inx: int):
    """
    Returns a requested column from the db
    :param inx: The column number
    :return: The requested column
    """
    global data
    tempv = [lbels[inx]]
    for i in range(len(data)):
        tempv.append(data[i][inx])
    return tempv


def genid():
    """
    Use only if ids generated a corrupt
    """
    global data
    global idv
    idv = 10000
    for i in range(len(data)):
        idv += 1
        data[i].pop(0)
        data[i].insert(0, idv)


def update_r(inx: int, val: list or tuple):
    """
    Updates the whole selected row
    :param inx: index of the row
    :param val: a list or tuple of the updated row
    """
    global data
    global cols
    global lbels
    lbels.pop(0)
    val = list(val)
    try:
        if len(val) > cols:
            print("no of columns in provided list too high")
            raise AttributeError
        data[inx] = val
        data[inx].insert(0, "")
    except IndexError:
        raise Exception("Row number invalid")
    lbels.insert(0, "id")
    genid()


def update_ri(inx_r: int, inx_o: int, val):
    """
    Updates a single item in a row
    :param inx_r: index of the row
    :param inx_o: index of the object
    :param val: the value of replaced object
    """
    global data
    data[inx_r][inx_o + 1] = val


def sort_col(index: int, reverse: bool = False):
    """
    Sorts the chosen column in descending order
    :param index: the index of the column
    :param reverse: reverse = True or False
    """
    global lbels
    global data
    global cols
    data.sort(key=lambda x: x[index])
    if reverse:
        data.reverse()
    genid()
