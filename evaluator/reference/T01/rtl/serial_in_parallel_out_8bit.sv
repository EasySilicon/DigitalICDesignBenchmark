module serial_in_parallel_out_8bit (
    input  logic       clock,
    input  logic       serial_in,
    output logic [7:0] parallel_out
);
  always_ff @(posedge clock)
    parallel_out <= {parallel_out[6:0], serial_in};
endmodule
