# Macro footprint and standard-cell area are different quantities.
set block [ord::get_db_block]
set dbu [$block getDbUnitsPerMicron]
set rect [$block getDieArea]
source [file join [file dirname [info script]] cell_area.tcl]
set children {}
if {[info exists ::env(T10_CHILD_MASTERS)]} {set children $::env(T10_CHILD_MASTERS)}
set areas [t10_cell_area $block $children]
foreach inst [$block getInsts] {
    if {[[$inst getMaster] isBlock]} {
        puts "T10_CHILD_INSTANCE [$inst getName] [[$inst getMaster] getName]"
    }
}
set stream [open $::env(T10_GEOMETRY) w]
puts $stream [format {{"width_um":%.12g,"height_um":%.12g,"cell_area_um2":%.12g,"filler_area_um2":%.12g,"internal_macro_area_um2":%.12g}} \
    [expr {double([$rect dx])/$dbu}] [expr {double([$rect dy])/$dbu}] \
    [dict get $areas area_um2] [dict get $areas filler_area_um2] [dict get $areas macro_area_um2]]
close $stream
