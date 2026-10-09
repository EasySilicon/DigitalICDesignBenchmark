`timescale 1ns/1ps

module tb_T04 #(
  parameter int N = 4,
  parameter int WIDTH = 8
);
  logic clk, rst_n;
  logic [N-1:0] in_valid, in_ready;
  logic [N-1:0][WIDTH-1:0] in_data;
  logic out_valid, out_ready;
  logic [WIDTH-1:0] out_data;
  logic [$clog2(N)-1:0] out_id;
  int pointer, expected_id, seed;
  int unsigned rng;
  int seq [0:N-1];
  logic [N-1:0] expected_ready;
  bit found;

  round_robin_stream_arbiter #(.N(N), .WIDTH(WIDTH)) dut (
    .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_ready(in_ready),
    .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready),
    .out_data(out_data), .out_id(out_id)
  );

  task automatic tick(input logic [N-1:0] requests, input bit downstream_ready);
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    in_valid = requests;
    out_ready = downstream_ready;
    for (int i = 0; i < N; i++)
      in_data[i] = WIDTH'(seq[i] * 31 + i);
    #2;
    expected_id = 0;
    found = 0;
    for (int distance = 0; distance < N; distance++) begin
      int candidate;
      candidate = (pointer + distance) % N;
      if (!found && requests[candidate]) begin
        expected_id = candidate;
        found = 1;
      end
    end
    if (out_valid !== found)
      $fatal(1, "AC-21 out_valid requests=%h expected=%0b actual=%0b",
             requests, found, out_valid);
    expected_ready = '0;
    if (found) begin
      if (out_id !== $clog2(N)'(expected_id))
        $fatal(1, "AC-21/22 expected id=%0d actual=%0d", expected_id, out_id);
      if (out_data !== in_data[expected_id])
        $fatal(1, "AC-23 id=%0d expected data=%h actual=%h",
               expected_id, in_data[expected_id], out_data);
      if (downstream_ready) expected_ready[expected_id] = 1;
    end
    if (in_ready !== expected_ready)
      $fatal(1, "AC-23 in_ready expected=%h actual=%h", expected_ready, in_ready);
    clk = 1;
    #2;
    if (found && downstream_ready) begin
      seq[expected_id]++;
      pointer = (expected_id + 1) % N;
    end
    clk = 0;
    #2;
  endtask

  initial begin
    if ($bits(dut.in_valid) != N || $bits(dut.in_ready) != N ||
        $bits(dut.in_data) != N * WIDTH || $bits(dut.out_data) != WIDTH ||
        $bits(dut.out_id) != $clog2(N))
      $fatal(1, "T04 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ 32'hbb67ae85;
    clk = 0;
    rst_n = 0;
    in_valid = '0;
    out_ready = 0;
    in_data = '0;
    pointer = 0;
    for (int i = 0; i < N; i++) seq[i] = 1;
    #2;
    clk = 1;
    #2;
    clk = 0;
    #2;
    rst_n = 1;
    #2;
    tick('0, 1);
    tick(N'(1 << 2), 1);
    // All sources stay valid. A source changes payload only after its own
    // handshake; backpressure leaves the selected payload unchanged.
    for (int cycle = 0; cycle < 256; cycle++) begin
      rng ^= rng << 13;
      rng ^= rng >> 17;
      rng ^= rng << 5;
      tick('1, (cycle < 16) ? 1'b0 : rng[0]);
    end
    for (int cycle = 0; cycle < N * 4; cycle++) tick('1, 1);
    $display("PUBLIC_PASS T04 N=%0d WIDTH=%0d seed=%0d", N, WIDTH, seed);
    $finish;
  end
endmodule
