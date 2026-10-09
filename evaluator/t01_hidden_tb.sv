`timescale 1ns/1ps

module t01_hidden_tb;
  logic clk;
  logic rst_n;
  logic rx_valid;
  logic [9:0] rx_bits;
  wire locked;
  wire symbol_valid;
  wire [9:0] symbol_out;
  logic [23:0] vectors [0:4095];
  string vector_path;
  int vector_count;

  serdes_rx_comma_aligner dut (
    .clk(clk), .rst_n(rst_n), .rx_valid(rx_valid), .rx_bits(rx_bits),
    .locked(locked), .symbol_valid(symbol_valid), .symbol_out(symbol_out)
  );

  initial begin
    clk = 1'b0;
    if ($test$plusargs("POWER_WORKLOAD"))
      forever #0.5 clk = ~clk;
    else
      forever #5 clk = ~clk;
  end

  initial begin
    rst_n = 1'b0;
    rx_valid = 1'b0;
    rx_bits = '0;
    if (!$value$plusargs("VECTORS=%s", vector_path))
      $fatal(1, "missing +VECTORS");
    if (!$value$plusargs("COUNT=%d", vector_count) || vector_count <= 0 || vector_count > 4096)
      $fatal(1, "invalid +COUNT");
    $readmemh(vector_path, vectors);
    for (int cycle = 0; cycle < vector_count; cycle++) begin
      @(negedge clk);
      rst_n = vectors[cycle][23];
      rx_valid = vectors[cycle][22];
      rx_bits = vectors[cycle][21:12];
      @(posedge clk);
      #0.1;
      if (locked !== vectors[cycle][11])
        $fatal(1, "locked mismatch cycle=%0d expected=%0b actual=%0b",
               cycle, vectors[cycle][11], locked);
      if (symbol_valid !== vectors[cycle][10])
        $fatal(1, "symbol_valid mismatch cycle=%0d expected=%0b actual=%0b",
               cycle, vectors[cycle][10], symbol_valid);
      if (vectors[cycle][10] && symbol_out !== vectors[cycle][9:0])
        $fatal(1, "symbol mismatch cycle=%0d expected=%03h actual=%03h",
               cycle, vectors[cycle][9:0], symbol_out);
    end
    $display("HIDDEN_PASS T01 cycles=%0d", vector_count);
    if ($test$plusargs("POWER_WORKLOAD")) begin
      $display("IC_GROUP AC-05 1 1");
      $display("IC_GROUP AC-06 1 1");
      $display("IC_GROUP AC-07 1 1");
      $display("IC_GROUP AC-08A 1 1");
      $display("IC_GROUP AC-08B 1 1");
    end
    $finish;
  end
endmodule
