# Project every non-macro instance in the complete 16x16 DUT into one of 25
# non-overlapping channel rectangles. A dbRegion containing many rectangles is
# treated by RePlAce as its outer bounding box, so each channel segment must be
# a separate physical cluster. The first unconstrained placement supplies
# connectivity-aware coordinates; nearest-channel projection preserves that
# locality while making macro overlap impossible in the following placement.
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]

set x_channels {
  {0.54 99.90}
  {2600.10 2699.90}
  {5200.10 5299.90}
  {7800.10 7899.90}
  {10400.10 10499.46}
}
set y_channels {
  {0.54 99.90}
  {2600.10 2699.90}
  {5200.10 5299.90}
  {7800.10 7899.90}
  {10400.10 10499.46}
}
set macro_x_ranges {
  {100.10 2599.90}
  {2700.10 5199.90}
  {5300.10 7799.90}
  {7900.10 10399.90}
}

# Five full-height vertical channels own the intersections. The twenty
# horizontal segments cover only the four macro-column spans, so no two
# regions overlap and their total area tracks the true free channel area.
set rects {}
set names {}
set index 0
foreach xr $x_channels {
  lassign $xr x0 x1
  lappend names [format "t10_top_channel_%02d" $index]
  lappend rects [list $x0 0.54 $x1 10499.46]
  incr index
}
foreach yr $y_channels {
  lassign $yr y0 y1
  foreach xr $macro_x_ranges {
    lassign $xr x0 x1
    lappend names [format "t10_top_channel_%02d" $index]
    lappend rects [list $x0 $y0 $x1 $y1]
    incr index
  }
}
if {[llength $rects] != 25} { error "T10 expected 25 channel rectangles" }

# This hook is sourced again after targeted buffer insertion. Rebuild the
# saved clusters so newly created cells are covered as well.
foreach name $names {
  set old_group [$block findGroup $name]
  if {$old_group ne "NULL"} { odb::dbGroup_destroy $old_group }
  set old_region [$block findRegion $name]
  if {$old_region ne "NULL"} { odb::dbRegion_destroy $old_region }
}

set bounds {}
for {set i 0} {$i < [llength $rects]} {incr i} {
  lassign [lindex $rects $i] x0 y0 x1 y1
  set ix0 [expr {round($x0 * $dbu)}]
  set iy0 [expr {round($y0 * $dbu)}]
  set ix1 [expr {round($x1 * $dbu)}]
  set iy1 [expr {round($y1 * $dbu)}]
  lappend bounds [list $ix0 $iy0 $ix1 $iy1]
}

set counts [lrepeat 25 0]
set members [lrepeat 25 {}]
set shell_count 0
set macro_count 0
foreach inst [$block getInsts] {
  if {[[$inst getMaster] isBlock]} {
    incr macro_count
    continue
  }
  set bbox [$inst getBBox]
  set cx [expr {([$bbox xMin] + [$bbox xMax]) / 2}]
  set cy [expr {([$bbox yMin] + [$bbox yMax]) / 2}]
  set best_index -1
  set best_distance -1
  for {set i 0} {$i < 25} {incr i} {
    lassign [lindex $bounds $i] x0 y0 x1 y1
    set dx 0
    set dy 0
    if {$cx < $x0} { set dx [expr {$x0 - $cx}] }
    if {$cx > $x1} { set dx [expr {$cx - $x1}] }
    if {$cy < $y0} { set dy [expr {$y0 - $cy}] }
    if {$cy > $y1} { set dy [expr {$cy - $y1}] }
    set distance [expr {$dx * $dx + $dy * $dy}]
    if {$best_index < 0 || $distance < $best_distance} {
      set best_index $i
      set best_distance $distance
    }
  }
  set channel_members [lindex $members $best_index]
  lappend channel_members $inst
  lset members $best_index $channel_members
  lset counts $best_index [expr {[lindex $counts $best_index] + 1}]
  incr shell_count
}
if {$macro_count != 16} {
  error "T10 full top expected 16 tile macros, found $macro_count"
}
set active_regions 0
for {set i 0} {$i < 25} {incr i} {
  set count [lindex $counts $i]
  if {$count == 0} {
    puts "T10_TOP_CHANNEL_REGION_SKIP index=$i instances=0 rect=[lindex $rects $i]"
    continue
  }
  set name [lindex $names $i]
  lassign [lindex $bounds $i] ix0 iy0 ix1 iy1
  set region [odb::dbRegion_create $block $name]
  odb::dbRegion_setRegionType $region INCLUSIVE
  odb::dbBox_create $region $ix0 $iy0 $ix1 $iy1
  set group [odb::dbGroup_create $block $name]
  odb::dbGroup_setType $group PHYSICAL_CLUSTER
  odb::dbRegion_addGroup $region $group
  foreach inst [lindex $members $i] { odb::dbGroup_addInst $group $inst }
  incr active_regions
  puts "T10_TOP_CHANNEL_REGION index=$i instances=$count rect=[lindex $rects $i]"
}
puts "T10_TOP_CHANNEL_REGION_SUMMARY active_regions=$active_regions candidate_regions=25 shell_instances=$shell_count macros=$macro_count"
