# Generate the complete timing/abstract evidence set for one routed T10
# hierarchy level.  GDS is intentionally outside the benchmark PPA gate.

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set lib_files [require_env T10_LIB_FILES]
set input_odb [require_env T10_INPUT_ODB]
set input_sdc [require_env T10_INPUT_SDC]
set input_spef ""
if {[info exists ::env(T10_INPUT_SPEF)]} {
  set input_spef $::env(T10_INPUT_SPEF)
}
set estimate_global_route [expr {
  [info exists ::env(T10_ESTIMATE_GLOBAL_ROUTE)] &&
  $::env(T10_ESTIMATE_GLOBAL_ROUTE) eq "1"
}]
set rcx_rules [require_env T10_RCX_RULES]
set setrc_tcl [require_env T10_SETRC_TCL]
set output_prefix [require_env T10_OUTPUT_PREFIX]
set threads [expr {
  [info exists ::env(T10_THREADS)] && $::env(T10_THREADS) ne "" ?
  $::env(T10_THREADS) : 4
}]

set required_inputs [concat $lib_files \
  [list $input_odb $input_sdc $rcx_rules $setrc_tcl]]
if {$input_spef ne ""} {
  lappend required_inputs $input_spef
}
foreach input $required_inputs {
  if {![file isfile $input]} {
    error "missing input file $input"
  }
}
file mkdir [file dirname $output_prefix]

set_thread_count $threads
foreach lib $lib_files {
  read_liberty $lib
}
read_db $input_odb
read_sdc $input_sdc
source $setrc_tcl
define_process_corner -ext_model_index 0 X
set spef_file "${output_prefix}.spef"
if {$input_spef ne ""} {
  # ORFS final_report already extracted this exact routed ODB.  Reuse that
  # SPEF so hierarchy export does not repeat a large OpenRCX extraction.
  read_spef $input_spef
  file copy -force $input_spef $spef_file
} elseif {$estimate_global_route} {
  estimate_parasitics -global_routing
} else {
  extract_parasitics -ext_model_file $rcx_rules
  write_spef $spef_file
}
set_propagated_clock [all_clocks]

set timing_file "${output_prefix}_timing.rpt"
report_worst_slack -max -digits 6 > $timing_file
report_tns -max -digits 6 >> $timing_file
report_worst_slack -min -digits 6 >> $timing_file
report_tns -min -digits 6 >> $timing_file
report_checks -path_delay max -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 100 >> $timing_file
report_checks -path_delay min -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 100 >> $timing_file

sta::redirect_file_begin "${output_prefix}_area.rpt"
report_design_area
sta::redirect_file_end
check_setup -verbose > "${output_prefix}_constraint_coverage.rpt"
check_setup -unconstrained_endpoints > "${output_prefix}_unconstrained.rpt"
report_check_types -violators -max_slew -max_capacitance -max_fanout \
  -max_count 100000 -digits 4 > "${output_prefix}_electrical.rpt"
check_antennas -report_violating_nets \
  -report_file "${output_prefix}_antenna.rpt"
if {$estimate_global_route} {
  # dbSta's GRT estimate is enough for the parent timing model.  PDN
  # connectivity on this 1.1 GiB macro checkpoint materializes a very large
  # graph and is already covered by the ordinary ORFS floorplan checks.
  set pg_skip [open "${output_prefix}_power_grid_check.txt" w]
  puts $pg_skip "skipped_for_global_route_abstract=1"
  close $pg_skip
} else {
  check_power_grid -net VDD -error_file "${output_prefix}_vdd_connectivity.rpt"
  check_power_grid -net VSS -error_file "${output_prefix}_vss_connectivity.rpt"
}

set ::env(REPORTS_DIR) [file dirname $output_prefix]
if {$estimate_global_route} {
  set clock_audit [open \
    [file join $::env(REPORTS_DIR) t10_clock_route_audit.tsv] w]
  puts $clock_audit "status\tglobal_route_abstract_no_detailed_segments"
  close $clock_audit
} else {
  source [file join [file dirname [file normalize [info script]]] \
    t10_clock_route_audit.tcl]
}

write_abstract_lef "${output_prefix}.lef"
write_verilog "${output_prefix}.v"
write_sdc -no_timestamp "${output_prefix}.sdc"
write_db "${output_prefix}.odb"

# The generated Liberty contains the routed internal clock-tree paths.  Clear
# only source latency so a parent level does not count it a second time.
set_clock_latency -source 0 [all_clocks]
write_timing_model "${output_prefix}.lib"

puts "T10_HIER_BLOCK_FINISH=$output_prefix"
exit
