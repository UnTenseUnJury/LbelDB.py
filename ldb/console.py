import ldb

# console based do not edit

while True:
    cmd = str(input("LDB > "))
    cmd = cmd.split(" ")
    if cmd[0].lower() == "exit":
        break
    elif cmd[0].lower() == "init":
        ldb.init()
    elif cmd[0].lower() == "create":
        ldb.create(list(cmd[1:]))
    elif cmd[0].lower() == "view":
        ldb.view()
    elif cmd[0].lower() == "add_c":
        ldb.add_c(list(cmd[1:]))
    elif cmd[0].lower() == "add_r":
        ldb.add_r(list(cmd[1:]))
    elif cmd[0].lower() == "clear_r":
        ldb.clear_r(cmd[1:])
    elif cmd[0].lower() == "clear_c":
        ldb.clear_c(cmd[1:])
    elif cmd[0].lower() == "clearall":
        ldb.clearall()
    elif cmd[0].lower() == "store":
        ldb.store()
    elif cmd[0].lower() == "retrieve":
        ldb.retrieve()
    elif cmd[0].lower() == "genid":
        ldb.genid()
    elif cmd[0].lower() == "return_r":
        print(ldb.return_r(cmd[1:]))
    elif cmd[0].lower() == "return_c":
        print(ldb.return_c(int(cmd[1])))
    elif cmd[0].lower() == "update_r":
        ldb.update_r(int(cmd[1]), cmd[2:])
    elif cmd[0].lower() == "update_c":
        ldb.update_c(int(cmd[1]), cmd[2:])
    elif cmd[0].lower() == "update_ri":
        ldb.update_ri(int(cmd[1]), int(cmd[2]), cmd[3:])
    elif cmd[0].lower() == "sort_col":
        ldb.sort_col(int(cmd[1]), True if len(cmd) == 2 else False)
    elif cmd[0].lower() == "find":
        ldb.find(cmd[1])
