current_design t10_reference_pe
create_clock -name clk_clock -period 1000 [get_ports clk]
create_clock -name vclk_in -period 1000
create_clock -name vclk_out -period 1000
# The PE is a synchronous hard macro inside a tile.  Model the common parent
# clock-tree insertion on its virtual boundary clock so that parent-level
# latency cancels instead of appearing as false input-hold/output-setup loss.
set_clock_latency -source 600 [get_clocks vclk_out]
set_input_delay 200 -clock vclk_in [all_inputs -no_clocks]
set_output_delay 200 -clock vclk_out [all_outputs]
set_false_path -from [get_ports rst_n]
