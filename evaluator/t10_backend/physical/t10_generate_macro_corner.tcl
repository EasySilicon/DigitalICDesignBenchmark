# Generate one extracted timing model for a routed T10 child macro.
#
# Required environment variables:
#   T10_CORNER       OpenSTA scene/corner name, for example "bc"
#   T10_LIB_FILES    Tcl list of standard-cell Liberty files for the corner
#   T10_INPUT_ODB    routed child-macro database
#   T10_INPUT_SDC    matching constraints
#   T10_INPUT_SPEF   matching extracted parasitics
#   T10_OUTPUT_LIB   generated macro Liberty model
# Optional:
#   T10_REPORT       timing report path (defaults to OUTPUT_LIB.rpt)
#   T10_THREADS      OpenROAD thread count (defaults to 4)

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set corner [require_env T10_CORNER]
set lib_files [require_env T10_LIB_FILES]
set input_odb [require_env T10_INPUT_ODB]
set input_sdc [require_env T10_INPUT_SDC]
set input_spef [require_env T10_INPUT_SPEF]
set output_lib [require_env T10_OUTPUT_LIB]
set report_file [expr {
  [info exists ::env(T10_REPORT)] && $::env(T10_REPORT) ne "" ?
  $::env(T10_REPORT) : "${output_lib}.rpt"
}]
set thread_count [expr {
  [info exists ::env(T10_THREADS)] && $::env(T10_THREADS) ne "" ?
  $::env(T10_THREADS) : 4
}]

foreach input [concat $lib_files [list $input_odb $input_sdc $input_spef]] {
  if {![file isfile $input]} {
    error "missing input file $input"
  }
}
file mkdir [file dirname $output_lib]
file mkdir [file dirname $report_file]

set_thread_count $thread_count
define_corners $corner
foreach lib $lib_files {
  read_liberty -corner $corner $lib
}
read_db $input_odb
read_sdc $input_sdc
read_spef -corner $corner $input_spef
set_propagated_clock [all_clocks]

set report_id [open $report_file w]
puts $report_id "T10_MACRO_CORNER=$corner"
puts $report_id "T10_INPUT_ODB=$input_odb"
puts $report_id "T10_INPUT_SPEF=$input_spef"
close $report_id
report_worst_slack -max -digits 4 >> $report_file
report_worst_slack -min -digits 4 >> $report_file
report_checks -path_delay max -scenes $corner -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 10 >> $report_file
report_checks -path_delay min -scenes $corner -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 10 >> $report_file

# write_timing_model includes propagated clock latency. Remove source latency so
# the parent level does not count it twice.
set_clock_latency -source 0 [all_clocks]
write_timing_model -scene $corner $output_lib
puts "T10_MACRO_MODEL=$output_lib"
exit
