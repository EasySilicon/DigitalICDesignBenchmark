# A regular 4x4 PE macro mesh with about 100 um channels. The placement follows
# the logical systolic row/column order so every internal wavefront hop is local.
set block [ord::get_db_block]
set count 0
foreach inst [$block getInsts] {
    if {![[$inst getMaster] isBlock]} { continue }
    set name [$inst getName]
    regsub -all {\\} $name {} normalized
    if {![regexp {pe_row\[([0-3])\]\.pe_col\[([0-3])\]\.pe$} $normalized -> r c]} {
        error "Unexpected T10 tile macro: $name"
    }
    set x [expr {113.0 + $c * 593.5}]
    # b_in is on the north edge and b_out is on the south edge.  Put logical
    # row 0 at the north and row 3 at the south so boundary traffic reaches
    # the nearest PE instead of crossing the full 2.25 mm tile.
    set y [expr {113.0 + (3 - $r) * 593.5}]
    place_macro -macro_name $name -location [list $x $y] -orientation R0
    puts "T10_FIXED_PE_MACRO $name $x $y"
    incr count
}
if {$count != 16} { error "T10 tile expected 16 PE macros, found $count" }
