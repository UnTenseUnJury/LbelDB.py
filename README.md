# LbelDB.py

>**A text based no corruption database for python. Easy to use. Made for beginners**

## Installation

Use the package manager pip to install LbelDB.py

```bash
pip install LbelDB
```

## Usage

```python
import ldb

ldb.init() # general initialization

ldb.create(("name","score")) # creates the dbs first labels or columns

for i in enumerate(scores):
    ldb.update_ri(i[0] , 1 , i[1]) # updates the scores in each row

ldb.store() # stores to the db to the `.lbel` file

ldb.view() # prints the db to the console
```

## Contributing
Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

Please make sure to update tests as appropriate.

## License
[Unlicence](https://choosealicense.com/licenses/unlicense/)
