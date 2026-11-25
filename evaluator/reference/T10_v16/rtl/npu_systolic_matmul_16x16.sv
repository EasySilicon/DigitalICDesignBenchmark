// -----------------------------------------------------------------------------
// npu_systolic_matmul_16x16
//   C[16][16] = A[16][64] x B[64][16] on a 16x16 output-stationary systolic
//   array built from 16 mm_tile (4x4 PEs each).
//
//   input register -> row/column skew -> 16 tiles -> column de-skew ->
//   row-group select -> compaction -> credit-controlled output FIFO (4 slots).
//
//   Timing (T = cycle whose rising edge accepts the last beat of a block):
//     PE(r,c) sees the beat in cycle T+1+r+c, its result is visible in cycle
//     T+11+r+c, row r is aligned in cycle T+26+r and is visible on the output
//     in cycle T+27+r (when the output is not back-pressured).
// -----------------------------------------------------------------------------
module npu_systolic_matmul_16x16 (
  input  logic          clk,
  input  logic          rst_n,
  input  logic          in_valid,
  output logic          in_ready,
  input  logic          in_start,
  input  logic [15:0]   in_block_id,
  input  logic [3:0]    mode,
  input  logic [255:0]  a_scale,
  input  logic [255:0]  b_scale,
  input  logic [1023:0] a_data,
  input  logic [1023:0] b_data,
  output logic [3:0]    out_valid,
  input  logic          out_ready,
  output logic [63:0]   out_block_id,
  output logic [15:0]   out_row,
  output logic [4095:0] out_data
);
  localparam int RW     = 39;            // stored result bits (38 + sign-ext flag)
  localparam int ROWW   = 16 * RW;       // one row of results
  localparam int SLOTW  = ROWW + 16 + 4; // data + block id + row
  localparam int DEPTH  = 62;            // output FIFO entries (4 slots each)
  localparam int TK0    = 25;            // token delay for row 0
  localparam int TKLEN  = TK0 + 16;
  // worst-case number of future FIFO pushes when a block is admitted:
  // 41 from older blocks + 16 from the new one
  localparam int RESERVE = 57;

  // ---------------------------------------------------------------------------
  // input protocol
  // ---------------------------------------------------------------------------
  logic         in_blk;
  logic [3:0]   cnt;
  logic [3:0]   mode_q;
  logic [15:0]  id_q;
  logic [255:0] asc_q, bsc_q;
  logic [6:0]   fcount;

  assign in_ready = in_blk | (fcount <= 7'(DEPTH - RESERVE));

  wire        accept   = in_valid & in_ready;
  wire        start    = accept & in_start;
  wire        cont     = accept & ~in_start & in_blk;
  wire        beat     = start | cont;
  wire [3:0]  cur_mode = start ? mode : mode_q;
  wire [3:0]  cur_cnt  = start ? 4'd0 : cnt;
  wire [15:0] cur_id   = start ? in_block_id : id_q;
  wire        w16      = (cur_mode == 4'd1) | (cur_mode == 4'd2) | (cur_mode == 4'd3);
  wire        w4       = (cur_mode == 4'd6) | (cur_mode == 4'd9);
  wire [3:0]  wm1      = w16 ? 4'd15 : (w4 ? 4'd3 : 4'd7);
  wire        cur_last = (cur_cnt == wm1);
  wire        half     = w16 ? cur_cnt[3] : (w4 ? cur_cnt[1] : cur_cnt[2]);
  wire [255:0] asc     = start ? a_scale : asc_q;
  wire [255:0] bsc     = start ? b_scale : bsc_q;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      in_blk <= 1'b0;
      cnt    <= 4'd0;
    end else if (beat) begin
      in_blk <= ~cur_last;
      cnt    <= cur_last ? 4'd0 : (cur_cnt + 4'd1);
    end
  end
  always_ff @(posedge clk) begin
    if (start) begin
      mode_q <= mode;
      id_q   <= in_block_id;
      asc_q  <= a_scale;
      bsc_q  <= b_scale;
    end
  end

  // ---------------------------------------------------------------------------
  // input register stage
  // ---------------------------------------------------------------------------
  logic          iv, i_first, i_last;
  logic [3:0]    i_mode;
  logic [1023:0] i_a, i_b;
  logic [127:0]  i_sa, i_sb;

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) iv <= 1'b0;
    else        iv <= beat;
  end
  always_ff @(posedge clk) begin
    if (beat) begin
      i_first <= start;
      i_last  <= cur_last;
      i_mode  <= cur_mode;
      i_a     <= a_data;
      i_b     <= b_data;
      for (int v = 0; v < 16; v++) begin
        i_sa[8*v +: 8] <= half ? asc[8*(2*v+1) +: 8] : asc[8*(2*v) +: 8];
        i_sb[8*v +: 8] <= half ? bsc[8*(2*v+1) +: 8] : bsc[8*(2*v) +: 8];
      end
    end
  end

  // ---------------------------------------------------------------------------
  // wavefront skew: row r of A is delayed r cycles, column c of B c cycles
  // ---------------------------------------------------------------------------
  logic [63:0] a_edge  [0:15];
  logic [14:0] at_edge [0:15];
  logic [63:0] b_edge  [0:15];
  logic [7:0]  bt_edge [0:15];

  for (genvar r = 0; r < 16; r++) begin : g_skew
    wire [78:0] a0 = {iv, i_first, i_last, i_mode, i_sa[8*r +: 8], i_a[64*r +: 64]};
    wire [71:0] b0 = {i_sb[8*r +: 8], i_b[64*r +: 64]};
    if (r == 0) begin : g_none
      assign a_edge[r]  = a0[63:0];
      assign at_edge[r] = a0[78:64];
      assign b_edge[r]  = b0[63:0];
      assign bt_edge[r] = b0[71:64];
    end else begin : g_chain
      logic [77:0] ad [1:r];
      logic        av [1:r];
      logic [71:0] bd [1:r];
      for (genvar k = 1; k <= r; k++) begin : g_stage
        if (k == 1) begin : g_first
          always_ff @(posedge clk) begin
            ad[k] <= a0[77:0];
            bd[k] <= b0;
          end
          always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) av[k] <= 1'b0;
            else        av[k] <= a0[78];
          end
        end else begin : g_next
          always_ff @(posedge clk) begin
            ad[k] <= ad[k-1];
            bd[k] <= bd[k-1];
          end
          always_ff @(posedge clk or negedge rst_n) begin
            if (!rst_n) av[k] <= 1'b0;
            else        av[k] <= av[k-1];
          end
        end
      end
      assign a_edge[r]  = ad[r][63:0];
      assign at_edge[r] = {av[r], ad[r][77:64]};
      assign b_edge[r]  = bd[r][63:0];
      assign bt_edge[r] = bd[r][71:64];
    end
  end

  // ---------------------------------------------------------------------------
  // 4x4 tiles of 4x4 PEs
  // ---------------------------------------------------------------------------
  logic [4*64-1:0]  ta  [0:3][0:4];
  logic [4*15-1:0]  tat [0:3][0:4];
  logic [4*64-1:0]  tb  [0:4][0:3];
  logic [4*8-1:0]   tbt [0:4][0:3];
  logic [16*64-1:0] tc  [0:3][0:3];

  for (genvar i = 0; i < 4; i++) begin : g_tedge
    for (genvar k = 0; k < 4; k++) begin : g_k
      assign ta[i][0][64*k +: 64]  = a_edge[4*i+k];
      assign tat[i][0][15*k +: 15] = at_edge[4*i+k];
      assign tb[0][i][64*k +: 64]  = b_edge[4*i+k];
      assign tbt[0][i][8*k +: 8]   = bt_edge[4*i+k];
    end
  end

  for (genvar tr = 0; tr < 4; tr++) begin : g_tr
    for (genvar tcx = 0; tcx < 4; tcx++) begin : g_tc
      mm_tile u_tile (
        .clk    (clk),
        .rst_n  (rst_n),
        .a_in   (ta[tr][tcx]),
        .at_in  (tat[tr][tcx]),
        .b_in   (tb[tr][tcx]),
        .bt_in  (tbt[tr][tcx]),
        .a_out  (ta[tr][tcx+1]),
        .at_out (tat[tr][tcx+1]),
        .b_out  (tb[tr+1][tcx]),
        .bt_out (tbt[tr+1][tcx]),
        .c_out  (tc[tr][tcx])
      );
    end
  end

  // ---------------------------------------------------------------------------
  // column de-skew: column c is delayed (15-c) cycles so that a whole row is
  // aligned in one cycle
  // ---------------------------------------------------------------------------
  logic [ROWW-1:0] row_al [0:15];

  for (genvar r = 0; r < 16; r++) begin : g_dr
    for (genvar c = 0; c < 16; c++) begin : g_dc
      wire [63:0]   res = tc[r/4][c/4][64*(4*(r%4)+(c%4)) +: 64];
      wire [RW-1:0] d0  = {&res[63:38], res[37:0]};
      if (c == 15) begin : g_none
        assign row_al[r][RW*c +: RW] = d0;
      end else begin : g_chain
        logic [RW-1:0] dd [0:14-c];
        always_ff @(posedge clk) begin
          dd[0] <= d0;
          for (int k = 1; k <= 14-c; k++) dd[k] <= dd[k-1];
        end
        assign row_al[r][RW*c +: RW] = dd[14-c];
      end
    end
  end

  // ---------------------------------------------------------------------------
  // block-end token delay line (which row of which block is aligned now)
  // ---------------------------------------------------------------------------
  logic [TKLEN-1:0] tkv;
  logic [15:0]      tkid [0:TKLEN-1];

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) tkv <= '0;
    else        tkv <= {tkv[TKLEN-2:0], (beat & cur_last)};
  end
  always_ff @(posedge clk) begin
    tkid[0] <= cur_id;
    for (int k = 1; k < TKLEN; k++) tkid[k] <= tkid[k-1];
  end

  // one row at most per group of four rows completes in a cycle
  logic [3:0]       lv;
  logic [SLOTW-1:0] lane [0:3];
  always_comb begin
    for (int g = 0; g < 4; g++) begin
      lv[g]   = 1'b0;
      lane[g] = '0;
      for (int k = 0; k < 4; k++) begin
        if (tkv[TK0 + 4*g + k]) begin
          lv[g]   = 1'b1;
          lane[g] = lane[g] | {4'(4*g + k), tkid[TK0 + 4*g + k], row_al[4*g + k]};
        end
      end
    end
  end

  // order-preserving compaction to the low slots
  logic [3:0]       pv;
  logic [SLOTW-1:0] pslot [0:3];
  always_comb begin
    logic [2:0] n;
    n  = 3'd0;
    pv = 4'd0;
    for (int s = 0; s < 4; s++) pslot[s] = '0;
    for (int g = 0; g < 4; g++) begin
      if (lv[g]) begin
        for (int s = 0; s < 4; s++) begin
          if (n == 3'(s)) begin
            pv[s]    = 1'b1;
            pslot[s] = lane[g];
          end
        end
        n = n + 3'd1;
      end
    end
  end

  // ---------------------------------------------------------------------------
  // output FIFO (one entry per arrival cycle, four slots), credit controlled
  // ---------------------------------------------------------------------------
  logic [4*SLOTW-1:0] fifo_d [0:DEPTH-1];
  logic [3:0]         fifo_v [0:DEPTH-1];
  logic [5:0]         wptr, rptr;

  wire push = |pv;
  wire pop  = out_ready & (fcount != 7'd0);

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      wptr   <= 6'd0;
      rptr   <= 6'd0;
      fcount <= 7'd0;
    end else begin
      if (push) wptr <= (wptr == 6'(DEPTH-1)) ? 6'd0 : (wptr + 6'd1);
      if (pop)  rptr <= (rptr == 6'(DEPTH-1)) ? 6'd0 : (rptr + 6'd1);
      fcount <= fcount + {6'd0, push} - {6'd0, pop};
    end
  end
  always_ff @(posedge clk) begin
    if (push) begin
      fifo_d[wptr] <= {pslot[3], pslot[2], pslot[1], pslot[0]};
      fifo_v[wptr] <= pv;
    end
  end

  wire [4*SLOTW-1:0] head_d = fifo_d[rptr];
  wire [3:0]         head_v = fifo_v[rptr];

  always_comb begin
    out_valid = (fcount != 7'd0) ? head_v : 4'd0;
    for (int s = 0; s < 4; s++) begin
      out_row[4*s +: 4]       = head_d[SLOTW*s + ROWW + 16 +: 4];
      out_block_id[16*s +: 16] = head_d[SLOTW*s + ROWW +: 16];
      for (int c = 0; c < 16; c++) begin
        out_data[1024*s + 64*c +: 64] =
            {{26{head_d[SLOTW*s + RW*c + 38]}}, head_d[SLOTW*s + RW*c +: 38]};
      end
    end
  end

endmodule
