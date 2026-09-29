`timescale 1ns/1ps
module tb_hidden_T08;
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
  logic [127:0] backing [0:1023];
  logic [7:0] ref_memory [0:16383];
  logic [7:0] ref_cache [0:15][0:15];
  logic [23:0] ref_tag [0:15];
  bit ref_valid [0:15], ref_dirty [0:15];
  logic [31:0] expected_addr [0:1];
  logic [127:0] expected_data [0:1];
  bit expected_write [0:1];
  int expected_count, expected_seen, active_group;
  logic [127:0] pending_data;
  bit pending_rsp, held_req, held_cpu_rsp;
  logic [31:0] held_addr, held_rsp_data;
  logic [127:0] held_data;
  bit held_write;
  int cycle_count, delay_left, seed;
  int unsigned rng;
  bit req_hs, rsp_hs, mem_req_hs, mem_rsp_hs, last_rsp_correct;
  int passed [38:43], total [38:43];
  bit first_failure [38:43];

  direct_mapped_writeback_cache dut (.*);

  function automatic int mem_index(input logic [31:0] addr);
    return int'({addr[31],addr[12:4]});
  endfunction
  function automatic logic [127:0] ref_cache_line(input int index);
    logic [127:0] result;
    for (int b=0; b<16; b++) result[8*b +: 8] = ref_cache[index][b];
    return result;
  endfunction
  function automatic logic [31:0] ref_word(input int index, input int word_index);
    logic [31:0] result;
    for (int b=0; b<4; b++) result[8*b +: 8] = ref_cache[index][4*word_index+b];
    return result;
  endfunction
  function automatic int unsigned next_random(input int unsigned value);
    int unsigned x;
    x = value ^ (value << 13);
    x = x ^ (x >> 17);
    return x ^ (x << 5);
  endfunction
  task automatic check(input int id, input bit okay, input string what);
    total[id]++;
    if (okay) passed[id]++;
    else if (!first_failure[id]) begin
      first_failure[id] = 1;
      $display("IC_FAILURE AC-%02d cycle=%0d %s", id, cycle_count, what);
    end
  endtask

  task automatic step;
    bit take_rsp;
    logic [127:0] response_line;
    int key;
    if (clk !== 0) $fatal(1, "testbench clock phase error");
    rng = next_random(rng);
    mem_req_ready = ((rng & 7) < 6);
    mem_rsp_valid = pending_rsp && delay_left == 0;
    mem_rsp_rdata = pending_data;
    #0.4;
    req_hs = req_valid && req_ready;
    rsp_hs = rsp_valid && rsp_ready;
    mem_req_hs = mem_req_valid && mem_req_ready;
    mem_rsp_hs = mem_rsp_valid && mem_rsp_ready;
    if (held_req)
      check(42, mem_req_valid === 1'b1 &&
                {mem_req_addr,mem_req_write,mem_req_wdata} ===
                {held_addr,held_write,held_data},
            "backend request changed under backpressure");
    held_req = mem_req_valid && !mem_req_ready;
    if (held_req) begin
      held_addr = mem_req_addr;
      held_write = mem_req_write;
      held_data = mem_req_wdata;
    end
    if (held_cpu_rsp)
      check(42, rsp_valid === 1'b1 && rsp_rdata === held_rsp_data,
            "CPU response changed under backpressure");
    held_cpu_rsp = rsp_valid && !rsp_ready;
    if (held_cpu_rsp) held_rsp_data = rsp_rdata;
    if (mem_req_hs) begin
      check(42, !pending_rsp, "multiple backend requests outstanding");
      if (expected_seen >= expected_count) begin
        check(38, 0, "hit issued an unexpected backend request");
        check(43, 0, "unexpected backend request, possibly on hit");
      end else begin
        check(active_group,
              {mem_req_write,mem_req_addr} ===
              {expected_write[expected_seen],expected_addr[expected_seen]},
              $sformatf("backend order/address expected=%b/%h actual=%b/%h",
                        expected_write[expected_seen],expected_addr[expected_seen],
                        mem_req_write,mem_req_addr));
        if (expected_write[expected_seen])
          check(40, mem_req_wdata === expected_data[expected_seen],
                "dirty writeback line data mismatch");
      end
      check(42, mem_req_addr[3:0] == 0 && mem_req_addr[30:13] == 0,
            "backend address outside accepted memory map");
      key = mem_index(mem_req_addr);
      response_line = (mem_req_addr[30:13] == 0) ? backing[key] : '0;
      if (mem_req_write && mem_req_addr[30:13] == 0) backing[key] = mem_req_wdata;
      pending_data = response_line;
      pending_rsp = 1;
      delay_left = int'((rng >> 8) & 7);
      expected_seen++;
    end
    take_rsp = mem_rsp_hs;
    clk = 1;
    #0.4;
    clk = 0;
    #0.2;
    cycle_count++;
    if (take_rsp) pending_rsp = 0;
    else if (pending_rsp && delay_left > 0) delay_left--;
  endtask

  task automatic prepare_reference(input bit write_op, input logic [31:0] addr,
                                   input logic [31:0] data, input logic [3:0] strb,
                                   output logic [31:0] expected_rsp);
    int index, key, victim_key;
    logic [31:0] victim_addr;
    bit miss, dirty_victim;
    index = int'(addr[7:4]);
    key = mem_index(addr);
    expected_count = 0;
    expected_seen = 0;
    miss = !ref_valid[index] || ref_tag[index] != addr[31:8];
    dirty_victim = miss && ref_valid[index] && ref_dirty[index];
    active_group = dirty_victim ? 40 : miss ? 39 : 38;
    if (miss) begin
      if (dirty_victim) begin
        victim_addr = {ref_tag[index],4'(index),4'b0};
        victim_key = mem_index(victim_addr);
        expected_write[expected_count] = 1;
        expected_addr[expected_count] = victim_addr;
        expected_data[expected_count] = ref_cache_line(index);
        expected_count++;
        for (int b=0; b<16; b++) ref_memory[16*victim_key+b] = ref_cache[index][b];
      end
      expected_write[expected_count] = 0;
      expected_addr[expected_count] = {addr[31:4],4'b0};
      expected_data[expected_count] = '0;
      expected_count++;
      for (int b=0; b<16; b++) ref_cache[index][b] = ref_memory[16*key+b];
      ref_tag[index] = addr[31:8];
      ref_valid[index] = 1;
      ref_dirty[index] = 0;
    end
    expected_rsp = write_op ? 0 : ref_word(index,int'(addr[3:2]));
    if (write_op && strb != 0) begin
      for (int b=0; b<4; b++)
        if (strb[b]) ref_cache[index][4*int'(addr[3:2])+b] = data[8*b +: 8];
      ref_dirty[index] = 1;
    end
  endtask

  task automatic cpu_tx(input bit write_op, input logic [31:0] addr,
                        input logic [31:0] data, input logic [3:0] strb);
    logic [31:0] expected_rsp;
    int accepted_cycle;
    bit accepted, returned;
    prepare_reference(write_op,addr,data,strb,expected_rsp);
    req_valid = 1;
    req_write = write_op;
    req_addr = addr;
    req_wdata = data;
    req_wstrb = strb;
    accepted = 0;
    for (int i=0; i<160; i++) begin
      step();
      if (req_hs) begin
        req_valid = 0;
        accepted_cycle = cycle_count;
        accepted = 1;
        break;
      end
    end
    check(42, accepted, "CPU request handshake timeout");
    returned = 0;
    last_rsp_correct = 0;
    for (int i=0; i<220; i++) begin
      if (rsp_valid) begin
        last_rsp_correct = rsp_rdata === expected_rsp;
        check(active_group, last_rsp_correct,
              $sformatf("CPU response addr=%h expected=%h actual=%h",
                        addr,expected_rsp,rsp_rdata));
        if (write_op)
          check(41, rsp_rdata === 0, "write response data was nonzero");
        if (expected_count == 0)
          check(43, cycle_count - accepted_cycle <= 2,
                "warm hit response exceeded two cycles");
        for (int j=0; j<3; j++) begin
          step();
          check(42, rsp_valid === 1'b1 && rsp_rdata === expected_rsp,
                "CPU response lost during backpressure");
        end
        rsp_ready = 1;
        step();
        check(42, rsp_hs, "CPU response handshake missing");
        rsp_ready = 0;
        returned = 1;
        break;
      end
      step();
    end
    check(active_group, returned, "CPU response timeout");
    check(active_group, expected_seen == expected_count,
          "missing or extra backend request");
    if (expected_count == 0)
      check(43, expected_seen == 0, "hit accessed backend");
    step();
    check(42, rsp_valid === 1'b0, "duplicate CPU response");
  endtask

  task automatic reset_cache;
    req_valid = 0;
    rsp_ready = 0;
    check(43, !pending_rsp && !rsp_valid, "reset attempted while cache busy");
    rst_n = 0;
    step();
    step();
    for (int i=0; i<16; i++) begin
      ref_valid[i] = 0;
      ref_dirty[i] = 0;
    end
    rst_n = 1;
    step();
    check(43, !rsp_valid && !mem_req_valid, "ghost request after reset");
  endtask

  initial begin
    seed = 20260925;
    void'($value$plusargs("SEED=%d",seed));
    rng = 32'(seed) ^ 32'ha54ff53a;
    clk = 0; rst_n = 0;
    req_valid = 0; req_addr = 0; req_write = 0;
    req_wdata = 0; req_wstrb = 0; rsp_ready = 0;
    mem_req_ready = 0; mem_rsp_valid = 0; mem_rsp_rdata = 0;
    pending_rsp = 0; delay_left = 0;
    held_req = 0; held_cpu_rsp = 0;
    expected_count = 0; expected_seen = 0; active_group = 38;
    cycle_count = 0;
    for (int i=38; i<=43; i++) begin
      passed[i]=0; total[i]=0; first_failure[i]=0;
    end
    check(38, $bits(dut.mem_req_wdata)==128 && $bits(dut.mem_rsp_rdata)==128 &&
              $bits(dut.req_addr)==32 && $bits(dut.req_wstrb)==4,
          "fixed interface width");
    for (int key=0; key<1024; key++)
      for (int b=0; b<16; b++) begin
        logic [7:0] value;
        value = 8'(key*13+b*7+(key>>4));
        backing[key][8*b +: 8] = value;
        ref_memory[16*key+b] = value;
      end
    for (int i=0; i<16; i++) begin
      ref_valid[i]=0; ref_dirty[i]=0; ref_tag[i]=0;
      for (int b=0; b<16; b++) ref_cache[i][b]=0;
    end
    step(); step(); rst_n=1; step();
    cpu_tx(0,32'h0000_0000,0,0);
    cpu_tx(0,32'h0000_0004,0,0);
    cpu_tx(1,32'h0000_0000,32'h1234_5678,4'b0101);
    cpu_tx(0,32'h0000_0000,0,0);
    check(41,last_rsp_correct,"partial write readback failed");
    cpu_tx(0,32'h8000_0000,0,0);
    cpu_tx(0,32'h0000_0000,0,0);
    cpu_tx(1,32'h0000_010c,32'hdead_beef,4'b1010);
    cpu_tx(0,32'h0000_000c,0,0);
    for (int strb=0; strb<16; strb++) begin
      cpu_tx(1,32'h0000_0080,32'(strb*32'h01020408),4'(strb));
      cpu_tx(0,32'h0000_0080,0,0);
      check(41,last_rsp_correct,$sformatf("WSTRB=%h readback",4'(strb)));
    end
    for (int i=0; i<600; i++) begin
      logic [31:0] addr;
      rng = next_random(rng);
      addr = {rng[31],18'b0,rng[12:2],2'b0};
      if ((i%3)==0) cpu_tx(1,addr,rng,4'(rng>>16));
      else cpu_tx(0,addr,0,0);
    end
    // Force every remaining dirty line to evict before comparing memory bytes.
    for (int index=0; index<16; index++)
      if (ref_valid[index] && ref_dirty[index]) begin
        logic [31:0] conflict;
        conflict = {~ref_tag[index][23],ref_tag[index][22:0],4'(index),4'b0};
        cpu_tx(0,conflict,0,0);
      end
    for (int key=0; key<1024; key++)
      for (int b=0; b<16; b++)
        check(41, backing[key][8*b +: 8] === ref_memory[16*key+b],
              $sformatf("backing byte key=%0d offset=%0d",key,b));
    // This dirty update is deliberately not evicted: reset must discard it.
    cpu_tx(1,32'h0000_00c0,32'hfeed_8765,4'hf);
    reset_cache();
    cpu_tx(0,32'h0000_00c0,0,0);
    check(43, expected_count == 1, "reset failed to invalidate cache line");
    check(43, last_rsp_correct, "reset retained an uncommitted dirty word");
    cpu_tx(0,32'h0000_00c0,0,0);
    $display("IC_STATS cycles=%0d",cycle_count);
    for (int i=38; i<=43; i++)
      $display("IC_GROUP AC-%02d %0d %0d",i,passed[i],total[i]);
    $finish;
  end
endmodule
