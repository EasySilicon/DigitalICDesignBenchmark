proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set lib_files [require_env T10_LIB_FILES]
set input_odb [require_env T10_INPUT_ODB]
set input_sdc [require_env T10_INPUT_SDC]
set setrc_tcl [require_env T10_SETRC_TCL]
set report_file [require_env T10_REPORT]

foreach lib $lib_files { read_liberty $lib }
read_db $input_odb
read_sdc $input_sdc
source $setrc_tcl
set_propagated_clock [all_clocks]
estimate_parasitics -global_routing

report_worst_slack -max -digits 6 > $report_file
report_tns -max -digits 6 >> $report_file
report_worst_slack -min -digits 6 >> $report_file
report_tns -min -digits 6 >> $report_file
report_checks -path_delay max -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 20 >> $report_file
report_checks -path_delay max -from [all_registers] -to [all_registers] \
  -format full_clock_expanded -digits 4 -group_path_count 20 >> $report_file
report_checks -path_delay min -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 20 >> $report_file
puts "T10_GLOBAL_ROUTE_PROBE=$report_file"
exit
