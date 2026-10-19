read_db $::env(T10_INPUT_ODB)
load $::env(T10_PATCH_SO) T10seed29
puts [t10_seed29 $::env(T10_PATCH_MODE)]
if {[string match "apply*" $::env(T10_PATCH_MODE)]} {
    if {[file exists $::env(T10_OUTPUT_ODB)]} { error "output exists; preserve earlier result" }
    write_db $::env(T10_OUTPUT_ODB)
}
exit
