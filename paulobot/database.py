import sqlite3
import os.path
import logging
import enum
import functools
import json
import datetime
import threading


# Export constants for system column names
UNIQUE_ID = '_pb_id'

LOGGER = logging.getLogger(__name__)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class TableRow(dict):
    """A regular dict, plus a system 'id' attribute."""
    __slots__ = ()

    def __init__(self, *args, **kwargs):
        super(TableRow, self).__init__(*args, **kwargs)
        if not UNIQUE_ID in self:
            raise ValueError(f"Cannot create table row from table with no {UNIQUE_ID} "
                             "column!")

    @property
    def id(self):
        return self[UNIQUE_ID]


class FieldType(enum.Enum):
    INTEGER = enum.auto()
    TEXT = enum.auto()
    DATETIME = enum.auto()
    JSON = enum.auto()


FIELD_TYPE_TO_SQL = {
    FieldType.INTEGER:  "INTEGER",
    FieldType.TEXT:     "TEXT",
    FieldType.DATETIME: "TEXT",
    FieldType.JSON:     "TEXT",
}

def synchronized(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        """A synchronized wrapper."""
        with self.lock:
            return func(self, *args, **kwargs)
    return wrapper

class Database:
    """
    Wrapper round an sqlite3 Database.

    All accesses are synchronous.

    """
    def __init__(self, filename):
        # Asyncio means that multiple threads execute code, so
        # turn off thread checking and use a lock
        self.connection = sqlite3.connect(filename,
                                          check_same_thread=False)
        self.cursor = self.connection.cursor()
        self.lock = threading.Lock()
        LOGGER.info("Database opened at %s", filename)

    @staticmethod
    def _sanitize(inp):
        inp = inp.replace('\\', '\\\\')
        inp = inp.replace('"', '\\"')
        return '"' + inp + '"'

    @staticmethod
    def _qMarks(fields, delim=""):
        return ", ".join(delim + "?" + delim for f in fields)

    @staticmethod
    def _stringFromFieldNames(fields):
        return ", ".join(Database._sanitize(f) for f in fields)

    @staticmethod
    def _stringFromListItems(list):
        return ", ".join(Database._sanitize(l) for l in list)

    @staticmethod
    def _tupleFromFieldValues(fields):
        return tuple(fields.values())

    @staticmethod
    def _buildConditions(conditions):
        return " and ".join(Database._sanitize(c[0]) + c[1] + "?" for c in conditions) or "1"

    @staticmethod
    def _buildConditionParams(conditions):
        return tuple(c[2] for c in conditions)

    @staticmethod
    def _buildSetConditions(fields):
        return ", ".join(Database._sanitize(c) + "=?" for c in fields)

    @synchronized
    def create_table(self, name, field_defs):
        """
        Create a new table in the database called 'name' and containing fields
        'field_defs', a dictionary of field name to sqllite3 type string

        """
        if any(f.startswith("_pb") for f in field_defs.keys()):
            raise ValueError("An attempt was made to create a table with "
                             "system-reserved column-name (prefix '_pb').")

        fields = [self._sanitize(k) + " " + v
                  for k, v in field_defs.items()]
        n = Database._sanitize(name)
        fields_string = ', '.join(['{0} INTEGER PRIMARY KEY AUTOINCREMENT'.format(UNIQUE_ID)] + fields)
        query = 'CREATE TABLE {0} ({1});'.format(n, fields_string)
        self.raw(query)

    @synchronized
    def table_exists(self, name):
        """Check to see if a table called 'name' exists in the database."""
        n = Database._sanitize(name)
        query = "SELECT `name` FROM `sqlite_master` WHERE `type`='table' AND `name`={0};".format(n)
        self.raw(query)
        r = self.cursor.fetchall()
        count = len(r)
        return count != 0

    @synchronized
    def insert(self, name, fields):
        """
        Insert a row into table 'name'.

        Fields is a dictionary mapping field names (as defined in
        create_table) to values.

        """
        n = Database._sanitize(name)
        query = "INSERT INTO {0} ({1}) VALUES ({2});".format(n,
                               Database._stringFromFieldNames(fields),
                               Database._qMarks(fields, ''))
        tup = Database._tupleFromFieldValues(fields)
        self.raw(query, tup)
        return self.cursor.lastrowid

    @synchronized
    def fetch(self, name, fields, conditions=(),
              order_by=None, reverse=False, limit=None):
        """
        Get data from the table 'name'.

        Returns a list of dictionaries mapping 'fields' to their values, one
        dictionary for each row which satisfies a condition in conditions.

        Conditions is an iterable of (field, op, val) tuples, e.g.

        (('name', '=', 'paulo'), ('age', '<', '100'))

        """
        n = Database._sanitize(name)
        fields = list(fields) + [UNIQUE_ID]
        query = "SELECT {0} FROM {1} WHERE ({2})".format(
            Database._stringFromListItems(fields), n,
            Database._buildConditions(conditions))
        if order_by:
            query += f" ORDER BY {Database._sanitize(order_by)}"
            if reverse:
                query += " DESC"
        if limit:
            query += f" LIMIT {limit}"
        query += ";"
        self.raw(query, Database._buildConditionParams(conditions))
        c = self.cursor.fetchall()
        rows = [TableRow(dict(zip(fields, item))) for item in c]
        return rows

    @synchronized
    def count(self, name, conditions=()):
        """Return the number of rows in table 'name' which satisfy conditions."""
        n = Database._sanitize(name)
        query = "SELECT COUNT(*) FROM {0} WHERE ({1});".format(n, Database._buildConditions(conditions))
        r = self.raw(query, Database._buildConditionParams(conditions)).fetchall()
        return r[0][0]

    @synchronized
    def delete(self, name, conditions=()):
        """Delete rows from table 'name' which satisfy conditions."""
        n = Database._sanitize(name)
        query = "DELETE FROM {0} WHERE ({1});".format(n, Database._buildConditions(conditions))
        self.raw(query, Database._buildConditionParams(conditions))
        return self.cursor.rowcount

    @synchronized
    def update(self, name, fields, conditions=()):
        """
        Update rows in table 'name' which satisfy conditions.

        Fields is a dictionary mapping the field names to their new values.

        """
        n = Database._sanitize(name)
        query = "UPDATE {0} SET {1} WHERE ({2});".format(
            n, Database._buildSetConditions(fields),
            Database._buildConditions(conditions))
        tup = Database._tupleFromFieldValues(fields)
        tup = tup + Database._buildConditionParams(conditions)
        self.raw(query, tup)
        return self.cursor.rowcount

    @synchronized
    def empty_table(self, name):
        """Remove all rows from table 'name'."""
        n = Database._sanitize(name)
        query = "DELETE FROM {0} WHERE 1;".format(n)
        self.raw(query)

    @synchronized
    def delete_table(self, name):
        """Delete table 'name'."""
        n = Database._sanitize(name)
        query = "DROP TABLE {0};".format(n)
        self.raw(query)

    def raw(self, command, params=()):
        """
        Perform raw query.

        Caller responsible for holding lock!.

        """
        assert self.lock.locked()

        p = self.cursor.execute(command, params)
        self.connection.commit()
        return p


def _convert_result(func):
    @functools.wraps(func)
    def wrapper(self, *args, **kwargs):
        res = func(self, *args, **kwargs)
        if res:
            if isinstance(res, TableRow):
                res = (res,)
            for idx, field, val in ((i, f, v)
                                    for i, rec in enumerate(res)
                                    for f, v in rec.items()
                                    if f != UNIQUE_ID):
                res[idx][field] = _from_raw_val(self._field_types[field],
                                                val)

        return res
    return wrapper


class Table:
    """
    Represents a table in the DB.

    Provides rich types, mapping them to basic sqltypes for use with
    Database.

    """

    def __init__(self, db, table_name, field_types):
        self._db = db
        self._table_name = table_name
        self._field_types = field_types

        # Create table if it doesn't exist
        if not self._db.table_exists(self._table_name):
            self._db.create_table(self._table_name,
                                  {k: FIELD_TYPE_TO_SQL[v]
                                  for k, v in field_types.items()})
            LOGGER.info("Created table %s, fields %s", table_name, field_types)

    def _prepare_fields(self, fields, context_str):
        for field, val in fields.items():
            if field not in self._field_types:
                raise Exception("{} error: {} is not a known "
                                "field for {}"
                                .format(context_str, field,
                                        self._table_name))
            fields[field] = _to_raw_val(
                self._field_types[field], val)

    def _get_fields(self):
        n = self._db._sanitize(self._table_name)
        query = f"PRAGMA table_info({n});"
        self._db.raw(query)
        r = self._db.cursor.fetchall()
        return [val[1] for val in r if val[1] != UNIQUE_ID]

    def _create_field(self, field_name):
        table_name = self._db._sanitize(self._table_name)
        field_name = self._db._sanitize(field_name)
        query = "ALTER TABLE {0} ADD COLUMN {1};".format(table_name,
                                                         field_name)
        self._db.raw(query)

    @_convert_result
    def find_all(self, start_id=None, end_id=None):
        """
        Find all records, optionally starting from an id.

        """
        conds = []
        if start_id is not None:
            conds.append((UNIQUE_ID, ">=", start_id))
        if end_id is not None:
            conds.append((UNIQUE_ID, "<", start_id))

        return self._db.fetch(self._table_name,
                              self._field_types.keys(),
                              conds)

    @_convert_result
    def find_last(self, number, end_id=None):
        """
        Get last x records in reverse order.

        """
        conds = ()
        if end_id is not None:
            conds = ((UNIQUE_ID, '<', end_id),)

        return self._db.fetch(self._table_name,
                              self._field_types.keys(),
                              conds,
                              order_by=UNIQUE_ID,
                              reverse=True,
                              limit=number)

    @_convert_result
    def find_list(self, record_ids):
        """
        Get list of records

        """
        ids = ",".join(str(r) for r in record_ids)
        cond = (UNIQUE_ID, "in", f"({ids})")
        return self._db.fetch(self._table_name,
                              self._field_types.keys(),
                              (cond,))

    @_convert_result
    def find_record(self, record_id):
        cond = (UNIQUE_ID, "=", record_id)
        return self._db.fetch(self._table_name,
                              self._field_types.keys(),
                              (cond,))[0]


    def update_record(self, fields, record_id, log_prev=False):
        # Lookup current record so we can log change
        if log_prev:
            prev_record = self.find_record(record_id)

        # Make sure the conditions and fields are valid
        self._prepare_fields(fields, "Update fields")
        self._db.update(fields, (UNIQUE_ID, "=", record_id,))

        if log_prev:
            LOGGER.info("Updated %s record id %s with %s (prev %s)",
                        self._table_name, record_id, fields,
                        {k : v for k, v in prev_record.items()
                        if k in fields})
        else:
            LOGGER.info("Updated %s record id %s with %s",
                        self._table_name, record_id, fields)

    def create(self, fields):
        # Make sure the conditions and fields are valid
        self._prepare_fields(fields, "Create fields")

        # Returns the record ID
        record_id = self._db.insert(self._table_name, fields)

        LOGGER.info("Created %s record id %s with %s",
                    self._table_name, record_id, fields)
        return record_id

    def delete_record(self, record_id):
        LOGGER.info("Deleting %s record id %s",
                    self._table_name, record_id)
        self._db.delete(self._table_name,
                        {UNIQUE_ID : record_id})

    def delete_record_by_field(self, field_name, field_val):
        LOGGER.info("Deleting %s record with %s val '%s'",
                    self._table_name, field_name, field_val)
        self._db.delete(self._table_name,
                        {field_name : field_val})

    def record_count(self):
        self._db.count(self._table_name, {})


def _from_raw_val(field_type, val):
    if field_type is FieldType.JSON:
        val = json.loads(val)

    if field_type is FieldType.DATETIME:
        val = datetime.datetime.strptime(val, TIME_FORMAT)

    return val


def _to_raw_val(field_type, val):
    if field_type is FieldType.JSON:
        val = json.dumps(val)

    if field_type is FieldType.DATETIME:
        val = val.strftime(TIME_FORMAT)

    return val