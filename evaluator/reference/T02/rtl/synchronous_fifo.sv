// Evaluator-owned reference implementation for T03.
module synchronous_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 3
)(
  input  logic             clk,
  input  logic             rst_n,
  input  logic             in_valid,
  output logic             in_ready,
  input  logic [WIDTH-1:0] in_data,
  output logic             out_valid,
  input  logic             out_ready,
  output logic [WIDTH-1:0] out_data
);
  localparam int PTR_W = $clog2(DEPTH);
  localparam int CNT_W = $clog2(DEPTH + 1);
  logic [WIDTH-1:0] storage [0:DEPTH-1];
  logic [PTR_W-1:0] rd_ptr, wr_ptr;
  logic [CNT_W-1:0] count;
  logic push, pop;

  assign out_valid = count != 0;
  assign out_data = storage[rd_ptr];
  assign in_ready = (count != DEPTH) || (out_valid && out_ready);
  assign push = in_valid && in_ready;
  assign pop = out_valid && out_ready;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      rd_ptr <= '0;
      wr_ptr <= '0;
      count <= '0;
    end else begin
      if (push) begin
        storage[wr_ptr] <= in_data;
        wr_ptr <= (wr_ptr == DEPTH - 1) ? '0 : wr_ptr + 1'b1;
      end
      if (pop)
        rd_ptr <= (rd_ptr == DEPTH - 1) ? '0 : rd_ptr + 1'b1;
      case ({push, pop})
        2'b10: count <= count + 1'b1;
        2'b01: count <= count - 1'b1;
        default: count <= count;
      endcase
    end
  end
endmodule
