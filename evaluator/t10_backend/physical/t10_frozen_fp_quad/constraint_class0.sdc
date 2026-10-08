current_design t10_reference_fp_quad_class0_exact
create_clock -name clk_clock -period 1000 [get_ports clk]
create_clock -name vclk -period 1000
set_input_delay 200 -clock vclk [all_inputs -no_clocks]
set_output_delay 200 -clock vclk [all_outputs]
