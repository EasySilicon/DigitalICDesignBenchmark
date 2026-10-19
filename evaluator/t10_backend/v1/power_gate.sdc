current_design npu_systolic_matmul_16x16
create_clock -name clk_clock -period 1000 [get_ports clk]
set_input_delay 200 -clock clk_clock [all_inputs -no_clocks]
set_output_delay 200 -clock clk_clock [all_outputs]
set_false_path -from [get_ports rst_n]
