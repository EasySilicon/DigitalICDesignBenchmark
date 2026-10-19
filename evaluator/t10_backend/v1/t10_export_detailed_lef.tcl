# ODB_INPUT and LEF_OUTPUT are supplied by the caller.
read_db $::env(ODB_INPUT)
write_abstract_lef $::env(LEF_OUTPUT)
