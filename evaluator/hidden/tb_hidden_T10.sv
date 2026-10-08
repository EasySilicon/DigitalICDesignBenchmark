`timescale 1ns/1ps
module tb_hidden_T10;
  localparam int MAX_CASES = 1024;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 1;
  logic cmd_valid = 0, cmd_ready;
  logic [3:0] mode = 0;
  logic [255:0] a_scale = 0, b_scale = 0;
  logic in_valid = 0, in_ready;
  logic [1023:0] a_data = 0, b_data = 0;
  logic out_valid, out_ready = 0;
  logic [3:0] out_row;
  logic [1023:0] out_data;
  logic [1023:0] a_mem [0:MAX_CASES*16-1];
  logic [1023:0] b_mem [0:MAX_CASES*16-1];
  logic [255:0] as_mem [0:MAX_CASES-1];
  logic [255:0] bs_mem [0:MAX_CASES-1];
  logic [3:0] mode_mem [0:MAX_CASES-1];
  logic [4:0] stall_mem [0:MAX_CASES-1];
  logic [15:0] pause_mem [0:MAX_CASES-1];
  logic [1:0] reset_mem [0:MAX_CASES-1];
  int case_count;
  string vectors;
  npu_systolic_matmul_16x16 dut (.*);

  task automatic reset_dut();
    @(negedge clk);
    rst_n = 0;
    cmd_valid = 0;
    in_valid = 0;
    out_ready = 0;
    repeat (2) @(negedge clk);
    rst_n = 1;
  endtask

  task automatic probe_reset(input int index);
    int beats, cycles;
    bit okay;
    okay=1;
    beats=(mode_mem[index]==1 || mode_mem[index]==2 || mode_mem[index]==3)?16:
          ((mode_mem[index]==6 || mode_mem[index]==9)?4:8);
    @(negedge clk);
    mode=mode_mem[index];
    a_scale=as_mem[index];
    b_scale=bs_mem[index];
    cmd_valid=1;
    if (!cmd_ready) okay=0;
    @(posedge clk);
    @(negedge clk);
    cmd_valid=0;
    for (int t=0;t<beats;t++) begin
      in_valid=1;
      a_data=a_mem[index*16+t];
      b_data=b_mem[index*16+t];
      if (!in_ready) okay=0;
      @(posedge clk);
      @(negedge clk);
    end
    in_valid=0;
    if (reset_mem[index]==2) begin
      cycles=0;
      while (!out_valid && cycles<160) begin @(negedge clk); cycles++; end
      if (!out_valid) okay=0;
    end
    rst_n=0;
    #1;
    if (out_valid || !cmd_ready || in_ready) okay=0;
    repeat (2) @(negedge clk);
    rst_n=1;
    @(negedge clk);
    if (out_valid || !cmd_ready) okay=0;
    $display("MM_RESET %0d %0d",index,int'(okay));
  endtask

  task automatic run_case(input int index);
    int beats, cycles, latency, got_rows;
    bit protocol_ok, timing_ok, output_ok, failed;
    logic [1023:0] held;
    logic [3:0] held_row;
    protocol_ok=1;
    timing_ok=1;
    output_ok=1;
    failed=0;
    got_rows=0;
    beats=(mode_mem[index]==1 || mode_mem[index]==2 || mode_mem[index]==3)?16:
          ((mode_mem[index]==6 || mode_mem[index]==9)?4:8);
    @(negedge clk);
    mode=mode_mem[index];
    a_scale=as_mem[index];
    b_scale=bs_mem[index];
    cmd_valid=1;
    cycles=0;
    while (!cmd_ready && cycles<128) begin
      @(negedge clk);
      cycles++;
    end
    if (!cmd_ready) failed=1;
    if (!failed) begin
      @(posedge clk);
      @(negedge clk);
      cmd_valid=0;
      for (int t=0;t<beats;t++) begin
        if (pause_mem[index][t]) begin
          in_valid=0;
          if (!in_ready) protocol_ok=0;
          @(posedge clk);
          @(negedge clk);
        end
        a_data=a_mem[index*16+t];
        b_data=b_mem[index*16+t];
        in_valid=1;
        if (!in_ready || cmd_ready || out_valid) protocol_ok=0;
        cycles=0;
        while (!in_ready && cycles<128) begin
          @(negedge clk);
          cycles++;
        end
        if (!in_ready) begin failed=1; break; end
        @(posedge clk);
        @(negedge clk);
      end
      in_valid=0;
      a_data='1;
      b_data='1;
    end
    if (!failed) begin
      latency=0;
      while (!out_valid && latency<160) begin
        if (cmd_ready) protocol_ok=0;
        @(negedge clk);
        latency++;
      end
      if (!out_valid) failed=1;
      if (latency>64) timing_ok=0;
    end
    if (!failed) begin
      for (int r=0;r<16;r++) begin
        cycles=0;
        while (!out_valid && cycles<64) begin
          @(negedge clk);
          cycles++;
        end
        if (!out_valid) begin failed=1; break; end
        if (r>0 && cycles!=0) timing_ok=0;
        if (out_row!==4'(r)) output_ok=0;
        $display("MM_ROW %0d %0d %h",index,r,out_data);
        got_rows++;
        held=out_data;
        held_row=out_row;
        for (int pause=0;pause<int'(stall_mem[index]);pause++) begin
          if (!out_valid || out_data!==held || out_row!==held_row || cmd_ready)
            protocol_ok=0;
          @(negedge clk);
        end
        out_ready=1;
        @(posedge clk);
        @(negedge clk);
        out_ready=0;
      end
    end
    if (failed || got_rows!=16) begin
      protocol_ok=0;
      timing_ok=0;
      output_ok=0;
    end
    $display("MM_CASE %0d %0d %0d %0d %0d",index,
             int'(protocol_ok),int'(timing_ok),int'(output_ok),got_rows);
    if (failed) reset_dut();
  endtask

  initial begin
    if (!$value$plusargs("VECTORS=%s",vectors)) $fatal(1,"VECTORS required");
    if (!$value$plusargs("CASE_COUNT=%d",case_count)) $fatal(1,"CASE_COUNT required");
    if (case_count<1 || case_count>MAX_CASES) $fatal(1,"bad case count");
    $readmemh({vectors,"/a.mem"},a_mem);
    $readmemh({vectors,"/b.mem"},b_mem);
    $readmemh({vectors,"/as.mem"},as_mem);
    $readmemh({vectors,"/bs.mem"},bs_mem);
    $readmemh({vectors,"/mode.mem"},mode_mem);
    $readmemh({vectors,"/stall.mem"},stall_mem);
    $readmemh({vectors,"/pause.mem"},pause_mem);
    $readmemh({vectors,"/reset.mem"},reset_mem);
    #1 rst_n=0;
    repeat (2) @(negedge clk);
    rst_n=1;
    for (int i=0;i<case_count;i++) begin
      if (reset_mem[i]!=0) probe_reset(i);
      run_case(i);
    end
    $display("MM_END cases=%0d",case_count);
    $finish;
  end
endmodule
