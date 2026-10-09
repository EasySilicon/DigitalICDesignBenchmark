`timescale 1ns/1ps

// Preserved feasibility prototype; the T08 identifier now denotes the MAC task.
module tb_T08;
  logic clk, rst_n;
  logic [8:0] in_valid, in_ready, in_vc;
  logic [8:0][63:0] in_flit;
  logic [8:0] out_valid, out_ready, out_vc;
  logic [8:0][63:0] out_flit;
  int seen_a, seen_b, cycles;

  noc_mesh_3x3 dut (.*);

  initial begin
    clk = 0;
    forever #1 clk = ~clk;
  end

  function automatic logic [63:0] flit(
      input bit head, input bit tail, input int dst,
      input int id, input logic [41:0] payload);
    return {head, tail, 2'(dst % 3), 2'(dst / 3), 16'(id), payload};
  endfunction

  task automatic send(input int src, input bit vc,
                      input logic [63:0] value);
    @(negedge clk);
    in_valid[src] = 1;
    in_vc[src] = vc;
    in_flit[src] = value;
    do @(posedge clk); while (!in_ready[src]);
    @(negedge clk);
    in_valid[src] = 0;
  endtask

  always @(posedge clk) begin
    if (rst_n) begin
      cycles++;
      if (out_valid[8] && out_ready[8]) begin
        if (out_vc[8] !== 0 || out_flit[8][57:42] !== 16'h0011)
          $fatal(1, "T08 public packet A corrupt or misrouted");
        if (out_flit[8][41:0] !== 42'(seen_a + 1))
          $fatal(1, "T08 public packet A reordered");
        seen_a++;
      end
      if (out_valid[6] && out_ready[6]) begin
        if (out_vc[6] !== 1 || out_flit[6][57:42] !== 16'h0022)
          $fatal(1, "T08 public packet B corrupt or misrouted");
        if (out_flit[6][41:0] !== 42'(seen_b + 11))
          $fatal(1, "T08 public packet B reordered");
        seen_b++;
      end
      if (cycles > 500) $fatal(1, "T08 public timeout");
    end
  end

  initial begin
    rst_n = 0;
    in_valid = '0;
    in_vc = '0;
    in_flit = '0;
    out_ready = '1;
    seen_a = 0;
    seen_b = 0;
    cycles = 0;
    repeat (4) @(posedge clk);
    @(negedge clk);
    rst_n = 1;
    fork
      begin
        send(0, 0, flit(1, 0, 8, 16'h0011, 42'd1));
        send(0, 0, flit(0, 0, 8, 16'h0011, 42'd2));
        send(0, 0, flit(0, 1, 8, 16'h0011, 42'd3));
      end
      begin
        send(2, 1, flit(1, 0, 6, 16'h0022, 42'd11));
        send(2, 1, flit(0, 1, 6, 16'h0022, 42'd12));
      end
    join
    wait (seen_a == 3 && seen_b == 2);
    repeat (5) @(posedge clk);
    $display("PUBLIC_PASS T08 packets=2 flits=5");
    $finish;
  end
endmodule
