`timescale 1ns/1ps
module tb_saif_window;
  logic clk = 1'b0;
  logic high_bit = 1'b1;
  logic low_bit = 1'b0;
  logic data_bit = 1'b1;
  always #0.5 clk = ~clk;
  initial begin
    #2.1;
    $dumpfile("window.saif");
    $dumpvars(0, tb_saif_window);
    #0.9 data_bit = 1'b0;
    #1.0 data_bit = 1'b1;
    #1.1;
    assert (clk == 1'b0 && high_bit && !low_bit && data_bit);
    $finish;
  end
endmodule
