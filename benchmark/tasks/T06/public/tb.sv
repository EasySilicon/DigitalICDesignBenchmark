`timescale 1ns/1ps

module tb_T06;
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
  logic [15:0] setup_addr;
  logic [31:0] setup_data;
  logic [3:0] setup_strb;
  logic [2:0] setup_prot;
  logic setup_write;
  bit apb_active;
  int apb_count, wait_left, next_wait;
  int seed;

  axi4lite_to_apb4_bridge dut (.*);

  function automatic logic [31:0] read_value(input logic [15:0] addr);
    return 32'h5a5a_0000 ^ {16'b0, addr};
  endfunction

  task automatic step;
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    PRDATA = read_value(PADDR);
    PSLVERR = (PADDR == 16'h0020);
    PREADY = (wait_left == 0);
    #2;
    aw_hs = AWVALID && AWREADY;
    w_hs = WVALID && WREADY;
    ar_hs = ARVALID && ARREADY;
    b_hs = BVALID && BREADY;
    r_hs = RVALID && RREADY;
    if (PSEL && !PENABLE) begin
      if (apb_active) $fatal(1, "AC-36 new APB setup while access pending");
      apb_active = 1;
      setup_addr = PADDR;
      setup_data = PWDATA;
      setup_strb = PSTRB;
      setup_prot = PPROT;
      setup_write = PWRITE;
      wait_left = next_wait;
      PREADY = (wait_left == 0);
    end else if (PSEL && PENABLE) begin
      if (!apb_active) $fatal(1, "AC-32/33 APB access without setup");
      if ({PADDR,PWDATA,PSTRB,PPROT,PWRITE} !==
          {setup_addr,setup_data,setup_strb,setup_prot,setup_write})
        $fatal(1, "AC-36 APB payload changed during access");
      if (PREADY) begin
        apb_count++;
        apb_active = 0;
      end else wait_left--;
    end else if (apb_active) $fatal(1, "AC-36 APB access disappeared");
    clk = 1;
    #2;
    clk = 0;
    #2;
  endtask

  task automatic send_aw(input logic [31:0] addr, input logic [2:0] prot);
    AWADDR = addr;
    AWPROT = prot;
    AWVALID = 1;
    for (int cycle = 0; cycle < 40; cycle++) begin
      step();
      if (aw_hs) begin
        AWVALID = 0;
        return;
      end
    end
    $fatal(1, "AC-35 AW handshake timeout");
  endtask

  task automatic send_w(input logic [31:0] data, input logic [3:0] strb);
    WDATA = data;
    WSTRB = strb;
    WVALID = 1;
    for (int cycle = 0; cycle < 40; cycle++) begin
      step();
      if (w_hs) begin
        WVALID = 0;
        return;
      end
    end
    $fatal(1, "AC-35 W handshake timeout");
  endtask

  task automatic receive_b(input logic [1:0] expected_resp);
    for (int cycle = 0; cycle < 60; cycle++) begin
      #1;
      if (BVALID) begin
        if (BRESP !== expected_resp)
          $fatal(1, "AC-34 BRESP expected=%b actual=%b", expected_resp, BRESP);
        repeat (3) begin
          step();
          #1;
          if (!BVALID || BRESP !== expected_resp)
            $fatal(1, "AC-36 B response not stable under backpressure");
        end
        BREADY = 1;
        step();
        if (!b_hs) $fatal(1, "AC-36 B handshake missing");
        BREADY = 0;
        return;
      end
      step();
    end
    $fatal(1, "AC-34 B response timeout");
  endtask

  task automatic write_tx(input bit w_first, input logic [31:0] addr,
                          input logic [31:0] data, input logic [3:0] strb,
                          input logic [2:0] prot, input logic [1:0] resp,
                          input bit expect_apb);
    int before_count;
    before_count = apb_count;
    if (w_first) begin
      send_w(data, strb);
      send_aw(addr, prot);
    end else begin
      send_aw(addr, prot);
      send_w(data, strb);
    end
    receive_b(resp);
    if (apb_count != before_count + int'(expect_apb))
      $fatal(1, "AC-32/34 APB write count mismatch");
    if (expect_apb && ({setup_write,setup_addr,setup_data,setup_strb,setup_prot} !==
                       {1'b1,addr[15:0],data,strb,prot}))
      $fatal(1, "AC-32 APB write payload mismatch");
  endtask

  task automatic read_tx(input logic [31:0] addr, input logic [2:0] prot,
                         input logic [1:0] resp, input bit expect_apb);
    int before_count;
    logic [31:0] expected_data;
    before_count = apb_count;
    expected_data = resp == 0 ? read_value(addr[15:0]) : 0;
    ARADDR = addr;
    ARPROT = prot;
    ARVALID = 1;
    for (int cycle = 0; cycle < 40; cycle++) begin
      step();
      if (ar_hs) begin
        ARVALID = 0;
        break;
      end
      if (cycle == 39) $fatal(1, "AC-33 AR handshake timeout");
    end
    for (int cycle = 0; cycle < 60; cycle++) begin
      #1;
      if (RVALID) begin
        if (RRESP !== resp || RDATA !== expected_data)
          $fatal(1, "AC-33/34 R response expected=%b/%h actual=%b/%h",
                 resp, expected_data, RRESP, RDATA);
        repeat (3) begin
          step();
          #1;
          if (!RVALID || RRESP !== resp || RDATA !== expected_data)
            $fatal(1, "AC-36 R response not stable under backpressure");
        end
        RREADY = 1;
        step();
        if (!r_hs) $fatal(1, "AC-36 R handshake missing");
        RREADY = 0;
        break;
      end
      step();
      if (cycle == 59) $fatal(1, "AC-33 R response timeout");
    end
    if (apb_count != before_count + int'(expect_apb))
      $fatal(1, "AC-33/34 APB read count mismatch");
    if (expect_apb && ({setup_write,setup_addr,setup_strb,setup_prot} !==
                       {1'b0,addr[15:0],4'b0,prot}))
      $fatal(1, "AC-33 APB read payload mismatch");
  endtask

  initial begin
    if ($bits(dut.AWADDR) != 32 || $bits(dut.WSTRB) != 4 ||
        $bits(dut.PADDR) != 16 || $bits(dut.PSTRB) != 4)
      $fatal(1, "T06 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    clk = 0; rst_n = 0;
    AWADDR = 0; AWPROT = 0; AWVALID = 0;
    WDATA = 0; WSTRB = 0; WVALID = 0; BREADY = 0;
    ARADDR = 0; ARPROT = 0; ARVALID = 0; RREADY = 0;
    PRDATA = 0; PREADY = 0; PSLVERR = 0;
    apb_active = 0; apb_count = 0; wait_left = 0; next_wait = 0;
    step();
    rst_n = 1;
    step();
    write_tx(0, 32'h0000_0010, 32'h1234_5678, 4'hf, 3'b101, 2'b00, 1);
    next_wait = 3;
    write_tx(1, 32'h0000_0014, 32'h89ab_cdef, 4'b0101, 3'b010, 2'b00, 1);
    next_wait = 0;
    write_tx(0, 32'h0000_0018, 32'hffff_ffff, 4'b0000, 3'b111, 2'b00, 0);
    write_tx(1, 32'h0001_0010, 32'habcd_1234, 4'hf, 3'b000, 2'b11, 0);
    read_tx(32'h0000_001c, 3'b011, 2'b00, 1);
    next_wait = 2;
    read_tx(32'h0000_0020, 3'b001, 2'b10, 1);
    read_tx(32'h0000_0003, 3'b010, 2'b11, 0);
    read_tx(32'h0002_0010, 3'b111, 2'b11, 0);
    $display("PUBLIC_PASS T06 seed=%0d", seed);
    $finish;
  end
endmodule
