set_thread_count 4
set platform /mnt/ubu_3T/ic_bcmk_orfs_asap7/flow/platforms/asap7
foreach lib [list \
  $platform/lib/NLDM/asap7sc7p5t_AO_RVT_SS_nldm_211120.lib.gz \
  $platform/lib/NLDM/asap7sc7p5t_INVBUF_RVT_SS_nldm_220122.lib.gz \
  $platform/lib/NLDM/asap7sc7p5t_OA_RVT_SS_nldm_211120.lib.gz \
  $platform/lib/NLDM/asap7sc7p5t_SEQ_RVT_SS_nldm_220123.lib \
  $platform/lib/NLDM/asap7sc7p5t_SIMPLE_RVT_SS_nldm_211120.lib.gz] {
  read_liberty $lib
}
read_db $::env(T10_INPUT_ODB)
read_sdc $::env(T10_INPUT_SDC)
source $platform/setRC.tcl
set_routing_layers -signal M2-M7 -clock M6-M7
set_wire_rc -clock -layer M7
set_global_routing_random -seed $::env(T10_ROUTE_SEED)
global_route -congestion_iterations 30 -verbose -resistance_aware
estimate_parasitics -global_routing
puts T10_CPA_REPAIRED_GRT_TIMING
report_worst_slack -max
report_worst_slack -min
report_tns -max

detailed_route -output_drc $::env(T10_DRC_REPORT) \
  -output_maze $::env(T10_MAZE_REPORT) \
  -or_seed $::env(T10_ROUTE_SEED) -droute_end_iter 64 \
  -verbose 1 -drc_report_iter_step 5
write_db $::env(T10_OUTPUT_ODB)
write_sdc -no_timestamp $::env(T10_OUTPUT_SDC)

define_process_corner -ext_model_index 0 X
extract_parasitics -ext_model_file $platform/rcx_patterns.rules
write_spef $::env(T10_OUTPUT_SPEF)
set_propagated_clock [all_clocks]
puts T10_CPA_REPAIRED_FINAL_TIMING
report_worst_slack -max
report_worst_slack -min
report_tns -max
report_tns -min
exit
