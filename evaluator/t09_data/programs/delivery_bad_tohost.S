.option norvc
.section .text.init
.globl _start
_start:
  li a0, 2
  li a1, 0x8003f000
  sw a0, 0(a1)
1:
  j 1b
