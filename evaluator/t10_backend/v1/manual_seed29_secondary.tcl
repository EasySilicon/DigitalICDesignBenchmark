read_db $::env(T10_INPUT_ODB)
load $::env(T10_PATCH_SO) T10secondary
puts [t10_seed29_secondary]
if {[file exists $::env(T10_OUTPUT_ODB)]} {error "output exists; preserve earlier candidate"}
write_db $::env(T10_OUTPUT_ODB)
exit
