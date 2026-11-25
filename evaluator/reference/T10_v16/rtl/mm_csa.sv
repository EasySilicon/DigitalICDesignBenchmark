// -----------------------------------------------------------------------------
// mm_csa : carry-save (3:2 counter) reduction of N W-bit rows to two rows.
//          sum + carry == sum of all rows (mod 2^W).  Purely combinational.
// -----------------------------------------------------------------------------
module mm_csa #(
  parameter int N = 9,
  parameter int W = 32
) (
  input  logic [N*W-1:0] rows,
  output logic [W-1:0]   s,
  output logic [W-1:0]   c
);
  localparam int LV = 8;

  function automatic int nxt(input int n);
    return (n <= 2) ? n : (2 * (n / 3) + (n % 3));
  endfunction
  function automatic int cnt(input int lvl);
    int n;
    n = N;
    for (int i = 0; i < lvl; i++) n = nxt(n);
    return n;
  endfunction

  logic [W-1:0] r [0:LV][0:N-1];

  for (genvar i = 0; i < N; i++) begin : g_in
    assign r[0][i] = rows[i*W +: W];
  end

  for (genvar l = 0; l < LV; l++) begin : g_lvl
    localparam int NIN = cnt(l);
    localparam int G   = (NIN > 2) ? (NIN / 3) : 0;
    localparam int REM = NIN - 3 * G;
    for (genvar g = 0; g < G; g++) begin : g_fa
      wire [W-1:0] x = r[l][3*g];
      wire [W-1:0] y = r[l][3*g+1];
      wire [W-1:0] z = r[l][3*g+2];
      wire [W-1:0] m = (x & y) | (x & z) | (y & z);
      assign r[l+1][2*g]   = x ^ y ^ z;
      assign r[l+1][2*g+1] = {m[W-2:0], 1'b0};
    end
    for (genvar k = 0; k < REM; k++) begin : g_pass
      assign r[l+1][2*G+k] = r[l][3*G+k];
    end
    for (genvar k = 2*G + REM; k < N; k++) begin : g_zero
      assign r[l+1][k] = '0;
    end
  end

  assign s = r[LV][0];
  assign c = (cnt(LV) > 1) ? r[LV][1] : '0;
endmodule
