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
set_propagated_clock [all_clocks]
estimate_parasitics -placement

# The ORFS final database contains density fillers.  They are not functional
# cells and must be removed before resizer is allowed to create legal space.
remove_fillers

puts T10_CPA_SETUP_REPAIR_BEFORE
report_worst_slack -max
report_worst_slack -min
report_tns -max

set clock_cells [get_cells -quiet {clkbuf_* clk_* clock_*}]
set clock_nets [get_nets -quiet {clk clk_* clknet_* clock_*}]
set_dont_touch $clock_cells
set_dont_touch $clock_nets
puts "T10_CPA_PROTECTED_CLOCK cells=[llength $clock_cells] nets=[llength $clock_nets]"

set before_cells [llength [get_cells -hierarchical *]]
repair_timing -setup -setup_margin 80 -repair_tns 100 \
  -max_passes 10 -max_iterations 5000 -max_buffer_percent 2 \
  -max_utilization 60 -skip_last_gasp \
  -sequence {unbuffer sizeup swap buffer} -verbose
set after_cells [llength [get_cells -hierarchical *]]
puts "T10_CPA_SETUP_REPAIR_CELL_DELTA=[expr {$after_cells-$before_cells}]"

set_placement_padding -global -left 0 -right 0
detailed_placement -incremental -max_displacement {20 20}
check_placement -verbose
estimate_parasitics -placement
puts T10_CPA_SETUP_REPAIR_PLACED
report_worst_slack -max
report_worst_slack -min
report_tns -max

set block [ord::get_db_block]
set unrouted 0
foreach net [$block getNets] {
  if {[$net getSigType] ne "SIGNAL"} { continue }
  if {[$net getWire] ne "NULL"} { odb::dbWire_destroy [$net getWire] }
  $net clearGuides
  incr unrouted
}
puts "T10_CPA_UNROUTED_SIGNAL_NETS=$unrouted"
write_db $::env(T10_OUTPUT_ODB)
write_sdc -no_timestamp $::env(T10_OUTPUT_SDC)
exit
