`timescale 1ns/1ps

module tb_T02;
  localparam logic [9:0] COMMA_P = 10'b0011111010;
  localparam logic [9:0] COMMA_N = 10'b1100000101;
  logic clk, rst_n, rx_valid;
  logic [9:0] rx_bits;
  wire locked, symbol_valid;
  wire [9:0] symbol_out;
  logic serial_bits [0:2047];
  logic [9:0] expected [0:127];
  int bit_count, expected_count, expected_index;
  int seed;

  serdes_rx_comma_aligner dut (
    .clk(clk), .rst_n(rst_n), .rx_valid(rx_valid), .rx_bits(rx_bits),
    .locked(locked), .symbol_valid(symbol_valid), .symbol_out(symbol_out)
  );

  task automatic append_symbol(input logic [9:0] symbol, input logic expect_output);
    begin
      for (int i = 0; i < 10; i++) serial_bits[bit_count + i] = symbol[i];
      bit_count += 10;
      if (expect_output) begin
        expected[expected_count] = symbol;
        expected_count++;
      end
    end
  endtask

  task automatic append_training(input logic polarity);
    logic [9:0] comma;
    begin
      comma = polarity ? COMMA_N : COMMA_P;
      append_symbol(comma, 1'b0);
      append_symbol(comma, 1'b0);
      append_symbol(comma, 1'b0);
    end
  endtask

  task automatic append_frame(input int frame);
    logic [9:0] payload;
    begin
      for (int i = 0; i < 15; i++) begin
        payload = 10'(frame * 73 + i * 29 + 341 + seed);
        if (payload == COMMA_P || payload == COMMA_N) payload = payload ^ 10'h201;
        append_symbol(payload, 1'b1);
      end
      append_symbol(((frame & 1) != 0) ? COMMA_N : COMMA_P, 1'b1);
    end
  endtask

  initial begin
    clk = 0;
    forever #5 clk = ~clk;
  end

  task automatic drive_stream;
    logic [9:0] chunk;
    begin
      for (int start = 0; start + 9 < bit_count; start += 10) begin
        chunk = '0;
        for (int i = 0; i < 10; i++) chunk[i] = serial_bits[start + i];
        @(negedge clk);
        rx_bits = chunk;
        rx_valid = 1'b1;
        @(posedge clk); #1;
        if (symbol_valid) begin
          if (!locked || expected_index >= expected_count ||
              symbol_out !== expected[expected_index])
            $fatal(1, "T02 output mismatch index=%0d expected=%03h actual=%03h locked=%0b",
                   expected_index, expected[expected_index], symbol_out, locked);
          expected_index++;
        end
      end
      @(negedge clk);
      rx_valid = 1'b0;
    end
  endtask

  initial begin
    if ($bits(dut.rx_bits) != 10 || $bits(dut.symbol_out) != 10)
      $fatal(1, "T02 fixed port width mismatch");
    seed = 20260927;
    void'($value$plusargs("SEED=%d", seed));
    rx_valid = 0; rx_bits = 0; rst_n = 0;
    bit_count = 0; expected_count = 0; expected_index = 0;
    for (int i = 0; i < 3; i++) begin
      serial_bits[bit_count] = (i == 1);
      bit_count++;
    end
    append_training(1'b0);
    append_frame(0); append_frame(1); append_frame(2);
    for (int i = 0; i < 7; i++) begin
      serial_bits[bit_count] = 1'b0;
      bit_count++;
    end
    repeat (2) @(posedge clk);
    @(negedge clk); rst_n = 1;
    for (int i = 0; i < 3; i++) begin
      rx_valid = 1'b1;
      rx_bits = COMMA_P;
      @(posedge clk); #1;
      if (locked !== (i == 2) || symbol_valid)
        $fatal(1, "T02 slice-aligned training timing mismatch comma=%0d locked=%0b valid=%0b",
               i + 1, locked, symbol_valid);
      @(negedge clk);
    end
    rx_bits = 10'h155;
    @(posedge clk); #1;
    if (!locked || !symbol_valid || symbol_out !== 10'h155)
      $fatal(1, "T02 first post-training symbol mismatch locked=%0b valid=%0b symbol=%03h",
             locked, symbol_valid, symbol_out);
    @(negedge clk); rst_n = 0; rx_valid = 0;
    #1;
    if (locked || symbol_valid)
      $fatal(1, "T02 asynchronous reset did not clear outputs");
    repeat (2) @(posedge clk);
    @(negedge clk); rst_n = 1;
    drive_stream();
    repeat (4) @(posedge clk);
    if (expected_index != expected_count)
      $fatal(1, "T02 did not emit all aligned symbols got=%0d expected=%0d", expected_index, expected_count);
    $display("PUBLIC_PASS T02 symbols=%0d", expected_count);
    $finish;
  end
endmodule
