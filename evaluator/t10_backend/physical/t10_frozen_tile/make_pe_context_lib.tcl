# Re-extract the routed PE timing model for its use inside the 4x4 tile.
#
# The PE forwarding outputs are intentionally unused in the tile-shell mesh;
# the shell owns the one-cycle A/B/token forwarding registers.  Excluding the
# corresponding PE register cones prevents those dead paths from dominating
# the PE input constraints while retaining all compute ingress paths, output
# arcs, and the routed internal clock-tree latency.  The synthesized names
# also select one reset tie cell per register; those cells are not timing
# endpoints, so including them in the false-path collection is inert.

proc require_env {name} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
  return $::env($name)
}

set lib_files [require_env T10_STD_LIBS]
set input_odb [require_env T10_PE_ODB]
set input_sdc [require_env T10_PE_SDC]
set input_spef [require_env T10_PE_SPEF]
set output_lib [require_env T10_PE_FILTERED_LIB]
set report_file [require_env T10_PE_CONTEXT_REPORT]

foreach path [concat $lib_files [list $input_odb $input_sdc $input_spef]] {
  if {![file isfile $path]} { error "missing PE context input $path" }
}
file mkdir [file dirname $output_lib]

foreach lib $lib_files { read_liberty $lib }
read_db $input_odb
read_sdc $input_sdc
read_spef $input_spef
set_propagated_clock [all_clocks]

set unused_forward_cone [get_cells -quiet -regexp \
  {^(a_out_n|b_out_n|at_out_payload|bt_out_payload|at_out_valid_n|bt_out_valid_n).*DFF.*}]
if {[llength $unused_forward_cone] != 368} {
  error "expected 368 cells in the unused PE forwarding cone, found [llength $unused_forward_cone]"
}
set_false_path -to $unused_forward_cone

sta::redirect_file_begin $report_file
puts "T10_PE_CONTEXT_EXCLUDED_FORWARD_CONE_CELLS=[llength $unused_forward_cone]"
report_worst_slack -max -digits 6
report_tns -max -digits 6
report_checks \
  -from [get_ports {a_in[*] at_in[*] b_in[*] bt_in[*]}] \
  -path_delay max -format full_clock_expanded \
  -fields {slew capacitance input_pin net fanout} -digits 4 \
  -group_path_count 100
sta::redirect_file_end

# A parent level supplies its own source latency.  Keep the PE's routed clock
# network in the timing model and clear only the external source component.
set_clock_latency -source 0 [all_clocks]
write_timing_model $output_lib
puts "T10_PE_CONTEXT_LIB=$output_lib"
exit
