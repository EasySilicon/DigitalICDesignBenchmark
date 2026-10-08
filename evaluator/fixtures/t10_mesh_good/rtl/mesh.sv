module mesh_cell (
    input  wire        clk,
    input  wire        rst_n,
    input  wire [63:0] left_data,
    input  wire [63:0] top_data,
    output reg  [63:0] right_data,
    output reg  [63:0] bottom_data,
    output reg  [63:0] local_sum
);
    always @(posedge clk or negedge rst_n) begin
        if (!rst_n) begin
            right_data  <= 64'b0;
            bottom_data <= 64'b0;
            local_sum   <= 64'b0;
        end else begin
            right_data  <= left_data;
            bottom_data <= top_data;
            local_sum   <= local_sum + left_data * top_data;
        end
    end
endmodule

module npu_systolic_matmul_16x16 (
    input  wire          clk,
    input  wire          rst_n,
    input  wire          in_valid,
    output wire          in_ready,
    input  wire          in_start,
    input  wire [15:0]   in_block_id,
    input  wire [3:0]    mode,
    input  wire [255:0]  a_scale,
    input  wire [255:0]  b_scale,
    input  wire [1023:0] a_data,
    input  wire [1023:0] b_data,
    input  wire          out_ready,
    output wire [3:0]    out_valid,
    output wire [63:0]   out_block_id,
    output wire [15:0]   out_row,
    output reg  [4095:0] out_data
);
    assign in_ready = 1'b1;
    assign out_valid = {4{in_valid}};
    assign out_block_id = {4{in_block_id}};
    assign out_row = {4{in_block_id[3:0]}};
    wire [63:0] a_link [0:15][0:15];
    wire [63:0] b_link [0:15][0:15];
    wire [63:0] sums [0:15][0:15];
    for (genvar r=0; r<16; r=r+1) begin : row_grid
        for (genvar c=0; c<16; c=c+1) begin : col_grid
            wire [63:0] a_in, b_in;
            if (c == 0) assign a_in = a_data[r*64 +: 64];
            else        assign a_in = a_link[r][c-1];
            if (r == 0) assign b_in = b_data[c*64 +: 64];
            else        assign b_in = b_link[r-1][c];
            mesh_cell cell_i (
                .clk(clk), .rst_n(rst_n),
                .left_data(a_in), .top_data(b_in),
                .right_data(a_link[r][c]),
                .bottom_data(b_link[r][c]),
                .local_sum(sums[r][c])
            );
        end
    end
    always @* begin
        out_data = 4096'b0;
        for (integer s=0; s<4; s=s+1)
            for (integer c=0; c<16; c=c+1)
                out_data[s*1024+c*64 +: 64] = sums[in_block_id[3:0]][c];
    end
endmodule
