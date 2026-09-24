`timescale 1ns/1ps

module tb_T04;
  logic clk, rst_n;
  logic PSEL, PENABLE, PWRITE;
  logic [11:0] PADDR;
  logic [31:0] PWDATA, PRDATA;
  logic [3:0] PSTRB;
  logic [2:0] PPROT;
  logic PREADY, PSLVERR, irq;
  logic [31:0] ctrl, load_value, count_value;
  logic pending;
  logic [31:0] next_ctrl, next_load, next_count;
  logic next_pending;
  logic valid_address, access_now;
  logic [31:0] expected_rdata;
  int seed;
  int unsigned rng;

  apb4_timer dut (
    .clk(clk), .rst_n(rst_n), .PSEL(PSEL), .PENABLE(PENABLE),
    .PWRITE(PWRITE), .PADDR(PADDR), .PWDATA(PWDATA), .PSTRB(PSTRB),
    .PPROT(PPROT), .PRDATA(PRDATA), .PREADY(PREADY),
    .PSLVERR(PSLVERR), .irq(irq)
  );

  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value,
      input logic [3:0] strobes);
    logic [31:0] merged;
    merged = old_value;
    for (int i = 0; i < 4; i++)
      if (strobes[i]) merged[i*8 +: 8] = new_value[i*8 +: 8];
    return merged;
  endfunction

  task automatic step(input bit select_bus, input bit enable_bus,
                      input bit write_bus, input logic [11:0] addr,
                      input logic [31:0] data, input logic [3:0] strobes);
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    PSEL = select_bus;
    PENABLE = enable_bus;
    PWRITE = write_bus;
    PADDR = addr;
    PWDATA = data;
    PSTRB = strobes;
    PPROT = 3'(rng);
    #2;
    access_now = select_bus && enable_bus;
    valid_address = (addr == 12'h000 || addr == 12'h004 ||
                     addr == 12'h008 || addr == 12'h00c);
    if (PREADY !== access_now)
      $fatal(1, "AC-19 PREADY mismatch addr=%h access=%0b", addr, access_now);
    if (PSLVERR !== (access_now && !valid_address))
      $fatal(1, "AC-20 PSLVERR mismatch addr=%h access=%0b", addr, access_now);
    if (irq !== (pending && ctrl[2]))
      $fatal(1, "AC-18 irq mismatch pending=%0b ctrl=%h", pending, ctrl);
    expected_rdata = 0;
    case (addr)
      12'h000: expected_rdata = ctrl;
      12'h004: expected_rdata = load_value;
      12'h008: expected_rdata = count_value;
      12'h00c: expected_rdata = {31'b0, pending};
      default: expected_rdata = 0;
    endcase
    if (access_now && !write_bus && PRDATA !== expected_rdata)
      $fatal(1, "AC-16 read addr=%h expected=%h actual=%h",
             addr, expected_rdata, PRDATA);

    next_ctrl = ctrl;
    next_load = load_value;
    next_count = count_value;
    next_pending = pending;
    if (ctrl[0]) begin
      if (count_value > 0) next_count = count_value - 1;
      else begin
        next_pending = 1;
        if (ctrl[1]) next_count = load_value;
        else next_ctrl[0] = 0;
      end
    end
    if (access_now && write_bus && valid_address) begin
      case (addr)
        12'h000: if (strobes != 0) next_ctrl = merge_bytes(ctrl, data, strobes) & 32'h7;
        12'h004: if (strobes != 0) next_load = merge_bytes(load_value, data, strobes);
        12'h008: if (strobes != 0) next_count = merge_bytes(count_value, data, strobes);
        12'h00c: if (strobes[0] && data[0]) next_pending = 0;
        default: ;
      endcase
    end
    clk = 1;
    #2;
    ctrl = next_ctrl;
    load_value = next_load;
    count_value = next_count;
    pending = next_pending;
    if (irq !== (pending && ctrl[2]))
      $fatal(1, "AC-18 post-edge irq mismatch");
    clk = 0;
    #2;
  endtask

  task automatic write_reg(input logic [11:0] addr,
                           input logic [31:0] data,
                           input logic [3:0] strobes);
    step(1, 0, 1, addr, data, strobes);
    step(1, 1, 1, addr, data, strobes);
  endtask

  task automatic read_reg(input logic [11:0] addr);
    step(1, 0, 0, addr, 0, 0);
    step(1, 1, 0, addr, 0, 0);
  endtask

  initial begin
    if ($bits(dut.PADDR) != 12 || $bits(dut.PWDATA) != 32 ||
        $bits(dut.PRDATA) != 32 || $bits(dut.PSTRB) != 4 ||
        $bits(dut.PPROT) != 3)
      $fatal(1, "T04 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ 32'h3c6ef372;
    clk = 0;
    rst_n = 0;
    PSEL = 0;
    PENABLE = 0;
    PWRITE = 0;
    PADDR = 0;
    PWDATA = 0;
    PSTRB = 0;
    PPROT = 0;
    ctrl = 0;
    load_value = 0;
    count_value = 0;
    pending = 0;
    #2;
    clk = 1;
    #2;
    clk = 0;
    #2;
    rst_n = 1;
    #2;

    read_reg(12'h000);
    read_reg(12'h004);
    write_reg(12'h004, 32'd3, 4'hf);
    write_reg(12'h008, 32'd2, 4'hf);
    write_reg(12'h000, 32'd5, 4'hf);
    repeat (3) step(0, 0, 0, 0, 0, 0);
    read_reg(12'h00c);
    write_reg(12'h00c, 32'd1, 4'h1);
    read_reg(12'h00c);
    write_reg(12'h004, 32'hdead_beef, 4'b0101);
    read_reg(12'h004);
    write_reg(12'h000, 32'd7, 4'hf);
    write_reg(12'h008, 32'd0, 4'hf);
    repeat (8) step(0, 0, 0, 0, 0, 0);
    read_reg(12'h008);
    read_reg(12'h00c);
    read_reg(12'h003);
    write_reg(12'h100, 32'hffff_ffff, 4'hf);

    for (int i = 0; i < 64; i++) begin
      rng ^= rng << 13;
      rng ^= rng >> 17;
      rng ^= rng << 5;
      case (rng[2:0])
        0: write_reg(12'h000, rng, 4'(rng >> 8));
        1: write_reg(12'h004, rng, 4'(rng >> 8));
        2: write_reg(12'h008, rng, 4'(rng >> 8));
        3: write_reg(12'h00c, rng, 4'(rng >> 8));
        4: read_reg(12'h000);
        5: read_reg(12'h008);
        6: read_reg(12'h00c);
        7: step(0, 0, 0, 0, 0, 0);
      endcase
    end
    $display("PUBLIC_PASS T04 seed=%0d", seed);
    $finish;
  end
endmodule
