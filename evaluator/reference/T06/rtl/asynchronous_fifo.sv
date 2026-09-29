module asynchronous_fifo #(
  parameter int WIDTH = 8,
  parameter int DEPTH = 8
) (
  input  logic             wr_clk,
  input  logic             wr_rst_n,
  input  logic             wr_valid,
  output logic             wr_ready,
  input  logic [WIDTH-1:0] wr_data,
  input  logic             rd_clk,
  input  logic             rd_rst_n,
  output logic             rd_valid,
  input  logic             rd_ready,
  output logic [WIDTH-1:0] rd_data
);
  localparam int ADDR_W = $clog2(DEPTH);
  localparam int PTR_W  = ADDR_W + 1;

  logic [WIDTH-1:0] mem [0:DEPTH-1];
  logic [PTR_W-1:0] wr_bin, wr_gray, rd_bin, rd_gray;
  logic [PTR_W-1:0] wr_bin_next, wr_gray_next;
  logic [PTR_W-1:0] rd_bin_next, rd_gray_next;
  (* ASYNC_REG = "TRUE" *) logic [PTR_W-1:0] rd_gray_sync1, rd_gray_sync2;
  (* ASYNC_REG = "TRUE" *) logic [PTR_W-1:0] wr_gray_sync1, wr_gray_sync2;
  logic full, empty, full_next, empty_next;

  assign wr_bin_next  = wr_bin + (wr_valid && wr_ready);
  assign wr_gray_next = (wr_bin_next >> 1) ^ wr_bin_next;
  assign rd_bin_next  = rd_bin + (rd_valid && rd_ready);
  assign rd_gray_next = (rd_bin_next >> 1) ^ rd_bin_next;

  assign full_next = wr_gray_next == {
    ~rd_gray_sync2[PTR_W-1:PTR_W-2], rd_gray_sync2[PTR_W-3:0]
  };
  assign empty_next = rd_gray_next == wr_gray_sync2;
  assign wr_ready = !full;
  assign rd_valid = !empty;
  assign rd_data = mem[rd_bin[ADDR_W-1:0]];

  always_ff @(posedge wr_clk or negedge wr_rst_n) begin
    if (!wr_rst_n) begin
      wr_bin  <= '0;
      wr_gray <= '0;
      full    <= 1'b0;
    end else begin
      wr_bin  <= wr_bin_next;
      wr_gray <= wr_gray_next;
      full    <= full_next;
      if (wr_valid && wr_ready)
        mem[wr_bin[ADDR_W-1:0]] <= wr_data;
    end
  end

  always_ff @(posedge rd_clk or negedge rd_rst_n) begin
    if (!rd_rst_n) begin
      rd_bin  <= '0;
      rd_gray <= '0;
      empty   <= 1'b1;
    end else begin
      rd_bin  <= rd_bin_next;
      rd_gray <= rd_gray_next;
      empty   <= empty_next;
    end
  end

  always_ff @(posedge wr_clk or negedge wr_rst_n) begin
    if (!wr_rst_n) begin
      rd_gray_sync1 <= '0;
      rd_gray_sync2 <= '0;
    end else begin
      rd_gray_sync1 <= rd_gray;
      rd_gray_sync2 <= rd_gray_sync1;
    end
  end

  always_ff @(posedge rd_clk or negedge rd_rst_n) begin
    if (!rd_rst_n) begin
      wr_gray_sync1 <= '0;
      wr_gray_sync2 <= '0;
    end else begin
      wr_gray_sync1 <= wr_gray;
      wr_gray_sync2 <= wr_gray_sync1;
    end
  end
endmodule
