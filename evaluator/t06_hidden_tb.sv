`timescale 1ps/1ps

module tb_hidden_T06 #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 8
);
  localparam int MAX_ITEMS = 120000;

  logic wr_clk, wr_rst_n, wr_valid, wr_ready;
  logic [WIDTH-1:0] wr_data;
  logic rd_clk, rd_rst_n, rd_valid, rd_ready;
  logic [WIDTH-1:0] rd_data;
  logic [WIDTH-1:0] expected [0:MAX_ITEMS-1];
  logic [WIDTH-1:0] stalled_data;
  bit stalled, drivers_enabled, force_offer, force_take, power_mode;
  int accepted, returned, goal, next_value;
  int offer_percent, take_percent;
  int passed [26:30], total [26:30];
  bit first_failure [26:30];
  int unsigned wr_rng, rd_rng;
  int seed, power_goal;
  time wr_half_ps, rd_half_ps;

  asynchronous_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
    .wr_clk(wr_clk), .wr_rst_n(wr_rst_n), .wr_valid(wr_valid),
    .wr_ready(wr_ready), .wr_data(wr_data),
    .rd_clk(rd_clk), .rd_rst_n(rd_rst_n), .rd_valid(rd_valid),
    .rd_ready(rd_ready), .rd_data(rd_data)
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

  initial begin
    wr_clk = 0;
    forever begin
      #(wr_half_ps);
      wr_clk = ~wr_clk;
    end
  end

  initial begin
    rd_clk = 0;
    #137;
    forever begin
      #(rd_half_ps);
      rd_clk = ~rd_clk;
    end
  end

  always @(negedge wr_clk) begin
    if (!wr_rst_n || !drivers_enabled || accepted >= goal) begin
      wr_valid = 0;
    end else if (!(wr_valid && !wr_ready)) begin
      wr_rng = next_random(wr_rng);
      wr_valid = force_offer || ((wr_rng % 100) < offer_percent);
      if (wr_valid)
        wr_data = WIDTH'(next_value);
    end
  end

  always @(posedge wr_clk) begin
    if (wr_rst_n && wr_valid && wr_ready) begin
      check(27, accepted - returned < DEPTH,
            $sformatf("overflow accepted=%0d returned=%0d", accepted, returned));
      if (accepted < MAX_ITEMS)
        expected[accepted] = wr_data;
      accepted++;
      next_value++;
    end
  end

  always @(negedge rd_clk) begin
    if (!rd_rst_n || !drivers_enabled) begin
      rd_ready = 0;
    end else begin
      rd_rng = next_random(rd_rng);
      rd_ready = force_take || ((rd_rng % 100) < take_percent);
    end
  end

  always @(posedge rd_clk) begin
    if (!rd_rst_n) begin
      stalled = 0;
    end else begin
      if (stalled)
        check(27, rd_valid === 1'b1 && rd_data === stalled_data,
              "rd_valid/rd_data changed while blocked");
      if (rd_valid)
        check(27, returned < accepted,
              $sformatf("unwritten item exposed accepted=%0d returned=%0d",
                        accepted, returned));
      if (rd_valid && rd_ready) begin
        check(26, returned < accepted && rd_data === expected[returned],
              $sformatf("order expected=%h actual=%h item=%0d",
                        expected[returned], rd_data, returned));
        returned++;
      end
      stalled = rd_valid && !rd_ready;
      if (stalled)
        stalled_data = rd_data;
    end
  end

  task automatic apply_reset(input int scenario);
    drivers_enabled = 0;
    wr_valid = 0;
    rd_ready = 0;
    wr_rst_n = 0;
    rd_rst_n = 0;
    #1;
    check(30, rd_valid === 1'b0,
          $sformatf("asynchronous assertion left rd_valid high scenario=%0d", scenario));
    repeat (4) @(posedge wr_clk);
    repeat (4) @(posedge rd_clk);
    accepted = 0;
    returned = 0;
    goal = 0;
    next_value = 32'h10000 * (scenario + 1);
    stalled = 0;
    wr_rst_n = 1;
    repeat (3) @(posedge wr_clk);
    rd_rst_n = 1;
    repeat (4) @(posedge rd_clk);
    check(30, rd_valid === 1'b0,
          $sformatf("stale item after reset release scenario=%0d", scenario));
  endtask

  task automatic wait_until_drained(input int max_rd_cycles, input string label);
    int cycles;
    cycles = 0;
    while ((accepted != goal || returned != goal) && cycles < max_rd_cycles) begin
      @(posedge rd_clk);
      cycles++;
    end
    check(26, accepted == goal && returned == goal,
          $sformatf("%s timeout accepted=%0d returned=%0d goal=%0d",
                    label, accepted, returned, goal));
  endtask

  task automatic run_phase(input time next_wr_half_ps,
                           input time next_rd_half_ps,
                           input int transfers,
                           input int next_offer_percent,
                           input int next_take_percent,
                           input string label);
    drivers_enabled = 0;
    @(negedge wr_clk);
    @(negedge rd_clk);
    if (!power_mode) begin
      wr_half_ps = next_wr_half_ps;
      rd_half_ps = next_rd_half_ps;
    end
    offer_percent = next_offer_percent;
    take_percent = next_take_percent;
    force_offer = 0;
    force_take = 0;
    goal = accepted + transfers;
    drivers_enabled = 1;
    wait_until_drained(transfers * 60 + 2000, label);
    drivers_enabled = 0;
    @(negedge wr_clk);
    wr_valid = 0;
    @(negedge rd_clk);
    rd_ready = 0;
    check(28, accepted == goal && returned == goal,
          $sformatf("clock-ratio phase failed: %s", label));
  endtask

  task automatic check_eventual_visible;
    int cycles;
    goal = accepted + 1;
    offer_percent = 100;
    take_percent = 0;
    force_offer = 1;
    force_take = 0;
    drivers_enabled = 1;
    while (accepted < goal)
      @(posedge wr_clk);
    cycles = 0;
    while (rd_valid !== 1'b1 && cycles < 200) begin
      @(posedge rd_clk);
      cycles++;
    end
    check(27, rd_valid === 1'b1 && cycles < 200,
          $sformatf("written item not visible within 200 rd clocks cycles=%0d", cycles));
    repeat (12) @(posedge rd_clk);
    force_take = 1;
    wait_until_drained(40, "eventual-visible drain");
    drivers_enabled = 0;
    force_offer = 0;
    force_take = 0;
  endtask

  initial begin
    seed = 20260928;
    void'($value$plusargs("SEED=%d", seed));
    power_mode = $value$plusargs("POWER_GOAL=%d", power_goal);
    if (!power_mode)
      power_goal = 0;
    wr_half_ps = power_mode ? 500 : 1300;
    rd_half_ps = power_mode ? 500 : 1900;
    wr_rng = 32'(seed) ^ (WIDTH * 32'h9e3779b9) ^ DEPTH;
    rd_rng = 32'(seed) ^ (DEPTH * 32'h85ebca6b) ^ WIDTH;
    wr_rst_n = 1;
    rd_rst_n = 1;
    wr_valid = 0;
    wr_data = 0;
    rd_ready = 0;
    drivers_enabled = 0;
    force_offer = 0;
    force_take = 0;
    accepted = 0;
    returned = 0;
    goal = 0;
    stalled = 0;
    for (int i = 26; i <= 30; i++) begin
      passed[i] = 0;
      total[i] = 0;
      first_failure[i] = 0;
    end

    check(29, $bits(dut.wr_data) == WIDTH && $bits(dut.rd_data) == WIDTH,
          "parameterized port width");
    // Give the initial high level a distinct time slot so the first reset
    // assertion is a real asynchronous falling edge in two-state simulation.
    #1;
    apply_reset(0);
    check_eventual_visible();

    if (power_mode) begin
      run_phase(500, 500, power_goal, 78, 69, "fixed-1GHz-power");
    end else begin
      // Leave unread data before a run-time reset, then prove that no stale
      // item is observable after independent reset release.
      goal = accepted + DEPTH - 1;
      offer_percent = 100;
      take_percent = 0;
      force_offer = 1;
      drivers_enabled = 1;
      while (accepted < goal)
        @(posedge wr_clk);
      apply_reset(1);

      // Four non-locking clock regimes total at least 100,000 transfers for
      // every WIDTH/DEPTH configuration.
      run_phase(500, 750, 25000, 85, 61, "ratio-2-to-3");
      run_phase(600, 1000, 25000, 91, 57, "ratio-3-to-5");
      run_phase(503, 509, 25000, 73, 71, "near-one-to-one");
      run_phase(900, 500, 25000, 67, 88, "slow-write-fast-read");
    end

    check(29, passed[26] == total[26] && passed[27] == total[27] &&
              passed[28] == total[28] && passed[30] == total[30],
          "parameter combination failed behavioral scenarios");
    $display("IC_STATS WIDTH=%0d DEPTH=%0d accepted=%0d returned=%0d power=%0d",
             WIDTH, DEPTH, accepted, returned, power_mode);
    for (int i = 26; i <= 30; i++)
      $display("IC_GROUP AC-%02d %0d %0d", i, passed[i], total[i]);
    $finish;
  end

  initial begin
    #5_000_000_000;
    $fatal(1, "T06 hidden timeout WIDTH=%0d DEPTH=%0d", WIDTH, DEPTH);
  end
endmodule
