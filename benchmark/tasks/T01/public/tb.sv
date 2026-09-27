`timescale 1ns/1ps

module tb_T01;
  logic clock;
  logic serial_in;
  wire [7:0] parallel_out;
  logic [7:0] expected;
  logic [7:0] before_edge;
  int seed;
  int unsigned state;

  serial_in_parallel_out_8bit dut (
    .clock(clock), .serial_in(serial_in), .parallel_out(parallel_out)
  );

  initial begin
    if ($bits(dut.clock) != 1 || $bits(dut.serial_in) != 1 ||
        $bits(dut.parallel_out) != 8)
      $fatal(1, "T01 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    state = 32'(seed) ^ 32'h9e3779b9;
    clock = 0;
    serial_in = 0;
    expected = 0;
    for (int sample = 0; sample < 320; sample++) begin
      state ^= state << 13;
      state ^= state >> 17;
      state ^= state << 5;
      serial_in = state[0];
      #2;
      if (sample >= 8 && parallel_out !== expected)
        $fatal(1, "AC-03/04 changed before rising edge sample=%0d expected=%02h actual=%02h",
               sample, expected, parallel_out);
      clock = 1;
      expected = {expected[6:0], serial_in};
      #2;
      if (sample >= 7 && parallel_out !== expected)
        $fatal(1, "AC-01/02 sample=%0d expected=%02h actual=%02h",
               sample, expected, parallel_out);
      before_edge = parallel_out;
      serial_in = ~serial_in;
      #2;
      if (sample >= 7 && parallel_out !== before_edge)
        $fatal(1, "AC-04 changed between edges sample=%0d", sample);
      clock = 0;
      #2;
      if (sample >= 7 && parallel_out !== before_edge)
        $fatal(1, "AC-03 changed on falling edge sample=%0d", sample);
    end
    $display("PUBLIC_PASS T01 samples=320 seed=%0d", seed);
    $finish;
  end
endmodule
