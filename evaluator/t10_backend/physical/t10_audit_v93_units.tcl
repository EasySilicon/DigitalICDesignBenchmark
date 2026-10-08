# Read-only provenance/configuration audit. No timing or placement mutation.
foreach lib $::env(T10_AUDIT_LIBS) { read_liberty $lib }
read_db $::env(T10_AUDIT_ODB)
read_sdc $::env(T10_AUDIT_SDC)
source $::env(T10_AUDIT_SETRC)
set_routing_layers -signal M2-M7 -clock M6-M7
set_wire_rc -clock -layer M7
report_units
report_layer_rc
foreach clock [get_clocks *] {
  puts "T10_AUDIT_CLOCK [get_full_name $clock] period=[get_property $clock period]"
}
set macros [get_cells -hierarchical -filter {ref_name == t10_reference_tile_4x4} *]
if {[llength $macros] != 16} { error "Expected sixteen tiles / 256 PEs" }
puts "T10_AUDIT_UNITS_DONE tile_macros=[llength $macros]"
