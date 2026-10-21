"""Run via openroad -python, not system Python."""
import odb

database=odb.dbDatabase.create()
assert database is not None
print('T10_OPENDB_RUNTIME_READY',flush=True)
