# RePlAce's physical clusters are temporary density constraints. At DPL,
# fixed tile macros and their row cuts provide the physical obstacles. Drop
# the channel clusters for a probe to avoid group placement/refinement over
# the full-chip site map; retain every instance, connection and macro position.
if {[info exists ::env(T10_REFERENCE_RELEASE_GPL_REGIONS)] &&
    $::env(T10_REFERENCE_RELEASE_GPL_REGIONS) == 1} {
  set block [ord::get_db_block]
  set removed_groups 0
  set removed_regions 0
  foreach group [$block getGroups] {
    if {[string match "t10_top_channel_*" [$group getName]]} {
      odb::dbGroup_destroy $group
      incr removed_groups
    }
  }
  foreach region [$block getRegions] {
    if {[string match "t10_top_channel_*" [$region getName]]} {
      odb::dbRegion_destroy $region
      incr removed_regions
    }
  }
  puts "T10_TOP_DPL_RELEASE_GPL_REGIONS groups=$removed_groups regions=$removed_regions"
}

# The 10.5 mm ASAP7 parent has roughly 678 million legal sites after macro row
# cuts.  The shell uses under one percent of that free area.  Keep a regular
# subset of rows in every channel before detailed placement so OpenDP can
# materialize its site map within host memory while still legally placing all
# complete-DUT shell cells.
set stride $::env(T10_REFERENCE_DPL_ROW_STRIDE)
if {$stride < 1} { error "T10_REFERENCE_DPL_ROW_STRIDE must be positive" }
if {$stride > 1} {
  set block [ord::get_db_block]
  set y_values {}
  foreach row [$block getRows] { lappend y_values [lindex [$row getOrigin] 1] }
  set y_values [lsort -integer -unique $y_values]
  set keep_y [dict create]
  set y_index 0
  foreach y $y_values {
    if {$y_index % $stride == 0 || $y_index == [expr {[llength $y_values] - 1}]} {
      dict set keep_y $y 1
    }
    incr y_index
  }
  set kept 0
  set removed 0
  foreach row [$block getRows] {
    set y [lindex [$row getOrigin] 1]
    if {[dict exists $keep_y $y]} {
      incr kept
    } else {
      odb::dbRow_destroy $row
      incr removed
    }
  }
  puts "T10_TOP_DPL_SPARSE_ROWS stride=$stride kept=$kept removed=$removed unique_y_before=[llength $y_values]"
}
