# Repair PE hold timing before global routing.  This hook runs after CTS with
# placement parasitics, legalizes every ECO batch, and deliberately reserves
# margin for the RC increase observed after global routing.
set hold_margin_ps 80
if {[info exists ::env(T10_HOLD_MARGIN_PS)]} {
  set hold_margin_ps $::env(T10_HOLD_MARGIN_PS)
}

puts "T10_PRE_GRT_HOLD_REPAIR_BEGIN margin_ps=$hold_margin_ps"
estimate_parasitics -placement
report_worst_slack -max
report_worst_slack -min

# First remove the large CTS hold debt.  Re-estimate after legalization because
# cell movement can expose a small second set of short paths.
repair_timing -hold -hold_margin 0 -max_iterations 5000 \
  -max_buffer_percent 10 -verbose
detailed_placement
check_placement -verbose
estimate_parasitics -placement
repair_timing -hold -hold_margin 0 -max_iterations 5000 \
  -max_buffer_percent 10 -verbose
detailed_placement
check_placement -verbose

# Global-route RC consumed 56 ps of placement-estimated margin in the measured
# seed-11 PE, so reserve 80 ps before routing.
estimate_parasitics -placement
repair_timing -hold -hold_margin $hold_margin_ps -max_iterations 5000 \
  -max_buffer_percent 10 -verbose
detailed_placement
check_placement -verbose
estimate_parasitics -placement

puts "T10_PRE_GRT_HOLD_REPAIR_END margin_ps=$hold_margin_ps"
report_worst_slack -max
report_worst_slack -min
report_clock_min_period
