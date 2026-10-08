current_design t10_reference_tile_4x4
create_clock -name clk_clock -period 1000 [get_ports clk]
create_clock -name vclk_in -period 1000
create_clock -name vclk_out -period 1000
# The routed tile clock insertion is about 2.9 ns.  The ideal network latency
# guides pre-CTS optimization and is replaced by propagated delay after CTS.
# Both virtual clocks model the same parent clock tree at the tile boundaries.
set_clock_latency 2900 [get_clocks clk_clock]
set_clock_latency -source 2900 [get_clocks vclk_in]
set_clock_latency -source 2900 [get_clocks vclk_out]
set_input_delay 200 -clock vclk_in [all_inputs -no_clocks]
set_output_delay 200 -clock vclk_out [all_outputs]
# row_read_slot changes only after the two-cycle row-consumed pipeline in the
# full DUT.  The distributed tile banks therefore have two cycles to capture
# the next selector; state the protocol budget explicitly at this hierarchy.
set_multicycle_path 2 -setup -from [get_ports {read_slot[*]}]
set_multicycle_path 1 -hold -from [get_ports {read_slot[*]}]
set_false_path -from [get_ports rst_n]
