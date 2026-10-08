# Fast placement RC comparison, explicitly not routed qualification.
foreach lib $::env(T10_RETIME_LIBS) { read_liberty $lib }
read_db $::env(T10_RETIME_ODB)
read_sdc $::env(T10_RETIME_SDC)
source $::env(T10_RETIME_SETRC)
set_routing_layers -signal M2-M7 -clock M6-M7
set_wire_rc -clock -layer M7
set timing_mode $::env(T10_CLOCK_ESTIMATE_MODE)
if {$timing_mode eq "ideal_clocks_cell_only" || $timing_mode eq "placement_ideal_clocks"} {
  unset_propagated_clock [get_clocks clk_clock]
} else {
  set_propagated_clock [get_clocks clk_clock]
}
if {$timing_mode eq "placement" || $timing_mode eq "placement_ideal_clocks"} { estimate_parasitics -placement }
set report $::env(T10_CLOCK_ESTIMATE_REPORT)
puts "T10_PLACEMENT_CLOCK_ESTIMATE diagnostic_only=1 timing_mode=$timing_mode report=$report"
report_worst_slack -max > $report
report_worst_slack -min >> $report
report_clock_skew >> $report
report_power >> $report
report_checks -path_delay min -group_path_count 1 -format full_clock_expanded \
  -fields {slew cap fanout input} >> $report
report_checks -path_delay max -group_path_count 1 -format full_clock_expanded \
  -fields {slew cap fanout input} >> $report
set macro_cells [get_cells -hierarchical -filter {ref_name == t10_reference_tile_4x4} *]
if {[llength $macro_cells] != 16} { error "Expected the complete DUT's sixteen tiles" }
set macro_outputs [get_pins -of_objects $macro_cells -filter {direction == output}]
set macro_inputs {}
foreach pin [get_pins -of_objects $macro_cells -filter {direction == input}] {
  if {[regexp {/(clk|rst_n|VDD|VSS)$} [get_full_name $pin]]} { continue }
  lappend macro_inputs $pin
}
set starts [concat [all_registers -output_pins] $macro_outputs]
set ends [concat [all_registers -data_pins] $macro_inputs]
puts "T10_PLACEMENT_PATH_SCOPE macros=[llength $macro_cells] starts=[llength $starts] ends=[llength $ends]"
report_checks -from $starts -to $ends -path_delay max -group_path_count 5 \
  -format full_clock_expanded -fields {slew cap fanout input} >> $report
report_checks -from $starts -to $ends -path_delay min -group_path_count 1 \
  -format full_clock_expanded -fields {slew cap fanout input} >> $report
puts "T10_PLACEMENT_CLOCK_ESTIMATE_DONE"
