# Re-extract and check the historical final checkpoint after the case-5 edit.
foreach name {T10_ORFS_FLOW T10_WORK_DIR T10_PATCH_SO} {
  if {![info exists ::env($name)]} { error "$name is required" }
}
set flow $::env(T10_ORFS_FLOW)
set work $::env(T10_WORK_DIR)
set variant ic_t10_frozen_pe_exact_v15_margin_escape_m7_wc_p1000_seed11
set historical $flow/results/asap7/t10_reference_pe/$variant
set_thread_count 4
source $flow/platforms/asap7/liberty_suppressions.tcl
# Reuse exactly the library list recorded by the original finish invocation.
set fh [open $flow/logs/asap7/t10_reference_pe/$variant/6_report.log r]
set finish_log [read $fh]
close $fh
foreach line [split $finish_log \n] {
  if {[string match {read_liberty *} $line]} { eval $line }
}
read_db $historical/6_final.odb
read_sdc $historical/6_final.sdc
source $flow/platforms/asap7/setRC.tcl
load $::env(T10_PATCH_SO) T10manualv15patch
puts "T10_MANUAL_V15_PATCH [t10_manual_v15_patch 5]"
if {[info exists ::env(T10_ENCLOSURE_SO)]} {
  load $::env(T10_ENCLOSURE_SO) T10manualv15enclosure
  puts "T10_MANUAL_V15_ENCLOSURE [t10_manual_v15_enclosure]"
  load $::env(T10_LOCAL_SO) T10manualv15local
  puts "T10_MANUAL_V15_LOCAL [t10_manual_v15_local]"
}
write_db $work/v15_manual_final.odb
write_sdc -no_timestamp $work/v15_manual_final.sdc
source $flow/scripts/deleteRoutingObstructions.tcl
deleteRoutingObstructions
define_process_corner -ext_model_index 0 X
extract_parasitics -ext_model_file $flow/platforms/asap7/rcx_patterns.rules
write_spef $work/v15_manual_final.spef
read_spef $work/v15_manual_final.spef
set_propagated_clock [all_clocks]
report_worst_slack -max -digits 6 > $work/setup.rpt
report_worst_slack -min -digits 6 > $work/hold.rpt
report_tns -max -digits 6 > $work/setup_tns.rpt
report_tns -min -digits 6 > $work/hold_tns.rpt
report_checks -path_delay max -format full_clock_expanded -digits 6 > $work/setup_path.rpt
report_checks -path_delay min -format full_clock_expanded -digits 6 > $work/hold_path.rpt
report_check_types -max_slew -max_capacitance -max_fanout -violators -digits 6 > $work/electrical.rpt
check_setup -verbose > $work/constraint_coverage.rpt
check_antennas -report_file $work/antenna.rpt
report_design_area
report_power -digits 6 > $work/power_vectorless.rpt
puts T10_MANUAL_V15_VERIFY_COMPLETE
exit
