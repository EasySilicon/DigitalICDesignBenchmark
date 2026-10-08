# Move the two 64-bit operand buses away from the measured lower-left pin escape hotspot.
set a_pins {}
set b_pins {}
for {set i 0} {$i < 64} {incr i} {
    lappend a_pins "a_raw\[$i\]"
    lappend b_pins "b_raw\[$i\]"
}
set_io_pin_constraint -pin_names $a_pins -region left:15-70
set_io_pin_constraint -pin_names $b_pins -region bottom:15-70
