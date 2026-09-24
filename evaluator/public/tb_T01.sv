`timescale 1ns/1ps

module tb_T01;
  logic [7:0] in;
  wire [2:0] out;
  int seed;
  int expected;
  logic [7:0] vectors [0:15];

  priority_encoder_8x3 dut (.in(in), .out(out));

  initial begin
    if ($bits(dut.in) != 8 || $bits(dut.out) != 3)
      $fatal(1, "T01 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    vectors[0] = 8'h00;
    for (int i = 0; i < 8; i++) vectors[i + 1] = 8'(1 << i);
    vectors[9] = 8'hff;
    vectors[10] = 8'h81;
    vectors[11] = 8'h55;
    vectors[12] = 8'haa;
    vectors[13] = 8'h18;
    vectors[14] = 8'h03;
    vectors[15] = 8'hc0;
    // The hidden scorer will use all 256 values. This public smoke is small.
    for (int pass = 0; pass < 2; pass++) begin
      for (int k = 0; k < 16; k++) begin
        in = vectors[(k * 5 + (seed & 15) + pass * 3) & 15];
        #1;
        expected = 0;
        for (int bit_index = 0; bit_index < 8; bit_index++)
          if (in[bit_index]) expected = bit_index;
        if (out !== 3'(expected))
          $fatal(1, "AC-01/02/03/04 in=%02h expected=%0d actual=%0d", in, expected, out);
      end
    end
    $display("PUBLIC_PASS T01 vectors=32 seed=%0d", seed);
    $finish;
  end
endmodule
