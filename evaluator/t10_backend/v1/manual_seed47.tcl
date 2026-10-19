read_db $::env(T10_INPUT_ODB)
load $::env(T10_PATCH_SO) T10seed47
puts [t10_seed47 $::env(T10_PATCH_MODE)]
if {$::env(T10_PATCH_MODE) in {apply apply_local}} {
    if {[file exists $::env(T10_OUTPUT_ODB)]} { error "output exists; preserve earlier result" }
    write_db $::env(T10_OUTPUT_ODB)
}
exit
