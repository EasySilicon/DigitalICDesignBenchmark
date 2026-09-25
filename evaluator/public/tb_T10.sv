`timescale 1ns/1ps
module tb_T10;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic cmd_valid = 0, cmd_ready;
  logic [3:0] mode = 0;
  logic [255:0] a_scale = 0, b_scale = 0;
  logic in_valid = 0, in_ready;
  logic [1023:0] a_data = 0, b_data = 0;
  logic out_valid, out_ready = 0;
  logic [3:0] out_row;
  logic [1023:0] out_data;
  logic [1023:0] beat_a [0:15], beat_b [0:15];
  npu_systolic_matmul_16x16 dut (.*);

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

  task automatic prepare_beats(input int m, input bit last_only);
    int w, lanes, count;
    logic [15:0] code;
    w = element_width(m);
    lanes = 64/w;
    count = w;
    for (int t=0; t<16; t++) begin
      beat_a[t]='0;
      beat_b[t]='0;
    end
    for (int t=0; t<count; t++) begin
      for (int r=0; r<16; r++) begin
        for (int j=0; j<lanes; j++) begin
          if (!last_only || (t==count-1 && j==lanes-1)) begin
            code=one_code(m,last_only && (r[0]!=0));
            for (int bit_idx=0;bit_idx<w;bit_idx++)
              beat_a[t][(r*lanes+j)*w+bit_idx]=code[bit_idx];
          end
        end
      end
      for (int c=0; c<16; c++) begin
        for (int j=0; j<lanes; j++) begin
          if (!last_only || (t==count-1 && j==lanes-1)) begin
            code=one_code(m,last_only && (c[0]!=0));
            for (int bit_idx=0;bit_idx<w;bit_idx++)
              beat_b[t][(c*lanes+j)*w+bit_idx]=code[bit_idx];
          end
        end
      end
    end
  endtask

  task automatic check_row(input int m, input bit last_only, input int r);
    logic [63:0] expected;
    if (out_row !== 4'(r)) $fatal(1,"wrong output row mode=%0d got=%0d exp=%0d",m,out_row,r);
    for (int c=0;c<16;c++) begin
      if (m<=1) begin
        if (last_only && (((r+c)%2)!=0)) expected=64'hffff_ffff_ffff_ffff;
        else expected=last_only ? 64'd1 : 64'd64;
      end else begin
        if (last_only && (((r+c)%2)!=0)) expected=64'h0000_0000_bf80_0000;
        else expected=last_only ? 64'h0000_0000_3f80_0000 : 64'h0000_0000_4280_0000;
      end
      if (out_data[c*64+:64] !== expected)
        $fatal(1,"wrong C[%0d][%0d] mode=%0d last=%0d got=%h exp=%h",
               r,c,m,last_only,out_data[c*64+:64],expected);
    end
  endtask

  task automatic run_case(input int m, input bit last_only);
    int count;
    bit seen;
    logic [1023:0] saved;
    count=element_width(m);
    prepare_beats(m,last_only);
    @(negedge clk);
    mode=4'(m);
    a_scale={32{8'd127}};
    b_scale={32{8'd127}};
    cmd_valid=1;
    if (!cmd_ready) $fatal(1,"command not ready mode=%0d",m);
    @(posedge clk);
    @(negedge clk);
    cmd_valid=0;
    in_valid=1;
    for (int t=0;t<count;t++) begin
      a_data=beat_a[t];
      b_data=beat_b[t];
      if (!in_ready) $fatal(1,"input bubble mode=%0d beat=%0d",m,t);
      @(posedge clk);
      @(negedge clk);
    end
    in_valid=0;
    a_data='1;
    b_data='1;
    seen=0;
    for (int wait_count=0;wait_count<=48;wait_count++) begin
      if (out_valid) begin seen=1; break; end
      if (cmd_ready) $fatal(1,"ready before output complete mode=%0d",m);
      @(negedge clk);
    end
    if (!seen) $fatal(1,"first row latency exceeded 48 mode=%0d",m);
    check_row(m,last_only,0);
    saved=out_data;
    repeat (3) begin
      @(negedge clk);
      if (!out_valid || out_row!==0 || out_data!==saved || cmd_ready)
        $fatal(1,"output unstable under backpressure mode=%0d",m);
    end
    out_ready=1;
    for (int r=0;r<16;r++) begin
      if (!out_valid) $fatal(1,"output bubble mode=%0d row=%0d",m,r);
      check_row(m,last_only,r);
      @(posedge clk);
      @(negedge clk);
    end
    out_ready=0;
    if (out_valid || !cmd_ready) $fatal(1,"tile not completed mode=%0d",m);
  endtask

  initial begin
    repeat (2) @(negedge clk);
    rst_n=1;
    for (int m=0;m<10;m++) begin
      run_case(m,0);
      run_case(m,1);
    end
    $display("PUBLIC_PASS T10 modes=10 cases=20 beats_per_operand=4/8/16 rows=16");
    $finish;
  end
endmodule
