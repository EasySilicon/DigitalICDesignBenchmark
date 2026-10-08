# Compact full-DUT diagnostics. This hook never qualifies a scoring baseline.
if {![info exists ::env(T10_REFERENCE_GRID_PROBE)] || $::env(T10_REFERENCE_GRID_PROBE) ne "1"} {
    error "Diagnostic route audit requires explicit probe mode"
}
set report $::env(REPORTS_DIR)/t10_full_top_route_diagnostic.rpt
report_worst_slack -max > $report
report_worst_slack -min >> $report
report_tns >> $report
report_clock_skew >> $report
report_power >> $report
# Select STA objects directly. OpenDB instance and bus names can contain
# literal escaped brackets; rebuilding get_pins patterns from them is unsafe.
set macro_cells [get_cells -hierarchical -filter {ref_name == t10_reference_tile_4x4} *]
set macros [llength $macro_cells]
if {$macros != 16} { error "Expected complete DUT with 16 tile macros, got $macros" }
set macro_outputs [get_pins -of_objects $macro_cells -filter {direction == output}]
set macro_inputs {}
foreach pin [get_pins -of_objects $macro_cells -filter {direction == input}] {
    if {[regexp {/(clk|rst_n|VDD|VSS)$} [get_full_name $pin]]} { continue }
    lappend macro_inputs $pin
}
if {[llength $macro_outputs] == 0 || [llength $macro_inputs] == 0} {
    error "Macro path-class selection returned no pins"
}
set starts [concat [all_registers -output_pins] $macro_outputs]
set ends [concat [all_registers -data_pins] $macro_inputs]
puts "T10_FULL_TOP_TIMING_AUDIT macros=$macros macro_starts=[llength $macro_outputs] macro_ends=[llength $macro_inputs] internal_starts=[llength $starts] internal_ends=[llength $ends] report=$report"
report_checks -from $starts -to $ends -path_delay max \
    -group_path_count 20 -format full_clock_expanded \
    -fields {slew cap fanout input} >> $report
report_checks -from $starts -to $ends -path_delay min \
    -group_path_count 20 -format full_clock_expanded \
    -fields {slew cap fanout input} >> $report
report_checks -to [all_outputs] -path_delay max \
    -group_path_count 8 -format full_clock_expanded \
    -fields {slew cap fanout input} >> $report
report_checks -from [all_inputs -no_clocks] -path_delay max \
    -group_path_count 8 -format full_clock_expanded \
    -fields {slew cap fanout input} >> $report
write_verilog $::env(RESULTS_DIR)/5_global_route_topology.v
puts "T10_FULL_TOP_TIMING_AUDIT_DONE"
