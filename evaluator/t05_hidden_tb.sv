`timescale 1ns/1ps
module tb_hidden_T05 #(
  parameter int N = 4,
  parameter int WIDTH = 8
);
  logic clk, rst_n;
  logic [N-1:0] in_valid, in_ready;
  logic [N-1:0][WIDTH-1:0] in_data;
  logic out_valid, out_ready;
  logic [WIDTH-1:0] out_data;
  logic [$clog2(N)-1:0] out_id;
  logic [N-1:0] pending_mask;
  logic [WIDTH-1:0] held_data;
  int held_id, pointer, seq [0:N-1], served [0:N-1];
  bit holding;
  int passed [21:25], total [21:25];
  bit first_failure [21:25];
  int unsigned rng;
  int seed;

  round_robin_stream_arbiter #(.N(N), .WIDTH(WIDTH)) dut (
    .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_ready(in_ready),
    .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready),
    .out_data(out_data), .out_id(out_id)
  );

  task automatic check(input int id, input bit okay, input string what);
    total[id]++;
    if (okay) passed[id]++;
    else if (!first_failure[id]) begin
      first_failure[id] = 1;
      $display("IC_FAILURE AC-%02d N=%0d WIDTH=%0d %s", id, N, WIDTH, what);
    end
  endtask

  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction

  task automatic reset_arbiter;
    clk = 0;
    rst_n = 0;
    in_valid = '0;
    in_data = '0;
    out_ready = 0;
    pending_mask = '0;
    pointer = 0;
    holding = 0;
    for (int i=0; i<N; i++) begin
      seq[i] = 1;
      served[i] = 0;
    end
    #0.4;
    clk = 1;
    #0.4;
    clk = 0;
    #0.4;
    rst_n = 1;
    #0.4;
  endtask

  task automatic step(input logic [N-1:0] requests, input bit sink_ready);
    bit found;
    bit observed_handshake;
    int expected_id;
    int observed_id;
    logic [N-1:0] expected_ready;
    logic [WIDTH-1:0] expected_data;
    clk = 0;
    in_valid = requests | pending_mask;
    out_ready = sink_ready;
    for (int i=0; i<N; i++)
      in_data[i] = WIDTH'(seq[i]*32'h01010101 ^ (i*32'hb7522fa9));
    #0.4;
    found = holding;
    expected_id = holding ? held_id : 0;
    if (!holding) begin
      for (int distance=0; distance<N; distance++) begin
        int candidate;
        candidate = (pointer + distance) % N;
        if (!found && in_valid[candidate]) begin
          found = 1;
          expected_id = candidate;
        end
      end
    end
    expected_data = holding ? held_data : in_data[expected_id];
    check(21, out_valid === found && (!found || out_id === $clog2(N)'(expected_id)),
          $sformatf("selection expected_valid=%b expected_id=%0d actual_valid=%b actual_id=%0d",
                    found, expected_id, out_valid, out_id));
    if (found) begin
      check(22, out_id === $clog2(N)'(expected_id),
            $sformatf("rotation expected_id=%0d actual_id=%0d", expected_id, out_id));
      check(23, out_data === expected_data,
            $sformatf("data expected=%h actual=%h", expected_data, out_data));
    end else check(22, out_valid === 0, "spurious arbitration output");
    expected_ready = '0;
    if (found && sink_ready) expected_ready[expected_id] = 1;
    check(23, in_ready === expected_ready,
          $sformatf("in_ready expected=%h actual=%h", expected_ready, in_ready));
    if (holding)
      check(24, out_valid === 1'b1 && out_id === $clog2(N)'(held_id) &&
                out_data === held_data, "blocked output changed");
    observed_handshake = out_valid && sink_ready;
    observed_id = int'(out_id);
    // A source whose actual handshake did not occur must retain valid and data.
    pending_mask = in_valid & ~in_ready;
    clk = 1;
    #0.4;
    for (int i=0; i<N; i++)
      if (in_valid[i] && in_ready[i]) seq[i]++;
    if (observed_handshake && observed_id < N) served[observed_id]++;
    if (found && sink_ready) begin
      pointer = (expected_id+1) % N;
      holding = 0;
    end else if (found && !holding) begin
      holding = 1;
      held_id = expected_id;
      held_data = expected_data;
    end
    clk = 0;
    #0.2;
  endtask

  initial begin
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ (N*32'h9e3779b9) ^ WIDTH;
    for (int i=21; i<=25; i++) begin
      passed[i] = 0;
      total[i] = 0;
      first_failure[i] = 0;
    end
    check(21, $bits(dut.in_valid)==N && $bits(dut.in_ready)==N &&
              $bits(dut.in_data)==N*WIDTH && $bits(dut.out_data)==WIDTH &&
              $bits(dut.out_id)==$clog2(N), "fixed interface width");
    // All request masks, each starting from the reset search pointer.
    for (int mask=0; mask<(1<<N); mask++) begin
      reset_arbiter();
      step(N'(mask), 1);
    end
    reset_arbiter();
    step(N'(1<<2), 0);
    for (int i=0; i<30; i++) begin
      rng = next_random(rng);
      step(N'(rng), 0);
    end
    step('1, 1);
    reset_arbiter();
    for (int round=0; round<40; round++) begin
      for (int i=0; i<N; i++) step('1, 1);
      for (int i=0; i<N; i++)
        check(25, served[i] == round+1,
              $sformatf("persistent source %0d service count=%0d round=%0d",
                        i, served[i], round));
    end
    reset_arbiter();
    for (int cycle=0; cycle<20000; cycle++) begin
      rng = next_random(rng);
      step(N'(rng>>3), (rng & 7) < 5);
    end
    for (int i=21; i<=25; i++)
      $display("IC_GROUP AC-%02d %0d %0d", i, passed[i], total[i]);
    $finish;
  end
endmodule
