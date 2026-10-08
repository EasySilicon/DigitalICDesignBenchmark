set_io_pin_constraint -pin_names {a_data* a_scale* in_valid in_start in_ready in_block_id* mode*} -region left:*
set_io_pin_constraint -pin_names {b_data* b_scale* clk rst_n} -region top:*
set_io_pin_constraint -pin_names {out_data*} -region bottom:*
set_io_pin_constraint -pin_names {out_valid* out_block_id* out_row* out_ready} -region right:*
