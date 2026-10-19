# Orient the PE's nearest-neighbor ports toward their mesh neighbors.
set_io_pin_constraint -pin_names {a_in* at_in*} -region left:*
set_io_pin_constraint -pin_names {a_out* at_out*} -region right:*
set_io_pin_constraint -pin_names {b_in* bt_in* clk rst_n} -region top:*
set_io_pin_constraint -pin_names {b_out* bt_out* result*} -region bottom:*
