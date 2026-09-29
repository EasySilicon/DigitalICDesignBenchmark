`timescale 1ns/1ps
module tb_hidden_T01;
  logic clock, serial_in;
  logic [7:0] parallel_out;
  logic [7:0] expected, held;
  int sampled, seed;
  int unsigned rng;
  int passed [1:4], total [1:4];
  bit first_failure [1:4];

  serial_in_parallel_out_8bit dut (.*);

  task automatic check(input int id, input bit okay, input string what);
    total[id]++;
    if (okay) passed[id]++;
    else if (!first_failure[id]) begin
      first_failure[id] = 1;
      $display("IC_FAILURE AC-%02d sample=%0d %s expected=%02h actual=%02h",
               id, sampled, what, expected, parallel_out);
    end
  endtask

  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction

  task automatic sample_bit(input logic value, input bit stream_bit,
                            input bit word_end);
    // The complete low and high phases are each 0.5 ns. Consecutive rising
    // edges are therefore exactly 1000 ps for the gate-level power workload.
    held = parallel_out;
    serial_in = ~value;
    #0.1;
    if (sampled >= 8) check(4, parallel_out === held, "low-phase input toggle");
    serial_in = value;
    #0.4;
    if (sampled >= 8) check(4, parallel_out === held, "held before rising edge");

    clock = 1;
    expected = {expected[6:0], value};
    sampled++;
    #0.1;
    if (stream_bit) check(2, parallel_out === expected, "sliding window");
    if (word_end) check(1, parallel_out === expected, "complete word");
    held = parallel_out;
    serial_in = ~value;
    #0.1;
    if (sampled >= 8) check(4, parallel_out === held, "high-phase input toggle");
    serial_in = value;
    #0.29;
    if (sampled >= 8) check(4, parallel_out === held, "held before falling edge");
    clock = 0;
    #0.01;
    if (sampled >= 8) check(3, parallel_out === held, "falling edge changed output");
  endtask

  task automatic send_word(input logic [7:0] value);
    for (int bit_index = 7; bit_index >= 0; bit_index--)
      sample_bit(value[bit_index], 0, bit_index == 0);
  endtask

  initial begin
    seed = 20260928;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ 32'h9e37_79b9;
    if (rng == 0) rng = 32'h6d2b_79f5;
    clock = 0;
    serial_in = 0;
    expected = 0;
    sampled = 0;
    for (int id = 1; id <= 4; id++) begin
      passed[id] = 0;
      total[id] = 0;
      first_failure[id] = 0;
    end
    check(1, $bits(dut.clock) == 1 && $bits(dut.serial_in) == 1 &&
             $bits(dut.parallel_out) == 8, "fixed interface width");
    send_word(8'h00);
    send_word(8'hff);
    send_word(8'ha5);
    send_word(8'h5a);
    send_word(8'h81);
    send_word(8'h7e);
    send_word(8'h96);
    send_word(8'h69);
    for (int index = 0; index < 1024; index++) begin
      rng = next_random(rng);
      sample_bit(rng[0], 1, 0);
    end
    for (int id = 1; id <= 4; id++)
      $display("IC_GROUP AC-%02d %0d %0d", id, passed[id], total[id]);
    $finish;
  end
endmodule
