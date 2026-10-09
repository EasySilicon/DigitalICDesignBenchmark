`timescale 1ns/1ps
module direct_mapped_writeback_cache (
input logic clk,rst_n,
input logic req_valid,req_write,
output logic req_ready,
input logic [31:0] req_addr,req_wdata,
input logic [3:0] req_wstrb,
output logic rsp_valid,
input logic rsp_ready,
output logic [31:0] rsp_rdata,
output logic mem_req_valid,mem_req_write,
input logic mem_req_ready,
output logic [31:0] mem_req_addr,
output logic [127:0] mem_req_wdata,
input logic mem_rsp_valid,
output logic mem_rsp_ready,
input logic [127:0] mem_rsp_rdata
);
  typedef enum logic [3:0] {IDLE, LOOKUP, WB_REQ, WB_RSP, RD_REQ, RD_RSP,
                            FILL, COMMIT, RESP} state_t;
  state_t state;
  logic [127:0] lines[0:15];
  logic [23:0] tags[0:15];
  logic valids[0:15], dirtys[0:15];
  logic [31:0] saved_addr,saved_data;
  logic [3:0] saved_strb;
  logic saved_write;
  logic [31:0] wb_addr;
  logic [127:0] wb_data;
  logic [127:0] refill_data;
  logic [127:0] commit_line;
  logic [15:0] commit_way;
  logic [23:0] commit_tag;
  logic commit_dirty;
  wire [3:0] index = saved_addr[7:4];
  assign req_ready = state == IDLE;
  assign rsp_valid = state == RESP;
  assign mem_req_valid = state == WB_REQ || state == RD_REQ;
  assign mem_req_write = state == WB_REQ;
  assign mem_req_addr = state == WB_REQ ? wb_addr : {saved_addr[31:4],4'b0};
  assign mem_req_wdata = wb_data;
  assign mem_rsp_ready = state == WB_RSP || state == RD_RSP;
  function automatic logic [127:0] put_word(input logic [127:0] line,
    input logic [1:0] word_idx, input logic [31:0] data, input logic [3:0] strb);
    logic [127:0] result;
    result = line;
    for (int b=0;b<4;b++) if(strb[b]) result[32*int'(word_idx)+8*b+:8] = data[8*b+:8];
    put_word = result;
  endfunction
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      state <= IDLE;
      rsp_rdata <= 0;
      saved_addr <= 0; saved_data <= 0; saved_strb <= 0; saved_write <= 0;
      wb_addr <= 0; wb_data <= 0; refill_data <= 0;
      commit_line <= 0; commit_way <= 0; commit_tag <= 0; commit_dirty <= 0;
      for (int i=0;i<16;i++) begin
        valids[i] <= 0; dirtys[i] <= 0;
      end
    end else case(state)
      IDLE: if(req_valid) begin
        saved_addr <= req_addr;
        saved_data <= req_wdata;
        saved_strb <= req_wstrb;
        saved_write <= req_write;
        state <= LOOKUP;
      end
      LOOKUP: begin
        if(valids[index] && tags[index] == saved_addr[31:8]) begin
          if(saved_write && saved_strb != 0) begin
            commit_line <= put_word(lines[index],saved_addr[3:2],saved_data,saved_strb);
            commit_way <= 16'b1 << index;
            commit_tag <= saved_addr[31:8];
            commit_dirty <= 1;
            rsp_rdata <= 0;
            state <= COMMIT;
          end else begin
            rsp_rdata <= saved_write ? 0 : lines[index][32*int'(saved_addr[3:2])+:32];
            state <= RESP;
          end
        end else begin
          wb_addr <= {tags[index],index,4'b0};
          wb_data <= lines[index];
          if(valids[index] && dirtys[index]) state <= WB_REQ;
          else state <= RD_REQ;
        end
      end
      WB_REQ: if(mem_req_ready) state <= WB_RSP;
      WB_RSP: if(mem_rsp_valid) state <= RD_REQ;
      RD_REQ: if(mem_req_ready) state <= RD_RSP;
      RD_RSP: if(mem_rsp_valid) begin
        refill_data <= mem_rsp_rdata;
        state <= FILL;
      end
      FILL: begin
        commit_line <= saved_write ? put_word(refill_data,saved_addr[3:2],saved_data,saved_strb) : refill_data;
        commit_way <= 16'b1 << index;
        commit_tag <= saved_addr[31:8];
        commit_dirty <= saved_write && saved_strb != 0;
        rsp_rdata <= saved_write ? 0 : refill_data[32*int'(saved_addr[3:2])+:32];
        state <= COMMIT;
      end
      COMMIT: begin
        for (int i=0;i<16;i++) if(commit_way[i]) begin
          lines[i] <= commit_line;
          tags[i] <= commit_tag;
          valids[i] <= 1;
          dirtys[i] <= commit_dirty;
        end
        state <= RESP;
      end
      RESP: if(rsp_ready) state <= IDLE;
      default: state <= IDLE;
    endcase
  end
endmodule
