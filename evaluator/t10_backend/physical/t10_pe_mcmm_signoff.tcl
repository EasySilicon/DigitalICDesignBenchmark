# Extract and sign off a routed T10 PE at ASAP7 worst/best timing corners.
# One OpenRCX parasitic network is loaded into both timing scenes so setup and
# hold differ only by their characterized cell/macro libraries.
#
# Required environment variables are documented by
# physical/t10_run_openroad_signoff.sh.

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set wc_libs [require_env T10_WC_LIB_FILES]
set bc_libs [require_env T10_BC_LIB_FILES]
set wc_macro_libs [require_env T10_WC_MACRO_LIB_FILES]
set bc_macro_libs [require_env T10_BC_MACRO_LIB_FILES]
set input_odb [require_env T10_INPUT_ODB]
set input_sdc [require_env T10_INPUT_SDC]
set rcx_rules [require_env T10_RCX_RULES]
set setrc_tcl [require_env T10_SETRC_TCL]
set output_prefix [require_env T10_OUTPUT_PREFIX]
set setup_uncertainty_ps [require_env T10_SETUP_UNCERTAINTY_PS]
set hold_uncertainty_ps [require_env T10_HOLD_UNCERTAINTY_PS]
set thread_count [expr {
  [info exists ::env(T10_THREADS)] && $::env(T10_THREADS) ne "" ?
  $::env(T10_THREADS) : 4
}]

foreach input [concat $wc_libs $bc_libs $wc_macro_libs $bc_macro_libs \
    [list $input_odb $input_sdc $rcx_rules $setrc_tcl]] {
  if {![file isfile $input]} {
    error "missing input file $input"
  }
}
file mkdir [file dirname $output_prefix]

set_thread_count $thread_count
define_corners wc bc
foreach lib [concat $wc_libs $wc_macro_libs] {
  read_liberty -corner wc $lib
}
foreach lib [concat $bc_libs $bc_macro_libs] {
  read_liberty -corner bc $lib
}

read_db $input_odb
read_sdc $input_sdc
# The ASAP7 reference SDC is expressed in ps (1 GHz is 1000 ps).  Require
# explicit nonzero margins at invocation time so a bare zero-uncertainty result
# cannot accidentally be presented as signoff timing.
if {![string is double -strict $setup_uncertainty_ps] || $setup_uncertainty_ps <= 0} {
  error "T10_SETUP_UNCERTAINTY_PS must be a positive number"
}
if {![string is double -strict $hold_uncertainty_ps] || $hold_uncertainty_ps <= 0} {
  error "T10_HOLD_UNCERTAINTY_PS must be a positive number"
}
set_clock_uncertainty -setup $setup_uncertainty_ps [all_clocks]
set_clock_uncertainty -hold $hold_uncertainty_ps [all_clocks]
source $setrc_tcl

define_process_corner -ext_model_index 0 X
extract_parasitics -ext_model_file $rcx_rules
set spef_file "${output_prefix}.spef"
write_spef $spef_file
read_spef -corner wc $spef_file
read_spef -corner bc $spef_file
set_propagated_clock [all_clocks]

# Audit the committed detailed-route geometry while the extracted RSegs are
# live.  The checker requires M6/M7 clock trunks and rejects M8/M9.  Short
# M1-M5 leaf access from those trunks to standard-cell pins remains legal.
set ::env(REPORTS_DIR) [file dirname $output_prefix]
source [file join [file dirname [file normalize [info script]]] \
  t10_clock_route_audit.tcl]

set summary_file "${output_prefix}_summary.rpt"
set summary_id [open $summary_file w]
puts $summary_id "T10_INPUT_ODB=$input_odb"
puts $summary_id "T10_INPUT_SDC=$input_sdc"
puts $summary_id "T10_RCX_RULES=$rcx_rules"
puts $summary_id "T10_SETRC_TCL=$setrc_tcl"
puts $summary_id "T10_WC_LIB_FILES=$wc_libs"
puts $summary_id "T10_BC_LIB_FILES=$bc_libs"
puts $summary_id "T10_WC_MACRO_LIB_FILES=$wc_macro_libs"
puts $summary_id "T10_BC_MACRO_LIB_FILES=$bc_macro_libs"
puts $summary_id "T10_SPEF=$spef_file"
puts $summary_id "T10_SETUP_SCENE=wc"
puts $summary_id "T10_HOLD_SCENE=bc"
puts $summary_id "T10_SETUP_UNCERTAINTY_PS=$setup_uncertainty_ps"
puts $summary_id "T10_HOLD_UNCERTAINTY_PS=$hold_uncertainty_ps"
close $summary_id

puts "T10_SIGNOFF_SETUP_WNS"
report_worst_slack -max -digits 4
report_worst_slack -max -digits 4 >> $summary_file
puts "T10_SIGNOFF_SETUP_TNS"
report_tns -max -digits 4
report_tns -max -digits 4 >> $summary_file
puts "T10_SIGNOFF_HOLD_WNS"
report_worst_slack -min -digits 4
report_worst_slack -min -digits 4 >> $summary_file
puts "T10_SIGNOFF_HOLD_TNS"
report_tns -min -digits 4
report_tns -min -digits 4 >> $summary_file

report_checks -path_delay max -scenes wc -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 100 > "${output_prefix}_setup_wc.rpt"
report_checks -path_delay min -scenes bc -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 100 > "${output_prefix}_hold_bc.rpt"
check_setup -verbose > "${output_prefix}_constraint_coverage.rpt"
check_setup -unconstrained_endpoints \
  > "${output_prefix}_unconstrained.rpt"
report_check_types -scenes wc -violators -max_slew -max_capacitance \
  -max_fanout -max_count 100000 -digits 4 \
  > "${output_prefix}_electrical_wc.rpt"
report_check_types -scenes bc -violators -max_slew -max_capacitance \
  -max_fanout -max_count 100000 -digits 4 \
  > "${output_prefix}_electrical_bc.rpt"
report_design_area >> $summary_file

check_antennas -report_violating_nets \
  -report_file "${output_prefix}_antenna.rpt"
check_power_grid -net VDD \
  -error_file "${output_prefix}_vdd_connectivity.rpt"
check_power_grid -net VSS \
  -error_file "${output_prefix}_vss_connectivity.rpt"

puts "T10_SIGNOFF_OUTPUT_PREFIX=$output_prefix"
exit
