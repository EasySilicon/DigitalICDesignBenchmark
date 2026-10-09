module round_robin_stream_arbiter #(
  parameter int N = 4,
  parameter int WIDTH = 8
)(
  input  logic clk, rst_n,
  input  logic [N-1:0] in_valid,
  output logic [N-1:0] in_ready,
  input  logic [N-1:0][WIDTH-1:0] in_data,
  output logic out_valid,
  input  logic out_ready,
  output logic [WIDTH-1:0] out_data,
  output logic [$clog2(N)-1:0] out_id
);
  localparam int ID_W = $clog2(N);
  logic [ID_W-1:0] search_start;
  logic [N-1:0] eligible, candidates, grant, selected;
  logic [N-1:0] locked_grant;
  logic locked;

  always_comb begin
    logic seen;
    eligible = in_valid & ({N{1'b1}} << search_start);
    candidates = (|eligible) ? eligible : in_valid;
    grant = '0;
    seen = 1'b0;
    for (int i = 0; i < N; i++) begin
      grant[i] = candidates[i] && !seen;
      seen |= candidates[i];
    end
    selected = locked ? locked_grant : grant;
    out_valid = locked || (|in_valid);
    out_id = '0;
    out_data = '0;
    for (int i = 0; i < N; i++) begin
      out_id |= ID_W'(i) & {ID_W{selected[i]}};
      out_data |= in_data[i] & {WIDTH{selected[i]}};
    end
    in_ready = selected & {N{out_ready}};
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      search_start <= '0;
      locked_grant <= '0;
      locked <= 1'b0;
    end else if (out_valid && out_ready) begin
      search_start <= out_id + 1'b1;
      locked <= 1'b0;
    end else if (out_valid && !locked) begin
      locked_grant <= selected;
      locked <= 1'b1;
    end
  end
endmodule
