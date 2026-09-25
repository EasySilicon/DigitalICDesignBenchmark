`timescale 1ns/1ps
module tb_T10;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic cmd_valid = 0;
  logic cmd_ready;
  logic [3:0] mode = 0;
  logic [1023:0] a_data = 0, b_data = 0;
  logic [63:0] a_scale = 0, b_scale = 0;
  logic rsp_valid;
  logic rsp_ready = 0;
  logic [1023:0] c_data;

  npu_systolic_matmul_4x4 dut (.*);

  function automatic int element_width(input int m);
    if (m == 1 || m == 2 || m == 3) return 16;
    if (m == 6 || m == 9) return 4;
    return 8;
  endfunction

  function automatic logic [15:0] one_code(input int m, input bit negative);
    logic [15:0] code;
    case (m)
      0: code = negative ? 16'h00ff : 16'h0001;
      1: code = negative ? 16'hffff : 16'h0001;
      2: code = negative ? 16'hbc00 : 16'h3c00;
      3: code = negative ? 16'hbf80 : 16'h3f80;
      4,7: code = negative ? 16'h00b8 : 16'h0038;
      5,8: code = negative ? 16'h00bc : 16'h003c;
      6,9: code = negative ? 16'h000a : 16'h0002;
      default: $fatal(1, "invalid mode");
    endcase
    return code;
  endfunction

  task automatic prepare_matrix(input int m, input bit last_only);
    int w, k_count;
    logic [15:0] code;
    w = element_width(m);
    k_count = 1024 / (4*w);
    a_data = '0;
    b_data = '0;
    a_scale = {8{8'd127}};
    b_scale = {8{8'd127}};
    for (int r = 0; r < 4; r++) begin
      for (int k = 0; k < k_count; k++) begin
        if (!last_only || k == k_count-1) begin
          code = one_code(m, last_only && (r[0] != 0));
          for (int bit_idx=0; bit_idx<w; bit_idx++)
            a_data[(r*k_count+k)*w+bit_idx] = code[bit_idx];
        end
      end
    end
    for (int c = 0; c < 4; c++) begin
      for (int k = 0; k < k_count; k++) begin
        if (!last_only || k == k_count-1) begin
          code = one_code(m, last_only && (c[0] != 0));
          for (int bit_idx=0; bit_idx<w; bit_idx++)
            b_data[(c*k_count+k)*w+bit_idx] = code[bit_idx];
        end
      end
    end
  endtask

  task automatic run_case(input int m, input bit last_only);
    int k_count;
    bit seen;
    logic [63:0] expected;
    logic [1023:0] saved;
    k_count = 1024 / (4*element_width(m));
    @(negedge clk);
    mode = 4'(m);
    prepare_matrix(m, last_only);
    cmd_valid = 1;
    rsp_ready = 0;
    if (!cmd_ready) $fatal(1, "not ready at new command m=%0d", m);
    @(posedge clk);
    @(negedge clk);
    cmd_valid = 0;
    a_data = ~a_data; // Accepted command must use its captured inputs.
    b_data = ~b_data;
    seen = 0;
    for (int wait_count = 0; wait_count <= k_count+12; wait_count++) begin
      if (rsp_valid) begin
        seen = 1;
        break;
      end
      if (cmd_ready) $fatal(1, "ready while command in flight m=%0d", m);
      @(negedge clk);
    end
    if (!seen) $fatal(1, "response latency exceeded K+12 m=%0d", m);
    for (int r = 0; r < 4; r++) begin
      for (int c = 0; c < 4; c++) begin
        if (m <= 1) begin
          if (last_only && (((r+c)%2) != 0)) expected = 64'hffff_ffff_ffff_ffff;
          else expected = last_only ? 64'd1 : 64'(k_count);
        end else begin
          if (last_only && (((r+c)%2) != 0)) expected = 64'h0000_0000_bf80_0000;
          else if (last_only) expected = 64'h0000_0000_3f80_0000;
          else if (k_count == 16) expected = 64'h0000_0000_4180_0000;
          else if (k_count == 32) expected = 64'h0000_0000_4200_0000;
          else expected = 64'h0000_0000_4280_0000;
        end
        if (c_data[(r*4+c)*64 +: 64] !== expected)
          $fatal(1, "wrong C[%0d][%0d] mode=%0d last=%0d got=%h expected=%h",
                 r,c,m,last_only,c_data[(r*4+c)*64 +: 64],expected);
      end
    end
    saved = c_data;
    repeat (3) begin
      @(negedge clk);
      if (!rsp_valid || cmd_ready || c_data !== saved)
        $fatal(1, "response not held under backpressure m=%0d", m);
    end
    rsp_ready = 1;
    @(posedge clk);
    @(negedge clk);
    rsp_ready = 0;
    if (rsp_valid) $fatal(1, "response not consumed m=%0d", m);
  endtask

  initial begin
    repeat (2) @(negedge clk);
    rst_n = 1;
    for (int m = 0; m < 10; m++) begin
      run_case(m, 0);
      run_case(m, 1);
    end
    $display("PUBLIC_PASS T10 modes=10 cases=20");
    $finish;
  end
endmodule
