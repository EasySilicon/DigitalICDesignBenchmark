# Deterministic aggregate replay from the original seed29 final database.
# No placement, routing search, pin, obstruction, PG or logical-netlist edit.
read_db $::env(T10_INPUT_ODB)
load $::env(T10_ROOT_PATCH_SO) T10seed29
load $::env(T10_SECONDARY_PATCH_SO) T10secondary
puts [t10_seed29 apply_clearance_bridge]
puts [t10_seed29_secondary]
puts [t10_seed29_bridge461]
puts [t10_seed29_shift19568]
puts [t10_seed29_stack571]
puts [t10_seed29_shift559]
puts [t10_seed29_bridge473]
puts [t10_seed29_bridge301]
puts [t10_seed29_bridge465]
if {[file exists $::env(T10_OUTPUT_ODB)]} {error "output exists; preserve earlier candidate"}
write_db $::env(T10_OUTPUT_ODB)
exit
