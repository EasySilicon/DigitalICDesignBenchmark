`timescale 1ns/1ps

module tb_T06 #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 8
);
  logic wr_clk, wr_rst_n, wr_valid, wr_ready;
  logic [WIDTH-1:0] wr_data;
  logic rd_clk, rd_rst_n, rd_valid, rd_ready;
  logic [WIDTH-1:0] rd_data;
  logic [WIDTH-1:0] oracle [0:255];
  logic [WIDTH-1:0] held_data;
  bit held, enabled;
  int writes, reads, target, seed;
  int unsigned rng;
  time wr_half_period = 5;
  time rd_half_period = 7;

  asynchronous_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
    .wr_clk(wr_clk), .wr_rst_n(wr_rst_n), .wr_valid(wr_valid),
    .wr_ready(wr_ready), .wr_data(wr_data),
    .rd_clk(rd_clk), .rd_rst_n(rd_rst_n), .rd_valid(rd_valid),
    .rd_ready(rd_ready), .rd_data(rd_data)
  );

  initial begin
    wr_clk = 0;
    forever #(wr_half_period) wr_clk = ~wr_clk;
  end

  initial begin
    rd_clk = 0;
    #3;
    forever #(rd_half_period) rd_clk = ~rd_clk;
  end

  always @(negedge wr_clk) begin
    wr_valid = enabled && wr_rst_n && writes < target;
    wr_data = WIDTH'(writes + 1);
  end

  always @(posedge wr_clk) begin
    if (wr_rst_n && wr_valid && wr_ready) begin
      if (writes - reads >= DEPTH)
        $fatal(1, "AC-27 FIFO accepted overflow writes=%0d reads=%0d", writes, reads);
      oracle[writes] = wr_data;
      writes++;
    end
  end

  always @(negedge rd_clk) begin
    rng ^= rng << 13;
    rng ^= rng >> 17;
    rng ^= rng << 5;
    rd_ready = enabled && rng[1];
  end

  always @(posedge rd_clk) begin
    if (!rd_rst_n) held = 0;
    else begin
      if (held && (rd_valid !== 1 || rd_data !== held_data))
        $fatal(1, "AC-26/27 output changed under backpressure");
      if (rd_valid && writes == reads)
        $fatal(1, "AC-27 read domain exposed unwritten data");
      if (rd_valid && rd_ready) begin
        if (rd_data !== oracle[reads])
          $fatal(1, "AC-26 expected=%h actual=%h item=%0d",
                 oracle[reads], rd_data, reads);
        reads++;
      end
      held = rd_valid && !rd_ready;
      if (held) held_data = rd_data;
    end
  end

  task automatic run_clock_phase(input time next_wr_half_period,
                                 input time next_rd_half_period,
                                 input int phase_transfers);
    enabled = 0;
    wr_rst_n = 0;
    rd_rst_n = 0;
    wr_half_period = next_wr_half_period;
    rd_half_period = next_rd_half_period;
    repeat (4) @(negedge wr_clk);
    repeat (4) @(negedge rd_clk);
    wr_rst_n = 1;
    repeat (2) @(negedge rd_clk);
    rd_rst_n = 1;
    target = writes + phase_transfers;
    enabled = 1;
    wait (writes == target && reads == target);
    enabled = 0;
  endtask

  initial begin
    if ($bits(dut.wr_data) != WIDTH || $bits(dut.rd_data) != WIDTH ||
        $bits(dut.wr_ready) != 1 || $bits(dut.rd_valid) != 1)
      $fatal(1, "T06 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ 32'ha54ff53a;
    wr_rst_n = 0;
    rd_rst_n = 0;
    wr_valid = 0;
    wr_data = 0;
    rd_ready = 0;
    writes = 0;
    reads = 0;
    target = 0;
    enabled = 0;
    held = 0;
    // Fixed non-locking ratios cover near-rate, write-faster, and read-faster flow.
    run_clock_phase(5, 7, 64);
    run_clock_phase(4, 9, 64);
    run_clock_phase(9, 4, 64);
    wr_rst_n = 0;
    rd_rst_n = 0;
    repeat (4) @(negedge wr_clk);
    repeat (4) @(negedge rd_clk);
    #50;
    if (rd_valid !== 0)
      $fatal(1, "AC-30 stale item after drain");
    $display("PUBLIC_PASS T06 WIDTH=%0d DEPTH=%0d writes=%0d reads=%0d clock_pairs=3 seed=%0d",
             WIDTH, DEPTH, writes, reads, seed);
    $finish;
  end

  initial begin
    #100000;
    $fatal(1, "AC-26 timeout writes=%0d reads=%0d target=%0d",
           writes, reads, target);
  end
endmodule
