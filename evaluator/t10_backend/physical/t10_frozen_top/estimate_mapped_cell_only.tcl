# Optimistic logic diagnostic of the full mapped DUT before physical trees.
# It does not qualify timing, placement, routing, power or a scoring baseline.
foreach lib $::env(T10_RETIME_LIBS) { read_liberty $lib }
foreach lef $::env(T10_CELL_ONLY_LEFS) { read_lef $lef }
read_verilog $::env(T10_CELL_ONLY_NETLIST)
link_design npu_systolic_matmul_16x16
read_sdc $::env(T10_RETIME_SDC)
unset_propagated_clock [all_clocks]
set macro_cells [get_cells -hierarchical -filter {ref_name == t10_reference_tile_4x4} *]
if {[llength $macro_cells] != 16} { error "Cell-only scope must contain sixteen tile macros" }
set report $::env(T10_CLOCK_ESTIMATE_REPORT)
puts "T10_MAPPED_CELL_ONLY diagnostic_only=1 ideal_wires=1 ideal_clocks=1 macros=16 report=$report"
report_worst_slack -max > $report
report_worst_slack -min >> $report
check_setup -verbose >> $report
set macro_outputs [get_pins -of_objects $macro_cells -filter {direction == output}]
set macro_inputs {}
foreach pin [get_pins -of_objects $macro_cells -filter {direction == input}] {
  if {[regexp {/(clk|rst_n|VDD|VSS)$} [get_full_name $pin]]} { continue }
  lappend macro_inputs $pin
}
set starts [concat [all_registers -output_pins] $macro_outputs]
set ends [concat [all_registers -data_pins] $macro_inputs]
puts "T10_MAPPED_CELL_ONLY_SCOPE starts=[llength $starts] ends=[llength $ends]"
report_checks -from $starts -to $ends -path_delay max -group_path_count 5 \
  -format full_clock_expanded -fields {slew cap fanout input} >> $report
report_checks -from $starts -to $ends -path_delay min -group_path_count 1 \
  -format full_clock_expanded -fields {slew cap fanout input} >> $report
report_checks -to [all_outputs] -path_delay max -group_path_count 3 \
  -format full_clock_expanded -fields {slew cap fanout input} >> $report
puts "T10_MAPPED_CELL_ONLY_FINISHED"
