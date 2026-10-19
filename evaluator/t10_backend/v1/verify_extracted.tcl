# Read-only checks on a completed routed and extracted physical block.
foreach name {T10_LIBRARY_LIST T10_INPUT_ODB T10_INPUT_SDC T10_INPUT_SPEF T10_VERIFY_OUTPUT} {
    if {![info exists ::env($name)]} { error "$name is required" }
}
set_thread_count 4
foreach lib $::env(T10_LIBRARY_LIST) { read_liberty $lib }
read_db $::env(T10_INPUT_ODB)
read_sdc $::env(T10_INPUT_SDC)
read_spef $::env(T10_INPUT_SPEF)
set_propagated_clock [all_clocks]
set output $::env(T10_VERIFY_OUTPUT)
file mkdir $output
report_worst_slack -max -digits 6 > $output/setup.rpt
report_worst_slack -min -digits 6 > $output/hold.rpt
report_tns -max -digits 6 > $output/setup_tns.rpt
report_tns -min -digits 6 > $output/hold_tns.rpt
set starts [all_registers -clock_pins]
set ends [all_registers -data_pins]
if {[llength $starts] == 0 || [llength $ends] == 0} { error "no sequential timing boundaries" }
report_checks -from $starts -to $ends -path_delay max -digits 6 > $output/internal_setup.rpt
report_checks -from $starts -to $ends -path_delay min -digits 6 > $output/internal_hold.rpt
check_setup -verbose > $output/constraint_coverage.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $output/electrical.rpt
check_antennas -report_file $output/antenna.rpt
report_design_area
puts T10_EXTRACTED_VERIFICATION_COMPLETE
exit
