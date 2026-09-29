`timescale 1ns/1ps
module tb_hidden_T07;
  logic clk, rst_n;
  logic [31:0] AWADDR, WDATA, ARADDR, RDATA;
  logic [2:0] AWPROT, ARPROT, PPROT;
  logic [3:0] WSTRB, PSTRB;
  logic AWVALID, AWREADY, WVALID, WREADY, BVALID, BREADY;
  logic [1:0] BRESP, RRESP;
  logic ARVALID, ARREADY, RVALID, RREADY;
  logic [15:0] PADDR;
  logic PSEL, PENABLE, PWRITE;
  logic [31:0] PWDATA, PRDATA;
  logic PREADY, PSLVERR;
  logic aw_hs, w_hs, ar_hs, b_hs, r_hs;
  logic [15:0] setup_addr, last_addr;
  logic [31:0] setup_data, last_data;
  logic [3:0] setup_strb, last_strb;
  logic [2:0] setup_prot, last_prot;
  logic setup_write, last_write;
  logic [31:0] mem [0:16383];
  bit apb_active;
  int apb_count, wait_left, next_wait;
  bit event_write [0:4095];
  int passed [32:37], total [32:37];
  bit first_failure [32:37];
  int unsigned rng;
  int seed;

  axi4lite_to_apb4_bridge dut (.*);

  task automatic check(input int id, input bit okay, input string what);
    total[id]++;
    if (okay) passed[id]++;
    else if (!first_failure[id]) begin
      first_failure[id] = 1;
      $display("IC_FAILURE AC-%02d APB=%0d %s", id, apb_count, what);
    end
  endtask

  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction

  function automatic logic [31:0] merge_bytes(
      input logic [31:0] old_value, new_value, input logic [3:0] strobes);
    logic [31:0] merged;
    merged = old_value;
    for (int i=0; i<4; i++)
      if (strobes[i]) merged[i*8 +: 8] = new_value[i*8 +: 8];
    return merged;
  endfunction

  task automatic step;
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    PRDATA = mem[PADDR[15:2]];
    PSLVERR = PADDR == 16'h0020;
    PREADY = wait_left == 0;
    #0.4;
    aw_hs = AWVALID && AWREADY;
    w_hs = WVALID && WREADY;
    ar_hs = ARVALID && ARREADY;
    b_hs = BVALID && BREADY;
    r_hs = RVALID && RREADY;
    if (rst_n) begin
      if (PSEL && !PENABLE) begin
        check(36, !apb_active, "new SETUP while APB busy");
        apb_active = 1;
        setup_addr = PADDR;
        setup_data = PWDATA;
        setup_strb = PSTRB;
        setup_prot = PPROT;
        setup_write = PWRITE;
        wait_left = next_wait;
      end else if (PSEL && PENABLE) begin
        check(36, apb_active, "ACCESS without SETUP");
        check(36, {PADDR,PWDATA,PSTRB,PPROT,PWRITE} ===
                  {setup_addr,setup_data,setup_strb,setup_prot,setup_write},
              "APB payload unstable");
        if (PREADY) begin
          last_addr = PADDR;
          last_data = PWDATA;
          last_strb = PSTRB;
          last_prot = PPROT;
          last_write = PWRITE;
          event_write[apb_count] = PWRITE;
          apb_count++;
          if (PWRITE && !PSLVERR)
            mem[PADDR[15:2]] = merge_bytes(mem[PADDR[15:2]], PWDATA, PSTRB);
          apb_active = 0;
        end else wait_left--;
      end else if (apb_active) check(36, 0, "APB access disappeared");
    end
    clk = 1;
    #0.4;
    clk = 0;
    #0.2;
  endtask

  task automatic send_aw(input logic [31:0] addr, input logic [2:0] prot);
    bit done;
    AWADDR = addr;
    AWPROT = prot;
    AWVALID = 1;
    done = 0;
    for (int cycle=0; cycle<80; cycle++) begin
      if (!done) begin
        step();
        if (aw_hs) begin AWVALID = 0; done = 1; end
      end
    end
    check(35, done, "AW handshake timeout");
    AWVALID = 0;
  endtask

  task automatic send_w(input logic [31:0] data, input logic [3:0] strb);
    bit done;
    WDATA = data;
    WSTRB = strb;
    WVALID = 1;
    done = 0;
    for (int cycle=0; cycle<80; cycle++) begin
      if (!done) begin
        step();
        if (w_hs) begin WVALID = 0; done = 1; end
      end
    end
    check(35, done, "W handshake timeout");
    WVALID = 0;
  endtask

  task automatic send_ar(input logic [31:0] addr, input logic [2:0] prot);
    bit done;
    ARADDR = addr;
    ARPROT = prot;
    ARVALID = 1;
    done = 0;
    for (int cycle=0; cycle<80; cycle++) begin
      if (!done) begin
        step();
        if (ar_hs) begin ARVALID = 0; done = 1; end
      end
    end
    check(35, done, "AR handshake timeout");
    ARVALID = 0;
  endtask

  task automatic receive_b(input logic [1:0] response);
    bit seen;
    seen = 0;
    for (int cycle=0; cycle<160; cycle++) begin
      if (!seen) begin
        if (BVALID) seen = 1;
        else step();
      end
    end
    check(34, seen, "B response timeout");
    if (seen) begin
      check(34, BRESP === response,
            $sformatf("BRESP expected=%b actual=%b", response, BRESP));
      for (int i=0; i<7; i++) begin
        step();
        check(36, BVALID === 1'b1 && BRESP === response,
              "B response changed under backpressure");
      end
      BREADY = 1;
      step();
      check(36, b_hs, "B handshake missing");
      BREADY = 0;
    end
  endtask

  task automatic receive_r(input logic [1:0] response,
                           input logic [31:0] expected_data);
    bit seen;
    seen = 0;
    for (int cycle=0; cycle<160; cycle++) begin
      if (!seen) begin
        if (RVALID) seen = 1;
        else step();
      end
    end
    check(34, seen, "R response timeout");
    if (seen) begin
      check(33, RRESP === response && RDATA === expected_data,
            $sformatf("R expected=%b/%h actual=%b/%h",
                      response, expected_data, RRESP, RDATA));
      for (int i=0; i<7; i++) begin
        step();
        check(36, RVALID === 1'b1 && RRESP === response &&
                  RDATA === expected_data, "R response changed under backpressure");
      end
      RREADY = 1;
      step();
      check(36, r_hs, "R handshake missing");
      RREADY = 0;
    end
  endtask

  task automatic write_tx(input bit w_first, input logic [31:0] addr,
                          input logic [31:0] data, input logic [3:0] strb,
                          input logic [2:0] prot);
    int before_count;
    bit valid_addr, expect_apb;
    logic [1:0] expected_resp;
    before_count = apb_count;
    valid_addr = addr[31:16] == 0 && addr[1:0] == 0;
    expect_apb = valid_addr && strb != 0;
    expected_resp = !valid_addr ? 2'b11 :
                    !expect_apb ? 2'b00 :
                    addr[15:0] == 16'h0020 ? 2'b10 : 2'b00;
    next_wait = int'(data[3:0]);
    if (w_first) begin send_w(data,strb); send_aw(addr,prot); end
    else begin send_aw(addr,prot); send_w(data,strb); end
    receive_b(expected_resp);
    check(32, apb_count == before_count + int'(expect_apb),
          "write APB count mismatch");
    if (expect_apb)
      check(32, {last_write,last_addr,last_data,last_strb,last_prot} ===
                {1'b1,addr[15:0],data,strb,prot}, "write APB payload mismatch");
    if (!valid_addr || !expect_apb)
      check(34, apb_count == before_count, "invalid/zero-strobe write touched APB");
  endtask

  task automatic read_tx(input logic [31:0] addr, input logic [2:0] prot);
    int before_count;
    bit valid_addr;
    logic [1:0] expected_resp;
    logic [31:0] expected_data;
    before_count = apb_count;
    valid_addr = addr[31:16] == 0 && addr[1:0] == 0;
    expected_resp = !valid_addr ? 2'b11 :
                    addr[15:0] == 16'h0020 ? 2'b10 : 2'b00;
    expected_data = expected_resp == 0 ? mem[addr[15:2]] : 0;
    next_wait = int'(addr[5:2]) % 16;
    send_ar(addr,prot);
    receive_r(expected_resp,expected_data);
    check(33, apb_count == before_count + int'(valid_addr),
          "read APB count mismatch");
    if (valid_addr)
      check(33, {last_write,last_addr,last_strb,last_prot} ===
                {1'b0,addr[15:0],4'b0,prot}, "read APB payload mismatch");
    if (!valid_addr)
      check(34, apb_count == before_count, "invalid read touched APB");
  endtask

  task automatic reset_bridge;
    AWVALID = 0; WVALID = 0; ARVALID = 0;
    BREADY = 0; RREADY = 0;
    rst_n = 0;
    #0.2;
    apb_active = 0;
    wait_left = 0;
    step();
    step();
    check(37, BVALID === 1'b0 && RVALID === 1'b0 && PSEL === 1'b0,
          "reset did not flush requests/responses");
    rst_n = 1;
    for (int i=0; i<8; i++) begin
      step();
      check(37, BVALID === 1'b0 && RVALID === 1'b0 && PSEL === 1'b0,
            "ghost transfer after reset");
    end
  endtask

  task automatic simultaneous_pair(input bit first_write);
    int before_count;
    bit aw_done, w_done, ar_done;
    logic [31:0] read_expected;
    before_count = apb_count;
    read_expected = mem[16'h0044 >> 2];
    AWADDR = 32'h0000_0040; AWPROT = 3'b101; AWVALID = 1;
    WDATA = 32'hfedc_ba98; WSTRB = 4'b0101; WVALID = 1;
    ARADDR = 32'h0000_0044; ARPROT = 3'b011; ARVALID = 1;
    aw_done = 0; w_done = 0; ar_done = 0;
    next_wait = 2;
    for (int i=0; i<80 && !(aw_done && w_done && ar_done); i++) begin
      step();
      if (aw_hs) begin AWVALID = 0; aw_done = 1; end
      if (w_hs) begin WVALID = 0; w_done = 1; end
      if (ar_hs) begin ARVALID = 0; ar_done = 1; end
    end
    check(35, aw_done && w_done && ar_done, "simultaneous AXI accept failed");
    for (int i=0; i<160 && apb_count < before_count+2; i++) step();
    check(35, apb_count == before_count+2, "read/write APB arbitration timeout");
    if (apb_count >= before_count+2) begin
      check(35, event_write[before_count] == first_write,
            "first APB transaction violated read/write alternation");
      check(35, event_write[before_count+1] != first_write,
            "second APB transaction did not serve other direction");
    end
    receive_b(2'b00);
    receive_r(2'b00,read_expected);
  endtask

  initial begin
    seed = 20260925;
    void'($value$plusargs("SEED=%d",seed));
    rng = 32'(seed) ^ 32'h3c6ef372;
    clk = 0; rst_n = 0;
    AWADDR = 0; AWPROT = 0; AWVALID = 0;
    WDATA = 0; WSTRB = 0; WVALID = 0; BREADY = 0;
    ARADDR = 0; ARPROT = 0; ARVALID = 0; RREADY = 0;
    PRDATA = 0; PREADY = 0; PSLVERR = 0;
    apb_active = 0; apb_count = 0; wait_left = 0; next_wait = 0;
    for (int i=0; i<16384; i++) mem[i] = 32'h9000_0000 ^ 32'(i*17);
    for (int i=32; i<=37; i++) begin
      passed[i]=0; total[i]=0; first_failure[i]=0;
    end
    check(32, $bits(dut.AWADDR)==32 && $bits(dut.WSTRB)==4 &&
              $bits(dut.PADDR)==16 && $bits(dut.PSTRB)==4,
          "fixed interface width");
    reset_bridge();
    write_tx(0,32'h10,32'h1234_5678,4'hf,3'b101);
    write_tx(1,32'h14,32'h89ab_cdef,4'b0101,3'b010);
    write_tx(0,32'h18,32'hffff_ffff,4'b0000,3'b111);
    write_tx(1,32'h0001_0010,32'habcd_1234,4'hf,0);
    read_tx(32'h10,3'b001);
    read_tx(32'h20,3'b010);
    read_tx(32'h3,3'b111);
    read_tx(32'h0002_0010,0);
    reset_bridge();
    simultaneous_pair(1);
    write_tx(0,32'h48,32'h3434_3434,4'hf,0);
    simultaneous_pair(0);
    for (int i=0; i<180; i++) begin
      logic [31:0] addr;
      rng = next_random(rng);
      addr = 32'((rng >> 5) & 32'hfffc);
      if (i%19==0) addr = 32'h0001_0000 | addr;
      else if (i%23==0) addr = addr | 1;
      else if (i%29==0) addr = 32'h20;
      write_tx(rng[4],addr,rng,4'(rng>>8),3'(rng>>12));
      if (i%3==0) read_tx(addr,3'(rng>>16));
    end
    send_aw(32'h0000_0050,3'b010);
    reset_bridge();
    send_aw(32'h0000_0054,0);
    send_w(32'habcd_1234,4'hf);
    for (int i=0; i<20 && !(PSEL && !PENABLE); i++) step();
    check(37, PSEL && !PENABLE, "could not reach SETUP for reset test");
    reset_bridge();
    next_wait = 8;
    send_aw(32'h0000_0058,0);
    send_w(32'h5678_abcd,4'hf);
    for (int i=0; i<20 && !(PSEL && PENABLE); i++) step();
    check(37, PSEL && PENABLE, "could not reach ACCESS for reset test");
    reset_bridge();
    send_aw(32'h0000_005c,0);
    send_w(32'h1111_2222,4'hf);
    for (int i=0; i<50 && !BVALID; i++) step();
    check(37, BVALID, "could not reach blocked B response");
    reset_bridge();
    write_tx(1,32'h60,32'h5555_aaaa,4'hf,3'b111);
    read_tx(32'h60,3'b111);
    for (int i=32; i<=37; i++)
      $display("IC_GROUP AC-%02d %0d %0d",i,passed[i],total[i]);
    $finish;
  end
endmodule
