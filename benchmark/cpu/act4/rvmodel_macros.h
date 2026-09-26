/*
 * Derived from riscv/riscv-arch-test,
 * config/cores/cve2/cv32e20/rvmodel_macros.h at revision
 * 4a42cbd3756259bbc1f92a7d816bc2fd2bd551cb.
 *
 * SPDX-License-Identifier: Apache-2.0
 *
 * Changes: reduced the upstream CV32E20 model macros to this benchmark's
 * RV32I/Zicsr tohost protocol and memory map. See
 * ../../../THIRD_PARTY_NOTICES.md.
 */
#ifndef IC_BCMK_RVMODEL_MACROS_H
#define IC_BCMK_RVMODEL_MACROS_H
#define RVMODEL_DATA_SECTION
#define RVMODEL_HALT_PASS \
  li x1, 1; \
  li t0, 0x8003f000; \
  sw x1, 0(t0); \
1: j 1b
#define RVMODEL_HALT_FAIL \
  li x1, 2; \
  li t0, 0x8003f000; \
  sw x1, 0(t0); \
1: j 1b
#define RVMODEL_IO_INIT(_R1, _R2, _R3)
#define RVMODEL_IO_WRITE_STR(_R1, _R2, _R3, _STR_PTR)
/* ACT4 requires these definitions even when privilege tests are excluded. */
#define RVMODEL_INTERRUPT_LATENCY 10
#define RVMODEL_TIMER_INT_SOON_DELAY 10000
#define RVMODEL_SET_MEXT_INT(_R1, _R2)
#define RVMODEL_CLR_MEXT_INT(_R1, _R2)
#define RVMODEL_SET_MSW_INT(_R1, _R2)
#define RVMODEL_CLR_MSW_INT(_R1, _R2)
#endif
