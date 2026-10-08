set_routing_layers -clock M6-M7
set_wire_rc -clock -layer M7
puts "T10_INT_GROUP_CLOCK_LAYERS M6-M7 ESTIMATED_CLOCK_RC M7"

# The class1 floating-point macro has signal pins on M6 along its left edge,
# while its internal M4 OBS reaches the boundary.  Keep lower-layer trunks a
# fraction of a micron away from that edge so DRT does not repeatedly move a
# single M4 spacing violation up and down the macro boundary.  M6/M7 pin and
# clock access remains open.
set db [ord::get_db]
set tech [$db getTech]
set block [[$db getChip] getBlock]
set dbu [$tech getDbUnitsPerMicron]
foreach layer_name {M2 M3 M4 M5} {
  set layer [$tech findLayer $layer_name]
  if {$layer eq "NULL"} {
    error "missing routing layer $layer_name"
  }
  odb::dbObstruction_create $block $layer \
    [expr {round(209.50 * $dbu)}] [expr {round(299.70 * $dbu)}] \
    [expr {round(210.20 * $dbu)}] [expr {round(406.70 * $dbu)}]
}
puts "T10_CLASS1_LEFT_ESCAPE bbox=209.50,299.70,210.20,406.70 layers=M2-M5"
