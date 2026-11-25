// -----------------------------------------------------------------------------
// mm_tile : 4x4 tile of processing elements (pure structural wiring).
//   a_in / at_in  : operands + tokens entering the 4 rows from the left
//   b_in / bt_in  : operands + tokens entering the 4 columns from the top
//   c_out         : 16 local results, index = 4*row + col
// -----------------------------------------------------------------------------
module mm_tile (
  input  logic            clk,
  input  logic            rst_n,
  input  logic [4*64-1:0] a_in,
  input  logic [4*15-1:0] at_in,
  input  logic [4*64-1:0] b_in,
  input  logic [4*8-1:0]  bt_in,
  output logic [4*64-1:0] a_out,
  output logic [4*15-1:0] at_out,
  output logic [4*64-1:0] b_out,
  output logic [4*8-1:0]  bt_out,
  output logic [16*64-1:0] c_out
);
  logic [63:0] ah  [0:3][0:4];
  logic [14:0] ath [0:3][0:4];
  logic [63:0] bv  [0:4][0:3];
  logic [7:0]  btv [0:4][0:3];

  for (genvar i = 0; i < 4; i++) begin : g_edge
    assign ah[i][0]  = a_in[64*i +: 64];
    assign ath[i][0] = at_in[15*i +: 15];
    assign bv[0][i]  = b_in[64*i +: 64];
    assign btv[0][i] = bt_in[8*i +: 8];
    assign a_out[64*i +: 64]  = ah[i][4];
    assign at_out[15*i +: 15] = ath[i][4];
    assign b_out[64*i +: 64]  = bv[4][i];
    assign bt_out[8*i +: 8]   = btv[4][i];
  end

  for (genvar r = 0; r < 4; r++) begin : g_row
    for (genvar c = 0; c < 4; c++) begin : g_col
      mm_pe u_pe (
        .clk    (clk),
        .rst_n  (rst_n),
        .a_in   (ah[r][c]),
        .at_in  (ath[r][c]),
        .b_in   (bv[r][c]),
        .bt_in  (btv[r][c]),
        .a_out  (ah[r][c+1]),
        .at_out (ath[r][c+1]),
        .b_out  (bv[r+1][c]),
        .bt_out (btv[r+1][c]),
        .c_out  (c_out[64*(4*r+c) +: 64])
      );
    end
  end
endmodule
