# Place the sixteen routed tile macros in logical systolic order. The 100 um
# channels carry only tile-boundary wavefront and top-shell control/result nets.
set block [ord::get_db_block]
set count 0
foreach inst [$block getInsts] {
    if {![[$inst getMaster] isBlock]} { continue }
    set name [$inst getName]
    regsub -all {\\} $name {} normalized
    if {![regexp {tile_row\[([0-3])\]\.tile_col\[([0-3])\]\.tile$} $normalized -> r c]} {
        error "Unexpected T10 top macro: $name"
    }
    set x [expr {100.0 + $c * 2600.0}]
    # Match the tile convention: b enters from the north, flows from logical
    # row 0 toward row 3, and exits at the south edge.
    set y [expr {100.0 + (3 - $r) * 2600.0}]
    place_macro -macro_name $name -location [list $x $y] -orientation R0
    puts "T10_FIXED_TILE_MACRO $name $x $y"
    incr count
}
if {$count != 16} { error "T10 top expected 16 tile macros, found $count" }
