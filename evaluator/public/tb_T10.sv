`timescale 1ns/1ps
module tb_T10;
  localparam int MAX_BLOCKS = 512;
  localparam int FIRST_ROW_LATENCY_LIMIT = 64;
  localparam int LAST_ROW_LATENCY_LIMIT = 80;
  logic clk = 0;
  always #5 clk = ~clk;
  logic rst_n = 0;
  logic in_valid = 0, in_ready, in_start = 0;
  logic [15:0] in_block_id = 0;
  logic [3:0] mode = 0;
  logic [255:0] a_scale = 0, b_scale = 0;
  logic [1023:0] a_data = 0, b_data = 0;
  logic [3:0] out_valid;
  logic out_ready = 0;
  logic [63:0] out_block_id;
  logic [15:0] out_row;
  logic [4095:0] out_data;
  npu_systolic_matmul_16x16 dut (.*);

  int cycle = 0, next_tag = 0, finished = 0;
  int active_input_tag = -1, active_input_beats = 0;
  int last_input_cycle [0:MAX_BLOCKS-1];
  int next_output_row [0:MAX_BLOCKS-1];
  int expected_mode [0:MAX_BLOCKS-1];
  bit expected_last_only [0:MAX_BLOCKS-1];
  bit accepted [0:MAX_BLOCKS-1];
  bit steady_check = 0;
  int steady_begin = 0, steady_end = 0, steady_rows = 0;
  bit held = 0;
  logic [3:0] held_valid;
  logic [63:0] held_id;
  logic [15:0] held_row;
  logic [4095:0] held_data;

  function automatic int width_of(input int m);
    if (m == 1 || m == 2 || m == 3) return 16;
    if (m == 6 || m == 9) return 4;
    return 8;
  endfunction

  function automatic logic [15:0] one_code(input int m, input bit negative);
    case (m)
      0: return negative ? 16'h00ff : 16'h0001;
      1: return negative ? 16'hffff : 16'h0001;
      2: return negative ? 16'hbc00 : 16'h3c00;
      3: return negative ? 16'hbf80 : 16'h3f80;
      4,7: return negative ? 16'h00b8 : 16'h0038;
      5,8: return negative ? 16'h00bc : 16'h003c;
      6,9: return negative ? 16'h000a : 16'h0002;
      default: $fatal(1, "bad mode");
    endcase
  endfunction

  function automatic logic [1023:0] make_beat(input int m, input bit last_only,
                                                input int beat, input bit is_a);
    logic [1023:0] beat_bits;
    logic [15:0] code;
    int w, lanes;
    beat_bits = '0;
    w = width_of(m);
    lanes = 64 / w;
    for (int vector=0; vector<16; vector++) begin
      for (int lane=0; lane<lanes; lane++) begin
        code = '0;
        if (!last_only || (beat == w-1 && lane == lanes-1))
          code = one_code(m, last_only && (vector[0] != 0));
        for (int bit_idx=0; bit_idx<w; bit_idx++)
          beat_bits[(vector*lanes+lane)*w+bit_idx] = code[bit_idx];
      end
    end
    return beat_bits;
  endfunction

  function automatic logic [63:0] expected_lane(input int m, input bit last_only,
                                                  input int row, input int col);
    bit negative;
    negative = last_only && ((row+col) % 2 != 0);
    if (m <= 1)
      return negative ? 64'hffff_ffff_ffff_ffff :
             (last_only ? 64'd1 : 64'd64);
    return negative ? 64'h0000_0000_bf80_0000 :
           (last_only ? 64'h0000_0000_3f80_0000 :
                        64'h0000_0000_4280_0000);
  endfunction

  always @(posedge clk) begin : monitor
    int tag, row, w, valid_count;
    logic [63:0] actual;
    if (rst_n) begin
      cycle = cycle + 1;
      if (in_valid && in_ready) begin
        if (in_start) begin
          tag = int'(in_block_id);
          if (active_input_beats != 0 || tag >= MAX_BLOCKS || accepted[tag])
            $fatal(1, "bad block start tag=%0d cycle=%0d", tag, cycle);
          active_input_tag = tag;
          active_input_beats = 0;
          accepted[tag] = 1;
          expected_mode[tag] = int'(mode);
          next_output_row[tag] = 0;
          last_input_cycle[tag] = -1;
        end else if (active_input_beats == 0)
          $fatal(1, "non-start input at block boundary");
        active_input_beats++;
        w = width_of(expected_mode[active_input_tag]);
        if (active_input_beats == w) begin
          last_input_cycle[active_input_tag] = cycle;
          active_input_tag = -1;
          active_input_beats = 0;
        end
      end
      if (held) begin
        if (out_valid !== held_valid)
          $fatal(1, "output valid changed under backpressure cycle=%0d", cycle);
        for (int slot=0;slot<4;slot++)
          if (held_valid[slot] &&
              (out_block_id[slot*16 +: 16] !== held_id[slot*16 +: 16] ||
               out_row[slot*4 +: 4] !== held_row[slot*4 +: 4] ||
               out_data[slot*1024 +: 1024] !== held_data[slot*1024 +: 1024]))
            $fatal(1, "output slot changed under backpressure cycle=%0d", cycle);
      end
      held = (out_valid != 0 && !out_ready);
      if (held) begin
        held_valid = out_valid;
        held_id = out_block_id;
        held_row = out_row;
        held_data = out_data;
      end
      valid_count = 0;
      for (int slot=0; slot<4; slot++) begin
        if (out_valid[slot]) begin
          valid_count++;
          if (out_ready) begin
            tag = int'(out_block_id[slot*16 +: 16]);
            row = int'(out_row[slot*4 +: 4]);
            if (tag >= MAX_BLOCKS || !accepted[tag] ||
                last_input_cycle[tag] < 0 || cycle <= last_input_cycle[tag])
              $fatal(1, "early/unknown output tag=%0d cycle=%0d", tag, cycle);
            if (row != next_output_row[tag])
              $fatal(1, "missing/duplicate/reordered row tag=%0d row=%0d expected=%0d",
                     tag, row, next_output_row[tag]);
            if (row == 0 && cycle-last_input_cycle[tag] > FIRST_ROW_LATENCY_LIMIT)
              $fatal(1, "first row latency tag=%0d", tag);
            if (row == 15 && cycle-last_input_cycle[tag] > LAST_ROW_LATENCY_LIMIT)
              $fatal(1, "last row latency tag=%0d", tag);
            for (int col=0; col<16; col++) begin
              actual = out_data[slot*1024 + col*64 +: 64];
              if (actual !== expected_lane(expected_mode[tag],
                                            expected_last_only[tag], row, col))
                $fatal(1, "wrong C tag=%0d row=%0d col=%0d got=%h", tag,row,col,actual);
            end
            next_output_row[tag]++;
            if (next_output_row[tag] == 16) finished++;
          end
        end
      end
      if (steady_check && cycle >= steady_begin && cycle <= steady_end) begin
        if (!out_ready || !in_ready || valid_count != steady_rows)
          $fatal(1, "steady rate failed cycle=%0d got_rows=%0d expected=%0d in_ready=%b",
                 cycle, valid_count, steady_rows, in_ready);
      end
    end
  end

  task automatic send_one(input int m, input bit last_only);
    int tag, w;
    tag = next_tag;
    if (tag >= MAX_BLOCKS) $fatal(1, "testbench tag capacity");
    next_tag++;
    expected_last_only[tag] = last_only;
    w = width_of(m);
    for (int beat=0; beat<w; beat++) begin
      in_valid = 1;
      in_start = (beat == 0);
      // Metadata is meaningful only on the first accepted beat.
      in_block_id = beat == 0 ? 16'(tag) : ~16'(tag);
      mode = beat == 0 ? 4'(m) : 4'((m+1)%10);
      a_scale = beat == 0 ? {32{8'd127}} : {32{8'd254}};
      b_scale = beat == 0 ? {32{8'd127}} : {32{8'd0}};
      a_data = make_beat(m,last_only,beat,1);
      b_data = make_beat(m,last_only,beat,0);
      #1;
      if (!in_ready)
        $fatal(1, "input bubble mode=%0d tag=%0d beat=%0d",m,tag,beat);
      @(posedge clk);
      @(negedge clk);
    end
  endtask

  task automatic drain(input int expected_finished);
    int timeout_count;
    in_valid = 0;
    in_start = 0;
    timeout_count = 0;
    while (finished < expected_finished && timeout_count < 256) begin
      @(negedge clk);
      timeout_count++;
    end
    if (finished != expected_finished)
      $fatal(1, "missing rows: finished=%0d expected=%0d",finished,expected_finished);
  endtask

  task automatic run_train(input int m, input int blocks);
    int start_cycle, w;
    w = width_of(m);
    start_cycle = cycle + 1;
    steady_begin = start_cycle + 64;
    steady_end = start_cycle + blocks*w - 1;
    steady_rows = 16 / w;
    steady_check = 1;
    out_ready = 1;
    for (int block=0; block<blocks; block++)
      send_one(m, block[0] != 0);
    steady_check = 0;
    drain(next_tag);
  endtask

  initial begin
    int wait_count;
    for (int i=0; i<MAX_BLOCKS; i++) begin
      accepted[i] = 0;
      next_output_row[i] = 0;
      expected_last_only[i] = 0;
    end
    repeat (2) @(negedge clk);
    rst_n = 1;
    @(negedge clk);
    for (int m=0; m<10; m++) begin
      if (width_of(m) == 4) run_train(m,40);
      else if (width_of(m) == 8) run_train(m,24);
      else run_train(m,16);
    end
    out_ready = 0;
    send_one(9,0);
    in_valid = 0;
    in_start = 0;
    wait_count = 0;
    while (out_valid == 0 && wait_count < 64) begin
      @(negedge clk);
      wait_count++;
    end
    if (out_valid == 0) $fatal(1,"backpressure setup timeout");
    repeat (5) @(negedge clk);
    out_ready = 1;
    drain(next_tag);
    $display("PUBLIC_PASS T10 blocks=%0d continuous_input=1 four_row_slots=1",next_tag);
    $finish;
  end
endmodule
