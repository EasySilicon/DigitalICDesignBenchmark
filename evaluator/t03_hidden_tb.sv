`timescale 1ns/1ps
module tb_hidden_T03;
  logic clk, rst_n, PSEL, PENABLE, PWRITE;
  logic [11:0] PADDR;
  logic [31:0] PWDATA, PRDATA;
  logic [3:0] PSTRB;
  logic [2:0] PPROT;
  logic PREADY, PSLVERR, irq;
  logic [31:0] ctrl, load_value, count_value;
  logic pending;
  int passed [16:20], total [16:20];
  bit first_failure [16:20];
  int unsigned rng;
  int seed;

  apb4_timer dut (
    .clk(clk), .rst_n(rst_n), .PSEL(PSEL), .PENABLE(PENABLE),
    .PWRITE(PWRITE), .PADDR(PADDR), .PWDATA(PWDATA), .PSTRB(PSTRB),
    .PPROT(PPROT), .PRDATA(PRDATA), .PREADY(PREADY),
    .PSLVERR(PSLVERR), .irq(irq)
  );

  task automatic check(input int id, input bit okay, input string what);
    total[id]++;
    if (okay) passed[id]++;
    else if (!first_failure[id]) begin
      first_failure[id] = 1;
      $display("IC_FAILURE AC-%02d %s", id, what);
    end
  endtask

  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value,
      input logic [3:0] strobes);
    logic [31:0] merged;
    merged = old_value;
    for (int i=0; i<4; i++)
      if (strobes[i]) merged[i*8 +: 8] = new_value[i*8 +: 8];
    return merged;
  endfunction

  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction

  task automatic reset_timer;
    clk = 0;
    rst_n = 0;
    PSEL = 0;
    PENABLE = 0;
    PWRITE = 0;
    PADDR = 0;
    PWDATA = 0;
    PSTRB = 0;
    PPROT = 0;
    #0.4;
    check(20, irq === 1'b0, "asynchronous reset did not clear irq");
    clk = 1;
    #0.4;
    clk = 0;
    #0.4;
    ctrl = 0;
    load_value = 0;
    count_value = 0;
    pending = 0;
    rst_n = 1;
    #0.4;
    check(20, irq === 1'b0, "irq high after reset release");
  endtask

  task automatic step(input bit select_bus, enable_bus, write_bus,
                      input logic [11:0] addr, input logic [31:0] data,
                      input logic [3:0] strobes, input logic [2:0] prot);
    bit access_now, valid_address;
    logic [31:0] expected_read, next_ctrl, next_load, next_count;
    logic next_pending;
    clk = 0;
    PSEL = select_bus;
    PENABLE = enable_bus;
    PWRITE = write_bus;
    PADDR = addr;
    PWDATA = data;
    PSTRB = strobes;
    PPROT = prot;
    #0.4;
    access_now = select_bus && enable_bus;
    valid_address = addr == 12'h000 || addr == 12'h004 ||
                    addr == 12'h008 || addr == 12'h00c;
    check(19, PREADY === access_now,
          $sformatf("PREADY select=%b enable=%b actual=%b", select_bus, enable_bus, PREADY));
    check(20, PSLVERR === (access_now && !valid_address),
          $sformatf("PSLVERR addr=%h expected=%b actual=%b", addr,
                    access_now && !valid_address, PSLVERR));
    check(18, irq === (pending && ctrl[2]), "pre-edge irq mismatch");
    expected_read = 0;
    case (addr)
      12'h000: expected_read = ctrl;
      12'h004: expected_read = load_value;
      12'h008: expected_read = count_value;
      12'h00c: expected_read = {31'b0, pending};
      default: expected_read = 0;
    endcase
    if (access_now && !write_bus) begin
      check(16, PRDATA === expected_read,
            $sformatf("read addr=%h expected=%h actual=%h", addr, expected_read, PRDATA));
      if (addr == 12'h008)
        check(17, PRDATA === expected_read, "timer count read mismatch");
      if (addr == 12'h00c)
        check(18, PRDATA === expected_read, "pending read mismatch");
      if (!valid_address)
        check(20, PRDATA === 0, "invalid address read did not return zero");
    end
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
        12'h000: if (|strobes) next_ctrl = merge_bytes(ctrl, data, strobes) & 32'h7;
        12'h004: next_load = merge_bytes(load_value, data, strobes);
        12'h008: if (|strobes) next_count = merge_bytes(count_value, data, strobes);
        12'h00c: if (strobes[0] && data[0]) next_pending = 0;
        default: ;
      endcase
    end
    clk = 1;
    #0.4;
    ctrl = next_ctrl;
    load_value = next_load;
    count_value = next_count;
    pending = next_pending;
    check(18, irq === (pending && ctrl[2]), "post-edge irq mismatch");
    clk = 0;
    #0.2;
  endtask

  task automatic wr(input logic [11:0] addr, input logic [31:0] data,
                    input logic [3:0] strobes, input logic [2:0] prot);
    step(1, 0, 1, addr, data, strobes, prot);
    step(1, 1, 1, addr, data, strobes, prot);
  endtask

  task automatic rd(input logic [11:0] addr, input logic [2:0] prot);
    step(1, 0, 0, addr, 0, 0, prot);
    step(1, 1, 0, addr, 0, 0, prot);
  endtask

  initial begin
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    rng = 32'(seed) ^ 32'h3c6ef372;
    clk = 0;
    rst_n = 1;
    for (int i=16; i<=20; i++) begin
      passed[i] = 0;
      total[i] = 0;
      first_failure[i] = 0;
    end
    check(16, $bits(dut.PADDR)==12 && $bits(dut.PWDATA)==32 &&
              $bits(dut.PRDATA)==32 && $bits(dut.PSTRB)==4 &&
              $bits(dut.PPROT)==3, "fixed interface width");
    reset_timer();
    for (int i=0; i<4; i++) rd(12'(i*4), 3'(i));
    wr(12'h004, 32'h12345678, 4'hf, 0);
    for (int s=0; s<16; s++) begin
      wr(12'h004, 32'hd3a57b19 ^ (32'(s)*32'h01020304), 4'(s), 3'(s));
      rd(12'h004, 3'(s));
    end
    wr(12'h000, 32'hffff_fff8, 4'hf, 0);
    rd(12'h000, 0);
    wr(12'h000, 32'h0000_0004, 4'h1, 0);
    wr(12'h008, 32'h0000_0000, 4'hf, 0);
    // Enable the timer at zero. The terminal event raises pending next cycle.
    wr(12'h000, 32'h0000_0005, 4'h1, 0);
    step(0, 0, 0, 0, 0, 0, 0);
    rd(12'h00c, 0);
    wr(12'h00c, 32'h0000_0000, 4'h1, 0);
    rd(12'h00c, 0);
    wr(12'h00c, 32'h0000_0001, 4'h0, 0);
    rd(12'h00c, 0);
    wr(12'h00c, 32'h0000_0100, 4'h2, 0);
    rd(12'h00c, 0);
    wr(12'h00c, 32'h0000_0001, 4'h1, 0);
    rd(12'h00c, 0);
    wr(12'h004, 32'h0000_0003, 4'hf, 0);
    wr(12'h008, 32'h0000_0002, 4'hf, 0);
    wr(12'h000, 32'h0000_0007, 4'h1, 0);
    for (int i=0; i<12; i++) rd(12'h008, 3'(i));
    rd(12'h00c, 0);
    // COUNT write on a decrement edge wins for COUNT only.
    wr(12'h008, 32'd7, 4'hf, 0);
    wr(12'h008, 32'd13, 4'hf, 0);
    rd(12'h008, 0);
    // A setup phase can be held without committing the CTRL write.
    reset_timer();
    wr(12'h000, 32'h0000_0001, 4'h1, 0);
    step(0, 0, 0, 0, 0, 0, 0);
    step(1, 0, 1, 12'h000, 32'h0000_0004, 4'h1, 0);
    for (int i=0; i<5; i++)
      step(1, 0, 1, 12'h000, 32'h0000_0004, 4'h1, 0);
    step(1, 1, 1, 12'h000, 32'h0000_0004, 4'h1, 0);
    rd(12'h000, 0);
    // Invalid and unaligned addresses never change state.
    rd(12'h003, 0);
    rd(12'h010, 0);
    wr(12'h003, 32'hffff_ffff, 4'hf, 0);
    wr(12'h100, 32'hffff_ffff, 4'hf, 0);
    for (int i=0; i<4; i++) rd(12'(i*4), 0);
    reset_timer();
    // Mixed register activity and all legal PPROT encodings.
    for (int i=0; i<1200; i++) begin
      rng = next_random(rng);
      case (rng[2:0])
        0,1: wr(12'h000, rng, 4'(rng>>9), 3'(rng>>13));
        2: wr(12'h004, rng, 4'(rng>>9), 3'(rng>>13));
        3: wr(12'h008, rng, 4'(rng>>9), 3'(rng>>13));
        4: wr(12'h00c, rng, 4'(rng>>9), 3'(rng>>13));
        5: rd(12'h008, 3'(rng>>13));
        6: rd(12'h00c, 3'(rng>>13));
        7: rd(12'(4*((rng>>8)%4)), 3'(rng>>13));
      endcase
      if ((i%31)==0) step(0, 0, 0, 0, 0, 0, 0);
    end
    for (int i=16; i<=20; i++)
      $display("IC_GROUP AC-%02d %0d %0d", i, passed[i], total[i]);
    $finish;
  end
endmodule
