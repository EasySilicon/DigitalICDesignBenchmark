`timescale 1ns/1ps
// Author-side, external-port concurrency/liveness regression. Never contestant input.
module tb_t11_stress;
    tb_T11 #(.HOST_MODE(1)) tb();
    int which_case;
    byte unsigned tx_expected[$], rx_expected[$];
    int tx_wire_lengths[$], rx_lengths[$];
    bit rx_tags[$];
    logic [15:0] rx_tcis[$];
    int tx_committed=0, tx_seen=0, tx_wire_position=0;
    int rx_completed=0, rx_seen=0, rx_position=0;
    int tx_stalls=0, tx_transfers=0, concurrent_cycles=0, rx_overflows=0;
    int tx_status_good=0, tx_status_bad=0, rx_status_good=0, rx_status_bad=0;
    int mac_bad=0, mac_fcs=0, tx_underflows=0;
    bit tx_was_enabled=0, auto_ready=0, epoch_abort=0, post_reset_quiet=0;
    int wire_concurrent_cycles=0;
    int ready_tick=0;

    // Every expected frame is registered before stimulus, with distinct identity.
    // Eligibility is separate: a tentative good frame may not publish a prefix.
    always @(posedge tb.logic_clk) begin
        if(post_reset_quiet && !tb.logic_rst && tb.rx_axis_tvalid)
            $fatal(1,"pre-reset RX traffic escaped into new epoch");
        if(!tb.logic_rst && !epoch_abort) begin
            if(tb.tx_axis_tvalid && !tb.tx_axis_tready) tx_stalls++;
            if(tb.tx_axis_tvalid && tb.tx_axis_tready) begin
                tx_transfers++;
                if(tb.tx_axis_tlast && !tb.tx_axis_tuser) tx_committed++;
            end
            if(tb.tx_axis_tvalid && tb.gmii_rx_dv) concurrent_cycles++;
            if(tb.rx_fifo_overflow) rx_overflows++;
            if(tb.tx_fifo_good_frame) tx_status_good++;
            if(tb.tx_fifo_bad_frame) tx_status_bad++;
            if(tb.rx_fifo_good_frame) rx_status_good++;
            if(tb.rx_fifo_bad_frame) rx_status_bad++;
            if(tb.rx_error_bad_frame) mac_bad++;
            if(tb.rx_error_bad_fcs) mac_fcs++;
            if(tb.tx_error_underflow) tx_underflows++;
            if(tb.rx_axis_tvalid && tb.rx_axis_tready) begin
                if(rx_seen>=rx_completed) $fatal(1,"RX prefix before physical frame completion");
                if(rx_expected.size()==0 || rx_lengths.size()==0)
                    $fatal(1,"unexpected RX prefix/frame");
                if(tb.rx_axis_tdata!==rx_expected.pop_front())
                    $fatal(1,"RX payload identity/order frame=%0d offset=%0d",rx_seen,rx_position);
                if(tb.rx_axis_tlast !== (rx_position==rx_lengths[0]-1))
                    $fatal(1,"RX frame boundary frame=%0d offset=%0d",rx_seen,rx_position);
                rx_position++;
                if(tb.rx_axis_tlast) begin
                    if(tb.rx_axis_tagged!==rx_tags[0] || tb.rx_axis_tci!==rx_tcis[0])
                        $fatal(1,"RX queued metadata association");
                    void'(rx_lengths.pop_front()); void'(rx_tags.pop_front()); void'(rx_tcis.pop_front());
                    rx_position=0; rx_seen++;
                end
            end
        end
    end
    always @(negedge tb.logic_clk) begin
        // The public monitor sees expectations stable before the next handshake.
        if(rx_tags.size()>0) begin tb.expected_tagged=rx_tags[0]; tb.expected_tci=rx_tcis[0]; end
        if(auto_ready && !tb.logic_rst) begin
            tb.rx_axis_tready=ready_tick%7>1; ready_tick++;
        end
    end
    always @(posedge tb.tx_clk) begin
        if(post_reset_quiet && !tb.tx_rst && tb.gmii_tx_en)
            $fatal(1,"pre-reset TX traffic escaped into new epoch");
        if(tb.tx_rst) begin tx_was_enabled=0; tx_wire_position=0; end
        else if(!epoch_abort) begin
            if(tb.gmii_tx_en && tb.gmii_rx_dv) wire_concurrent_cycles++;
            if(tb.gmii_tx_en) begin
                if(!tx_was_enabled && tx_seen>=tx_committed)
                    $fatal(1,"TX prefix before accepted good terminal");
                if(tx_expected.size()==0 || tx_wire_lengths.size()==0)
                    $fatal(1,"unexpected TX byte/frame");
                if(tb.gmii_txd!==tx_expected.pop_front())
                    $fatal(1,"TX wire identity/body/padding/CRC frame=%0d offset=%0d",tx_seen,tx_wire_position);
                tx_wire_position++;
            end else if(tx_was_enabled) begin
                if(tx_wire_position!=tx_wire_lengths.pop_front()) $fatal(1,"TX wire frame boundary");
                tx_wire_position=0; tx_seen++;
            end
            tx_was_enabled=tb.gmii_tx_en;
        end
    end

    function automatic byte unsigned identity_byte(input int id, offset);
        if(offset<4) return 8'(32'(id)>>(8*offset));
        return 8'((offset*17+id*29+3) ^ (tb.seed&255));
    endfunction
    task automatic body_make(output byte unsigned body[], input int length,id,
                             input bit has_tag=1, input logic [15:0] tci=16'ha007);
        body=new[length];
        foreach(body[i]) body[i]=identity_byte(id,i);
        if(length>13) begin body[12]=has_tag ? 8'h81 : 8'h08; body[13]=0; end
        if(has_tag && length>=18) begin body[14]=tci[15:8]; body[15]=tci[7:0]; body[16]=8'h08; body[17]=0; end
    endtask
    task automatic expect_rx(input byte unsigned body[], input bit has_tag,
                             input logic [15:0] tci);
        foreach(body[i]) rx_expected.push_back(body[i]);
        rx_lengths.push_back(body.size()); rx_tags.push_back(has_tag); rx_tcis.push_back(has_tag ? tci : 0);
    endtask
    task automatic expect_tx(input int length,id);
        int wire_body;
        logic [31:0] c,fcs;
        byte unsigned datum;
        wire_body=length<60 ? 60 : length;
        for(int i=0;i<7;i++) tx_expected.push_back(8'h55);
        tx_expected.push_back(8'hd5); c=32'hffffffff;
        for(int i=0;i<wire_body;i++) begin
            datum=i<length ? identity_byte(id,i) : 8'd0;
            tx_expected.push_back(datum); c=tb.crc_byte(c,datum);
        end
        fcs=~c;
        for(int i=0;i<4;i++) tx_expected.push_back(8'(fcs>>(8*i)));
        tx_wire_lengths.push_back(wire_body+12);
    endtask
    task automatic tx_send(input int length,id, input bit bad=0);
        if(!bad) expect_tx(length,id);
        for(int i=0;i<length;i++) begin
            // No unconditional idle cycle: consecutive bytes can transfer every
            // logic clock. A stalled byte remains unchanged until accepted.
            @(negedge tb.logic_clk);
            tb.tx_axis_tvalid=1; tb.tx_axis_tdata=identity_byte(id,i);
            tb.tx_axis_tlast=i==length-1; tb.tx_axis_tuser=bad && tb.tx_axis_tlast;
            begin : await_accept
                bit accepted;
                accepted=0;
                for(int wait_cycles=0;wait_cycles<100000;wait_cycles++) begin
                    @(posedge tb.logic_clk);
                    if(tb.tx_axis_tready) begin accepted=1; break; end
                end
                if(!accepted) $fatal(1,"TX ready failed to recover with clocks running id=%0d offset=%0d",id,i);
            end
        end
        @(negedge tb.logic_clk); tb.tx_axis_tvalid=0; tb.tx_axis_tlast=0; tb.tx_axis_tuser=0;
    endtask
    task automatic rx_send(input byte unsigned body[], input bit deliver=1,
                           input bit has_tag=1, input logic [15:0] tci=16'ha007,
                           input bit bad_crc=0);
        logic [31:0] c,fcs;
        if(deliver) expect_rx(body,has_tag,tci);
        c=32'hffffffff; foreach(body[i]) c=tb.crc_byte(c,body[i]); fcs=~c;
        if(bad_crc) fcs^=32'h01000000;
        for(int i=0;i<8;i++) begin
            @(negedge tb.rx_clk); tb.gmii_rx_dv=1; tb.gmii_rxd=i==7 ? 8'hd5 : 8'h55;
        end
        foreach(body[i]) begin @(negedge tb.rx_clk); tb.gmii_rxd=body[i]; end
        for(int i=0;i<4;i++) begin @(negedge tb.rx_clk); tb.gmii_rxd=8'(fcs>>(8*i)); end
        @(negedge tb.rx_clk); tb.gmii_rx_dv=0; tb.gmii_rxd=0;
        if(deliver) rx_completed++;
        repeat(12) @(negedge tb.rx_clk);
    endtask
    task automatic rx_drain;
        for(int cycles=0;cycles<30000;cycles++) begin
            @(negedge tb.logic_clk);
            if(!auto_ready) tb.rx_axis_tready=1;
            if(rx_expected.size()==0 && rx_lengths.size()==0) break;
        end
        if(rx_expected.size()!=0 || rx_lengths.size()!=0) $fatal(1,"RX retained frames failed to drain");
        repeat(100) @(negedge tb.logic_clk);
        if(tb.rx_axis_tvalid || rx_position!=0) $fatal(1,"RX ghost/unfinished frame after drain");
    endtask
    task automatic tx_drain;
        for(int cycles=0;cycles<30000;cycles++) begin
            @(negedge tb.tx_clk);
            if(tx_expected.size()==0 && tx_wire_lengths.size()==0 && !tb.gmii_tx_en) break;
        end
        if(tx_expected.size()!=0 || tx_wire_lengths.size()!=0 || tx_seen!=tx_committed)
            $fatal(1,"TX committed frames failed to drain seen=%0d committed=%0d",tx_seen,tx_committed);
        repeat(100) @(negedge tb.tx_clk);
    endtask
    task automatic reset_epoch(input int order=0);
        // Stop scoreboarding before assertion: independent edges may coincide
        // with this driver's logic-clock negedge. Interrupted frames are aborted.
        epoch_abort=1;
        post_reset_quiet=0;
        auto_ready=0;
        @(negedge tb.logic_clk); tb.logic_rst=1; tb.tx_rst=1; tb.rx_rst=1;
        tb.tx_axis_tvalid=0; tb.tx_axis_tlast=0; tb.tx_axis_tuser=0;
        tb.gmii_rx_dv=0; tb.gmii_rx_er=0; tb.rx_axis_tready=0;
        tx_expected.delete(); tx_wire_lengths.delete(); rx_expected.delete(); rx_lengths.delete();
        rx_tags.delete(); rx_tcis.delete();
        repeat(16) @(negedge tb.logic_clk);
        // No candidate input is valid through release/settling. Any published
        // byte here belongs to an aborted epoch, even before clocks stabilize.
        post_reset_quiet=1;
        case(order)
        0: begin @(negedge tb.logic_clk); tb.logic_rst=0; @(negedge tb.tx_clk); tb.tx_rst=0; @(negedge tb.rx_clk); tb.rx_rst=0; end
        1: begin @(negedge tb.logic_clk); tb.logic_rst=0; @(negedge tb.rx_clk); tb.rx_rst=0; @(negedge tb.tx_clk); tb.tx_rst=0; end
        2: begin @(negedge tb.tx_clk); tb.tx_rst=0; @(negedge tb.logic_clk); tb.logic_rst=0; @(negedge tb.rx_clk); tb.rx_rst=0; end
        3: begin @(negedge tb.tx_clk); tb.tx_rst=0; @(negedge tb.rx_clk); tb.rx_rst=0; @(negedge tb.logic_clk); tb.logic_rst=0; end
        4: begin @(negedge tb.rx_clk); tb.rx_rst=0; @(negedge tb.logic_clk); tb.logic_rst=0; @(negedge tb.tx_clk); tb.tx_rst=0; end
        5: begin @(negedge tb.rx_clk); tb.rx_rst=0; @(negedge tb.tx_clk); tb.tx_rst=0; @(negedge tb.logic_clk); tb.logic_rst=0; end
        default: $fatal(1,"unknown coordinated release order");
        endcase
        repeat(24) @(negedge tb.logic_clk);
        tx_committed=0; tx_seen=0; tx_wire_position=0; tx_was_enabled=0;
        rx_completed=0; rx_seen=0; rx_position=0;
        tb.wire_bytes.delete(); tb.received.delete(); tb.tx_frames=0; tb.rx_frames=0; tb.policy_drops=0;
        tb.expected_tagged=0; tb.expected_tci=0;
        post_reset_quiet=0;
        epoch_abort=0;
    endtask
    task automatic tx_pressure;
        int old_good,old_stalls;
        old_good=tx_status_good; old_stalls=tx_stalls;
        for(int frame=0;frame<32;frame++) tx_send(1518,1000+frame);
        tx_drain();
        if(tb.logic_half_ns<=3.126 && tx_stalls==old_stalls) $fatal(1,"160 MHz TX pressure never exercised backpressure");
        if(tx_status_good-old_good!=32 || tx_underflows!=0) $fatal(1,"TX pressure status/underflow");
        // Restart after empty without reset and discard under continued traffic.
        for(int frame=0;frame<24;frame++) tx_send(frame%3==0 ? 1518 : 60+frame,2000+frame,frame%5==2);
        tx_drain();
    endtask
    task automatic full_duplex;
        auto_ready=1;
        tb.config_set(1,1,0,3,48'h000000016007);
        fork
            begin
                for(int frame=0;frame<48;frame++) tx_send(frame%4==0 ? 60 : 1518,3000+frame,frame%7==3);
                tx_drain();
            end
            begin
                byte unsigned body[];
                logic [15:0] tci;
                for(int batch=0;batch<16;batch++) begin
                    for(int frame=0;frame<5;frame++) begin
                        tci=16'(((batch+frame)<<12) | (frame%2==0 ? 7 : 22));
                        body_make(body,frame==4 ? 512 : 60+frame*20,4000+batch*10+frame,frame!=2,tci);
                        rx_send(body,1,frame!=2,tci);
                    end
                    body_make(body,80,4005+batch*10,1,16'hb008); rx_send(body,0);
                    body_make(body,100,4006+batch*10); rx_send(body,0,1,16'ha007,1);
                    rx_drain();
                end
            end
        join
        auto_ready=0;
        if(concurrent_cycles==0 || wire_concurrent_cycles==0)
            $fatal(1,"full duplex input and wire stimulus did not overlap");
        if(rx_overflows!=0 || tb.policy_drops!=16 || mac_fcs!=16 || mac_bad!=16)
            $fatal(1,"full duplex overflow/drop/MAC status");
    endtask
    task automatic overflow_release;
        byte unsigned a[],b[],c[],d[];
        int old_overflows,old_drops;
        tb.config_set(1,0,0,1,48'd7);
        for(int round=0;round<6;round++) begin
            old_overflows=rx_overflows; old_drops=tb.policy_drops;
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            body_make(a,1518,5000+round*4); body_make(b,1518,5001+round*4);
            body_make(c,1518,5002+round*4); body_make(d,80,5003+round*4);
            rx_send(a); rx_send(b);
            fork
                rx_send(c,0);
                begin
                    // Far beyond remaining capacity, regardless of small prefetch
                    // differences, but before C terminates. Freeing space cannot
                    // resurrect an already-overflowed tentative frame.
                    repeat(1220+round*17) @(negedge tb.rx_clk);
                    rx_drain();
                end
            join
            rx_drain(); rx_send(d); rx_drain();
            if(rx_overflows!=old_overflows+1 || tb.policy_drops!=old_drops)
                $fatal(1,"overflow/release recovery event accounting");
        end
    endtask
    task automatic publication_windows;
        int offsets[12]='{0,4,8,16,64,80,84,88,92,96,100,108};
        byte unsigned a[],b[],c[],d[];
        int old_drops,old_overflows,old_fcs;
        tb.config_set(1,0,0,1,48'd7);
        foreach(offsets[window]) for(int kind=0;kind<3;kind++) begin
            old_drops=tb.policy_drops; old_overflows=rx_overflows; old_fcs=mac_fcs;
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            body_make(a,80,6000+window*16+kind*4); body_make(b,81,6001+window*16+kind*4);
            body_make(c,80,6002+window*16+kind*4,1,kind==2 ? 16'hb008 : 16'ha007);
            body_make(d,60,6003+window*16+kind*4);
            rx_send(a); rx_send(b);
            fork
                rx_send(c,kind==0,1,16'ha007,kind==1);
                begin repeat(offsets[window]) @(negedge tb.rx_clk); rx_drain(); end
            join
            rx_drain(); rx_send(d); rx_drain();
            if(tb.policy_drops!=old_drops+int'(kind==2) || rx_overflows!=old_overflows ||
               mac_fcs!=old_fcs+int'(kind==1)) $fatal(1,"publication window event accounting");
        end
    endtask
    task automatic reset_inflight;
        byte unsigned body[];
        for(int order=0;order<6;order++) begin
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            tb.config_set(1,0,0,1,48'd7);
            body_make(body,80,7000+order*3); rx_send(body);
            tx_send(14,7001+order*3);
            for(int cycles=0;cycles<30000;cycles++) begin
                @(negedge tb.tx_clk);
                if(tb.gmii_tx_en && tx_wire_position>=(order%2==0 ? 30 : 69)) break;
            end
            if(!tb.gmii_tx_en || !tb.rx_axis_tvalid) $fatal(1,"reset stimulus failed to establish in-flight traffic");
            $display("RESET_WINDOW order=%0d tx_wire_offset=%0d",order,tx_wire_position);
            reset_epoch(order); tb.config_set(1,0,0,1,48'd7);
            @(negedge tb.logic_clk); tb.rx_axis_tready=1;
            fork
                begin tx_send(61,7002+order*3); tx_drain(); end
                begin body_make(body,80,8000+order); rx_send(body); rx_drain(); end
            join
        end
    endtask
    task automatic near_full_read_write;
        byte unsigned a[],b[],c[],d[],e[];
        int old_overflows;
        int offsets[4]='{0,8,32,64};
        tb.config_set(1,0,0,1,48'd7);
        foreach(offsets[window]) begin
            old_overflows=rx_overflows;
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            body_make(a,1518,9000+window*5); body_make(b,1518,9001+window*5);
            body_make(c,900,9002+window*5); body_make(d,128,9003+window*5);
            body_make(e,60,9004+window*5);
            // Retained prefix uses 3936 of 4096 RAM entries, with no assumed
            // exact external full point or packet capacity. Release while D
            // writes; E then reuses asynchronously returned space.
            rx_send(a); rx_send(b); rx_send(c);
            fork
                begin rx_send(d); rx_send(e); end
                begin repeat(offsets[window]) @(negedge tb.rx_clk); rx_drain(); end
            join
            rx_drain();
            if(rx_overflows!=old_overflows) $fatal(1,"near-full release lost available capacity");
        end
    endtask
    initial begin
        if(!$value$plusargs("STRESS_CASE=%d",which_case)) $fatal(1,"missing STRESS_CASE");
        reset_epoch(); tb.config_set(0,1,0,0,0);
        case(which_case)
        0: tx_pressure();
        1: full_duplex();
        2: overflow_release();
        3: publication_windows();
        4: reset_inflight();
        5: near_full_read_write();
        default: $fatal(1,"unknown stress case");
        endcase
        if(tx_expected.size()!=0 || tx_wire_lengths.size()!=0 || rx_expected.size()!=0 || rx_lengths.size()!=0)
            $fatal(1,"uncompleted expected transactions");
        $display("STRESS_METRICS {\"tx_stall_cycles\":%0d,\"tx_transfers\":%0d,\"tx_frames\":%0d,\"rx_frames\":%0d,\"concurrent_cycles\":%0d,\"wire_concurrent_cycles\":%0d,\"rx_overflows\":%0d}",
                 tx_stalls,tx_transfers,tx_seen,rx_seen,concurrent_cycles,wire_concurrent_cycles,rx_overflows);
        $display("STRESS_PASS T11 CASE=%0d",which_case); $finish;
    end
endmodule
