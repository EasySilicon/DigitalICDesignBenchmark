# Extract the edited geometry using the same fixed WC models and RC rules.
set_thread_count 4
foreach lib $::env(T10_LIBRARY_LIST) { read_liberty $lib }
read_db $::env(T10_INPUT_ODB)
read_sdc $::env(T10_INPUT_SDC)
source $::env(T10_PLATFORM)/setRC.tcl
source $::env(T10_ORFS_FLOW)/scripts/deleteRoutingObstructions.tcl
deleteRoutingObstructions
define_process_corner -ext_model_index 0 X
extract_parasitics -ext_model_file $::env(T10_PLATFORM)/rcx_patterns.rules
write_spef $::env(T10_OUTPUT_SPEF)
read_spef $::env(T10_OUTPUT_SPEF)
set_propagated_clock [all_clocks]
report_worst_slack -max -digits 6 > $::env(T10_MANUAL_DIR)/setup.rpt
report_worst_slack -min -digits 6 > $::env(T10_MANUAL_DIR)/hold.rpt
report_tns -max -digits 6 > $::env(T10_MANUAL_DIR)/setup_tns.rpt
report_tns -min -digits 6 > $::env(T10_MANUAL_DIR)/hold_tns.rpt
puts T10_MANUAL_EXTRACTION_COMPLETE
exit
