# Resume the near-clean M6/M7 T10 PE route and always save the best committed
# database for a focused follow-up.  Environment variables keep the run bound
# to an explicit input/output pair instead of silently reusing stale files.
foreach name {T10_INPUT_ODB T10_OUTPUT_ODB T10_DRC_REPORT T10_MAZE_REPORT} {
  if {![info exists ::env($name)] || $::env($name) eq ""} {
    error "missing required environment variable $name"
  }
}

set threads 2
if {[info exists ::env(T10_THREADS)]} {
  set threads $::env(T10_THREADS)
}
set iterations 22
if {[info exists ::env(T10_DRT_ITERATIONS)]} {
  set iterations $::env(T10_DRT_ITERATIONS)
}
set route_seed 31
if {[info exists ::env(T10_ROUTE_SEED)]} {
  set route_seed $::env(T10_ROUTE_SEED)
}

read_db $::env(T10_INPUT_ODB)
set_thread_count $threads
set_routing_layers -signal M2-M7 -clock M6-M7

puts "T10_PE_ROUTE_RESUME_BEGIN input=$::env(T10_INPUT_ODB) iterations=$iterations seed=$route_seed"
detailed_route \
  -output_drc $::env(T10_DRC_REPORT) \
  -output_maze $::env(T10_MAZE_REPORT) \
  -or_seed $route_seed \
  -or_k 1 \
  -droute_end_iter $iterations \
  -no_pin_access \
  -verbose 1

set drvs [detailed_route_num_drvs]
puts "T10_PE_ROUTE_RESUME_RESULT drvs=$drvs"
write_db $::env(T10_OUTPUT_ODB)
puts "T10_PE_ROUTE_RESUME_END output=$::env(T10_OUTPUT_ODB)"
exit
