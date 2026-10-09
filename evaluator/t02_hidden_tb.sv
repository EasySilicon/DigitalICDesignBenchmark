`timescale 1ns/1ps

module tb_hidden_T02 #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 3
);
  logic clk, rst_n, in_valid, in_ready, out_valid, out_ready;
  logic [WIDTH-1:0] in_data, out_data;
  logic [WIDTH-1:0] oracle [0:DEPTH-1];
  logic [WIDTH-1:0] pending_data, stalled_data;
  bit pending, stalled;
  int rd_ptr, wr_ptr, count, accepted, returned;
  int passed [9:15], total [9:15];
  bit first_failure [9:15];
  int unsigned rng;
  int seed;

  synchronous_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
    .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_ready(in_ready),
    .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready), .out_data(out_data)
  );

  task automatic check(input int group_id, input bit okay, input string what);
    total[group_id]++;
    if (okay) passed[group_id]++;
    else if (!first_failure[group_id]) begin
      first_failure[group_id] = 1;
      $display("IC_FAILURE AC-%02d WIDTH=%0d DEPTH=%0d %s",
               group_id, WIDTH, DEPTH, what);
    end
  endtask

  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction

  // One step has a 1 ns rising-edge-to-rising-edge interval. This keeps the
  // checked functional workload identical to the 1 GHz power workload.
  task automatic step(input bit offer, input logic [WIDTH-1:0] value,
                      input bit take, input bit replacement_check);
    bit expected_valid, expected_ready, push, pop;
    logic [WIDTH-1:0] offered_data;
    clk = 0;
    in_valid = pending || offer;
    offered_data = pending ? pending_data : value;
    in_data = offered_data;
    out_ready = take;
    #0.4;
    expected_valid = count > 0;
    expected_ready = (count < DEPTH) || (expected_valid && take);
    check(10, out_valid === expected_valid && in_ready === expected_ready,
          $sformatf("occupancy=%0d out_valid=%b in_ready=%b expected_ready=%b",
                    count, out_valid, in_ready, expected_ready));
    if (expected_valid)
      check(9, out_valid === 1'b1 && out_data === oracle[rd_ptr],
            $sformatf("order expected=%h actual=%h", oracle[rd_ptr], out_data));
    if (stalled)
      check(14, out_valid === 1'b1 && out_data === stalled_data,
            "blocked output changed");
    if (replacement_check)
      check(11, count == DEPTH && in_valid && out_ready &&
                in_ready === 1'b1 && out_valid === 1'b1,
            "full simultaneous read/write was rejected");
    push = in_valid === 1'b1 && in_ready === 1'b1;
    pop = out_valid === 1'b1 && take;
    if (push && count == DEPTH && !pop)
      check(10, 0, "overflow handshake");
    if (pop && count == 0)
      check(10, 0, "empty read handshake");
    stalled = out_valid === 1'b1 && !take;
    if (stalled) stalled_data = out_data;
    pending = in_valid && !push;
    if (pending) pending_data = offered_data;
    clk = 1;
    #0.4;
    if (pop && count > 0) begin
      rd_ptr = (rd_ptr + 1) % DEPTH;
      count--;
      returned++;
    end
    if (push && count < DEPTH) begin
      oracle[wr_ptr] = offered_data;
      wr_ptr = (wr_ptr + 1) % DEPTH;
      count++;
      accepted++;
    end
    clk = 0;
    #0.2;
  endtask

  task automatic reset_fifo(input int scenario);
    in_valid = 0;
    out_ready = 0;
    // Create an observable high-to-low transition.  Driving 1 and 0 in the
    // same time slot makes the first reset check depend on simulator startup
    // values instead of the DUT's asynchronous-reset behavior.
    rst_n = 1;
    #0.1;
    rst_n = 0;
    #0.2;
    check(13, out_valid === 1'b0,
          $sformatf("asynchronous reset failed scenario=%0d", scenario));
    clk = 1;
    #0.4;
    clk = 0;
    #0.2;
    rd_ptr = 0;
    wr_ptr = 0;
    count = 0;
    pending = 0;
    stalled = 0;
    rst_n = 1;
    #0.2;
    check(13, out_valid === 1'b0, "stale valid after reset release");
  endtask

  initial begin
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ (WIDTH * 32'h9e3779b9) ^ DEPTH;
    clk = 0;
    rst_n = 1;
    in_valid = 0;
    out_ready = 0;
    pending = 0;
    stalled = 0;
    rd_ptr = 0;
    wr_ptr = 0;
    count = 0;
    accepted = 0;
    returned = 0;
    for (int i = 9; i <= 15; i++) begin
      passed[i] = 0;
      total[i] = 0;
      first_failure[i] = 0;
    end
    check(12, $bits(dut.in_data) == WIDTH && $bits(dut.out_data) == WIDTH,
          "parameterized port width");
    reset_fifo(0);
    for (int i = 0; i < DEPTH; i++)
      step(1, WIDTH'(32'h12345600 ^ i), 0, 0);
    check(10, count == DEPTH, "exact capacity could not be filled");
    step(1, WIDTH'('h5a), 0, 0);
    for (int i = 0; i < DEPTH * 4; i++) begin
      step(1, WIDTH'(i ^ 'ha5), 1, 1);
      check(11, count == DEPTH, "replacement changed occupancy");
    end
    for (int i = 0; i < 30; i++)
      step(0, '0, 0, 0);
    begin
      int drain_cycles;
      drain_cycles = 0;
      while (count > 0 && drain_cycles < DEPTH + 8) begin
        step(0, '0, 1, 0);
        drain_cycles++;
      end
      check(9, count == 0, "directed drain timeout");
      check(10, count == 0 && out_valid === 1'b0,
            "phantom item or unreadable entry after drain");
    end
    step(0, '0, 1, 0);
    if (DEPTH == 3) begin
      for (int i = 0; i < 300; i++) begin
        step(1, WIDTH'(i * 17 + 3), 0, 0);
        step(0, '0, 1, 0);
      end
      check(15, count == 0 && !pending, "non-power-of-two wraparound");
    end else check(15, 1, "other depth neutral");
    for (int i = 0; i < DEPTH / 2 + 1; i++)
      step(1, WIDTH'(i + 19), 0, 0);
    reset_fifo(1);
    step(0, '0, 1, 0);
    check(13, out_valid === 1'b0, "old item survived nonempty reset");
    for (int i = 0; i < DEPTH; i++)
      step(1, WIDTH'(i + 44), 0, 0);
    reset_fifo(2);
    check(13, out_valid === 1'b0, "old item survived full reset");
    begin
      int goal, cycles;
      goal = (WIDTH == 8 && DEPTH == 3) ? 110000 : 5000;
      cycles = 0;
      while (accepted < goal && cycles < goal * 12) begin
        rng = next_random(rng);
        step((rng % 8) < 6, WIDTH'(rng ^ (cycles * 32'h01010101)),
             ((rng >> 5) % 8) < 5, 0);
        cycles++;
      end
      check(9, accepted >= goal,
            $sformatf("random progress accepted=%0d goal=%0d", accepted, goal));
    end
    begin
      int limit;
      limit = 0;
      while ((count > 0 || pending) && limit < DEPTH + 8) begin
        step(0, '0, 1, 0);
        limit++;
      end
      check(9, count == 0 && !pending, "final drain incomplete");
    end
    check(12, passed[9] == total[9] && passed[10] == total[10] &&
              passed[11] == total[11] && passed[13] == total[13] &&
              passed[14] == total[14] && passed[15] == total[15],
          "parameter combination failed functional scenarios");
    $display("IC_STATS WIDTH=%0d DEPTH=%0d accepted=%0d returned=%0d",
             WIDTH, DEPTH, accepted, returned);
    for (int i = 9; i <= 15; i++)
      $display("IC_GROUP AC-%02d %0d %0d", i, passed[i], total[i]);
    $finish;
  end
endmodule
