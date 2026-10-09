module rv32i_five_stage_cpu (
  input  logic clk, rst_n,
  output logic imem_valid,
  output logic [31:0] imem_addr,
  input  logic [31:0] imem_rdata,
  output logic dmem_req_valid,
  input  logic dmem_req_ready,
  output logic dmem_req_write,
  output logic [31:0] dmem_req_addr, dmem_req_wdata,
  output logic [3:0] dmem_req_wstrb,
  input  logic dmem_rsp_valid,
  output logic dmem_rsp_ready,
  input  logic [31:0] dmem_rsp_rdata,
  input  logic dmem_rsp_err,
  output logic commit_valid,
  output logic [31:0] commit_pc, commit_insn,
  output logic [4:0] commit_rd,
  output logic [31:0] commit_wdata, commit_mem_addr, commit_mem_wdata,
  output logic [3:0] commit_mem_wstrb,
  output logic trap_valid,
  output logic [31:0] trap_pc, trap_cause, trap_tval
);
  localparam logic [31:0] RESET_PC = 32'h8000_0000;

  typedef struct packed {
    logic valid;
    logic [31:0] pc, insn;
  } ifid_t;
  typedef struct packed {
    logic valid;
    logic [31:0] pc, insn, rs1_value, rs2_value;
    logic [31:0] pc_plus4;
    logic [4:0] rs1, rs2;
  } idex_t;
  typedef struct packed {
    logic valid, reg_write, is_load, is_store, trap;
    logic [31:0] pc, insn, result, addr, fault_addr, store_data;
    logic [4:0] rd;
    logic [3:0] store_strb;
    logic [1:0] load_size, load_lane;
    logic load_unsigned;
    logic [31:0] trap_cause, trap_tval;
  } stage_t;

  logic [31:0] regs [0:31];
  logic [31:0] fetch_pc, pending_pc;
  logic pending_valid, mem_accepted;
  ifid_t ifid;
  idex_t idex;
  stage_t exmem, memwb, ex_result;
  logic [31:0] csr_mstatus, csr_mtvec, csr_mscratch;
  logic [31:0] csr_mepc, csr_mcause, csr_mtval;
  logic csr_write_en;
  logic [11:0] csr_write_addr;
  logic [31:0] csr_write_data;
  logic ex_redirect, ex_mret, ex_trap;
  logic [31:0] ex_target;
  logic hold_memory, memory_done, memory_error;
  logic load_dependency_stall, execute_start, pipeline_advance;
  logic front_advance, redirect, trap_redirect;
  logic [31:0] redirect_target;
  // Two returned-instruction skid entries preserve in-flight responses while
  // EX/MEM waits. Fetch credits do not depend on forwarded EX data or traps.
  logic [31:0] fetch_queue_pc [0:1], fetch_queue_insn [0:1];
  logic fetch_head, fetch_tail;
  logic [1:0] fetch_count;
  logic queue_push, queue_pop;
  logic [31:0] src1, src2;
  logic [31:0] load_result;
  logic jalr_pending;
  logic [31:0] jalr_target_reg;
  logic [31:0] jalr_imm;
  logic jalr_start;
  logic branch_pending, branch_taken_reg, branch_start;
  logic [31:0] branch_target_reg, jal_target_reg;
  logic jal_pending, jal_start;
  logic use_rs1, use_rs2, ex_hazard1, ex_hazard2;
  logic ex_forward1, ex_forward2;
  // One-hot source choices: RF snapshot, MEM/WB, EX/MEM. All-zero means x0.
  logic [2:0] operand_select1, operand_select2;

  function automatic logic writes_rd(input logic [31:0] instruction);
    case (instruction[6:0])
      7'h37, 7'h17, 7'h6f, 7'h67, 7'h03, 7'h13, 7'h33: writes_rd = 1'b1;
      7'h73: writes_rd = instruction[14:12] != 0;
      default: writes_rd = 1'b0;
    endcase
  endfunction

  function automatic logic [2:0] operand_selection(input logic [4:0] source);
    if (source == 0) operand_selection = 3'b000;
    else if (idex.valid && writes_rd(idex.insn) && idex.insn[6:0] != 7'h03 &&
             idex.insn[11:7] != 0 && source == idex.insn[11:7])
      operand_selection = 3'b100;
    else if (exmem.valid && exmem.reg_write && !exmem.trap && exmem.rd != 0 &&
             source == exmem.rd)
      operand_selection = 3'b010;
    else operand_selection = 3'b001;
  endfunction

  // Four carry-select blocks. No latency is added: forwarded
  // operands, arithmetic and EX/MEM capture still occur in the same EX cycle.
  function automatic logic [31:0] fast_add(input logic [31:0] a, b,
                                         input logic carry_in);
    logic [8:0] sum_zero [0:3], sum_one [0:3];
    logic [4:0] carry;
    carry[0] = carry_in;
    for (int block_index=0; block_index<4; block_index++) begin
      sum_zero[block_index] = {1'b0,a[8*block_index+:8]} +
                              {1'b0,b[8*block_index+:8]};
      sum_one[block_index] = {1'b0,a[8*block_index+:8]} +
                             {1'b0,b[8*block_index+:8]} + 9'd1;
      carry[block_index+1] = sum_zero[block_index][8] |
          ((&(a[8*block_index+:8] ^ b[8*block_index+:8])) & carry[block_index]);
      fast_add[8*block_index+:8] = carry[block_index] ?
                                  sum_one[block_index][7:0] : sum_zero[block_index][7:0];
    end
  endfunction

  assign jalr_imm = {{20{idex.insn[31]}}, idex.insn[31:20]};
  assign jalr_start = idex.valid && idex.insn[6:0] == 7'h67 &&
                      idex.insn[14:12] == 3'b000 &&
                      idex.insn[1:0] == 2'b11 && !jalr_pending;
  assign branch_start = idex.valid && idex.insn[6:0] == 7'h63 &&
                        idex.insn[1:0] == 2'b11 && !branch_pending;
  assign jal_start = idex.valid && idex.insn[6:0] == 7'h6f && !jal_pending;

  function automatic logic [31:0] read_csr(input logic [11:0] address);
    case (address)
      12'h300: read_csr = csr_mstatus;
      12'h301: read_csr = 32'h4000_0100;
      12'h305: read_csr = csr_mtvec;
      12'h340: read_csr = csr_mscratch;
      12'h341: read_csr = csr_mepc;
      12'h342: read_csr = csr_mcause;
      12'h343: read_csr = csr_mtval;
      12'hf14: read_csr = 32'b0;
      default: read_csr = 32'b0;
    endcase
  endfunction

  function automatic logic csr_implemented(input logic [11:0] address);
    case (address)
      12'h300,12'h301,12'h305,12'h340,12'h341,12'h342,12'h343,12'hf14:
        csr_implemented = 1'b1;
      default: csr_implemented = 1'b0;
    endcase
  endfunction

  assign use_rs1 = idex.valid &&
                   (idex.insn[6:0] == 7'h67 || idex.insn[6:0] == 7'h63 ||
                    idex.insn[6:0] == 7'h03 || idex.insn[6:0] == 7'h23 ||
                    idex.insn[6:0] == 7'h13 || idex.insn[6:0] == 7'h33 ||
                    (idex.insn[6:0] == 7'h73 && !idex.insn[14]));
  assign use_rs2 = idex.valid &&
                   (idex.insn[6:0] == 7'h63 || idex.insn[6:0] == 7'h23 ||
                    idex.insn[6:0] == 7'h33);
  // A non-reading instruction ignores its source operands naturally. Do not
  // put its opcode decoder on the forwarding-to-ALU data path; qualify only
  // interlocks with use_rs, where false dependencies would cost cycles.
  assign ex_hazard1 = ex_forward1;
  assign ex_hazard2 = ex_forward2;
  // Genuine EX/MEM and MEM/WB forwarding: ordinary ALU dependencies never
  // become an extra execute cycle. A load is forwarded from MEM/WB only.
  always_comb begin
    src1 = (idex.rs1_value & {32{operand_select1[0]}}) |
           (memwb.result & {32{operand_select1[1]}}) |
           (exmem.result & {32{operand_select1[2]}});
    src2 = (idex.rs2_value & {32{operand_select2[0]}}) |
           (memwb.result & {32{operand_select2[1]}}) |
           (exmem.result & {32{operand_select2[2]}});
  end

  always_comb begin : execute
    logic [31:0] insn, imm_i, imm_s, imm_b, imm_u, imm_j;
    logic [31:0] target, addr, old_csr, csr_source, csr_new;
    logic [6:0] opcode, funct7;
    logic [2:0] funct3;
    logic [1:0] lane;
    logic branch_taken, legal, csr_do_write;
    logic [4:0] rd;
    ex_result = '0;
    csr_write_en = 1'b0;
    csr_write_addr = '0;
    csr_write_data = '0;
    ex_redirect = 1'b0;
    ex_mret = 1'b0;
    ex_trap = 1'b0;
    ex_target = '0;
    insn = idex.insn;
    opcode = insn[6:0];
    funct3 = insn[14:12];
    funct7 = insn[31:25];
    rd = insn[11:7];
    imm_i = {{20{insn[31]}},insn[31:20]};
    imm_s = {{20{insn[31]}},insn[31:25],insn[11:7]};
    imm_b = {{19{insn[31]}},insn[31],insn[7],insn[30:25],insn[11:8],1'b0};
    imm_u = {insn[31:12],12'b0};
    imm_j = {{11{insn[31]}},insn[31],insn[19:12],insn[20],insn[30:21],1'b0};
    target = '0;
    addr = '0;
    lane = '0;
    branch_taken = 1'b0;
    legal = 1'b1;
    csr_do_write = 1'b0;
    old_csr = '0;
    csr_source = '0;
    csr_new = '0;
    ex_result.valid = idex.valid;
    ex_result.pc = idex.pc;
    ex_result.insn = insn;
    ex_result.rd = rd;
    if (idex.valid) begin
      case (opcode)
        7'h37: begin // LUI
          ex_result.result = imm_u;
          ex_result.reg_write = (rd != 0);
        end
        7'h17: begin // AUIPC
          ex_result.result = idex.pc + imm_u;
          ex_result.reg_write = (rd != 0);
        end
        7'h6f: begin // JAL
          target = jal_target_reg;
          ex_result.result = idex.pc_plus4;
          ex_result.reg_write = (rd != 0);
          branch_taken = jal_pending;
        end
        7'h67: begin // JALR
          if (funct3 != 0) legal = 1'b0;
          else begin
            target = jalr_target_reg;
            ex_result.result = idex.pc_plus4;
            ex_result.reg_write = (rd != 0);
            branch_taken = jalr_pending;
          end
        end
        7'h63: begin // branches
          case (funct3)
            3'b000, 3'b001, 3'b100, 3'b101, 3'b110, 3'b111:
              branch_taken = branch_pending && branch_taken_reg;
            default: legal = 1'b0;
          endcase
          target = branch_target_reg;
        end
        7'h03: begin // loads
          addr = fast_add(src1, imm_i, 1'b0);
          lane = addr[1:0];
          ex_result.addr = {addr[31:2],2'b0};
          ex_result.fault_addr = addr;
          ex_result.load_lane = lane;
          ex_result.reg_write = (rd != 0);
          ex_result.is_load = 1'b1;
          case (funct3)
            3'b000: begin ex_result.load_size = 2'd0; ex_result.load_unsigned = 0; end
            3'b001: begin ex_result.load_size = 2'd1; ex_result.load_unsigned = 0; end
            3'b010: begin ex_result.load_size = 2'd2; ex_result.load_unsigned = 0; end
            3'b100: begin ex_result.load_size = 2'd0; ex_result.load_unsigned = 1; end
            3'b101: begin ex_result.load_size = 2'd1; ex_result.load_unsigned = 1; end
            default: legal = 1'b0;
          endcase
          if (legal && ((ex_result.load_size == 2'd1 && lane[0]) ||
                        (ex_result.load_size == 2'd2 && lane != 0))) begin
            ex_result.trap = 1'b1;
            ex_result.trap_cause = 4;
            ex_result.trap_tval = addr;
          end
        end
        7'h23: begin // stores
          addr = fast_add(src1, imm_s, 1'b0);
          lane = addr[1:0];
          ex_result.addr = {addr[31:2],2'b0};
          ex_result.fault_addr = addr;
          ex_result.rd = 0;
          ex_result.is_store = 1'b1;
          case (funct3)
            3'b000: ex_result.store_strb = 4'b0001 << lane;
            3'b001: begin
              ex_result.store_strb = 4'b0011 << lane;
              if (lane[0]) begin
                ex_result.trap = 1'b1;
                ex_result.trap_cause = 6;
                ex_result.trap_tval = addr;
              end
            end
            3'b010: begin
              ex_result.store_strb = 4'b1111;
              if (lane != 0) begin
                ex_result.trap = 1'b1;
                ex_result.trap_cause = 6;
                ex_result.trap_tval = addr;
              end
            end
            default: legal = 1'b0;
          endcase
          ex_result.store_data = src2 << (8*lane);
        end
        7'h13: begin // OP-IMM
          ex_result.reg_write = (rd != 0);
          case (funct3)
            3'b000: ex_result.result = fast_add(src1, imm_i, 1'b0);
            3'b010: ex_result.result = ($signed(src1) < $signed(imm_i)) ? 1 : 0;
            3'b011: ex_result.result = (src1 < imm_i) ? 1 : 0;
            3'b100: ex_result.result = src1 ^ imm_i;
            3'b110: ex_result.result = src1 | imm_i;
            3'b111: ex_result.result = src1 & imm_i;
            3'b001: begin
              ex_result.result = src1 << insn[24:20];
              if (funct7 != 0) legal = 1'b0;
            end
            3'b101: begin
              if (funct7 == 0) ex_result.result = src1 >> insn[24:20];
              else if (funct7 == 7'h20)
                ex_result.result = $signed(src1) >>> insn[24:20];
              else legal = 1'b0;
            end
          endcase
        end
        7'h33: begin // OP
          ex_result.reg_write = (rd != 0);
          case ({funct7,funct3})
            {7'h00,3'b000}: ex_result.result = fast_add(src1, src2, 1'b0);
            {7'h20,3'b000}: ex_result.result = fast_add(src1, ~src2, 1'b1);
            {7'h00,3'b001}: ex_result.result = src1 << src2[4:0];
            {7'h00,3'b010}: ex_result.result = ($signed(src1) < $signed(src2)) ? 1 : 0;
            {7'h00,3'b011}: ex_result.result = (src1 < src2) ? 1 : 0;
            {7'h00,3'b100}: ex_result.result = src1 ^ src2;
            {7'h00,3'b101}: ex_result.result = src1 >> src2[4:0];
            {7'h20,3'b101}: ex_result.result = $signed(src1) >>> src2[4:0];
            {7'h00,3'b110}: ex_result.result = src1 | src2;
            {7'h00,3'b111}: ex_result.result = src1 & src2;
            default: legal = 1'b0;
          endcase
        end
        7'h0f: begin // FENCE only
          ex_result.rd = 0;
          if (funct3 != 0) legal = 1'b0;
        end
        7'h73: begin // SYSTEM, CSR, MRET
          if (insn == 32'h0000_0073) begin
            ex_result.trap = 1'b1;
            ex_result.trap_cause = 11;
            ex_result.trap_tval = 0;
          end else if (insn == 32'h0010_0073) begin
            ex_result.trap = 1'b1;
            ex_result.trap_cause = 3;
            ex_result.trap_tval = 0;
          end else if (insn == 32'h3020_0073) begin
            ex_mret = 1'b1;
            branch_taken = 1'b1;
            target = csr_mepc;
            ex_result.rd = 0;
          end else if (funct3 == 3'b001 || funct3 == 3'b010 ||
                       funct3 == 3'b011 || funct3 == 3'b101 ||
                       funct3 == 3'b110 || funct3 == 3'b111) begin
            csr_write_addr = insn[31:20];
            if (!csr_implemented(csr_write_addr)) legal = 1'b0;
            old_csr = read_csr(csr_write_addr);
            csr_source = funct3[2] ? {27'b0,insn[19:15]} : src1;
            csr_do_write = (funct3[1:0] == 2'b01) || (insn[19:15] != 0);
            if (csr_do_write && (csr_write_addr == 12'h301 ||
                                 csr_write_addr == 12'hf14)) legal = 1'b0;
            case (funct3[1:0])
              2'b01: csr_new = csr_source;
              2'b10: csr_new = old_csr | csr_source;
              2'b11: csr_new = old_csr & ~csr_source;
              default: legal = 1'b0;
            endcase
            ex_result.result = old_csr;
            ex_result.reg_write = (rd != 0);
            csr_write_en = legal && csr_do_write;
            csr_write_data = csr_new;
          end else legal = 1'b0;
        end
        default: legal = 1'b0;
      endcase
      if (insn[1:0] != 2'b11) legal = 1'b0;
      if (!legal) begin
        ex_result.trap = 1'b1;
        ex_result.trap_cause = 2;
        ex_result.trap_tval = insn;
        csr_write_en = 0;
        ex_mret = 0;
        branch_taken = 0;
      end
      if (legal && branch_taken && target[1:0] != 0) begin
        ex_result.trap = 1'b1;
        ex_result.trap_cause = 0;
        ex_result.trap_tval = target;
        ex_mret = 0;
        branch_taken = 0;
      end
      if (ex_result.trap) begin
        ex_result.reg_write = 0;
        ex_result.is_load = 0;
        ex_result.is_store = 0;
        ex_result.store_strb = 0;
        ex_result.rd = 0;
        ex_trap = 1;
        // Redirect this precise exception from EX/MEM next cycle. A younger
        // instruction can enter ID/EX but is blocked before EX/MEM/CSR writes.
        // Forwarded address/alignment logic therefore never controls fetch.
        ex_redirect = 0;
        ex_target = 0;
      end
      // Do not gate all control redirects with the shared exception result:
      // doing so reintroduces a false forwarded-address -> alignment -> IF
      // control path. Each control opcode checks its own registered target.
      case (opcode)
        7'h63: if (branch_pending &&
                    (funct3 == 0 || funct3 == 1 || funct3 == 4 ||
                     funct3 == 5 || funct3 == 6 || funct3 == 7) &&
                    (!branch_taken_reg || branch_target_reg[1:0] == 0)) begin
          ex_redirect = 1;
          ex_target = branch_taken_reg ? branch_target_reg : idex.pc_plus4;
        end
        7'h6f: if (jal_pending && jal_target_reg[1:0] == 0) begin
          ex_redirect = 1;
          ex_target = jal_target_reg;
        end
        7'h67: if (funct3 == 0 && jalr_pending && jalr_target_reg[1:0] == 0) begin
          ex_redirect = 1;
          ex_target = jalr_target_reg;
        end
        7'h73: if (insn == 32'h3020_0073) begin
          ex_redirect = 1;
          ex_target = target;
        end
        default: ;
      endcase
    end
  end

  always_comb begin
    logic [31:0] shifted;
    shifted = dmem_rsp_rdata >> (8*exmem.load_lane);
    case (exmem.load_size)
      2'd0: load_result = exmem.load_unsigned ? {24'b0,shifted[7:0]} :
                                      {{24{shifted[7]}},shifted[7:0]};
      2'd1: load_result = exmem.load_unsigned ? {16'b0,shifted[15:0]} :
                                      {{16{shifted[15]}},shifted[15:0]};
      default: load_result = shifted;
    endcase
  end

  assign hold_memory = exmem.valid && (exmem.is_load || exmem.is_store);
  assign memory_done = hold_memory && mem_accepted && dmem_rsp_valid;
  assign memory_error = memory_done && dmem_rsp_err;
  assign trap_redirect = exmem.valid && exmem.trap;
  assign load_dependency_stall = hold_memory && exmem.is_load &&
                                 ((use_rs1 && ex_hazard1) || (use_rs2 && ex_hazard2));
  assign execute_start = jalr_start || branch_start || jal_start;
  assign pipeline_advance = (!hold_memory || memory_done) &&
                            !memory_error && !load_dependency_stall && !trap_redirect;
  assign redirect = memory_error || trap_redirect ||
                    (pipeline_advance && !execute_start && idex.valid && ex_redirect);
  assign redirect_target = (memory_error || trap_redirect) ? csr_mtvec : ex_target;
  assign front_advance = pipeline_advance && !execute_start && !redirect;
  assign queue_pop = front_advance && fetch_count != 0;
  assign queue_push = pending_valid && !redirect &&
                      (!front_advance || fetch_count != 0);
  // Requests accepted on a redirect edge are permitted speculative fetches;
  // their next-cycle responses are dropped. Credits include the in-flight
  // response, so even an arbitrarily long data wait cannot overflow the queue.
  assign imem_valid = rst_n && ({1'b0,fetch_count} + {2'b0,pending_valid} < 3'd2);
  assign imem_addr = fetch_pc;
  assign dmem_req_valid = rst_n && hold_memory && !mem_accepted;
  assign dmem_req_write = exmem.is_store;
  assign dmem_req_addr = exmem.addr;
  assign dmem_req_wstrb = exmem.is_store ? exmem.store_strb : 4'b0;
  assign dmem_req_wdata = exmem.store_data;
  assign dmem_rsp_ready = rst_n && hold_memory && mem_accepted;
  assign commit_valid = memwb.valid && !memwb.trap;
  assign commit_pc = memwb.pc;
  assign commit_insn = memwb.insn;
  assign commit_rd = memwb.reg_write ? memwb.rd : 5'b0;
  assign commit_wdata = memwb.result;
  assign commit_mem_addr = memwb.addr;
  assign commit_mem_wstrb = memwb.is_store ? memwb.store_strb : 4'b0;
  assign commit_mem_wdata = memwb.store_data;
  assign trap_valid = memwb.valid && memwb.trap;
  assign trap_pc = memwb.pc;
  assign trap_cause = memwb.trap_cause;
  assign trap_tval = memwb.trap_tval;

  // Fetch/IF-ID bookkeeping is independent of execute datapath selection.
  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fetch_pc <= RESET_PC;
      pending_pc <= 0;
      pending_valid <= 0;
      ifid <= '0;
      fetch_head <= 0;
      fetch_tail <= 0;
      fetch_count <= 0;
      for (int i=0; i<2; i++) begin
        fetch_queue_pc[i] <= 0;
        fetch_queue_insn[i] <= 0;
      end
    end else if (redirect) begin
      fetch_pc <= redirect_target;
      pending_valid <= 0;
      ifid.valid <= 0;
      fetch_count <= 0;
      fetch_head <= 0;
      fetch_tail <= 0;
    end else begin
      pending_valid <= imem_valid;
      if (imem_valid) begin
        pending_pc <= fetch_pc;
        fetch_pc <= fetch_pc + 4;
      end
      if (queue_push) begin
        fetch_queue_pc[fetch_tail] <= pending_pc;
        fetch_queue_insn[fetch_tail] <= imem_rdata;
        fetch_tail <= !fetch_tail;
      end
      if (queue_pop) fetch_head <= !fetch_head;
      case ({queue_push,queue_pop})
        2'b10: fetch_count <= fetch_count + 1'b1;
        2'b01: fetch_count <= fetch_count - 1'b1;
        default: ;
      endcase
      if (front_advance) begin
        ifid.valid <= (fetch_count != 0) || pending_valid;
        ifid.pc <= fetch_count != 0 ? fetch_queue_pc[fetch_head] : pending_pc;
        ifid.insn <= fetch_count != 0 ? fetch_queue_insn[fetch_head] : imem_rdata;
      end
    end
  end

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      idex <= '0;
      exmem <= '0;
      memwb <= '0;
      mem_accepted <= 0;
      ex_forward1 <= 0;
      ex_forward2 <= 0;
      operand_select1 <= 0;
      operand_select2 <= 0;
      jalr_pending <= 0;
      jalr_target_reg <= 0;
      branch_pending <= 0;
      branch_taken_reg <= 0;
      branch_target_reg <= 0;
      jal_pending <= 0;
      jal_target_reg <= 0;
      csr_mstatus <= 32'h0000_1800;
      csr_mtvec <= RESET_PC;
      csr_mscratch <= 0;
      csr_mepc <= 0;
      csr_mcause <= 0;
      csr_mtval <= 0;
      for (int i=0; i<32; i++) regs[i] <= 0;
    end else begin
      memwb <= '0;
      if (hold_memory) begin
        if (!mem_accepted && dmem_req_valid && dmem_req_ready)
          mem_accepted <= 1;
        if (memory_done) begin
          memwb <= exmem;
          mem_accepted <= 0;
          if (dmem_rsp_err) begin
            memwb.trap <= 1;
            memwb.trap_cause <= exmem.is_load ? 5 : 7;
            memwb.trap_tval <= exmem.fault_addr;
            memwb.reg_write <= 0;
            memwb.is_store <= 0;
            memwb.store_strb <= 0;
            memwb.rd <= 0;
          end else if (exmem.is_load) begin
            memwb.result <= load_result;
            if (exmem.reg_write) regs[exmem.rd] <= load_result;
          end
        end
      end else begin
        memwb <= exmem;
        if (exmem.valid && exmem.reg_write && exmem.rd != 0)
          regs[exmem.rd] <= exmem.result;
        mem_accepted <= 0;
      end

      // Architectural exception state is written from the registered MEM
      // instruction, not from the forwarded EX address/alignment path.
      if (memory_error || (!hold_memory && exmem.valid && exmem.trap)) begin
        csr_mstatus[7] <= csr_mstatus[3];
        csr_mstatus[3] <= 0;
        csr_mstatus[12:11] <= 2'b11;
        csr_mepc <= exmem.pc;
        csr_mcause <= memory_error ? (exmem.is_load ? 5 : 7) : exmem.trap_cause;
        csr_mtval <= memory_error ? exmem.fault_addr : exmem.trap_tval;
      end else if (pipeline_advance && !execute_start && idex.valid) begin
        if (ex_mret) begin
          csr_mstatus[3] <= csr_mstatus[7];
          csr_mstatus[7] <= 1;
          csr_mstatus[12:11] <= 2'b11;
        end else if (csr_write_en) begin
          case (csr_write_addr)
            12'h300: csr_mstatus <= {19'b0,2'b11,3'b0,
                                    csr_write_data[7],3'b0,
                                    csr_write_data[3],3'b0};
            12'h305: csr_mtvec <= {csr_write_data[31:2],2'b0};
            12'h340: csr_mscratch <= csr_write_data;
            12'h341: csr_mepc <= {csr_write_data[31:2],2'b0};
            12'h342: csr_mcause <= csr_write_data;
            12'h343: csr_mtval <= csr_write_data;
            default: ;
          endcase
        end
      end

      if (redirect) begin
        idex.valid <= 0;
        ex_forward1 <= 0;
        ex_forward2 <= 0;
        operand_select1 <= 0;
        operand_select2 <= 0;
        jalr_pending <= 0;
        branch_pending <= 0;
        jal_pending <= 0;
        exmem <= (memory_error || trap_redirect) ? stage_t'('0) : ex_result;
      end else if (pipeline_advance) begin
        if (execute_start) begin
          // Extra control-resolution cycles are allowed; ALU and memory
          // address generation remain genuine one-cycle EX operations.
          if (jalr_start) begin
            jalr_target_reg <= (src1 + jalr_imm) & 32'hffff_fffe;
            jalr_pending <= 1;
          end
          if (branch_start) begin
            branch_pending <= 1;
            branch_target_reg <= idex.pc +
                {{19{idex.insn[31]}},idex.insn[31],idex.insn[7],
                 idex.insn[30:25],idex.insn[11:8],1'b0};
            case (idex.insn[14:12])
              3'b000: branch_taken_reg <= src1 == src2;
              3'b001: branch_taken_reg <= src1 != src2;
              3'b100: branch_taken_reg <= $signed(src1) < $signed(src2);
              3'b101: branch_taken_reg <= $signed(src1) >= $signed(src2);
              3'b110: branch_taken_reg <= src1 < src2;
              3'b111: branch_taken_reg <= src1 >= src2;
              default: branch_taken_reg <= 0;
            endcase
          end
          if (jal_start) begin
            jal_pending <= 1;
            jal_target_reg <= idex.pc +
                {{11{idex.insn[31]}},idex.insn[31],idex.insn[19:12],
                 idex.insn[20],idex.insn[30:21],1'b0};
          end
          exmem <= '0;
          idex.rs1_value <= src1;
          idex.rs2_value <= src2;
          // The values just captured in ID/EX outlive the drained producers.
          operand_select1 <= idex.rs1 == 0 ? 3'b000 : 3'b001;
          operand_select2 <= idex.rs2 == 0 ? 3'b000 : 3'b001;
          ex_forward1 <= 0;
          ex_forward2 <= 0;
        end else begin
          jalr_pending <= 0;
          branch_pending <= 0;
          jal_pending <= 0;
          exmem <= ex_result;
          idex.valid <= ifid.valid;
          idex.pc <= ifid.pc;
          idex.insn <= ifid.insn;
          idex.pc_plus4 <= ifid.pc + 4;
          idex.rs1 <= ifid.insn[19:15];
          idex.rs2 <= ifid.insn[24:20];
          idex.rs1_value <= ifid.insn[19:15] == 0 ? 0 : regs[ifid.insn[19:15]];
          idex.rs2_value <= ifid.insn[24:20] == 0 ? 0 : regs[ifid.insn[24:20]];
          // Compare register identities in ID, in parallel with the RF read.
          // WB qualifications are captured here too. EX producers are
          // conservatively decoded; a faulting producer redirects from MEM
          // before its younger consumer can execute or make any side effect.
          // EX data never traverses a register-number comparator.
          operand_select1 <= operand_selection(ifid.insn[19:15]);
          operand_select2 <= operand_selection(ifid.insn[24:20]);
          ex_forward1 <= idex.valid && writes_rd(idex.insn) && idex.insn[11:7] != 0 &&
                         ifid.insn[19:15] == idex.insn[11:7];
          ex_forward2 <= idex.valid && writes_rd(idex.insn) && idex.insn[11:7] != 0 &&
                         ifid.insn[24:20] == idex.insn[11:7];
        end
      end else begin
        // Preserve producer values while a memory request waits and old WB
        // forwarding sources drain. The returning load is NOT used until WB.
        idex.rs1_value <= src1;
        idex.rs2_value <= src2;
        operand_select1 <= idex.rs1 == 0 ? 3'b000 :
                           memory_done && ex_forward1 ? 3'b010 : 3'b001;
        operand_select2 <= idex.rs2 == 0 ? 3'b000 :
                           memory_done && ex_forward2 ? 3'b010 : 3'b001;
        if (memory_done || !hold_memory) begin
          ex_forward1 <= 0;
          ex_forward2 <= 0;
        end
        if (memory_done) exmem <= '0;
        else if (!hold_memory) exmem <= '0;
      end
    end
  end
endmodule
