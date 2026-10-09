(* blackbox *)
module fakeram7_tdp_4096x32 (
    input clk_A, ce_in_A, we_in_A,
    input [11:0] addr_in_A,
    input [31:0] wd_in_A, w_mask_in_A,
    output [31:0] rd_out_A,
    input clk_B, ce_in_B, we_in_B,
    input [11:0] addr_in_B,
    input [31:0] wd_in_B, w_mask_in_B,
    output [31:0] rd_out_B
);
endmodule
