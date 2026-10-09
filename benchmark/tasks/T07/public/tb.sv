`timescale 1ns/1ps

module tb_T07;
  logic clk, rst_n;
  logic req_valid, req_ready, req_write;
  logic [31:0] req_addr, req_wdata;
  logic [3:0] req_wstrb;
  logic rsp_valid, rsp_ready;
  logic [31:0] rsp_rdata;
  logic mem_req_valid, mem_req_ready, mem_req_write;
  logic [31:0] mem_req_addr;
  logic [127:0] mem_req_wdata;
  logic mem_rsp_valid, mem_rsp_ready;
  logic [127:0] mem_rsp_rdata;

  logic [127:0] backing [0:31];
  logic [127:0] ref_backing [0:31];
  logic [127:0] ref_lines [0:15];
  logic [23:0] ref_tags [0:15];
  bit ref_valid [0:15];
  bit ref_dirty [0:15];
  logic [31:0] expected_addr [0:1];
  logic [127:0] expected_data [0:1];
  bit expected_write [0:1];
  int expected_count, expected_seen;
  logic [127:0] pending_data;
  bit pending_rsp, held_req, held_cpu_rsp;
  logic [31:0] held_addr, held_rsp_data;
  logic [127:0] held_data;
  logic [1:0] held_rsp_type;
  logic [3:0] held_strb;
  bit held_write;
  int cycle_count, delay_left, seed;
  bit req_hs, rsp_hs, mem_req_hs, mem_rsp_hs;

  direct_mapped_writeback_cache dut (.*);

  function automatic logic [31:0] word_at(input logic [127:0] line,
                                            input logic [1:0] word_index);
    return line[32*int'(word_index) +: 32];
  endfunction

  function automatic logic [127:0] put_word(input logic [127:0] old_line,
                                             input logic [1:0] word_index,
                                             input logic [31:0] data,
                                             input logic [3:0] strb);
    logic [127:0] result;
    result = old_line;
    for (int byte_index = 0; byte_index < 4; byte_index++)
      if (strb[byte_index])
        result[32*int'(word_index) + 8*byte_index +: 8] = data[8*byte_index +: 8];
    return result;
  endfunction

  task automatic step;
    bit take_req, take_rsp;
    logic [127:0] response_line;
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    mem_req_ready = (cycle_count % 5 != 2);
    mem_rsp_valid = pending_rsp && delay_left == 0;
    mem_rsp_rdata = pending_data;
    #2;
    req_hs = req_valid && req_ready;
    rsp_hs = rsp_valid && rsp_ready;
    mem_req_hs = mem_req_valid && mem_req_ready;
    mem_rsp_hs = mem_rsp_valid && mem_rsp_ready;
    if (held_req && (!mem_req_valid ||
                     {mem_req_addr,mem_req_write,mem_req_wdata} !==
                     {held_addr,held_write,held_data}))
      $fatal(1, "AC-42 backend request changed under backpressure");
    held_req = mem_req_valid && !mem_req_ready;
    if (held_req) begin
      held_addr = mem_req_addr;
      held_write = mem_req_write;
      held_data = mem_req_wdata;
    end
    if (held_cpu_rsp && (!rsp_valid || rsp_rdata !== held_rsp_data))
      $fatal(1, "AC-42 CPU response changed under backpressure");
    held_cpu_rsp = rsp_valid && !rsp_ready;
    if (held_cpu_rsp) held_rsp_data = rsp_rdata;
    take_req = mem_req_hs;
    take_rsp = mem_rsp_hs;
    if (take_req) begin
      if (pending_rsp) $fatal(1, "AC-42 multiple backend requests outstanding");
      if (expected_seen >= expected_count)
        $fatal(1, "AC-38 unexpected backend request addr=%h", mem_req_addr);
      if ({mem_req_write,mem_req_addr} !==
          {expected_write[expected_seen],expected_addr[expected_seen]})
        $fatal(1, "AC-39/40 backend order/address wrong expected=%b/%h actual=%b/%h",
               expected_write[expected_seen],expected_addr[expected_seen],
               mem_req_write,mem_req_addr);
      if (mem_req_write && mem_req_wdata !== expected_data[expected_seen])
        $fatal(1, "AC-40/41 writeback data mismatch addr=%h", mem_req_addr);
      if (mem_req_addr[3:0] != 0 || mem_req_addr[31:9] != 0)
        $fatal(1, "AC-39 backend address outside test memory");
      response_line = backing[mem_req_addr[8:4]];
      if (mem_req_write) backing[mem_req_addr[8:4]] = mem_req_wdata;
      pending_data = response_line;
      pending_rsp = 1;
      delay_left = 2;
      expected_seen++;
    end
    clk = 1;
    #2;
    clk = 0;
    #2;
    cycle_count++;
    if (take_rsp) pending_rsp = 0;
    else if (pending_rsp && delay_left > 0) delay_left--;
  endtask

  task automatic prepare_reference(input bit write_op, input logic [31:0] addr,
                                   input logic [31:0] data, input logic [3:0] strb,
                                   output logic [31:0] expected_rsp);
    int index, line_number, victim_number;
    logic [23:0] tag;
    index = int'(addr[7:4]);
    line_number = int'(addr[8:4]);
    tag = addr[31:8];
    expected_count = 0;
    expected_seen = 0;
    if (!ref_valid[index] || ref_tags[index] != tag) begin
      if (ref_valid[index] && ref_dirty[index]) begin
        victim_number = int'({ref_tags[index][0], 4'(index)});
        expected_write[expected_count] = 1;
        expected_addr[expected_count] = {ref_tags[index], 4'(index), 4'b0};
        expected_data[expected_count] = ref_lines[index];
        expected_count++;
        if (victim_number >= 32) $fatal(1, "reference victim outside memory");
        ref_backing[victim_number] = ref_lines[index];
      end
      expected_write[expected_count] = 0;
      expected_addr[expected_count] = {addr[31:4],4'b0};
      expected_data[expected_count] = 0;
      expected_count++;
      ref_lines[index] = ref_backing[line_number];
      ref_tags[index] = tag;
      ref_valid[index] = 1;
      ref_dirty[index] = 0;
    end
    expected_rsp = write_op ? 0 : word_at(ref_lines[index], addr[3:2]);
    if (write_op && strb != 0) begin
      ref_lines[index] = put_word(ref_lines[index], addr[3:2], data, strb);
      ref_dirty[index] = 1;
    end
  endtask

  task automatic cpu_tx(input bit write_op, input logic [31:0] addr,
                        input logic [31:0] data, input logic [3:0] strb);
    logic [31:0] expected_rsp;
    int accepted_cycle;
    bit accepted, returned;
    prepare_reference(write_op, addr, data, strb, expected_rsp);
    req_valid = 1;
    req_write = write_op;
    req_addr = addr;
    req_wdata = data;
    req_wstrb = strb;
    accepted = 0;
    for (int i = 0; i < 80; i++) begin
      step();
      if (req_hs) begin
        req_valid = 0;
        accepted_cycle = cycle_count;
        accepted = 1;
        break;
      end
    end
    if (!accepted) $fatal(1, "AC-42 CPU request timeout addr=%h", addr);
    returned = 0;
    for (int i = 0; i < 100; i++) begin
      #1;
      if (rsp_valid) begin
        if (rsp_rdata !== expected_rsp)
          $fatal(1, "AC-38/41 response addr=%h expected=%h actual=%h",
                 addr, expected_rsp, rsp_rdata);
        if (expected_count == 0 && cycle_count - accepted_cycle > 2)
          $fatal(1, "AC-43 warm hit response later than two cycles");
        repeat (2) begin
          step();
          #1;
          if (!rsp_valid || rsp_rdata !== expected_rsp)
            $fatal(1, "AC-42 CPU response lost under backpressure");
        end
        rsp_ready = 1;
        step();
        if (!rsp_hs) $fatal(1, "AC-42 CPU response handshake missing");
        rsp_ready = 0;
        returned = 1;
        break;
      end
      step();
    end
    if (!returned) $fatal(1, "AC-38 CPU response timeout addr=%h", addr);
    if (expected_seen != expected_count)
      $fatal(1, "AC-39/40 missing backend transaction addr=%h expected=%0d seen=%0d",
             addr, expected_count, expected_seen);
    step();
  endtask

  initial begin
    if ($bits(dut.mem_req_wdata) != 128 || $bits(dut.mem_rsp_rdata) != 128 ||
        $bits(dut.req_addr) != 32 || $bits(dut.req_wstrb) != 4)
      $fatal(1, "T07 fixed port width mismatch");
    seed = 20260925;
    void'($value$plusargs("SEED=%d", seed));
    clk = 0; rst_n = 0;
    req_valid = 0; req_addr = 0; req_write = 0;
    req_wdata = 0; req_wstrb = 0; rsp_ready = 0;
    mem_req_ready = 0; mem_rsp_valid = 0; mem_rsp_rdata = 0;
    pending_rsp = 0; delay_left = 0;
    held_req = 0; held_cpu_rsp = 0;
    expected_count = 0; expected_seen = 0; cycle_count = 0;
    for (int line_index = 0; line_index < 32; line_index++) begin
      backing[line_index] = {32'(line_index*4+3),32'(line_index*4+2),
                             32'(line_index*4+1),32'(line_index*4)};
      ref_backing[line_index] = backing[line_index];
    end
    for (int index = 0; index < 16; index++) begin
      ref_valid[index] = 0;
      ref_dirty[index] = 0;
      ref_tags[index] = 0;
      ref_lines[index] = 0;
    end
    step(); step();
    rst_n = 1;
    step();
    cpu_tx(0, 32'h0000_0000, 0, 0);
    cpu_tx(0, 32'h0000_0004, 0, 0);
    cpu_tx(1, 32'h0000_0000, 32'h1234_5678, 4'b0101);
    cpu_tx(0, 32'h0000_0000, 0, 0);
    cpu_tx(1, 32'h0000_0008, 32'(seed), 4'hf);
    cpu_tx(0, 32'h0000_0100, 0, 0);
    cpu_tx(0, 32'h0000_0000, 0, 0);
    cpu_tx(1, 32'h0000_010c, 32'hdead_beef, 4'b1010);
    cpu_tx(0, 32'h0000_000c, 0, 0);
    for (int line_index = 0; line_index < 32; line_index++)
      if (backing[line_index] !== ref_backing[line_index])
        $fatal(1, "AC-41 backing memory mismatch line=%0d", line_index);
    rst_n = 0;
    step(); step();
    for (int index = 0; index < 16; index++) ref_valid[index] = 0;
    rst_n = 1;
    step();
    cpu_tx(0, 32'h0000_0000, 0, 0);
    $display("PUBLIC_PASS T07 seed=%0d", seed);
    $finish;
  end
endmodule
