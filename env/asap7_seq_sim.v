`timescale 1ps/1ps
// Functional models for the sequential ASAP7 RVT cells observed in the
// locked ORFS mappings. Liberty remains the source of timing and power data;
// these models supply values for zero-delay gate-level activity simulation.
module DFFHQx4_ASAP7_75t_R(output reg Q, input D, CLK);
  always @(posedge CLK) Q <= D;
endmodule

module DFFASRHQNx1_ASAP7_75t_R(output reg QN,
                                input D, RESETN, SETN, CLK);
  always @(posedge CLK or negedge RESETN or negedge SETN) begin
    if (!RESETN) QN <= 1'b1;
    else if (!SETN) QN <= 1'b0;
    else QN <= ~D;
  end
endmodule
