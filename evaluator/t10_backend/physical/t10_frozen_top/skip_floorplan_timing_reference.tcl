# Hierarchical reference probe only.
#
# ORFS normally performs setup repair immediately after floorplan creation,
# before placement parasitics exist.  The conservative routed-tile Liberty
# model makes that pass revisit the same macro read_slot boundary thousands of
# times without changing its slack.  Placement and the controlled top-shell
# trees provide the useful timing evidence for this hierarchical reference.
rename repair_timing_helper t10_orfs_floorplan_repair_timing_helper
proc repair_timing_helper {args} {
  puts "T10_TOP_REFERENCE_SKIP_FLOORPLAN_TIMING reason=unplaced_macro_boundary_model"
}
