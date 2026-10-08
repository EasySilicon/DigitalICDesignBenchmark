# Retime the exact saved route: no new routing and no changed constraints.
foreach lib $::env(T10_RETIME_LIBS) { read_liberty $lib }
read_db $::env(T10_RETIME_ODB)
read_sdc $::env(T10_RETIME_SDC)
source $::env(T10_RETIME_SETRC)
set_routing_layers -signal M2-M7 -clock M6-M7
set_propagated_clock [get_clocks clk_clock]
read_global_route_segments $::env(T10_RETIME_SEGMENTS)
estimate_parasitics -global_routing
source [file join $::env(T10_BACKEND_ROOT) physical t10_frozen_top/post_global_route_diagnostic.tcl]
