`timescale 1ns/1ps
module tb_hidden_T10_stream;
  localparam int MAX_CASES = 4096;
  logic clk=0;
  always #5 clk=~clk;
  logic rst_n=0, in_valid=0, in_ready, in_start=0;
  logic [15:0] in_block_id=0;
  logic [3:0] mode=0;
  logic [255:0] a_scale=0, b_scale=0;
  logic [1023:0] a_data=0, b_data=0;
  logic [3:0] out_valid;
  logic out_ready=1;
  logic [63:0] out_block_id;
  logic [15:0] out_row;
  logic [4095:0] out_data;
  logic [1023:0] a_mem[0:MAX_CASES*16-1];
  logic [1023:0] b_mem[0:MAX_CASES*16-1];
  logic [255:0] as_mem[0:MAX_CASES-1];
  logic [255:0] bs_mem[0:MAX_CASES-1];
  logic [3:0] mode_mem[0:MAX_CASES-1];
  logic [3:0] phase_mem[0:MAX_CASES-1];
  int case_count;
  int first_latency_limit=64, last_latency_limit=80;
  string vectors;
  int cycle=0, active_tag=-1, active_beats=0, finished=0;
  int last_input[0:MAX_CASES-1];
  int next_row[0:MAX_CASES-1];
  bit accepted[0:MAX_CASES-1];
  bit input_error[0:MAX_CASES-1];
  bit output_error[0:MAX_CASES-1];
  bit latency_error[0:MAX_CASES-1];
  bit phase_error[0:13];
  bit steady_check=0;
  bit bp_active=0;
  bit bp_mixed=0;
  int steady_begin=0, steady_end=0, steady_rows=0;
  int current_phase=0;
  bit held=0;
  logic [3:0] held_valid;
  logic [63:0] held_id;
  logic [15:0] held_row;
  logic [4095:0] held_data;
  bit report_emitted=0;
  npu_systolic_matmul_16x16 dut (.*);

  always @(negedge clk)
    if (rst_n && bp_active) out_ready=((cycle % 53)>=32);

  function automatic int width_of(input int m);
    if (m==1 || m==2 || m==3) return 16;
    if (m==6 || m==9) return 4;
    return 8;
  endfunction

  task automatic emit_report(input string reason);
    if (!report_emitted) begin
      report_emitted=1;
      for (int i=0;i<case_count;i++)
        $display("MM_CASE %0d %0d %0d %0d %0d",i,
                 int'(!output_error[i]),
                 int'(!latency_error[i] && !phase_error[int'(phase_mem[i])]),
                 int'(!input_error[i] && !output_error[i]),next_row[i]);
      $display("MM_STREAM input_bubble_phases=%b finished=%0d",
               {phase_error[13],phase_error[12],phase_error[11],
               phase_error[10],phase_error[9],phase_error[8],phase_error[7],
               phase_error[6],phase_error[5],phase_error[4],phase_error[3],
               phase_error[2],phase_error[1],phase_error[0]},finished);
      $display("MM_END reason=%s",reason);
    end
  endtask

  always @(posedge clk) begin : monitor
    int tag, row, valid_count;
    if (rst_n) begin
      cycle++;
      if (in_valid && in_ready) begin
        if (in_start) begin
          tag=int'(in_block_id);
          if (tag>=case_count || accepted[tag] || active_beats!=0) begin
            phase_error[current_phase]=1;
            emit_report("invalid block start");
            $fatal(1,"invalid block start tag=%0d",tag);
          end
          accepted[tag]=1;
          active_tag=tag;
          active_beats=0;
          last_input[tag]=-1;
        end else if (active_beats==0) begin
          phase_error[current_phase]=1;
          emit_report("missing in_start at block boundary");
          $fatal(1,"missing in_start at block boundary");
        end
        active_beats++;
        if (active_beats==width_of(int'(mode_mem[active_tag]))) begin
          last_input[active_tag]=cycle;
          active_beats=0;
          active_tag=-1;
        end
      end
      if (held) begin
        if (out_valid!==held_valid) phase_error[current_phase]=1;
        for (int slot=0;slot<4;slot++)
          if (held_valid[slot] &&
              (out_block_id[slot*16 +: 16]!==held_id[slot*16 +: 16] ||
               out_row[slot*4 +: 4]!==held_row[slot*4 +: 4] ||
               out_data[slot*1024 +: 1024]!==held_data[slot*1024 +: 1024]))
            phase_error[current_phase]=1;
      end
      held=(out_valid!=0 && !out_ready);
      if (held) begin
        held_valid=out_valid;
        held_id=out_block_id;
        held_row=out_row;
        held_data=out_data;
      end
      valid_count=0;
      for (int slot=0;slot<4;slot++) begin
        if (out_valid[slot]) begin
          valid_count++;
          if (out_ready) begin
            tag=int'(out_block_id[slot*16 +: 16]);
            row=int'(out_row[slot*4 +: 4]);
            if (tag>=case_count) begin
              phase_error[current_phase]=1;
              emit_report("unknown output tag");
              $fatal(1,"unknown output tag=%0d",tag);
            end
            if (!accepted[tag] || last_input[tag]<0 || cycle<=last_input[tag])
              output_error[tag]=1;
            if (row!=next_row[tag]) output_error[tag]=1;
            if (phase_mem[tag]!=4'd11 && phase_mem[tag]!=4'd13 &&
                !(bp_mixed && phase_mem[tag]==4'd12)) begin
              if (row==0 && cycle-last_input[tag]>first_latency_limit) latency_error[tag]=1;
              if (row==15 && cycle-last_input[tag]>last_latency_limit) latency_error[tag]=1;
            end
            $display("MM_ROW %0d %0d %h",tag,row,out_data[slot*1024 +: 1024]);
            if (row==next_row[tag]) begin
              next_row[tag]++;
              if (next_row[tag]==16) finished++;
            end
          end
        end
      end
      if (steady_check && cycle>=steady_begin && cycle<=steady_end &&
          (!out_ready || !in_ready || valid_count!=steady_rows))
        phase_error[current_phase]=1;
    end
  end

  task automatic drive_case(input int index);
    int wait_count, beats;
    beats=width_of(int'(mode_mem[index]));
    for (int beat=0;beat<beats;beat++) begin
      if (current_phase==11 && index%4==0 && beat==2) begin
        in_valid=0;
        #1;
        if (!in_ready) input_error[index]=1;
        @(posedge clk);
        @(negedge clk);
      end
      in_valid=1;
      in_start=(beat==0);
      // Deliberately poison metadata after the first beat. A compliant DUT
      // retains the first beat's ID, format and scales for the whole block.
      in_block_id=(beat==0) ? 16'(index) : ~16'(index);
      mode=(beat==0) ? mode_mem[index] : 4'((int'(mode_mem[index])+1)%10);
      a_scale=(beat==0) ? as_mem[index] : ~as_mem[index];
      b_scale=(beat==0) ? bs_mem[index] : ~bs_mem[index];
      a_data=a_mem[index*16+beat];
      b_data=b_mem[index*16+beat];
      #1;
      wait_count=0;
      while (!in_ready && wait_count<256) begin
        if (beat!=0 || (current_phase!=11 && current_phase!=13 &&
                        !(bp_mixed && current_phase==12))) begin
          input_error[index]=1;
          phase_error[current_phase]=1;
        end
        @(negedge clk);
        #1;
        wait_count++;
      end
      if (!in_ready) begin
        input_error[index]=1;
        phase_error[current_phase]=1;
        emit_report("input deadlock");
        $fatal(1,"input deadlock tag=%0d beat=%0d",index,beat);
      end
      @(posedge clk);
      @(negedge clk);
    end
  endtask

  initial begin : driver
    int phase_beats, phase, timeout_count;
    if (!$value$plusargs("VECTORS=%s",vectors)) $fatal(1,"VECTORS required");
    if (!$value$plusargs("CASE_COUNT=%d",case_count)) $fatal(1,"CASE_COUNT required");
    void'($value$plusargs("FIRST_LATENCY=%d",first_latency_limit));
    void'($value$plusargs("LAST_LATENCY=%d",last_latency_limit));
    bp_mixed=$test$plusargs("BP_MIXED");
    if (case_count<1 || case_count>MAX_CASES) $fatal(1,"bad CASE_COUNT");
    $readmemh({vectors,"/a.mem"},a_mem);
    $readmemh({vectors,"/b.mem"},b_mem);
    $readmemh({vectors,"/as.mem"},as_mem);
    $readmemh({vectors,"/bs.mem"},bs_mem);
    $readmemh({vectors,"/mode.mem"},mode_mem);
    $readmemh({vectors,"/phase.mem"},phase_mem);
    for (int i=0;i<case_count;i++) begin
      accepted[i]=0;
      input_error[i]=0;
      output_error[i]=0;
      latency_error[i]=0;
      next_row[i]=0;
      last_input[i]=-1;
    end
    for (int p=0;p<=13;p++) phase_error[p]=0;
    repeat (2) @(negedge clk);
    rst_n=1;
    @(negedge clk);
    for (int i=0;i<case_count;i++) begin
      phase=int'(phase_mem[i]);
      if (phase>13) $fatal(1,"invalid phase");
      if (i==0 || phase!=int'(phase_mem[i-1])) begin
        if ((phase==11 || phase==13 || (bp_mixed && phase==12)) && i>0) begin
          if (bp_mixed) begin
            bp_active=0;
            out_ready=1;
          end
          in_valid=0;
          in_start=0;
          timeout_count=0;
          // Up to fifteen accepted blocks may be queued when mixed-format
          // backpressure ends. At the slowest readout rate they need as many
          // as 15*16 cycles, plus pipeline drain, after out_ready returns.
          while (finished<i && timeout_count<512) begin
            @(negedge clk);
            timeout_count++;
          end
          if (finished!=i) begin
            phase_error[current_phase]=1;
            emit_report("pre-backpressure phase did not drain");
            $fatal(1,"pre-backpressure phase did not drain");
          end
        end
        current_phase=phase;
        phase_beats=0;
        for (int j=i;j<case_count;j++) begin
          if (phase_mem[j]!=phase_mem[i]) break;
          phase_beats+=width_of(int'(mode_mem[j]));
        end
        steady_check=(phase!=0 && phase!=11 && phase!=12 && phase!=13);
        bp_active=(phase==11 || phase==13 || (bp_mixed && phase==12));
        if (!bp_active) out_ready=1;
        steady_begin=cycle+1+64;
        steady_end=cycle+phase_beats;
        steady_rows=16/width_of(int'(mode_mem[i]));
      end
      drive_case(i);
    end
    in_valid=0;
    in_start=0;
    steady_check=0;
    bp_active=0;
    out_ready=1;
    timeout_count=0;
    while (finished<case_count && timeout_count<512) begin
      @(negedge clk);
      timeout_count++;
    end
    emit_report("complete");
    $finish;
  end
endmodule
