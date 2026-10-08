# T10 24%-utilization hierarchical single-PE experiment.
# Source from ORFS PRE_GLOBAL_PLACE_TCL after placing the nine child macros
# with physical/t10_pe_u24_macro_place.tcl. The L-shaped soft blockages
# clear standard cells from the measured CPA and class-2 FP macro pin escapes.
create_blockage -soft -region {195 208.2 230 225}
create_blockage -soft -region {195 190 210 208.2}
create_blockage -soft -region {350 195 390 210}
create_blockage -soft -region {350 210 365 225}
