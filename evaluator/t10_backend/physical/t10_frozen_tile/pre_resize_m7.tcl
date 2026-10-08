# The systolic links span one 493 um PE plus the inter-macro channel.  Model
# placement-stage data wiring with the M7 RC used by resistance-aware routing
# so the resizer inserts repeaters for the actual long-wire regime.
set_wire_rc -signal -layer M7
puts "T10_TILE_PLACEMENT_SIGNAL_RC M7"
