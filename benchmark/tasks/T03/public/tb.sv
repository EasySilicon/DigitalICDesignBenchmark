`timescale 1ns/1ps

module tb_T03 #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 3
);
  logic clk, rst_n;
  logic in_valid, in_ready;
  logic [WIDTH-1:0] in_data;
  logic out_valid, out_ready;
  logic [WIDTH-1:0] out_data;
  logic [WIDTH-1:0] oracle [0:DEPTH-1];
  logic [WIDTH-1:0] held_data;
  bit held;
  int rd_ptr, wr_ptr, count, accepted, returned;
  int seed;
  int unsigned random_state;

  synchronous_fifo #(.WIDTH(WIDTH), .DEPTH(DEPTH)) dut (
    .clk(clk), .rst_n(rst_n), .in_valid(in_valid), .in_ready(in_ready),
    .in_data(in_data), .out_valid(out_valid), .out_ready(out_ready),
    .out_data(out_data)
  );

  task automatic reset_fifo;
    clk = 0;
    rst_n = 0;
    in_valid = 0;
    out_ready = 0;
    #2;
    clk = 1;
    #2;
    clk = 0;
    #2;
    if (out_valid !== 0) $fatal(1, "AC-13 reset did not clear FIFO");
    rd_ptr = 0;
    wr_ptr = 0;
    count = 0;
    held = 0;
    rst_n = 1;
    #2;
  endtask

  task automatic tick(input bit want_write, input logic [WIDTH-1:0] value,
                      input bit want_read);
    bit push, pop;
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    in_valid = want_write;
    in_data = value;
    out_ready = want_read;
    #2;
    if (count == 0 && out_valid !== 0)
      $fatal(1, "AC-10 empty FIFO asserted out_valid");
    if (count == DEPTH && !want_read && in_ready !== 0)
      $fatal(1, "AC-10 full FIFO asserted in_ready");
    if (held && (out_valid !== 1 || out_data !== held_data))
      $fatal(1, "AC-14 output changed under backpressure");
    if (out_valid) begin
      if (count == 0) $fatal(1, "AC-10 phantom item");
      if (out_data !== oracle[rd_ptr])
        $fatal(1, "AC-09 sequence mismatch expected=%h actual=%h count=%0d",
               oracle[rd_ptr], out_data, count);
    end
    push = in_valid && in_ready;
    pop = out_valid && out_ready;
    if (push && count == DEPTH && !pop)
      $fatal(1, "AC-10 overflow accepted");
    held = out_valid && !out_ready;
    if (held) held_data = out_data;
    clk = 1;
    #2;
    if (pop) begin
      rd_ptr = (rd_ptr + 1) % DEPTH;
      count--;
      returned++;
    end
    if (push) begin
      oracle[wr_ptr] = value;
      wr_ptr = (wr_ptr + 1) % DEPTH;
      count++;
      accepted++;
    end
    clk = 0;
    #2;
  endtask

  initial begin
    if ($bits(dut.in_data) != WIDTH || $bits(dut.out_data) != WIDTH ||
        $bits(dut.in_valid) != 1 || $bits(dut.out_valid) != 1)
      $fatal(1, "T03 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    random_state = 32'(seed) ^ 32'h6a09e667;
    accepted = 0;
    returned = 0;
    reset_fifo();

    // Fill exact capacity, then reject the next write until one item is read.
    for (int i = 0; i < DEPTH; i++)
      tick(1, WIDTH'(i + 8'h31), 0);
    if (count != DEPTH) $fatal(1, "AC-10 failed to fill exact capacity");
    tick(1, WIDTH'('hfe), 0);
    if (count != DEPTH) $fatal(1, "AC-10 overflow changed occupancy");
    tick(1, WIDTH'('hfd), 1);
    if (count != DEPTH) $fatal(1, "AC-11 full simultaneous pop/push failed");

    // Repeated wraparound, mixed pressure and an independent software queue.
    for (int i = 0; i < 512; i++) begin
      random_state ^= random_state << 13;
      random_state ^= random_state >> 17;
      random_state ^= random_state << 5;
      tick(random_state[0], WIDTH'(random_state ^ (i * 17)), random_state[2]);
    end
    for (int i = 0; i < DEPTH + 8; i++) tick(0, '0, 1);
    if (count != 0) $fatal(1, "AC-09 drain timeout count=%0d", count);

    // A running reset must invalidate old entries.
    tick(1, WIDTH'('h55), 0);
    if (count != 1) $fatal(1, "AC-13 setup failed");
    reset_fifo();
    tick(0, '0, 1);
    if (count != 0) $fatal(1, "AC-13 stale data after reset");
    $display("PUBLIC_PASS T03 WIDTH=%0d DEPTH=%0d accepted=%0d returned=%0d seed=%0d",
             WIDTH, DEPTH, accepted, returned, seed);
    $finish;
  end
endmodule
