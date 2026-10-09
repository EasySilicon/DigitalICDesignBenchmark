`timescale 1ns/1ps
// Host-only independent stimulus. Never copied into contestant workspaces.
module tb_t08_acceptance;
    tb_T08 #(.HOST_MODE(1)) tb();
    int which_case;
    int overflow_events=0;
    int mac_bad_events=0, mac_fcs_events=0;
    always @(posedge tb.logic_clk)
        if(!tb.logic_rst && tb.rx_fifo_overflow) overflow_events++;
    // MAC status ports are synchronized to the system domain; VLAN drop is RX.
    always @(posedge tb.logic_clk) begin
        if(!tb.logic_rst && tb.rx_error_bad_frame) mac_bad_events++;
        if(!tb.logic_rst && tb.rx_error_bad_fcs) mac_fcs_events++;
    end
    // Independently stated policy, evaluated from actual external body bytes.
    // Return {deliver, tagged, TCI}; do not inspect a candidate parser signal.
    function automatic logic [17:0] policy_oracle(
        input byte unsigned body[], input bit enabled, untagged, priority_ok,
        input logic [3:0] mask, input logic [47:0] vids);
        logic [15:0] outer_type, inner_type, tci;
        bit matched;
        if(!enabled) return {1'b1,1'b0,16'd0};
        if(body.size()<14) return 18'd0;
        outer_type={body[12],body[13]};
        if(outer_type==16'h88a8) return 18'd0;
        if(outer_type!=16'h8100) return {untagged,1'b0,16'd0};
        if(body.size()<18) return 18'd0;
        tci={body[14],body[15]}; inner_type={body[16],body[17]};
        if(inner_type==16'h8100 || inner_type==16'h88a8 || tci[11:0]==12'hfff)
            return 18'd0;
        if(tci[11:0]==0) matched=priority_ok;
        else begin
            matched=0;
            for(int slot=0;slot<4;slot++)
                matched |= mask[slot] && vids[12*slot +: 12]==tci[11:0];
        end
        return matched ? {1'b1,1'b1,tci} : 18'd0;
    endfunction
    // Short-body error injection must actually assert GMII ER: the reusable
    // public helper's historical offset 22 is outside a tiny body.
    task automatic boundary_send(input byte unsigned body[],
                                 input bit bad_crc, gmii_error);
        logic [31:0] c, fcs;
        if(body.size()<1) $fatal(1,"boundary stimulus requires at least one body byte");
        c=32'hffffffff;
        foreach(body[i]) c=tb.crc_byte(c,body[i]);
        fcs=~c; if(bad_crc) fcs^=32'h01000000;
        for(int i=0;i<8;i++) begin
            @(negedge tb.rx_clk); tb.gmii_rx_dv=1;
            tb.gmii_rxd=i==7 ? 8'hd5 : 8'h55; tb.gmii_rx_er=0;
        end
        foreach(body[i]) begin
            @(negedge tb.rx_clk); tb.gmii_rxd=body[i];
            tb.gmii_rx_er=gmii_error && i==body.size()/2;
        end
        for(int i=0;i<4;i++) begin
            @(negedge tb.rx_clk); tb.gmii_rxd=8'(fcs>>(8*i)); tb.gmii_rx_er=0;
        end
        @(negedge tb.rx_clk); tb.gmii_rx_dv=0; tb.gmii_rxd=0;
        repeat(12) @(negedge tb.rx_clk);
    endtask
    task automatic boundary_rx_check(input byte unsigned body[],
        input bit deliver, has_tag, input logic [15:0] tci,
        input int drops, input bit bad_crc=0, gmii_error=0);
        int old_frames,old_drops,old_bad,old_fcs;
        old_frames=tb.rx_frames; old_drops=tb.policy_drops;
        old_bad=mac_bad_events; old_fcs=mac_fcs_events;
        tb.received.delete();
        // Register expectations before releasing the sink or injecting bytes.
        tb.expected_tagged=has_tag; tb.expected_tci=has_tag ? tci : 0;
        @(negedge tb.logic_clk); tb.rx_axis_tready=1;
        boundary_send(body,bad_crc,gmii_error);
        for(int k=0;k<body.size()*4+400;k++) begin
            @(negedge tb.logic_clk); tb.rx_axis_tready=k%7>1;
        end
        @(negedge tb.logic_clk); tb.rx_axis_tready=0;
        if(tb.rx_frames-old_frames!=int'(deliver) ||
           tb.received.size()!=(deliver ? body.size() : 0))
            $fatal(1,"boundary delivery length=%0d expected=%0b bytes=%0d frames=%0d",
                   body.size(),deliver,tb.received.size(),tb.rx_frames-old_frames);
        if(tb.policy_drops-old_drops!=drops) $fatal(1,"boundary VLAN-drop count");
        if(!bad_crc && !gmii_error && (mac_bad_events!=old_bad || mac_fcs_events!=old_fcs))
            $fatal(1,"valid-FCS boundary stimulus was unexpectedly MAC-bad");
        if(bad_crc && mac_fcs_events==old_fcs) $fatal(1,"CRC error stimulus did not trigger MAC FCS event");
        if(gmii_error && mac_bad_events==old_bad) $fatal(1,"GMII error stimulus did not trigger MAC bad event");
        if(deliver) foreach(body[i])
            if(tb.received[i]!=body[i]) $fatal(1,"boundary payload mismatch offset=%0d",i);
        if(tb.rx_axis_tvalid) $fatal(1,"unaccounted pending boundary output");
    endtask
    task automatic short_boundary_check(input int mode);
        byte unsigned body[],prime[];
        for(int length=1;length<=18;length++) begin
            // Each length gets a genuine fresh/reset or explicit predecessor.
            tb.reset_all();
            if(mode==2 || mode==4) begin
                tb.config_set(1,0,0,1,48'd7);
                tb.make_body(prime,80,16'h8100,16'ha007,16'h0800);
                boundary_rx_check(prime,1,1,16'ha007,0);
            end else if(mode==3) begin
                tb.config_set(0,0,0,0,0);
                tb.make_body(prime,80,16'h0800);
                boundary_rx_check(prime,1,0,0,0);
            end
            tb.config_set(mode==0 || mode==3 || mode==4,1,1,1,48'd7);
            tb.make_body(body,length,16'h0800);
            $display("BOUNDARY mode=%0d length=%0d",mode,length);
            boundary_rx_check(body,mode==1 || mode==2 || length>=14,0,0,
                              (mode==0 || mode==3 || mode==4) && length<14 ? 1 : 0);
        end
    endtask
    task automatic short_integrity_check;
        int lengths[8]='{1,2,12,13,14,17,18,80};
        byte unsigned body[],successor[];
        foreach(lengths[n]) for(int enabled=0;enabled<2;enabled++)
            for(int error_kind=0;error_kind<2;error_kind++) begin
                tb.reset_all(); tb.config_set(1,0,0,1,48'd7);
                tb.make_body(successor,80,16'h8100,16'ha007,16'h0800);
                boundary_rx_check(successor,1,1,16'ha007,0);
                tb.config_set(1'(enabled),1,1,1,48'd7);
                tb.make_body(body,lengths[n],16'h8100,16'ha007,16'h0800);
                // MAC bad wins even when policy would also reject the header.
                boundary_rx_check(body,0,0,0,0,error_kind==0,error_kind==1);
                boundary_rx_check(successor,1,1'(enabled),16'ha007,0);
            end
    endtask
    task automatic policy_cross_check;
        int lengths[16]='{1,2,3,12,13,14,15,16,17,18,19,31,60,80,127,256};
        logic [15:0] outers[5]='{16'h8100,16'h88a8,16'h0800,16'h002e,16'h86dd};
        logic [15:0] inners[4]='{16'h8100,16'h88a8,16'h0800,16'h86dd};
        int vids_pool[7]='{0,7,22,333,4094,4095,8};
        byte unsigned body[];
        int unsigned rng;
        bit enabled,untagged,priority_ok;
        logic [3:0] mask;
        logic [47:0] slots;
        logic [15:0] outer_type,inner_type,tci;
        logic [17:0] expectation;
        rng=32'(tb.seed);
        for(int trial=0;trial<192;trial++) begin
            rng=rng*32'd1664525+32'd1013904223;
            enabled=rng[17]; untagged=rng[18]; priority_ok=rng[19]; mask=rng[23:20];
            slots=48'hffe14d016007;
            // Include duplicate matches, invalid equality, and VID=0/reserved
            // in the list: priority/reserved precedence must still dominate.
            if(trial%4==0) slots={4{12'd7}};
            if(trial%4==1) slots={4{12'd0}};
            if(trial%4==2) slots={4{12'hfff}};
            outer_type=outers[(rng>>8)%5]; inner_type=inners[(rng>>13)%4];
            tci=16'(((rng>>24)<<12) | vids_pool[(rng>>4)%7]);
            tb.make_body(body,lengths[trial%16],outer_type,tci,inner_type);
            foreach(body[i]) if(i<12 || i>=18) body[i]^=8'(rng>>24);
            tb.config_set(enabled,untagged,priority_ok,mask,slots);
            expectation=policy_oracle(body,enabled,untagged,priority_ok,mask,slots);
            $display("POLICY_CROSS trial=%0d length=%0d enable=%0b mask=%h",trial,body.size(),enabled,mask);
            boundary_rx_check(body,expectation[17],expectation[16],expectation[15:0],
                              enabled && !expectation[17] ? 1 : 0);
        end
    endtask
    task automatic mixed_metadata_queue_check;
        byte unsigned first[],second[],third[],denied[];
        int old_frames,old_drops,cursor,hold_cycles,held_frame,position;
        logic [15:0] first_tci,second_tci;
        tb.config_set(1,1,0,3,48'h000000016007);
        // >4096 retained bytes, distinct adjacent payloads and metadata.
        for(int round=0;round<16;round++) begin
            first_tci=16'((round<<12)|7); second_tci=16'(((15-round)<<12)|22);
            make_distinct_body(first,60+round,11+round,1,first_tci);
            make_distinct_body(second,80+round,79+round,1,second_tci);
            make_distinct_body(third,100+round,151+round);
            make_distinct_body(denied,80,203+round,1,16'hb008);
            tb.received.delete(); old_frames=tb.rx_frames; old_drops=tb.policy_drops;
            tb.expected_tagged=1; tb.expected_tci=first_tci;
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            tb.send_rx(first); tb.send_rx(denied); tb.send_rx(second); tb.send_rx(third);
            hold_cycles=0; held_frame=-1;
            for(int k=0;k<2400;k++) begin
                @(negedge tb.logic_clk);
                position=tb.rx_frames-old_frames;
                tb.expected_tagged=position<2;
                tb.expected_tci=position==0 ? first_tci : position==1 ? second_tci : 16'd0;
                if(tb.rx_axis_tvalid && tb.rx_axis_tlast && held_frame!=position) begin
                    held_frame=position; hold_cycles=5;
                end
                tb.rx_axis_tready=k%7>1 && hold_cycles==0;
                if(hold_cycles>0) hold_cycles--;
            end
            @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            if(tb.rx_frames!=old_frames+3 || tb.policy_drops!=old_drops+1)
                $fatal(1,"mixed metadata queue lost/duplicated frame or drop");
            if(tb.received.size()!=first.size()+second.size()+third.size())
                $fatal(1,"mixed metadata queue length");
            cursor=0;
            foreach(first[i]) if(tb.received[cursor++]!=first[i]) $fatal(1,"mixed first body");
            foreach(second[i]) if(tb.received[cursor++]!=second[i]) $fatal(1,"mixed second body");
            foreach(third[i]) if(tb.received[cursor++]!=third[i]) $fatal(1,"mixed third body");
            if(tb.rx_axis_tvalid) $fatal(1,"mixed queue left unaccounted output");
        end
    endtask
    task automatic reset_single_beat_check;
        byte unsigned tagged_body[],tiny[];
        for(int round=0;round<4;round++) begin
            tb.config_set(1,0,0,1,48'd7);
            tb.make_body(tagged_body,80,16'h8100,16'ha007,16'h0800);
            tb.send_rx(tagged_body); repeat(50) @(negedge tb.logic_clk);
            if(!tb.rx_axis_tvalid) $fatal(1,"reset control must have queued metadata");
            tb.reset_all(); tb.make_body(tiny,1,16'h0800);
            tb.config_set(1,1,1,1,48'd7); boundary_rx_check(tiny,0,0,0,1);
            tb.config_set(0,0,0,0,0); boundary_rx_check(tiny,1,0,0,0);
        end
    endtask
    // Long leading frame guarantees later complete bodies queue before its tail.
    // Every frame's expected CRC is initialized independently of previous bytes.
    task automatic queued_tx_check;
        int lengths[5] = '{1518, 42, 59, 60, 61};
        int target, cursor, body_length;
        logic [31:0] c, fcs;
        tb.wire_bytes.delete();
        target = tb.tx_frames + 5;
        foreach (lengths[n]) tb.send_tx(lengths[n], 0, 0);
        for (int t=0; t<15000 && tb.tx_frames<target; t++) @(negedge tb.tx_clk);
        if (tb.tx_frames != target) $fatal(1, "queued TX frame count");
        cursor = 0;
        foreach (lengths[n]) begin
            body_length = lengths[n] < 60 ? 60 : lengths[n];
            if (cursor + body_length + 12 > tb.wire_bytes.size())
                $fatal(1, "queued TX truncated burst frame=%0d", n);
            for (int k=0;k<7;k++)
                if (tb.wire_bytes[cursor+k] != 8'h55) $fatal(1, "queued preamble");
            if (tb.wire_bytes[cursor+7] != 8'hd5) $fatal(1, "queued SFD");
            c = 32'hffffffff;
            for (int k=0;k<body_length;k++) begin
                if (tb.wire_bytes[cursor+8+k] != (k<lengths[n] ? tb.pattern(k) : 8'h00))
                    $fatal(1, "queued body/pad frame=%0d offset=%0d", n, k);
                c = tb.crc_byte(c, tb.wire_bytes[cursor+8+k]);
            end
            fcs = ~c;
            for (int k=0;k<4;k++)
                if (tb.wire_bytes[cursor+8+body_length+k] != 8'(fcs>>(8*k)))
                    $fatal(1, "queued CRC epoch/tail frame=%0d fcs_byte=%0d", n, k);
            cursor += body_length + 12;
        end
        if (cursor != tb.wire_bytes.size()) $fatal(1, "queued TX extra bytes");
    endtask
    // Validate a burst containing discarded frames without using FIFO hierarchy.
    // A single large good frame keeps the wire busy while later bodies commit.
    task automatic rollback_tx_check(input int rounds);
        int lengths[3] = '{1518, 60, 61};
        int target, cursor;
        logic [31:0] c, fcs;
        for (int round=0;round<rounds;round++) begin
            tb.wire_bytes.delete(); target=tb.tx_frames+3;
            tb.send_tx(lengths[0],0,0);
            tb.send_tx(lengths[1],0,0);
            tb.send_tx(80+round,1,0);
            tb.send_tx(lengths[2],0,0);
            for(int t=0;t<15000 && tb.tx_frames<target;t++) @(negedge tb.tx_clk);
            // Also detect delayed unwanted bad-frame prefixes/duplicate frames.
            repeat(300) @(negedge tb.tx_clk);
            if(tb.tx_frames!=target) $fatal(1,"TX rollback lost/duplicated frame round=%0d",round);
            cursor=0;
            foreach(lengths[n]) begin
                if(cursor+lengths[n]+12>tb.wire_bytes.size()) $fatal(1,"TX rollback truncated frame");
                for(int k=0;k<7;k++)
                    if(tb.wire_bytes[cursor+k]!=8'h55) $fatal(1,"TX rollback preamble");
                if(tb.wire_bytes[cursor+7]!=8'hd5) $fatal(1,"TX rollback SFD");
                c=32'hffffffff;
                for(int k=0;k<lengths[n];k++) begin
                    if(tb.wire_bytes[cursor+8+k]!=tb.pattern(k))
                        $fatal(1,"TX rollback payload round=%0d frame=%0d offset=%0d",round,n,k);
                    c=tb.crc_byte(c,tb.wire_bytes[cursor+8+k]);
                end
                fcs=~c;
                for(int k=0;k<4;k++)
                    if(tb.wire_bytes[cursor+8+lengths[n]+k]!=8'(fcs>>(8*k)))
                        $fatal(1,"TX rollback CRC round=%0d frame=%0d",round,n);
                cursor+=lengths[n]+12;
            end
            if(cursor!=tb.wire_bytes.size()) $fatal(1,"TX rollback extra bytes");
        end
    endtask
    task automatic make_distinct_body(output byte unsigned body[], input int length,
                                      input int salt, input bit has_tag=0,
                                      input logic [15:0] tci=0);
        tb.make_body(body,length,has_tag ? 16'h8100 : 16'h0800,tci,16'h0800);
        for(int i=0;i<length;i++)
            if(i<12 || i>=18) body[i]^=8'(salt+3*i);
    endtask
    task automatic check_received_pair(input byte unsigned first[], second[], input int old_frames);
        if(tb.rx_frames!=old_frames+2 || tb.received.size()!=first.size()+second.size())
            $fatal(1,"RX rollback lost frame or leaked prefix frames=%0d bytes=%0d expected_bytes=%0d",
                   tb.rx_frames-old_frames,tb.received.size(),first.size()+second.size());
        for(int i=0;i<tb.received.size();i++)
            if(tb.received[i]!=(i<first.size() ? first[i] : second[i-first.size()]))
                $fatal(1,"RX rollback body mismatch offset=%0d",i);
    endtask
    task automatic drain_pair(input byte unsigned first[], second[], input int old_frames);
        for(int k=0;k<2*(first.size()+second.size())+600;k++) begin
            @(negedge tb.logic_clk); tb.rx_axis_tready=k%7!=0 && k%7!=1;
        end
        @(negedge tb.logic_clk); tb.rx_axis_tready=0;
        check_received_pair(first,second,old_frames);
    endtask
    task automatic overflow_rx_check;
        byte unsigned first[], second[], overflow_body[];
        make_distinct_body(first,1518,11);
        make_distinct_body(second,1518,79);
        make_distinct_body(overflow_body,1518,203);
        tb.send_rx(first); tb.send_rx(second); tb.send_rx(overflow_body);
        // Third body exceeds capacity; the first two must stay intact.
        // No policy drop is justified by a plain FIFO overflow.
        drain_pair(first,second,0);
        if(overflow_events!=1) $fatal(1,"expected one whole-frame capacity overflow");
        if(tb.policy_drops!=0) $fatal(1,"FIFO overflow counted as VLAN denial");
        tb.rx_check(84,16'h0800,0,0,1,0);
    endtask
    task automatic speculative_rx_check;
        byte unsigned first[], second[], bad_body[];
        make_distinct_body(first,80,11);
        make_distinct_body(second,80,79);
        make_distinct_body(bad_body,1518,203);
        tb.send_rx(first); tb.send_rx(second);
        fork
            tb.send_rx(bad_body,1);
            begin
                // Release the sink while the third body's FCS is still unknown.
                // No byte belonging to that transaction may become observable.
                repeat(80+tb.seed%41) @(negedge tb.rx_clk);
                for(int k=0;k<7000;k++) begin
                    @(negedge tb.logic_clk); tb.rx_axis_tready=k%7!=0;
                    if(tb.received.size()>160) $fatal(1,"uncommitted RX prefix became visible");
                end
                @(negedge tb.logic_clk); tb.rx_axis_tready=0;
            end
        join
        check_received_pair(first,second,0);
        tb.rx_check(84,16'h0800,0,0,1,0);
    endtask
    task automatic policy_rollback_wrap_check;
        byte unsigned first[], second[], denied[];
        int old_frames, old_drops;
        tb.config_set(1,0,0,1,48'd7);
        tb.expected_tagged=1; tb.expected_tci=16'ha007;
        // More than two ring capacities of retained data, with discarded
        // transactions reusing slots and stalled terminal metadata each round.
        for(int round=0;round<3;round++) begin
            old_frames=tb.rx_frames; old_drops=tb.policy_drops;
            tb.received.delete();
            make_distinct_body(first,1518,11+13*round,1,16'ha007);
            make_distinct_body(second,1518,79+19*round,1,16'ha007);
            make_distinct_body(denied,80+round,203,1,16'hb008);
            tb.send_rx(first); tb.send_rx(second); tb.send_rx(denied);
            drain_pair(first,second,old_frames);
            if(tb.policy_drops!=old_drops+1) $fatal(1,"policy rollback event count");
        end
    endtask
    // Single-field edits cannot be masked by a simultaneous enable change.
    // With the supplied raw GMII decoder, offsets 8/10/12 are after decoded
    // byte zero has been sampled and before decoded type offsets 13/17.
    // New feature pipelines must retain this inherited raw snapshot anchor.
    // No candidate hierarchy is referenced by these checks.
    task automatic early_snapshot_check(input int field_id);
        int slot_count;
        bit old_allow, has_tag;
        logic [3:0] mask;
        logic [47:0] vids;
        logic [15:0] outer_type, tci;
        slot_count = field_id <= 2 ? 4 : 1;
        for (int slot=0; slot<slot_count; slot++) begin
            for (int direction=0; direction<2; direction++) begin
                old_allow = direction == 1;
                for (int update_at=8; update_at<=12; update_at+=2) begin
                    mask = 0; vids = 0;
                    outer_type = field_id == 3 ? 16'h0800 : 16'h8100;
                    tci = field_id == 4 ? 16'he000 : 16'ha007;
                    has_tag = field_id != 3;
                    case (field_id)
                    1: begin
                        mask = 4'(1 << slot);
                        vids = 48'(old_allow ? 12'h007 : 12'hff8) << (12*slot);
                    end
                    2: begin
                        mask = old_allow ? 4'(1 << slot) : ~4'(1 << slot);
                        vids = 48'd7 << (12*slot);
                    end
                    3,4: begin end
                    default: $fatal(1,"unknown early-snapshot field");
                    endcase
                    tb.config_set(1, field_id==3 && old_allow,
                                  field_id==4 && old_allow, mask, vids);
                    $display("SNAPSHOT field=%0d slot=%0d old_allow=%0b wire_update_offset=%0d",
                             field_id, slot, old_allow, update_at);
                    // Current frame obeys OLD snapshot, including denial.
                    tb.rx_check(80,outer_type,tci,16'h0800,old_allow,
                                has_tag && old_allow,int'(!old_allow),
                                0,0,1,update_at,field_id);
                    // Identical next body must obey NEW configuration.
                    tb.rx_check(80,outer_type,tci,16'h0800,!old_allow,
                                has_tag && !old_allow,int'(old_allow));
                end
            end
        end
    endtask
    initial begin
        if(!$value$plusargs("CASE=%d",which_case)) $fatal(1,"missing CASE");
        tb.reset_all(); tb.config_set(0,1,0,0,0);
        case(which_case)
        0: begin tb.tx_check(60); tb.tx_check(61); tb.tx_check(1518); end
        1: begin
            tb.send_tx(80,1); repeat(250) @(negedge tb.logic_clk);
            if(tb.tx_frames!=0) $fatal(1,"bad TX frame emitted");
            tb.tx_check(80);
        end
        2: begin
            tb.rx_check(60,16'h0800,0,0,1,0);
            tb.rx_check(1518,16'h0800,0,0,1,0);
        end
        3: begin
            tb.rx_check(80,16'h0800,0,0,0,0,0,1);
            tb.rx_check(80,16'h0800,0,0,0,0,0,0,1);
            tb.rx_check(80,16'h0800,0,0,1,0);
        end
        4: tb.tx_check(14);
        5: begin tb.tx_check(42); tb.tx_check(42); end
        6: tb.tx_check(59);
        7: begin for(int n=15;n<59;n+=3) tb.tx_check(n); end
        8: begin
            tb.config_set(1,1,0,0,0); tb.rx_check(80,16'h0800,0,0,1,0);
            tb.config_set(1,0,0,0,0); tb.rx_check(80,16'h0800,0,0,0,0,1);
        end
        9: begin
            for(int slot=0;slot<4;slot++) begin
                tb.config_set(1,0,0,4'(1<<slot),48'(23)<<12*slot);
                tb.rx_check(80,16'h8100,23,16'h0800,1,1);
                tb.rx_check(80,16'h8100,24,16'h0800,0,0,1);
            end
            tb.config_set(1,0,0,0,48'd23);
            tb.rx_check(80,16'h8100,23,16'h0800,0,0,1);
        end
        10: begin
            tb.config_set(1,0,0,15,0); tb.rx_check(80,16'h8100,0,16'h0800,0,0,1);
            tb.config_set(1,0,1,0,0); tb.rx_check(80,16'h8100,16'he000,16'h0800,1,1);
            tb.config_set(1,0,1,15,48'hffffffffffff);
            tb.rx_check(80,16'h8100,16'hffff,16'h0800,0,0,1);
        end
        11: begin
            tb.config_set(1,1,1,15,48'd7);
            tb.rx_check(80,16'h88a8,0,0,0,0,1);
            tb.rx_check(80,16'h8100,7,16'h8100,0,0,1);
            tb.rx_check(80,16'h8100,7,16'h88a8,0,0,1);
            tb.rx_check(80,16'h8100,8,16'h0800,0,0,0,1);
        end
        12: begin
            tb.config_set(1,1,0,1,48'd7);
            for(int bits=0;bits<16;bits++)
                tb.rx_check(64+bits,16'h8100,16'((bits<<12)|7),16'h86dd,1,1);
            tb.rx_check(80,16'h0800,0,0,1,0);
        end
        13: begin
            tb.config_set(1,1,1,1,48'd7);
            tb.rx_check(13,16'h0800,0,0,0,0,1);
            for(int len=14;len<18;len++)
                tb.rx_check(len,16'h8100,7,16'h0800,0,0,1);
            tb.rx_check(18,16'h8100,7,16'h0800,1,1);
            tb.rx_check(18,16'h8100,7,16'h8100,0,0,1);
        end
        14: begin
            tb.config_set(1,0,0,1,48'd7);
            tb.rx_check(100,16'h8100,7,16'h0800,1,1,0,0,0,1);
            // Previous config flipped to bypass, still zero metadata next frame.
            tb.rx_check(100,16'h8100,8,16'h0800,1,0);
        end
        15: begin
            tb.config_set(0,0,0,1,48'd7);
            tb.rx_check(100,16'h8100,7,16'h0800,1,0,0,0,0,1);
            // All fields flipped; original bypass cannot apply to this new packet.
            tb.rx_check(100,16'h8100,7,16'h0800,0,0,1);
        end
        16: begin
            byte unsigned body[];
            tb.make_body(body,80,16'h8100,7,16'h0800);
            tb.config_set(1,0,0,1,48'd7);
            tb.send_rx(body);
            repeat(50) @(negedge tb.logic_clk);
            if(!tb.rx_axis_tvalid) $fatal(1,"expected queued pre-reset frame");
            tb.reset_all(); tb.config_set(1,1,0,0,0);
            tb.rx_check(80,16'h0800,0,0,1,0);
            tb.rx_check(80,16'h8100,7,16'h0800,0,0,1);
        end
        17: begin
            tb.send_tx(100); // Reset while committed TX may be on the wire.
            tb.reset_all(); tb.tx_check(60);
            tb.config_set(0,0,0,0,0); tb.rx_check(80,16'h0800,0,0,1,0);
        end
        18: queued_tx_check();
        19: early_snapshot_check(1); // VID list values only.
        20: early_snapshot_check(2); // Valid mask only.
        21: early_snapshot_check(3); // Untagged flag only.
        22: early_snapshot_check(4); // Priority flag only.
        23: rollback_tx_check(1);
        24: overflow_rx_check();
        25: speculative_rx_check();
        26: policy_rollback_wrap_check();
        27: rollback_tx_check(4);
        28: short_boundary_check(0);
        29: short_boundary_check(1);
        30: short_boundary_check(2);
        31: short_boundary_check(3);
        32: short_integrity_check();
        33: policy_cross_check();
        34: mixed_metadata_queue_check();
        35: reset_single_beat_check();
        36: short_boundary_check(4);
        default: $fatal(1,"unknown case");
        endcase
        $display("ACCEPT_PASS T08 CASE=%0d",which_case); $finish;
    end
endmodule
