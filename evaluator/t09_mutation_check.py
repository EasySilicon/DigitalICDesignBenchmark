#!/usr/bin/env python3
"""Generate and qualify targeted T09 RTL fault mutants against independent oracles."""

from __future__ import annotations

import argparse
import json
import tempfile
from dataclasses import dataclass
from pathlib import Path

from t09_oracle_check import run

HERE = Path(__file__).resolve().parent
REFERENCE = HERE / "reference" / "T09" / "rtl" / "ref.sv"
DIRECTED = HERE / "t09_data" / "programs" / "directed"


@dataclass(frozen=True)
class Mutation:
    name: str
    original: str
    replacement: str
    elf: str


MUTATIONS = (
    Mutation("addi_sub", "ex_result.result = src1 + imm_i;",
             "ex_result.result = src1 - imm_i;", "int_add_sub_v0.elf"),
    Mutation("sub_add", "ex_result.result = src1 - src2;",
             "ex_result.result = src1 + src2;", "int_add_sub_v0.elf"),
    Mutation("xor_or", "ex_result.result = src1 ^ src2;",
             "ex_result.result = src1 | src2;", "int_bitwise_v0.elf"),
    Mutation("sra_logical", "ex_result.result = $signed(src1) >>> insn[24:20];",
             "ex_result.result = src1 >> insn[24:20];", "int_shift_immediate_v0.elf"),
    Mutation("beq_inverted", "3'b000: branch_taken_reg <= src1 == src2;",
             "3'b000: branch_taken_reg <= src1 != src2;", "int_beq_bne_v0.elf"),
    Mutation("blt_unsigned", "3'b100: branch_taken_reg <= $signed(src1) < $signed(src2);",
             "3'b100: branch_taken_reg <= src1 < src2;", "int_signed_branches_v0.elf"),
    Mutation("jal_link_plus8", "7'h6f: begin // JAL\n          target = jal_target_reg;\n          ex_result.result = idex.pc_plus4;",
             "7'h6f: begin // JAL\n          target = jal_target_reg;\n          ex_result.result = idex.pc_plus4 + 4;",
             "int_jal_link_flush_v0.elf"),
    Mutation("jalr_lsb", "jalr_target_reg <= (src1 + jalr_imm) & 32'hffff_fffe;",
             "jalr_target_reg <= src1 + jalr_imm;", "int_jalr_lsb_x0_v0.elf"),
    Mutation("lb_zero_extend", "{{24{shifted[7]}},shifted[7:0]}",
             "{24'b0,shifted[7:0]}", "mem_lb_sign_v0.elf"),
    Mutation("lh_zero_extend", "{{16{shifted[15]}},shifted[15:0]}",
             "{16'b0,shifted[15:0]}", "mem_lh_sign_v0.elf"),
    Mutation("sb_unshifted", "ex_result.store_data = mem_src2_reg << (8*lane);",
             "ex_result.store_data = mem_src2_reg;", "mem_sb_byte_lane_v0.elf"),
    Mutation("sb_lane0_only", "3'b000: ex_result.store_strb = 4'b0001 << lane;",
             "3'b000: ex_result.store_strb = 4'b0001;", "mem_sb_byte_lane_v0.elf"),
    Mutation("load_lane0_only", "shifted = dmem_rsp_rdata >> (8*exmem.load_lane);",
             "shifted = dmem_rsp_rdata;", "mem_same_address_partial_sequence_v0.elf"),
    Mutation("no_rs1_forward", "if (ex_hazard1) idex.rs1_value <= exmem.result;",
             "if (ex_hazard1) idex.rs1_value <= 0;",
             "haz_ex_to_ex_chain_v0.elf"),
    Mutation("no_rs2_forward", "if (ex_hazard2) idex.rs2_value <= exmem.result;",
             "if (ex_hazard2) idex.rs2_value <= 0;",
             "haz_both_sources_same_register_v0.elf"),
    Mutation("load_misalign_cause5", "ex_result.trap_cause = 4;",
             "ex_result.trap_cause = 5;", "trap_load_misaligned_v0.elf"),
    Mutation("store_fault_cause5", "memwb.trap_cause <= exmem.is_load ? 5 : 7;",
             "memwb.trap_cause <= 5;", "trap_store_access_fault_v0.elf"),
    Mutation("mret_skips_one", "target = csr_mepc;",
             "target = csr_mepc + 4;", "trap_ecall_m_v0.elf"),
    Mutation("mstatus_wrong_mie", "csr_write_data[3],3'b0};",
             "csr_write_data[4],3'b0};", "csr_machine_csr_masks_v1.elf"),
    Mutation("repeat_bus_request", "assign dmem_req_valid = rst_n && hold_memory && !mem_accepted;",
             "assign dmem_req_valid = rst_n && hold_memory;", "mem_sw_overwrite_v0.elf"),
    Mutation("never_accept_response", "assign dmem_rsp_ready = rst_n && hold_memory && mem_accepted;",
             "assign dmem_rsp_ready = 1'b0;", "mem_lw_full_width_v0.elf"),
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=HERE / "t09_mutation_qualification.json")
    args = parser.parse_args()
    source = REFERENCE.read_text()
    outcomes = []
    with tempfile.TemporaryDirectory(prefix="ic_bcmk_t09_mutants_") as directory:
        root = Path(directory)
        for mutation in MUTATIONS:
            if source.count(mutation.original) != 1:
                raise RuntimeError(f"{mutation.name}: source pattern not unique")
            submission = root / f"T09_{mutation.name}"
            rtl = submission / "rtl"
            rtl.mkdir(parents=True)
            (rtl / "ref.sv").write_text(source.replace(mutation.original,
                                                        mutation.replacement, 1))
            (rtl / "files.f").write_text("ref.sv\n")
            result = run(submission, 20260925, mutation.elf,
                         DIRECTED, DIRECTED, "CPU-MUTATION")
            valid_mutant = result.get("phase") == "run"
            caught = valid_mutant and result.get("cases_passed") == 0
            outcome = {"name": mutation.name, "elf": mutation.elf,
                       "compilable": valid_mutant, "caught": caught,
                       "reason": result.get("outcomes", [{}])[0].get("reason")
                       if valid_mutant else result.get("error")}
            outcomes.append(outcome)
            print(f"{mutation.name}: {'CAUGHT' if caught else 'SURVIVED/INVALID'}",
                  flush=True)
    summary = {"mutants": len(outcomes), "compilable": sum(x["compilable"] for x in outcomes),
               "caught": sum(x["caught"] for x in outcomes), "outcomes": outcomes}
    path = args.output
    path.parent.mkdir(exist_ok=True)
    path.write_text(json.dumps(summary, indent=2) + "\n")
    return 0 if summary["caught"] == summary["mutants"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
