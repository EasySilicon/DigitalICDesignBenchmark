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
  logic hold_memory, hold_fetch_for_mem;
  logic [31:0] src1, src2;
  logic [31:0] load_result;
  logic jalr_pending;
  logic [31:0] jalr_target_reg;
  logic [31:0] jalr_imm;
  logic jalr_start;
  logic branch_pending, branch_taken_reg, branch_start;
  logic [31:0] branch_target_reg, jal_target_reg;
  logic jal_pending, jal_start;
  logic mem_pending, mem_start;
  logic [31:0] mem_src1_reg, mem_src2_reg;
  logic operands_ready, hazard_start;
  logic use_rs1, use_rs2, ex_hazard1, ex_hazard2;
  logic wb_hazard1, wb_hazard2;

  assign jalr_imm = {{20{idex.insn[31]}}, idex.insn[31:20]};
  assign jalr_start = idex.valid && idex.insn[6:0] == 7'h67 &&
                      idex.insn[14:12] == 3'b000 &&
                      idex.insn[1:0] == 2'b11 && !jalr_pending;
  assign branch_start = idex.valid && idex.insn[6:0] == 7'h63 &&
                        idex.insn[1:0] == 2'b11 && !branch_pending;
  assign jal_start = idex.valid && idex.insn[6:0] == 7'h6f && !jal_pending;
  assign mem_start = idex.valid &&
                     (idex.insn[6:0] == 7'h03 || idex.insn[6:0] == 7'h23) &&
                     !mem_pending;

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
  assign ex_hazard1 = use_rs1 && idex.rs1 != 0 && exmem.valid &&
                      exmem.reg_write && exmem.rd == idex.rs1;
  assign ex_hazard2 = use_rs2 && idex.rs2 != 0 && exmem.valid &&
                      exmem.reg_write && exmem.rd == idex.rs2;
  assign wb_hazard1 = use_rs1 && idex.rs1 != 0 && memwb.valid &&
                      memwb.reg_write && memwb.rd == idex.rs1;
  assign wb_hazard2 = use_rs2 && idex.rs2 != 0 && memwb.valid &&
                      memwb.reg_write && memwb.rd == idex.rs2;
  assign hazard_start = !operands_ready &&
                        (ex_hazard1 || ex_hazard2 || wb_hazard1 || wb_hazard2);
  assign src1 = idex.rs1_value;
  assign src2 = idex.rs2_value;

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
          addr = mem_src1_reg + imm_i;
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
          addr = mem_src1_reg + imm_s;
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
          ex_result.store_data = mem_src2_reg << (8*lane);
        end
        7'h13: begin // OP-IMM
          ex_result.reg_write = (rd != 0);
          case (funct3)
            3'b000: ex_result.result = src1 + imm_i;
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
            {7'h00,3'b000}: ex_result.result = src1 + src2;
            {7'h20,3'b000}: ex_result.result = src1 - src2;
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
        ex_redirect = 1;
        ex_target = csr_mtvec;
      end else if (opcode == 7'h63 && branch_pending) begin
        // A branch consumes an extra EX cycle. Re-fetch the sequential
        // instruction when the branch is not taken as well, because any
        // younger response accepted during that cycle is speculative.
        ex_redirect = 1;
        ex_target = branch_taken_reg ? target : idex.pc_plus4;
      end else if (branch_taken) begin
        ex_redirect = 1;
        ex_target = target;
      end
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
  assign hold_fetch_for_mem = idex.valid &&
                               (idex.insn[6:0] == 7'h03 || idex.insn[6:0] == 7'h23);
  // A request issued on a redirect cycle may be wrong-path. Its following
  // response is discarded because pending_valid is cleared on that edge.
  assign imem_valid = rst_n && !hold_memory && !hold_fetch_for_mem;
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

  always_ff @(posedge clk or negedge rst_n) begin
    if (!rst_n) begin
      fetch_pc <= RESET_PC;
      pending_pc <= 0;
      pending_valid <= 0;
      ifid <= '0;
      idex <= '0;
      exmem <= '0;
      memwb <= '0;
      mem_accepted <= 0;
      jalr_pending <= 0;
      jalr_target_reg <= 0;
      branch_pending <= 0;
      branch_taken_reg <= 0;
      branch_target_reg <= 0;
      jal_pending <= 0;
      jal_target_reg <= 0;
      mem_pending <= 0;
      mem_src1_reg <= 0;
      mem_src2_reg <= 0;
      operands_ready <= 0;
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
        // Older instructions may retire while this memory operation waits.
        // Refresh stalled ID operands; the returning load is forwarded from
        // MEM/WB on the cycle after its response.
        idex.rs1_value <= idex.rs1 == 0 ? 0 : regs[idex.rs1];
        idex.rs2_value <= idex.rs2 == 0 ? 0 : regs[idex.rs2];
        if (!mem_accepted) begin
          if (dmem_req_valid && dmem_req_ready) mem_accepted <= 1;
        end else if (dmem_rsp_valid && dmem_rsp_ready) begin
          memwb <= exmem;
          if (dmem_rsp_err) begin
            memwb.trap <= 1;
            memwb.trap_cause <= exmem.is_load ? 5 : 7;
            memwb.trap_tval <= exmem.fault_addr;
            memwb.reg_write <= 0;
            memwb.is_store <= 0;
            memwb.store_strb <= 0;
            memwb.rd <= 0;
            csr_mstatus[7] <= csr_mstatus[3];
            csr_mstatus[3] <= 0;
            csr_mstatus[12:11] <= 2'b11;
            csr_mepc <= exmem.pc;
            csr_mcause <= exmem.is_load ? 5 : 7;
            csr_mtval <= exmem.fault_addr;
            fetch_pc <= csr_mtvec;
            pending_valid <= 0;
            ifid.valid <= 0;
            idex.valid <= 0;
          end else begin
            if (exmem.is_load) begin
              memwb.result <= load_result;
              if (exmem.reg_write) regs[exmem.rd] <= load_result;
            end
          end
          exmem <= '0;
          mem_accepted <= 0;
        end
      end else begin
        memwb <= exmem;
        if (exmem.valid && exmem.reg_write && exmem.rd != 0)
          regs[exmem.rd] <= exmem.result;
        // The exception is already in EX/MEM when its architectural CSR
        // state is written.  This keeps address generation and alignment
        // checking off the EX-to-CSR timing path.
        if (exmem.valid && exmem.trap) begin
          csr_mstatus[7] <= csr_mstatus[3];
          csr_mstatus[3] <= 0;
          csr_mstatus[12:11] <= 2'b11;
          csr_mepc <= exmem.pc;
          csr_mcause <= exmem.trap_cause;
          csr_mtval <= exmem.trap_tval;
        end
        mem_accepted <= 0;
        if (imem_valid) pending_pc <= fetch_pc;
        if (hazard_start || jalr_start || branch_start || jal_start ||
            mem_start) begin
          if (hazard_start) begin
            if (ex_hazard1) idex.rs1_value <= exmem.result;
            else if (wb_hazard1) idex.rs1_value <= memwb.result;
            if (ex_hazard2) idex.rs2_value <= exmem.result;
            else if (wb_hazard2) idex.rs2_value <= memwb.result;
            operands_ready <= 1;
            if (pending_valid) fetch_pc <= pending_pc;
            pending_valid <= 0;
          end
          // Resolve forwarded operands separately from redirect control.
          // Both control instructions remain in EX for one extra cycle.
          if (jalr_start && !hazard_start) begin
            jalr_target_reg <= (src1 + jalr_imm) & 32'hffff_fffe;
            jalr_pending <= 1;
          end
          if (branch_start && !hazard_start) begin
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
          if (jal_start && !hazard_start) begin
            jal_pending <= 1;
            jal_target_reg <= idex.pc +
                {{11{idex.insn[31]}},idex.insn[31],idex.insn[19:12],
                 idex.insn[20],idex.insn[30:21],1'b0};
          end
          exmem <= ex_result;
          exmem.valid <= 0;
          if (mem_start && !hazard_start) begin
            mem_src1_reg <= src1;
            mem_src2_reg <= src2;
            mem_pending <= 1;
            // Keep IF/ID while this memory instruction spends an extra EX
            // cycle. Drop and later re-request any younger in-flight fetch.
            if (pending_valid) fetch_pc <= pending_pc;
            pending_valid <= 0;
          end else if (!hazard_start) begin
            ifid.valid <= pending_valid;
            ifid.pc <= pending_pc;
            ifid.insn <= imem_rdata;
            pending_valid <= imem_valid;
            if (imem_valid) fetch_pc <= fetch_pc + 4;
          end
        end else begin
          jalr_pending <= 0;
          branch_pending <= 0;
          jal_pending <= 0;
          mem_pending <= 0;
          operands_ready <= 0;
          exmem <= ex_result;
        if (idex.valid && ex_mret) begin
          csr_mstatus[3] <= csr_mstatus[7];
          csr_mstatus[7] <= 1;
          csr_mstatus[12:11] <= 2'b11;
        end else if (idex.valid && csr_write_en) begin
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
        if (idex.valid && ex_redirect) begin
          fetch_pc <= ex_target;
          pending_valid <= 0;
          ifid.valid <= 0;
          idex.valid <= 0;
        end else begin
          idex.valid <= ifid.valid;
          idex.pc <= ifid.pc;
          idex.insn <= ifid.insn;
          idex.pc_plus4 <= ifid.pc + 4;
          idex.rs1 <= ifid.insn[19:15];
          idex.rs2 <= ifid.insn[24:20];
          idex.rs1_value <= ifid.insn[19:15] == 0 ? 0 : regs[ifid.insn[19:15]];
          idex.rs2_value <= ifid.insn[24:20] == 0 ? 0 : regs[ifid.insn[24:20]];
          ifid.valid <= pending_valid;
          ifid.pc <= pending_pc;
          ifid.insn <= imem_rdata;
          pending_valid <= imem_valid;
          if (imem_valid) begin
            fetch_pc <= fetch_pc + 4;
          end
        end
        end
      end
    end
  end
endmodule
