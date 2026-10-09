`timescale 1ns/1ps
// Evaluator-owned, fixed 1 GHz full-duplex workload. External payload, CRC,
// metadata and rejection checks must pass before its activity can be scored.
module tb_t08_power;
    logic logic_clk=0, tx_clk=0, rx_clk=0;
    real logic_half_ns=0.5, rx_phase_ns=0.17;
    initial begin
        forever #(logic_half_ns) logic_clk=~logic_clk;
    end
    initial begin
        #0.31;
        forever #0.5 tx_clk=~tx_clk;
    end
    initial begin
        #(rx_phase_ns); forever #0.5 rx_clk=~rx_clk;
    end
    logic logic_rst=1, tx_rst=1, rx_rst=1;
    logic [7:0] tx_axis_tdata=0, rx_axis_tdata, gmii_rxd=0, gmii_txd;
    logic tx_axis_tvalid=0, tx_axis_tlast=0, tx_axis_tuser=0, tx_axis_tready;
    logic rx_axis_tvalid, rx_axis_tlast, rx_axis_tuser, rx_axis_tready=0;
    logic rx_axis_tagged; logic [15:0] rx_axis_tci;
    logic gmii_rx_dv=0, gmii_rx_er=0, gmii_tx_en, gmii_tx_er;
    logic cfg_vlan_enable=0, cfg_accept_untagged=1, cfg_accept_priority=0;
    logic [3:0] cfg_vlan_valid=0; logic [47:0] cfg_vlan_vids=0;
    logic rx_vlan_drop;
    logic tx_error_underflow, rx_error_bad_frame, rx_error_bad_fcs;
    logic tx_fifo_overflow, tx_fifo_bad_frame, tx_fifo_good_frame;
    logic rx_fifo_overflow, rx_fifo_bad_frame, rx_fifo_good_frame;
    mac_1g_repair dut (.*);

    bit power_active=0; // Start activity capture only after coordinated reset.
    longint unsigned power_ops=0; // Accepted TX and delivered RX body octets.
    always @(posedge logic_clk) begin
        if(power_active && !logic_rst)
            power_ops=power_ops+int'(tx_axis_tvalid && tx_axis_tready)+
                                  int'(rx_axis_tvalid && rx_axis_tready);
    end
    initial begin
        string vcd_path;
        if($value$plusargs("POWER_VCD=%s",vcd_path)) begin
            wait(!logic_rst && !tx_rst && !rx_rst);
            #2;
            power_active=1;
            $dumpfile(vcd_path);
            $dumpvars(0,dut);
        end
    end
    final if(power_active) $display("POWER_OPS=%0d",power_ops);

    byte unsigned wire_bytes[$], received[$]; // Captured external octets.
    int tx_frames=0, rx_frames=0, policy_drops=0;
    bit previous_tx_en=0; int idle_tx_cycles=1000;
    bit expected_tagged=0; logic [15:0] expected_tci=0;
    bit previous_stall=0; logic [27:0] stalled_payload;
    int seed=20261007;
    initial void'($value$plusargs("SEED=%d",seed));

    always @(posedge tx_clk) begin
        if (tx_rst) begin previous_tx_en=0; idle_tx_cycles=1000; end
        else begin
            if (gmii_tx_en) begin
                if (!previous_tx_en && idle_tx_cycles<12) $fatal(1,"IFG too short");
                if (gmii_tx_er) $fatal(1,"unexpected GMII TX error");
                wire_bytes.push_back(gmii_txd);
                idle_tx_cycles=0;
            end else begin
                idle_tx_cycles++;
                if(previous_tx_en) tx_frames++;
            end
            previous_tx_en=gmii_tx_en;
        end
    end
    always @(posedge rx_clk)
        if (!rx_rst && rx_vlan_drop) policy_drops++;
    always @(posedge logic_clk) begin
        if(logic_rst) previous_stall=0;
        else begin
            if(previous_stall && {rx_axis_tvalid,rx_axis_tdata,rx_axis_tlast,
                rx_axis_tuser,rx_axis_tagged,rx_axis_tci} !== stalled_payload)
                $fatal(1,"RX output changed during backpressure");
            previous_stall=rx_axis_tvalid && !rx_axis_tready;
            stalled_payload={rx_axis_tvalid,rx_axis_tdata,rx_axis_tlast,
                             rx_axis_tuser,rx_axis_tagged,rx_axis_tci};
            if(rx_axis_tvalid && rx_axis_tready) begin
                if(rx_axis_tuser) $fatal(1,"bad frame escaped frame FIFO");
                if(!rx_axis_tlast && (rx_axis_tagged || rx_axis_tci))
                    $fatal(1,"metadata must be terminal only");
                received.push_back(rx_axis_tdata);
                if(rx_axis_tlast) begin
                    if(rx_axis_tagged !== expected_tagged || rx_axis_tci !== expected_tci)
                        $fatal(1,"metadata got %b/%h expected %b/%h",
                               rx_axis_tagged,rx_axis_tci,expected_tagged,expected_tci);
                    rx_frames++;
                end
            end
        end
    end

    function automatic logic [31:0] crc_byte(input logic [31:0] old,
                                             input byte unsigned datum);
        logic [31:0] c;
        c=old;
        for(int b=0;b<8;b++) begin
            if(c[0] ^ datum[b]) c=(c>>1)^32'hEDB88320;
            else c=c>>1;
        end
        return c;
    endfunction
    function automatic byte unsigned pattern(input int i);
        return 8'((17*i+3) ^ (seed & 255));
    endfunction
    task automatic reset_all;
        @(negedge logic_clk); logic_rst=1; tx_rst=1; rx_rst=1;
        tx_axis_tvalid=0; tx_axis_tlast=0; gmii_rx_dv=0; gmii_rx_er=0;
        rx_axis_tready=0;
        repeat(16) @(negedge logic_clk);
        logic_rst=0;
        @(negedge tx_clk); tx_rst=0;
        @(negedge rx_clk); rx_rst=0;
        repeat(24) @(negedge logic_clk);
        wire_bytes.delete(); received.delete(); tx_frames=0; rx_frames=0; policy_drops=0;
        expected_tagged=0; expected_tci=0;
    endtask
    task automatic config_set(input bit enabled, untagged, priority_ok,
                              input logic [3:0] mask, input logic [47:0] vids);
        @(negedge rx_clk);
        cfg_vlan_enable=enabled; cfg_accept_untagged=untagged;
        cfg_accept_priority=priority_ok; cfg_vlan_valid=mask; cfg_vlan_vids=vids;
    endtask
    task automatic send_tx(input int length, input bit bad=0, input bit gaps=1);
        for(int i=0;i<length;i++) begin
            @(negedge logic_clk);
            tx_axis_tvalid=1; tx_axis_tdata=pattern(i);
            tx_axis_tlast=(i==length-1); tx_axis_tuser=bad && tx_axis_tlast;
            do @(posedge logic_clk); while(!tx_axis_tready);
            @(negedge logic_clk); tx_axis_tvalid=0; tx_axis_tlast=0; tx_axis_tuser=0;
            if(gaps && i%7==0) repeat(3) @(negedge logic_clk);
        end
    endtask
    task automatic tx_check(input int length, input bit gaps=1);
        logic [31:0] c, fcs; int wire_body, target;
        wire_bytes.delete(); target=tx_frames+1;
        send_tx(length,0,gaps);
        for(int t=0;t<10000 && tx_frames<target;t++) @(negedge tx_clk);
        if(tx_frames!=target) $fatal(1,"TX timeout");
        wire_body=length<60 ? 60 : length;
        if(wire_bytes.size()!=8+wire_body+4) $fatal(1,"wire length");
        for(int i=0;i<7;i++) if(wire_bytes[i]!=8'h55) $fatal(1,"preamble");
        if(wire_bytes[7]!=8'hd5) $fatal(1,"SFD");
        c=32'hffffffff;
        for(int i=0;i<wire_body;i++) begin
            if(wire_bytes[8+i] != (i<length ? pattern(i) : 8'h00))
                $fatal(1,"TX body/padding mismatch offset %0d",i);
            c=crc_byte(c,wire_bytes[8+i]);
        end
        fcs=~c;
        for(int i=0;i<4;i++)
            if(wire_bytes[8+wire_body+i] != 8'(fcs>>(8*i)))
                $fatal(1,"TX FCS mismatch length=%0d byte=%0d got=%h expected=%h",
                       length,i,wire_bytes[8+wire_body+i],8'(fcs>>(8*i)));
    endtask
    task automatic make_body(output byte unsigned body[], input int length,
                             input logic [15:0] outer_type,
                             input logic [15:0] tci=0, inner_type=16'h0800);
        body=new[length];
        for(int i=0;i<length;i++) body[i]=pattern(i);
        if(length>12) body[12]=outer_type[15:8];
        if(length>13) body[13]=outer_type[7:0];
        if(outer_type==16'h8100) begin
            if(length>14) body[14]=tci[15:8];
            if(length>15) body[15]=tci[7:0];
            if(length>16) body[16]=inner_type[15:8];
            if(length>17) body[17]=inner_type[7:0];
        end
    endtask
    task automatic send_rx(input byte unsigned body[], input bit bad_crc=0,
                           input bit gmii_error=0, input bit mid_update=0,
                           input int update_offset=30, input int update_field=0);
        logic [31:0] c,fcs;
        c=32'hffffffff;
        for(int i=0;i<body.size();i++) c=crc_byte(c,body[i]);
        fcs=~c; if(bad_crc) fcs^=32'h01000000;
        for(int i=0;i<8;i++) begin
            @(negedge rx_clk); gmii_rx_dv=1; gmii_rxd=i==7 ? 8'hd5 : 8'h55;
        end
        for(int i=0;i<body.size();i++) begin
            @(negedge rx_clk); gmii_rxd=body[i]; gmii_rx_er=gmii_error && i==22;
            if(mid_update && i==update_offset) begin
                case(update_field)
                0: begin // Legacy all-fields update, normally after the header.
                    cfg_vlan_enable=~cfg_vlan_enable;
                    cfg_accept_untagged=~cfg_accept_untagged;
                    cfg_accept_priority=~cfg_accept_priority;
                    cfg_vlan_valid=~cfg_vlan_valid; cfg_vlan_vids=~cfg_vlan_vids;
                end
                1: cfg_vlan_vids=~cfg_vlan_vids;
                2: cfg_vlan_valid=~cfg_vlan_valid;
                3: cfg_accept_untagged=~cfg_accept_untagged;
                4: cfg_accept_priority=~cfg_accept_priority;
                default: $fatal(1,"unknown configuration update field");
                endcase
            end
        end
        for(int i=0;i<4;i++) begin
            @(negedge rx_clk); gmii_rxd=8'(fcs>>(8*i)); gmii_rx_er=0;
        end
        @(negedge rx_clk); gmii_rx_dv=0; gmii_rxd=0;
        repeat(12) @(negedge rx_clk);
    endtask
    task automatic rx_check(input int length, input logic [15:0] outer_type,
                            input logic [15:0] tci, inner_type,
                            input bit deliver, has_tag,
                            input int expected_drops=0,
                            input bit bad_crc=0, gmii_error=0, mid_update=0,
                            input int update_offset=30, input int update_field=0);
        byte unsigned body[]; int old_frames, old_drops;
        make_body(body,length,outer_type,tci,inner_type);
        received.delete(); old_frames=rx_frames; old_drops=policy_drops;
        expected_tagged=has_tag; expected_tci=has_tag ? tci : 0;
        rx_axis_tready=0;
        send_rx(body,bad_crc,gmii_error,mid_update,update_offset,update_field);
        // Receive with deterministic stalls; monitors check complete payload stability.
        for(int k=0;k<length*3+300 && (!deliver || k<64 || rx_frames==old_frames);k++) begin
            @(negedge logic_clk); rx_axis_tready=(k%7!=0 && k%7!=1);
        end
        @(negedge logic_clk); rx_axis_tready=0;
        if(rx_frames-old_frames != int'(deliver)) $fatal(1,"RX frame count");
        if(policy_drops-old_drops != expected_drops) $fatal(1,"VLAN drop count");
        if(received.size() != (deliver ? length : 0)) $fatal(1,"RX byte count");
        if(deliver)
            for(int i=0;i<length;i++) if(received[i]!=body[i])
                $fatal(1,"RX body mismatch offset %0d",i);
    endtask
    initial begin : workload
        reset_all();
        config_set(1,1,1,4'b0001,48'd7);
        fork
            begin : tx_work
                tx_check(60,0);
                repeat(12) @(negedge tx_clk);
                tx_check(512,0);
                repeat(12) @(negedge tx_clk);
                tx_check(1514,0);
            end
            begin : rx_work
                rx_check(60,16'h0800,0,0,1,0);
                rx_check(512,16'h8100,16'ha007,16'h0800,1,1);
                rx_check(1514,16'h8100,16'h5007,16'h0800,1,1);
                rx_check(80,16'h8100,16'h0008,16'h0800,0,0,1);
                rx_check(80,16'h8100,16'h0007,16'h0800,0,0,0,1);
                rx_check(60,16'h8100,16'hb000,16'h0800,1,1);
                config_set(0,0,0,0,0);
                rx_check(64,16'h8100,16'hffff,16'h8100,1,0);
            end
        join
        repeat(64) @(negedge logic_clk);
        if(tx_frames!=3 || rx_frames!=5 || policy_drops!=1)
            $fatal(1,"power workload completion counts");
        if(power_active && power_ops!=4296)
            $fatal(1,"power workload useful-byte count got %0d",power_ops);
        $display("T08_POWER_PASS TX=3 RX=5 DROP=1 OPS=4296");
        $finish;
    end
    initial begin #5000000; $fatal(1,"testbench watchdog"); end
endmodule
