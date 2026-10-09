// Evaluator-owned technology mapping. No clock ORing, no generated clocks.
module $__T11_FAKERAM_4096X32_ (
    input PORT_W_CLK,
    input [11:0] PORT_W_ADDR,
    input [31:0] PORT_W_WR_DATA,
    input [31:0] PORT_W_WR_EN,
    input PORT_R_CLK,
    input [11:0] PORT_R_ADDR,
    output [31:0] PORT_R_RD_DATA
);
    fakeram7_tdp_4096x32 _TECHMAP_REPLACE_ (
        .clk_A(PORT_W_CLK), .ce_in_A(|PORT_W_WR_EN),
        .addr_in_A(PORT_W_ADDR), .we_in_A(1'b1),
        .wd_in_A(PORT_W_WR_DATA), .w_mask_in_A(PORT_W_WR_EN),
        .rd_out_A(),
        .clk_B(PORT_R_CLK), .ce_in_B(1'b1),
        .addr_in_B(PORT_R_ADDR), .we_in_B(1'b0),
        .wd_in_B(32'b0), .w_mask_in_B(32'b0),
        .rd_out_B(PORT_R_RD_DATA)
    );
endmodule
