# Complete-DUT diagnosis, frozen 1 GHz SDC and native placement parasitics.
foreach lib $::env(T10_RETIME_LIBS) { read_liberty $lib }
read_db $::env(T10_RETIME_ODB)
read_sdc $::env(T10_RETIME_SDC)
source $::env(T10_RETIME_SETRC)
set_routing_layers -signal M2-M7 -clock M6-M7
unset_propagated_clock [get_clocks clk_clock]
estimate_parasitics -placement
set macros [get_cells -hierarchical -filter {ref_name == t10_reference_tile_4x4} *]
if {[llength $macros] != 16} { error "Expected full DUT with sixteen tile macros" }
set macro_outputs [get_pins -of_objects $macros -filter {direction == output}]
set macro_inputs {}
foreach pin [get_pins -of_objects $macros -filter {direction == input}] {
    if {![regexp {/(clk|rst_n|VDD|VSS)$} [get_full_name $pin]]} { lappend macro_inputs $pin }
}
set reg_outputs {}
foreach pin [all_registers -output_pins] {
    if {![regexp {^tile_row\[.*\.tile/} [get_full_name $pin]]} { lappend reg_outputs $pin }
}
set reg_inputs {}
foreach pin [all_registers -data_pins] {
    if {![regexp {^tile_row\[.*\.tile/} [get_full_name $pin]]} { lappend reg_inputs $pin }
}
set inputs {}
foreach port [all_inputs] {
    if {[get_full_name $port] ni {clk rst_n}} { lappend inputs $port }
}
set outputs [all_outputs]
set root $::env(T10_TOP_PATH_AUDIT_ROOT)
file mkdir $root
report_worst_slack -max > $root/summary.rpt
report_worst_slack -min >> $root/summary.rpt
report_clock_properties >> $root/summary.rpt
check_setup -verbose >> $root/summary.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators > $root/electrical.rpt
proc t10_report_path_scope {root name from to} {
    puts "T10_TOP_PATH_SCOPE $name starts=[llength $from] ends=[llength $to]"
    if {[llength $from] == 0 || [llength $to] == 0} { error "Empty path scope $name" }
    report_checks -from $from -to $to -path_delay max -group_path_count 100 \
        -endpoint_path_count 1 -format full_clock_expanded -digits 4 \
        -fields {slew cap fanout input} > $root/${name}_setup.rpt
    report_checks -from $from -to $to -path_delay min -group_path_count 10 \
        -endpoint_path_count 1 -format full_clock_expanded -digits 4 \
        -fields {slew cap fanout input} > $root/${name}_hold.rpt
}
t10_report_path_scope $root reg_to_reg $reg_outputs $reg_inputs
t10_report_path_scope $root reg_to_macro $reg_outputs $macro_inputs
t10_report_path_scope $root macro_to_reg $macro_outputs $reg_inputs
t10_report_path_scope $root macro_to_macro $macro_outputs $macro_inputs
t10_report_path_scope $root input_to_internal $inputs [concat $reg_inputs $macro_inputs]
t10_report_path_scope $root internal_to_output [concat $reg_outputs $macro_outputs] $outputs
puts "T10_FULL_DUT_PATH_AUDIT_FINISHED diagnostic_only=1 macros=16 pe_hierarchy=256 root=$root"
