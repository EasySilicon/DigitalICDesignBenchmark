# The ASAP7 M6/M7 legal width table includes 0.160 um.  Assign that width and
# the corresponding 0.072 um parallel spacing to every generated clock net.
# The ordinary CTS "apply_ndr" option increases spacing only; this explicit
# NDR also lowers resistance on the long channel routes between PE macros.
if {[info exists ::env(T10_WIDE_CLOCK_NDR)] &&
    $::env(T10_WIDE_CLOCK_NDR) eq "1"} {
  set block [ord::get_db_block]
  if {[$block findNonDefaultRule T10_CLK_M67_W160_S072] eq "NULL"} {
    create_ndr -name T10_CLK_M67_W160_S072 \
      -width {M6 0.160 M7 0.160} \
      -spacing {M6 0.072 M7 0.072}
  }
  assign_ndr -ndr T10_CLK_M67_W160_S072 -all_clocks
  puts "T10_TILE_CLOCK_NDR layers=M6-M7 width_um=0.160 spacing_um=0.072"
}
