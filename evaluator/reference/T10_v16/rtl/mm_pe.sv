// -----------------------------------------------------------------------------
// mm_pe : one processing element of the 16x16 output-stationary systolic array.
//
//   * registers and forwards the 64-bit A operand (to the right neighbour) and
//     the 64-bit B operand (to the neighbour below) together with a small token
//   * multiplies all lanes of the beat (4 x 16 bit, 8 x 8 bit or 16 x 4 bit)
//   * accumulates the beat EXACTLY in a local 584-bit two's complement
//     fixed-point accumulator (bit 0 = 2^-286 in floating modes, 2^0 in integer
//     modes) held as 19 chunks of 32 bits with lazily propagated carries
//   * converts the exact sum to INT64 / binary32 (truncation, exact overflow
//     decision) in a registered 64-bit result
//
// Token on the A path : {valid, first, last, mode[3:0], a_scale[7:0]}
// Token on the B path : {b_scale[7:0]}
//
// Pipeline (x = cycle in which the beat is present on a_in/b_in), every stage
// is short enough for a 1 ns clock in ASAP7 RVT / slow corner:
//   x    P0  multiplier operand select, block scale exponent (from a_in/b_in)
//   x+1  P1  partial products + carry-save trees, small-format decode
//   x+2  P2  product carry-propagate adds, fine lane shift, sign
//   x+3  P3  coarse lane shift + carry-save lane reduction
//   x+4  P4  beat sum / 16-bit lane alignment -> four accumulator slots
//   x+5  P5  slot placement + carry-save accumulation (feedback loop, no CPA)
//   x+6  P6  per-chunk add + chunk carry look-ahead (digits D, carries cin)
//   x+7  P7  sign, top-chunk select, exact sticky
//   x+8  P8  fine normalisation
//   x+9  P9  pack / exceptions                       -> c_out valid in x+10
// -----------------------------------------------------------------------------
module mm_pe (
  input  logic        clk,
  input  logic        rst_n,
  input  logic [63:0] a_in,
  input  logic [14:0] at_in,
  input  logic [63:0] b_in,
  input  logic [7:0]  bt_in,
  output logic [63:0] a_out,
  output logic [14:0] at_out,
  output logic [63:0] b_out,
  output logic [7:0]  bt_out,
  output logic [63:0] c_out
);
  localparam int NCH  = 19;                  // chunk 18 is the wrapping top chunk
  localparam int TOPW = 8;
  localparam int YW   = 104;
  localparam int PRE  = 1;                   // coarse lane-shift bits resolved in P2
  localparam int LPW  = 18 + 8*((1 << PRE) - 1);

  // ---------------------------------------------------------------------------
  // operand / token forwarding registers (one per hop)
  // ---------------------------------------------------------------------------
  logic [13:0] at_d;
  logic        at_v;
  always_ff @(posedge clk) begin
    a_out  <= a_in;
    b_out  <= b_in;
    at_d   <= at_in[13:0];
    bt_out <= bt_in;
  end
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) at_v <= 1'b0;
    else        at_v <= at_in[14];
  end
  assign at_out = {at_v, at_d};

  // ---------------------------------------------------------------------------
  // P0 : multiplier operand select (combinational from the PE inputs)
  // ---------------------------------------------------------------------------
  wire       v0      = at_in[14];
  wire [3:0] mode0   = at_in[11:8];
  wire       p0_int8  = v0 & (mode0 == 4'd0);
  wire       p0_int16 = v0 & (mode0 == 4'd1);
  wire       p0_fp16  = v0 & (mode0 == 4'd2);
  wire       p0_bf16  = v0 & (mode0 == 4'd3);

  wire       p0_e4m3  = v0 & ((mode0 == 4'd4) | (mode0 == 4'd7));
  wire       p0_e2m1  = v0 & ((mode0 == 4'd6) | (mode0 == 4'd9));
  wire       p0_mx    = v0 & ((mode0 == 4'd7) | (mode0 == 4'd8) | (mode0 == 4'd9));

  // block scale exponent: t = sa + sb + offset (accumulator LSB = 2^-286)
  wire [7:0] sae0  = p0_mx ? at_in[7:0] : 8'd127;
  wire [7:0] sbe0  = p0_mx ? bt_in      : 8'd127;
  wire [4:0] toff0 = p0_e4m3 ? 5'd14 : (p0_e2m1 ? 5'd30 : 5'd0);
  wire [9:0] t0    = (p0_int8 | p0_int16) ? 10'd0
                                          : ({2'b0, sae0} + {2'b0, sbe0} + {5'b0, toff0});

  logic signed [16:0] opa16_1 [0:3], opb16_1 [0:3];
  logic signed [8:0]  opa8_1  [0:3], opb8_1  [0:3];
  logic [9:0]         t_1;
  logic [7:0]         rm2_1;        // (t mod 32) - 2
  logic               snan_1;
  logic [6:0]         md_1;         // one-hot format class of the beat (0 when idle)
  always_ff @(posedge clk) begin
    md_1   <= {p0_e2m1, v0 & ((mode0 == 4'd5) | (mode0 == 4'd8)), p0_e4m3,
               p0_bf16, p0_fp16, p0_int16, p0_int8};
    t_1    <= t0;
    rm2_1  <= {3'b0, t0[4:0]} - 8'd2;
    snan_1 <= p0_mx & ((&at_in[7:0]) | (&bt_in));
  end

  always_ff @(posedge clk) begin
    for (int j = 0; j < 4; j++) begin
      logic [15:0] xa, xb;
      xa = a_in[16*j +: 16];
      xb = b_in[16*j +: 16];
      if (p0_int16) begin
        opa16_1[j] <= {xa[15], xa};
        opb16_1[j] <= {xb[15], xb};
      end else if (p0_fp16) begin
        opa16_1[j] <= {6'b0, |xa[14:10], xa[9:0]};
        opb16_1[j] <= {6'b0, |xb[14:10], xb[9:0]};
      end else if (p0_bf16) begin
        opa16_1[j] <= {9'b0, |xa[14:7], xa[6:0]};
        opb16_1[j] <= {9'b0, |xb[14:7], xb[6:0]};
      end else if (p0_int8) begin
        opa16_1[j] <= {{9{xa[7]}}, xa[7:0]};
        opb16_1[j] <= {{9{xb[7]}}, xb[7:0]};
      end else begin
        opa16_1[j] <= '0;
        opb16_1[j] <= '0;
      end
      if (p0_int8) begin
        opa8_1[j] <= {xa[15], xa[15:8]};
        opb8_1[j] <= {xb[15], xb[15:8]};
      end else begin
        opa8_1[j] <= '0;
        opb8_1[j] <= '0;
      end
    end
  end

  // control pipeline (valid-governing bits are asynchronously reset)
  logic [9:1] vld, fst, lst;
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      vld <= '0; fst <= '0; lst <= '0;
    end else begin
      vld <= {vld[8:1], v0};
      fst <= {fst[8:1], v0 & at_in[13]};
      lst <= {lst[8:1], v0 & at_in[12]};
    end
  end

  // ---------------------------------------------------------------------------
  // P1 : partial products + carry-save trees; decode of the small formats
  //      (sources: registered copies a_out / b_out / at_out / bt_out)
  // ---------------------------------------------------------------------------
  wire       m_int8  = md_1[0];
  wire       m_int16 = md_1[1];
  wire       m_fp16  = md_1[2];
  wire       m_bf16  = md_1[3];
  wire       m_e4m3  = md_1[4];
  wire       m_e5m2  = md_1[5];
  wire       m_e2m1  = md_1[6];
  wire       m_fp8   = m_e4m3 | m_e5m2;
  wire       m_ln16  = m_fp16 | m_bf16;
  wire [9:0] t1        = t_1;
  wire       scale_nan = snan_1;

  // 17x17 signed multipliers (INT16 / FP16 / BF16 / even INT8 lanes)
  // (Baugh-Wooley rows, products are taken mod 2^32 / 2^16)
  logic [17*32-1:0] pp16 [0:3];
  logic [9*16-1:0]  pp8  [0:3];
  logic [31:0]      cs16_s [0:3], cs16_c [0:3];
  logic [15:0]      cs8_s  [0:3], cs8_c  [0:3];
  always_comb begin
    for (int j = 0; j < 4; j++) begin
      logic [16:0] a, b;
      logic [8:0]  c, d;
      a = opa16_1[j];  b = opb16_1[j];
      c = opa8_1[j];   d = opb8_1[j];
      pp16[j] = '0;
      for (int i = 0; i < 16; i++) begin
        for (int k = 0; k < 16; k++) pp16[j][32*i + i + k] = a[k] & b[i];
        pp16[j][32*i + 16 + i] = ~(a[16] & b[i]);
        pp16[j][32*16 + 16 + i] = ~(b[16] & a[i]);
      end
      pp16[j][17] = 1'b1;                     // correction constant 2^17 (free slot of row 0)
      pp8[j] = '0;
      for (int i = 0; i < 8; i++) begin
        for (int k = 0; k < 8; k++) pp8[j][16*i + i + k] = c[k] & d[i];
        pp8[j][16*i + 8 + i] = ~(c[8] & d[i]);
        pp8[j][16*8 + 8 + i] = ~(d[8] & c[i]);
      end
      pp8[j][9] = 1'b1;                       // correction constant 2^9
    end
  end
  for (genvar j = 0; j < 4; j++) begin : g_mul
    mm_csa #(.N(17), .W(32)) u_csa16 (.rows(pp16[j]), .s(cs16_s[j]), .c(cs16_c[j]));
    mm_csa #(.N(9),  .W(16)) u_csa8  (.rows(pp8[j]),  .s(cs8_s[j]),  .c(cs8_c[j]));
  end

  // 16-bit float lanes: shift amount, sign, exceptions
  logic [9:0] sh16_p1 [0:3];
  logic [3:0] sg16_p1, nan16, pinf16, ninf16;
  always_comb begin
    for (int j = 0; j < 4; j++) begin
      logic [15:0] xa, xb;
      logic [7:0]  ea, eb;
      logic        za, zb, na, nb, ia, ib, zra, zrb, s;
      xa = a_out[16*j +: 16];
      xb = b_out[16*j +: 16];
      s  = xa[15] ^ xb[15];
      if (m_fp16) begin
        ea = {3'b0, xa[14:10]};  eb = {3'b0, xb[14:10]};
        na = (xa[14:10] == 5'h1f) & (xa[9:0] != 10'd0);
        nb = (xb[14:10] == 5'h1f) & (xb[9:0] != 10'd0);
        ia = (xa[14:10] == 5'h1f) & (xa[9:0] == 10'd0);
        ib = (xb[14:10] == 5'h1f) & (xb[9:0] == 10'd0);
      end else begin
        ea = xa[14:7];           eb = xb[14:7];
        na = (xa[14:7] == 8'hff) & (xa[6:0] != 7'd0);
        nb = (xb[14:7] == 8'hff) & (xb[6:0] != 7'd0);
        ia = (xa[14:7] == 8'hff) & (xa[6:0] == 7'd0);
        ib = (xb[14:7] == 8'hff) & (xb[6:0] == 7'd0);
      end
      za  = (ea == 8'd0);
      zb  = (eb == 8'd0);
      zra = (xa[14:0] == 15'd0);
      zrb = (xb[14:0] == 15'd0);
      nan16[j]  = m_ln16 & (na | nb | (ia & zrb) | (ib & zra));
      pinf16[j] = m_ln16 & (ia | ib) & ~s;
      ninf16[j] = m_ln16 & (ia | ib) &  s;
      sg16_p1[j] = m_ln16 & s;
      // FP16: 2^-48 -> +238 ; BF16: 2^-266 -> +20 ; minus 2 for the two "-1"s
      // (E + (E==0)) == E | (E==0); both formats are evaluated in parallel
      sh16_p1[j] = m_fp16
          ? ({5'b0, xa[14:11], xa[10] | ~|xa[14:10]} + {5'b0, xb[14:11], xb[10] | ~|xb[14:10]} + 10'd236)
          : ({2'b0, xa[14:8],  xa[7]  | ~|xa[14:7]}  + {2'b0, xb[14:8],  xb[7]  | ~|xb[14:7]}  + 10'd18);
    end
  end

  // 8-bit float lanes: 4x4 mantissa product, shift amount, sign, exceptions
  logic [7:0] fm_p1 [0:7];
  logic [6:0] sh8_p1 [0:7];
  logic [7:0] sg8_p1, nan8, pinf8, ninf8;
  always_comb begin
    for (int i = 0; i < 8; i++) begin
      logic [7:0] xa, xb;
      logic [4:0] ea, eb;
      logic [3:0] ma, mb;
      logic [7:0] shs;
      logic       za, zb, na, nb, ia, ib, zra, zrb, s;
      xa = a_out[8*i +: 8];
      xb = b_out[8*i +: 8];
      s  = xa[7] ^ xb[7];
      ea = m_e4m3 ? {1'b0, xa[6:3]} : xa[6:2];
      eb = m_e4m3 ? {1'b0, xb[6:3]} : xb[6:2];
      za = (ea == 5'd0);
      zb = (eb == 5'd0);
      zra = (xa[6:0] == 7'd0);
      zrb = (xb[6:0] == 7'd0);
      if (m_e4m3) begin
        na = (xa[6:0] == 7'h7f);  nb = (xb[6:0] == 7'h7f);
        ia = 1'b0;                ib = 1'b0;
        ma = {~za, xa[2:0]};      mb = {~zb, xb[2:0]};
      end else begin
        na = (xa[6:2] == 5'h1f) & (xa[1:0] != 2'd0);
        nb = (xb[6:2] == 5'h1f) & (xb[1:0] != 2'd0);
        ia = (xa[6:2] == 5'h1f) & (xa[1:0] == 2'd0);
        ib = (xb[6:2] == 5'h1f) & (xb[1:0] == 2'd0);
        ma = {1'b0, ~za, xa[1:0]}; mb = {1'b0, ~zb, xb[1:0]};
      end
      nan8[i]   = m_fp8 & (na | nb | (ia & zrb) | (ib & zra));
      pinf8[i]  = m_fp8 & (ia | ib) & ~s;
      ninf8[i]  = m_fp8 & (ia | ib) &  s;
      sg8_p1[i] = m_fp8 & s;
      fm_p1[i]  = m_fp8 ? (ma * mb) : 8'd0;
      // lane shift = ea' + eb' + (t mod 32), ea' = max(E,1)-1
      shs = {3'b0, ea[4:1], ea[0] | za} + {3'b0, eb[4:1], eb[0] | zb} + rm2_1;
      sh8_p1[i] = shs[6:0];
    end
  end

  // 4-bit lanes (E2M1): product with own shift, sign
  logic [7:0]  e2v_p1 [0:15];
  logic [15:0] e2s_p1;
  always_comb begin
    for (int n = 0; n < 16; n++) begin
      logic [3:0] xa, xb, pr;
      logic [1:0] ma, mb;
      logic [2:0] sh;
      xa = a_out[4*n +: 4];
      xb = b_out[4*n +: 4];
      ma = {|xa[2:1], xa[0]};
      mb = {|xb[2:1], xb[0]};
      pr = ma * mb;
      sh = {1'b0, xa[2:1]} + {1'b0, xb[2:1]} + {2'b0, ~|xa[2:1]} + {2'b0, ~|xb[2:1]} - 3'd2;
      e2v_p1[n] = m_e2m1 ? ({4'b0, pr} << sh) : 8'd0;
      e2s_p1[n] = m_e2m1 & (xa[3] ^ xb[3]);
    end
  end

  // ---- stage-2 registers ----
  logic [31:0] cs16s_2 [0:3], cs16c_2 [0:3];
  logic [15:0] cs8s_2  [0:3], cs8c_2  [0:3];
  logic [9:0]  sh16_2  [0:3];
  logic [3:0]  sg16_2;
  logic [7:0]  fm_2 [0:7];
  logic [6:0]  sh8_2 [0:7];
  logic [7:0]  sg8_2;
  logic [7:0]  e2v_2 [0:15];
  logic [15:0] e2s_2;
  logic [4:0]  r_2, q_2;
  logic        bnan_2, bpinf_2, bninf_2;
  logic        int8_2, int16_2, ln16_2, fp8_2, e2m1_2;

  always_ff @(posedge clk) begin
    for (int j = 0; j < 4; j++) begin
      cs16s_2[j] <= cs16_s[j];
      cs16c_2[j] <= cs16_c[j];
      cs8s_2[j]  <= cs8_s[j];
      cs8c_2[j]  <= cs8_c[j];
      sh16_2[j]  <= sh16_p1[j];
    end
    for (int i = 0; i < 8; i++) begin
      fm_2[i]  <= fm_p1[i];
      sh8_2[i] <= sh8_p1[i];
    end
    for (int n = 0; n < 16; n++) e2v_2[n] <= e2v_p1[n];
    e2s_2   <= e2s_p1;
    sg16_2  <= sg16_p1;
    sg8_2   <= sg8_p1;
    r_2     <= t1[4:0];
    q_2     <= t1[9:5];
    bnan_2  <= scale_nan | (|nan16) | (|nan8);
    bpinf_2 <= (|pinf16) | (|pinf8);
    bninf_2 <= (|ninf16) | (|ninf8);
    int8_2  <= m_int8;
    int16_2 <= m_int16;
    ln16_2  <= m_ln16;
    fp8_2   <= m_fp8;
    e2m1_2  <= m_e2m1;
  end

  // ---------------------------------------------------------------------------
  // P2 : carry-propagate adds (with folded negation), fine lane shift
  // ---------------------------------------------------------------------------
  logic [31:0]        prod16_p2 [0:3];
  logic [15:0]        prod8_p2  [0:3];
  logic signed [17:0] lane_p2   [0:7];
  logic [3:0]         ch_p2     [0:7];
  logic signed [LPW-1:0] lanex_p2 [0:7];   // lane pre-shifted by ch[PRE-1:0] bytes

  always_comb begin
    for (int j = 0; j < 4; j++) begin
      logic [16:0] lo, hi0, hi1;
      lo  = {1'b0, cs16s_2[j][15:0]}  + {1'b0, cs16c_2[j][15:0]};
      hi0 = {1'b0, cs16s_2[j][31:16]} + {1'b0, cs16c_2[j][31:16]};
      hi1 = {1'b0, cs16s_2[j][31:16]} + {1'b0, cs16c_2[j][31:16]} + 17'd1;
      prod16_p2[j] = {lo[16] ? hi1[15:0] : hi0[15:0], lo[15:0]};
      prod8_p2[j]  = cs8s_2[j] + cs8c_2[j];
    end
    for (int i = 0; i < 8; i++) begin
      logic signed [17:0] fv, ev;
      logic signed [8:0]  s0, s1;
      logic signed [9:0]  pr;
      logic [14:0]        fsh;
      // FP8 : +-(mantissa product << fine shift)
      fsh = {7'd0, fm_2[i]} << sh8_2[i][2:0];
      fv  = sg8_2[i] ? -$signed({3'b0, fsh}) : $signed({3'b0, fsh});
      // E2M1 : signed pair sum << fine shift
      s0  = e2s_2[2*i]   ? -$signed({1'b0, e2v_2[2*i]})   : $signed({1'b0, e2v_2[2*i]});
      s1  = e2s_2[2*i+1] ? -$signed({1'b0, e2v_2[2*i+1]}) : $signed({1'b0, e2v_2[2*i+1]});
      pr  = s0 + s1;
      ev  = $signed({{8{pr[9]}}, pr}) <<< r_2[2:0];
      if (fp8_2) begin
        lane_p2[i] = fv;
        ch_p2[i]   = sh8_2[i][6:3];
      end else if (e2m1_2) begin
        lane_p2[i] = ev;
        ch_p2[i]   = {2'b0, r_2[4:3]};
      end else if (int8_2) begin
        lane_p2[i] = (i % 2 == 0) ? $signed({{2{prod16_p2[i/2][15]}}, prod16_p2[i/2][15:0]})
                                  : $signed({{2{prod8_p2[i/2][15]}}, prod8_p2[i/2]});
        ch_p2[i]   = 4'd0;
      end else begin
        lane_p2[i] = '0;
        ch_p2[i]   = 4'd0;
      end
      lanex_p2[i] = $signed({{(LPW-18){lane_p2[i][17]}}, lane_p2[i]}) <<< {ch_p2[i][PRE-1:0], 3'b000};
    end
  end

  // Sign-extension-free lane placement.  A signed LPW-bit lane v placed at bit
  // 16*c equals  {~v[LPW-1], v[LPW-2:0]} << 16c  -  2^(LPW-1+16c).  The second
  // terms of all lanes are collected in one row K = sum_c cnt_c * 2^(LPW-1+16c)
  // (cnt_c = number of lanes at position c, at most 8 -> 4-bit fields that never
  // overlap); the lane tree then adds ~K and a +1 in the free carry-row bit 0.
  logic [5:0] ohc_p2  [0:7];
  logic [3:0] kcnt_p2 [0:4];
  always_comb begin
    for (int i = 0; i < 8; i++)
      for (int c = 0; c < 6; c++)
        ohc_p2[i][c] = ~int16_2 & (ch_p2[i][3:PRE] == 3'(c));
    for (int c = 0; c < 5; c++) begin
      kcnt_p2[c] = 4'd0;
      for (int i = 0; i < 8; i++) kcnt_p2[c] = kcnt_p2[c] + {3'd0, ohc_p2[i][c]};
    end
  end

  logic [31:0]        prod16_3 [0:3];
  logic signed [LPW-1:0] lane_3 [0:7];
  logic [5:0]         ohc_3    [0:7];
  logic [3:0]         kcnt_3   [0:4];
  logic [9:0]         sh16_3   [0:3];
  logic [4:0]         q_3;
  logic               int16_3, ln16_3, int_3;
  logic [3:0]         sg16_3;
  logic               f_nan, f_pinf, f_ninf;

  always_ff @(posedge clk) begin
    for (int j = 0; j < 4; j++) begin
      prod16_3[j] <= prod16_p2[j];
      sh16_3[j]   <= sh16_2[j];
    end
    for (int i = 0; i < 8; i++) begin
      lane_3[i] <= {~lanex_p2[i][LPW-1], lanex_p2[i][LPW-2:0]};
      ohc_3[i]  <= ohc_p2[i];
    end
    for (int c = 0; c < 5; c++) kcnt_3[c] <= kcnt_p2[c];
    q_3     <= q_2;
    sg16_3  <= sg16_2;
    int16_3 <= int16_2;
    ln16_3  <= ln16_2;
    int_3   <= int8_2 | int16_2;
    // sticky exception flags of the running block
    if (vld[2]) begin
      f_nan  <= (fst[2] ? 1'b0 : f_nan)  | bnan_2;
      f_pinf <= (fst[2] ? 1'b0 : f_pinf) | bpinf_2;
      f_ninf <= (fst[2] ? 1'b0 : f_ninf) | bninf_2;
    end
  end

  // ---------------------------------------------------------------------------
  // P3 : coarse lane shift + carry-save reduction of the eight lanes
  // ---------------------------------------------------------------------------
  logic [9*YW-1:0] nrows;
  logic [YW-1:0]   ys_p3, yc_p3;
  always_comb begin
    logic [YW-1:0] krow;
    for (int i = 0; i < 8; i++) begin
      logic [YW+LPW-1:0] row;
      row = '0;
      for (int c = 0; c < 6; c++)
        if (ohc_3[i][c]) row = row | ((YW+LPW)'(unsigned'(lane_3[i])) << (16*c));
      if (int16_3 && i < 4)
        row[31:0] = row[31:0] | {~prod16_3[i%4][31], prod16_3[i%4][30:0]};
      nrows[YW*i +: YW] = row[YW-1:0];
    end
    // ~K : INT16 uses four 32-bit rows -> K = 4 * 2^31 = 2^33
    krow = '1;
    for (int c = 0; c < 5; c++) krow[LPW-1+16*c +: 4] = ~kcnt_3[c];
    krow[33] = ~int16_3;
    nrows[YW*8 +: YW] = krow;
  end
  mm_csa #(.N(9), .W(YW)) u_csay (.rows(nrows), .s(ys_p3), .c(yc_p3));

  logic signed [24:0] sv_p3 [0:3];
  always_comb begin
    for (int j = 0; j < 4; j++)
      sv_p3[j] = sg16_3[j] ? -$signed({3'b0, prod16_3[j][21:0]}) : $signed({3'b0, prod16_3[j][21:0]});
  end

  logic [YW-1:0] ys_4, yc_4;
  logic [4:0]    q_4;
  logic          ln16_4, int_4;
  logic [2:0]    fl_4;
  always_ff @(posedge clk) begin
    if (ln16_3) begin
      // 16-bit float lanes bypass the lane tree: {signed product, shift}
      ys_4 <= {4'd0, sv_p3[3], sv_p3[2], sv_p3[1], sv_p3[0]};
      yc_4 <= {64'd0, sh16_3[3], sh16_3[2], sh16_3[1], sh16_3[0]};
    end else begin
      ys_4 <= ys_p3;
      yc_4 <= {yc_p3[YW-1:1], 1'b1};        // carry row bit 0 is free: -K = ~K + 1
    end
    q_4    <= q_3;
    ln16_4 <= ln16_3;
    int_4  <= int_3;
    fl_4   <= {f_nan, f_pinf, f_ninf};
  end

  // ---------------------------------------------------------------------------
  // P4 : beat sum (narrow formats) / fine alignment (16-bit float lanes)
  //      -> four slots {neg, hi[31:0], lo[31:0]} at chunk index q
  // ---------------------------------------------------------------------------
  logic [31:0]    lo_p4 [0:3], hi_p4 [0:3];
  logic [4:0]     sq_p4 [0:3];
  logic [3:0]     neg_p4;
  logic [NCH-1:0] oh_p4 [0:3], th_p4 [0:3];
  always_comb begin
    logic [YW-1:0] y;
    y = ys_4 + yc_4;
    for (int p = 0; p < 4; p++) begin
      logic signed [56:0] lv;
      lv = $signed({{32{ys_4[25*p+24]}}, ys_4[25*p +: 25]}) <<< yc_4[10*p +: 5];
      if (ln16_4) begin
        lo_p4[p]  = lv[31:0];
        hi_p4[p]  = {{7{lv[56]}}, lv[56:32]};
        neg_p4[p] = lv[56];
        sq_p4[p]  = yc_4[10*p+5 +: 5];
      end else if (p == 0) begin
        lo_p4[p]  = y[31:0];
        hi_p4[p]  = y[63:32];
        neg_p4[p] = 1'b0;
        sq_p4[p]  = q_4;
      end else if (p == 1) begin
        lo_p4[p]  = y[95:64];
        hi_p4[p]  = {{24{y[103]}}, y[103:96]};
        neg_p4[p] = y[103];
        sq_p4[p]  = q_4 + 5'd2;
      end else begin
        lo_p4[p]  = '0;
        hi_p4[p]  = '0;
        neg_p4[p] = 1'b0;
        sq_p4[p]  = '0;
      end
      for (int j = 0; j < NCH; j++) begin
        oh_p4[p][j] = vld[4] & (sq_p4[p] == 5'(j));
        th_p4[p][j] = vld[4] & neg_p4[p] & ({1'b0, sq_p4[p]} + 6'd2 <= 6'(j));
      end
    end
  end

  logic [31:0]    lo_5 [0:3], hi_5 [0:3];
  logic [NCH-1:0] oh_5 [0:3], th_5 [0:3];
  logic           int_5;
  logic [2:0]     fl_5;
  always_ff @(posedge clk) begin
    for (int p = 0; p < 4; p++) begin
      lo_5[p] <= lo_p4[p];
      hi_5[p] <= hi_p4[p];
      oh_5[p] <= oh_p4[p];
      th_5[p] <= th_p4[p];
    end
    int_5 <= int_4;
    fl_5  <= fl_4;
  end

  // ---------------------------------------------------------------------------
  // P5 : slot placement (non-negative digits: negative slots are sign-extended
  //      with all-ones chunks) and exact carry-save accumulation.  The loop
  //      contains only 3:2 counters; the accumulator is the pair (acc_s, acc_c).
  // ---------------------------------------------------------------------------
  localparam int XW = 32*(NCH-1) + TOPW;      // 584

  logic [XW-1:0]   acc_s, acc_c, nxt_s, nxt_c;
  logic [6*XW-1:0] arow;
  always_comb begin
    for (int p = 0; p < 4; p++) begin
      for (int j = 0; j < NCH; j++) begin
        logic [31:0] d;
        d = ({32{oh_5[p][j]}} & lo_5[p]) | {32{th_5[p][j]}};
        if (j > 0) d = d | ({32{oh_5[p][(j == 0) ? 0 : j-1]}} & hi_5[p]);
        if (j == NCH-1) arow[XW*p + 32*j +: TOPW] = d[TOPW-1:0];
        else            arow[XW*p + 32*j +: 32]   = d;
      end
    end
    arow[XW*4 +: XW] = fst[5] ? '0 : acc_s;
    arow[XW*5 +: XW] = fst[5] ? '0 : acc_c;
  end
  mm_csa #(.N(6), .W(XW)) u_csaacc (.rows(arow), .s(nxt_s), .c(nxt_c));

  logic       int_6;
  logic [2:0] fl_6;
  always_ff @(posedge clk) begin
    acc_s <= nxt_s;
    acc_c <= nxt_c;
    int_6 <= int_5;
    fl_6  <= fl_5;
  end

  // ---------------------------------------------------------------------------
  // P6 : per-chunk add (digit D) and chunk-level carry look-ahead (cin)
  //      exact value  X[32j +: 32] = D[j] + cin[j]  (mod 2^32)
  // ---------------------------------------------------------------------------
  logic [31:0]    d_p6 [0:NCH-1];
  logic [NCH-1:0] g_p6, p_p6, cin_p6, dz_p6, do_p6, dfe_p6;
  always_comb begin
    for (int j = 0; j < NCH; j++) begin
      logic [31:0] a, b;
      logic [16:0] lo, hi0, hi1;
      logic [31:0] tg, tp;
      a = '0; b = '0;
      if (j == NCH-1) begin
        a[TOPW-1:0] = acc_s[32*j +: TOPW];
        b[TOPW-1:0] = acc_c[32*j +: TOPW];
      end else begin
        a = acc_s[32*j +: 32];
        b = acc_c[32*j +: 32];
      end
      // digits: 16/16 carry-select add
      lo  = {1'b0, a[15:0]}  + {1'b0, b[15:0]};
      hi0 = {1'b0, a[31:16]} + {1'b0, b[31:16]};
      hi1 = {1'b0, a[31:16]} + {1'b0, b[31:16]} + 17'd1;
      d_p6[j] = {lo[16] ? hi1[15:0] : hi0[15:0], lo[15:0]};
      // chunk generate / propagate : balanced (g,p) reduction tree, depth 5
      tg = a & b;
      tp = a ^ b;
      for (int w = 32; w > 1; w = w / 2)
        for (int k = 0; k < w / 2; k++) begin
          tg[k] = tg[2*k+1] | (tp[2*k+1] & tg[2*k]);
          tp[k] = tp[2*k+1] & tp[2*k];
        end
      // early "a + b == K" detectors (no carry propagation needed):
      //   K = 0          : p[0] = 0 and p[i+1] == (a[i] | b[i])
      //   K = 0xFFFFFFFF : p == all ones
      //   K = 0xFFFFFFFE : p[0] = 0 and p[i+1] == ~(a[i] & b[i])
      begin
        logic [31:0] px, orx, andx;
        px   = a ^ b;
        orx  = a | b;
        andx = a & b;
        dz_p6[j]  = ~px[0] & (px[31:1] == orx[30:0]);
        do_p6[j]  = &px;
        dfe_p6[j] = ~px[0] & (px[31:1] == ~andx[30:0]);
      end
      if (j == NCH-1) begin
        g_p6[j] = 1'b0;
        p_p6[j] = 1'b0;
      end else begin
        g_p6[j] = tg[0];
        p_p6[j] = tp[0];
      end
    end
  end
  always_comb begin
    logic [NCH-1:0] g, p;
    g = g_p6;
    p = p_p6;
    for (int d = 1; d < NCH; d = d * 2) begin
      g = g | (p & (g << d));
      p = p & (p << d);
    end
    cin_p6 = g << 1;
  end
  // top chunk: sign / all-zero / all-one flags for both values of its carry-in
  logic [7:0] dt_p6;
  logic [4:0] tf_p6;       // {s(cin=1), s(cin=0), D==FE, D==FF, D==00}
  always_comb begin
    dt_p6 = d_p6[NCH-1][TOPW-1:0];
    tf_p6 = {dt_p6[7] ^ (&dt_p6[6:0]), dt_p6[7], dt_p6 == 8'hfe, dt_p6 == 8'hff, dt_p6 == 8'h00};
  end

  logic [31:0]    d_7 [0:NCH-1];
  logic [NCH-1:0] cin_7, dz_7, do_7, dfe_7;
  logic           int_7;
  logic [2:0]     fl_7;
  logic [4:0]     tf_7;
  always_ff @(posedge clk) begin
    tf_7 <= tf_p6;
    for (int j = 0; j < NCH; j++) begin
      d_7[j]   <= d_p6[j];
      dz_7[j]  <= dz_p6[j];
      do_7[j]  <= do_p6[j];
      dfe_7[j] <= dfe_p6[j];
    end
    cin_7 <= cin_p6;
    int_7 <= int_6;
    fl_7  <= fl_6;
  end

  // ---------------------------------------------------------------------------
  // P7 : sign, top non-fill chunk, 64-bit window {X[t], X[t-1]}, exact sticky
  //      chunk 12 holds bits 384..415  (2^127 <-> bit 413, 2^-126 <-> bit 160)
  // ---------------------------------------------------------------------------
  logic [31:0]    x7 [0:12];
  logic [NCH-1:0] xz7, xo7, fill7, nfge7;
  logic           s7, big7, small7, sticky7;
  logic [63:0]    win7;
  logic [3:0]     tsel7;
  always_comb begin
    for (int j = 0; j <= 12; j++) x7[j] = d_7[j] + {31'd0, cin_7[j]};
    s7  = cin_7[NCH-1] ? tf_7[4] : tf_7[3];
    for (int j = 0; j < NCH-1; j++) begin
      xz7[j] = cin_7[j] ? do_7[j]  : dz_7[j];
      xo7[j] = cin_7[j] ? dfe_7[j] : do_7[j];
    end
    xz7[NCH-1] = cin_7[NCH-1] ? tf_7[1] : tf_7[0];
    xo7[NCH-1] = cin_7[NCH-1] ? tf_7[2] : tf_7[1];
    fill7 = s7 ? xo7 : xz7;
    // nfge7[j] : some chunk >= j is not sign fill
    for (int j = 0; j < NCH; j++) nfge7[j] = |(~fill7 >> j);
    big7   = nfge7[13];
    small7 = ~nfge7[4];
    win7   = '0;
    tsel7  = '0;
    for (int j = 4; j <= 12; j++) begin
      if (~fill7[j] & ~nfge7[j+1]) begin
        win7  = win7 | {x7[j], x7[j-1]};
        tsel7 = tsel7 | 4'(j - 4);
      end
    end
    sticky7 = 1'b0;
    for (int j = 0; j <= 10; j++) sticky7 = sticky7 | (~xz7[j] & nfge7[j+2]);
  end

  logic [63:0] win_9;
  logic [3:0]  tsel_9;
  logic        s_9, big_9, small_9, sticky_9, int_9;
  logic [2:0]  fl_9;
  always_ff @(posedge clk) begin
    if (lst[7]) begin
      win_9    <= int_7 ? {x7[1], x7[0]} : win7;
      tsel_9   <= tsel7;
      s_9      <= s7;
      big_9    <= big7;
      small_9  <= small7;
      sticky_9 <= sticky7;
      int_9    <= int_7;
      fl_9     <= fl_7;
    end
  end

  // ---------------------------------------------------------------------------
  // P8 : fine normalisation of the window
  // ---------------------------------------------------------------------------
  function automatic logic [4:0] clz32(input logic [31:0] x);
    logic [31:0] v;
    logic [4:0]  c [0:31];
    int n;
    for (int i = 0; i < 32; i++) begin
      v[i] = x[31-i];
      c[i] = '0;
    end
    n = 32;
    for (int k = 0; k < 5; k++) begin
      n = n / 2;
      for (int i = 0; i < n; i++) begin
        logic vu, vl;
        logic [4:0] cu, cl;
        vu = v[2*i]; vl = v[2*i+1];
        cu = c[2*i]; cl = c[2*i+1];
        v[i] = vu | vl;
        c[i] = vu ? cu : (cl | (5'd1 << k));
      end
    end
    return c[0];
  endfunction

  logic [37:0] r_10;
  logic        s_10, big_10, small_10, int_10;
  logic [2:0]  fl_10;
  always_ff @(posedge clk) begin
    logic [63:0] z, ws, zs;
    logic [4:0]  lz;
    logic [8:0]  e;
    logic [23:0] mant;
    logic        den, st, inc;
    z    = win_9 ^ {64{s_9}};
    lz   = clz32(z[63:32]);
    den  = (tsel_9 == 4'd0);
    ws   = win_9 << lz;
    zs   = ws ^ {64{s_9}};
    mant = den ? {1'b0, z[63:41]} : zs[63:40];
    e    = den ? 9'd0 : ({tsel_9, 5'd0} - {4'd0, lz});
    st   = sticky_9 | (den ? (|win_9[40:0]) : (|ws[39:0]));   // discarded bits of X
    // negative values: |X| = ~X + 1.  The +1 reaches the kept mantissa only if
    // every discarded bit of X is zero.
    inc  = s_9 & ~st;
    r_10     <= int_9 ? win_9[37:0] : {3'd0, inc, st, e, mant};
    s_10     <= s_9;
    big_10   <= big_9;
    small_10 <= small_9;
    int_10   <= int_9;
    fl_10    <= fl_9;
  end

  // ---------------------------------------------------------------------------
  // P9 : pack.  Conversion truncates the exact magnitude toward zero (exact
  //      whenever the sum is representable); overflow decided exactly:
  //       S > MAX  <=> e >= 255, or e == 254 with an all-ones mantissa of the
  //       ones' complement and (positive: any lower bit set | negative: always,
  //       since |X| = ~X + 1).  The magnitude increment of a negative value is
  //       folded into the {exponent, fraction} field add.
  // ---------------------------------------------------------------------------
  logic [37:0] c_reg;
  logic        c_ext;
  always_ff @(posedge clk) begin
    logic [23:0] mant;
    logic [8:0]  e;
    logic        st, ovf;
    mant = r_10[23:0];
    e    = r_10[32:24];
    st   = r_10[33];
    ovf  = big_10 | (~small_10 & ((e >= 9'd255) | ((e == 9'd254) & (&mant) & (s_10 | st))));
    if (int_10) begin
      c_reg <= r_10;
      c_ext <= r_10[37];
    end else begin
      c_ext <= 1'b0;
      if (fl_10[2] | (fl_10[1] & fl_10[0])) c_reg <= {6'b0, 32'h7fc0_0000};
      else if (fl_10[1])                    c_reg <= {6'b0, 32'h7f80_0000};
      else if (fl_10[0])                    c_reg <= {6'b0, 32'hff80_0000};
      else if (ovf)                         c_reg <= {6'b0, s_10, 8'hff, 23'd0};
      else if (small_10)                    c_reg <= {6'b0, s_10, 31'd0};
      else                                  c_reg <= {6'b0, s_10, {e[7:0], mant[22:0]} + {30'd0, r_10[34]}};
    end
  end
  assign c_out = {{26{c_ext}}, c_reg};

endmodule
