# Run one bounded detailed-routing stage for the frozen T10 PE and write an
# explicit checkpoint.  The shell driver supplies every path and keeps a
# stage successful only when both the ODB and the status file are complete.
foreach name {
  T10_INPUT_ODB T10_OUTPUT_ODB T10_DRC_REPORT T10_MAZE_REPORT
  T10_ROUTE_STATUS T10_ROUTE_MODE T10_DRT_ITERATIONS T10_ROUTE_SEED
} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
}

set threads 4
if {[info exists ::env(T10_THREADS)] && $::env(T10_THREADS) ne ""} {
  set threads $::env(T10_THREADS)
}

read_db $::env(T10_INPUT_ODB)
set_thread_count $threads
set_routing_layers -signal M2-M7 -clock M6-M7

set args [list \
  -output_drc $::env(T10_DRC_REPORT) \
  -output_maze $::env(T10_MAZE_REPORT) \
  -or_seed $::env(T10_ROUTE_SEED) \
  -or_k 1 \
  -droute_end_iter $::env(T10_DRT_ITERATIONS) \
  -drc_report_iter_step 1 \
  -verbose 1]
if {$::env(T10_ROUTE_MODE) eq "repair"} {
  lappend args -no_pin_access
} elseif {$::env(T10_ROUTE_MODE) ne "initial"} {
  error "T10_ROUTE_MODE must be initial or repair"
}

puts "T10_PE_CHECKPOINT_BEGIN mode=$::env(T10_ROUTE_MODE) input=$::env(T10_INPUT_ODB) iterations=$::env(T10_DRT_ITERATIONS) seed=$::env(T10_ROUTE_SEED)"
detailed_route {*}$args
set drvs [detailed_route_num_drvs]
write_db $::env(T10_OUTPUT_ODB)

set stream [open $::env(T10_ROUTE_STATUS) w]
puts $stream "drvs=$drvs"
puts $stream "mode=$::env(T10_ROUTE_MODE)"
puts $stream "iterations=$::env(T10_DRT_ITERATIONS)"
puts $stream "seed=$::env(T10_ROUTE_SEED)"
close $stream
puts "T10_PE_CHECKPOINT_END output=$::env(T10_OUTPUT_ODB) drvs=$drvs"
exit
