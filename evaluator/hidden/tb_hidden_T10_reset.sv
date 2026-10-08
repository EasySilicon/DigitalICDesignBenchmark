`timescale 1ns/1ps
module tb_hidden_T10_reset;
  logic clk=0;
  always #5 clk=~clk;
  logic rst_n=0, in_valid=0, in_ready, in_start=0;
  logic [15:0] in_block_id=0;
  logic [3:0] mode=9;
  logic [255:0] a_scale={32{8'd127}}, b_scale={32{8'd127}};
  logic [1023:0] a_data={256{4'h2}}, b_data={256{4'h2}};
  logic [3:0] out_valid;
  logic out_ready=0;
  logic [63:0] out_block_id;
  logic [15:0] out_row;
  logic [4095:0] out_data;
  int next_row=0;
  npu_systolic_matmul_16x16 dut (.*);

  task automatic send_beats(input logic [15:0] tag, input int count);
    for (int beat=0;beat<count;beat++) begin
      @(negedge clk);
      in_valid=1;
      in_start=(beat==0);
      in_block_id=tag;
      mode=9;
      a_scale={32{8'd127}};
      b_scale={32{8'd127}};
      a_data={256{4'h2}};
      b_data={256{4'h2}};
      #1;
      if (!in_ready) $fatal(1,"input credit lost inside accepted block tag=%h",tag);
      @(posedge clk);
    end
    @(negedge clk);
    in_valid=0;
    in_start=0;
  endtask

  task automatic clear_and_check;
    @(negedge clk);
    rst_n=0;
    in_valid=0;
    #1;
    if (out_valid!=0) $fatal(1,"output survived asynchronous reset");
    repeat (2) @(negedge clk);
    rst_n=1;
    repeat (4) begin
      @(negedge clk);
      if (out_valid!=0) $fatal(1,"ghost output after reset");
    end
  endtask

  initial begin : probe
    int wait_count;
    logic [3:0] saved_valid;
    logic [63:0] saved_id;
    logic [15:0] saved_row;
    logic [4095:0] saved_data;
    repeat (2) @(negedge clk);
    rst_n=1;
    send_beats(16'hfffe,2);
    clear_and_check();

    send_beats(16'hfffd,4);
    clear_and_check();

    out_ready=0;
    send_beats(16'hfffc,4);
    wait_count=0;
    while (out_valid==0 && wait_count<64) begin
      @(negedge clk);
      wait_count++;
    end
    if (out_valid==0) $fatal(1,"blocked output never appeared");
    saved_valid=out_valid;
    saved_id=out_block_id;
    saved_row=out_row;
    saved_data=out_data;
    repeat (5) begin
      @(negedge clk);
      if (out_valid!==saved_valid) $fatal(1,"valid changed under backpressure");
      for (int slot=0;slot<4;slot++)
        if (saved_valid[slot] &&
            (out_block_id[slot*16 +: 16]!==saved_id[slot*16 +: 16] ||
             out_row[slot*4 +: 4]!==saved_row[slot*4 +: 4] ||
             out_data[slot*1024 +: 1024]!==saved_data[slot*1024 +: 1024]))
          $fatal(1,"payload changed under backpressure");
    end
    clear_and_check();

    out_ready=0;
    send_beats(16'h0000,4);
    wait_count=0;
    while (next_row<16 && wait_count<96) begin
      @(negedge clk);
      if (out_valid!=0) begin
        for (int slot=0;slot<4;slot++) begin
          if (out_valid[slot]) begin
            if (out_block_id[slot*16 +: 16]!==16'h0000 ||
                out_row[slot*4 +: 4]!==4'(next_row))
              $fatal(1,"old block ID or reordered row after reset");
            for (int col=0;col<16;col++)
              if (out_data[slot*1024+col*64 +: 64]!==64'h0000_0000_4280_0000)
                $fatal(1,"wrong fresh result after reset");
            next_row++;
          end
        end
        out_ready=1;
        @(posedge clk);
        @(negedge clk);
        out_ready=0;
      end
      wait_count++;
    end
    if (next_row!=16) $fatal(1,"fresh block incomplete after reset");
    $display("MM_RESET_STREAM PASS partial_input=1 wavefront=1 blocked_output=1 fresh_block=1");
    $finish;
  end
endmodule
