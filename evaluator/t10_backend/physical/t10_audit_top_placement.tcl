# Audit whether the full 16x16 hierarchical top has physically legal shell
# placement.  This script intentionally needs only an ODB; it does not run
# timing or modify the database.
if {![info exists ::env(T10_AUDIT_ODB)] || $::env(T10_AUDIT_ODB) eq {}} {
  puts stderr "T10_AUDIT_ODB must name the full-top ODB"
  exit 2
}
read_db $::env(T10_AUDIT_ODB)
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set macros {}
set status_counts [dict create]
foreach inst [$block getInsts] {
  set status [$inst getPlacementStatus]
  dict incr status_counts $status
  if {[[$inst getMaster] isBlock]} {
    lappend macros $inst
  }
}
puts "T10_TOP_AUDIT instances=[llength [$block getInsts]] macros=[llength $macros] rows=[llength [$block getRows]] status=$status_counts"
set overlap_count 0
set movable_count 0
set examples 0
foreach inst [$block getInsts] {
  if {[[$inst getMaster] isBlock]} { continue }
  if {[$inst isFixed]} { continue }
  incr movable_count
  set ibox [$inst getBBox]
  set ix0 [$ibox xMin]
  set iy0 [$ibox yMin]
  set ix1 [$ibox xMax]
  set iy1 [$ibox yMax]
  foreach macro $macros {
    set mbox [$macro getBBox]
    if {$ix0 < [$mbox xMax] && $ix1 > [$mbox xMin] &&
        $iy0 < [$mbox yMax] && $iy1 > [$mbox yMin]} {
      incr overlap_count
      if {$examples < 12} {
        puts "T10_TOP_OVERLAP inst=[$inst getName] status=[$inst getPlacementStatus] xy_um=[expr {$ix0/double($dbu)}],[expr {$iy0/double($dbu)}] macro=[$macro getName]"
        incr examples
      }
      break
    }
  }
}
puts "T10_TOP_AUDIT_RESULT movable=$movable_count macro_overlaps=$overlap_count"
if {[info exists ::env(T10_AUDIT_CELL_BOXES)] && $::env(T10_AUDIT_CELL_BOXES) ne {}} {
  set fp [open $::env(T10_AUDIT_CELL_BOXES) w]
  foreach inst [$block getInsts] {
    if {[[$inst getMaster] isBlock]} { continue }
    set box [$inst getBBox]
    puts $fp "[$inst getName]\t[$box xMin]\t[$box yMin]\t[$box xMax]\t[$box yMax]"
  }
  close $fp
}
if {$overlap_count != 0} { exit 3 }
