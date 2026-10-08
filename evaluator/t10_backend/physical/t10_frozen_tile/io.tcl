# Align each wavefront lane with the PE row or column that consumes it. This
# prevents a legal but pathological pin assignment from crossing the tile.
set row_regions {{113-606} {706-1200} {1300-1793} {1893-2387}}
set col_regions {{113-606} {706-1200} {1300-1793} {1893-2387}}
for {set row 0} {$row < 4} {incr row} {
    # Logical row zero is physically north, hence the reversed edge segment.
    set region [lindex $row_regions [expr {3 - $row}]]
    set in_pins {}
    set out_pins {}
    for {set bit 0} {$bit < 64} {incr bit} {
        lappend in_pins [format {a_in_data[%d]} [expr {$row * 64 + $bit}]]
        lappend out_pins [format {a_out_data[%d]} [expr {$row * 64 + $bit}]]
    }
    for {set bit 0} {$bit < 28} {incr bit} {
        lappend in_pins [format {a_in_token[%d]} [expr {$row * 28 + $bit}]]
        lappend out_pins [format {a_out_token[%d]} [expr {$row * 28 + $bit}]]
    }
    lappend in_pins [format {read_slot[%d]} [expr {$row * 4}]]
    lappend in_pins [format {read_slot[%d]} [expr {$row * 4 + 1}]]
    lappend in_pins [format {read_slot[%d]} [expr {$row * 4 + 2}]]
    lappend in_pins [format {read_slot[%d]} [expr {$row * 4 + 3}]]
    lappend out_pins [format {boundary_done[%d]} $row]
    for {set bit 0} {$bit < 4} {incr bit} {
        lappend out_pins [format {boundary_slot[%d]} [expr {$row * 4 + $bit}]]
    }
    set_io_pin_constraint -pin_names $in_pins -region left:$region
    set_io_pin_constraint -pin_names $out_pins -region right:$region
}
for {set col 0} {$col < 4} {incr col} {
    set region [lindex $col_regions $col]
    set in_pins {}
    set out_pins {}
    for {set bit 0} {$bit < 64} {incr bit} {
        lappend in_pins [format {b_in_data[%d]} [expr {$col * 64 + $bit}]]
        lappend out_pins [format {b_out_data[%d]} [expr {$col * 64 + $bit}]]
    }
    for {set bit 0} {$bit < 28} {incr bit} {
        lappend in_pins [format {b_in_token[%d]} [expr {$col * 28 + $bit}]]
        lappend out_pins [format {b_out_token[%d]} [expr {$col * 28 + $bit}]]
    }
    set_io_pin_constraint -pin_names $in_pins -region top:$region
    set_io_pin_constraint -pin_names $out_pins -region bottom:$region
}
set_io_pin_constraint -pin_names {clk rst_n} -region top:2387-2499

# Each 256-bit row is four 64-bit cell outputs. Put the two western columns
# on the left edge and the two eastern columns on the right edge so no result
# bus crosses the full tile merely to reach a hierarchical pin.
set read_data_left {}
set read_data_right {}
for {set row 0} {$row < 4} {incr row} {
    for {set col 0} {$col < 4} {incr col} {
        for {set bit 0} {$bit < 64} {incr bit} {
            set index [expr {$row * 256 + $col * 64 + $bit}]
            set pin [format {read_data[%d]} $index]
            if {$col < 2} {
                lappend read_data_left $pin
            } else {
                lappend read_data_right $pin
            }
        }
    }
}
set_io_pin_constraint -pin_names $read_data_left -region left:*
set_io_pin_constraint -pin_names $read_data_right -region right:*
