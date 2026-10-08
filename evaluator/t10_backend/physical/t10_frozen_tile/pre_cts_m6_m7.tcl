set_routing_layers -clock M6-M7
set_wire_rc -clock -layer M7
set_wire_rc -signal -layer M7
if {[info exists ::env(T10_CTS_CELL_LIB)] &&
    $::env(T10_CTS_CELL_LIB) ne ""} {
  read_liberty $::env(T10_CTS_CELL_LIB)
  puts "T10_TILE_CTS_EXTRA_LIB $::env(T10_CTS_CELL_LIB)"
}
puts "T10_TILE_CLOCK_LAYERS M6-M7 ESTIMATED_CLOCK_RC M7"
