# Repair all hold paths under the unchanged 1 GHz SDC, then route ECO buffers.
puts "T10_HOLD_REPAIR_BEFORE"
report_worst_slack -max
report_worst_slack -min
repair_timing -hold -verbose
puts "T10_HOLD_REPAIR_BUFFERED"
report_worst_slack -max
report_worst_slack -min
global_route -start_incremental
detailed_placement
check_placement -verbose
global_route -end_incremental -congestion_report_file $::env(REPORTS_DIR)/t10_hold_eco_congestion.rpt
estimate_parasitics -global_routing
write_guides $::env(RESULTS_DIR)/route.guide
puts "T10_HOLD_REPAIR_ROUTED"
report_worst_slack -max
report_worst_slack -min
