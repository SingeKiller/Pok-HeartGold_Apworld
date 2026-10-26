.nds
.thumb

DIV         equ 0x020F2998
MASK_OF     equ 0x020726C0
GET_MON     equ 0x0206E540
IS_EGG      equ 76

.create OUT, 0x022378C0
.incbin IN

.org 0x0223E79C
    ldr     r1, =MULTIPLIER
    mul     r0, r1
    mov     r1, #100
    blx     DIV
    add     r4, r0, #0
.if GLOBAL == 1
    ldr     r1, [sp, #4]
    blx     DIV
    mov     r1, #0x9C
    bl      clamp_store
    lsr     r0, r4, #1
    mov     r1, #0xA0
    bl      clamp_store
    b       0x0223E80E
.else
    ldr     r1, [sp, #0]
    cmp     r1, #0
    beq     @@no_share
    lsr     r4, r4, #1
    add     r0, r4, #0
    ldr     r1, [sp, #4]
    blx     DIV
    mov     r1, #0x9C
    bl      clamp_store
    add     r0, r4, #0
    ldr     r1, [sp, #0]
    blx     DIV
    mov     r1, #0xA0
    bl      clamp_store
    b       0x0223E80E
@@no_share:
    ldr     r1, [sp, #4]
    blx     DIV
    mov     r1, #0x9C
    bl      clamp_store
    mov     r0, #0
    mov     r1, #0xA0
    str     r0, [r5, r1]
    b       0x0223E80E
.endif

clamp_store:
    cmp     r0, #0
    bne     @@store
    mov     r0, #1
@@store:
    str     r0, [r5, r1]
    bx      lr
.pool
.if org() > 0x0223E808
    .error "CalcExpGain patch overflows into vanilla code still in use"
.endif

.if GLOBAL == 1
.org 0x022458F4
    b       0x0224591A

.org 0x02245A36
    add     r0, r5, #0
    bl      MASK_OF
    ldr     r1, [sp, #0x44]
    lsl     r2, r1, #2
    ldr     r1, [sp, #0x24]
    add     r2, r1, r2
    add     r2, #0xA4
    ldr     r2, [r2]
    tst     r0, r2
    beq     @@not_participant
    mov     r2, #0x9C
    b       @@load
@@not_participant:
    add     r0, r6, #0
    mov     r1, #IS_EGG
    mov     r2, #0
    bl      GET_MON
    cmp     r0, #0
    bne     0x02245B3E
    ldr     r1, [sp, #0x24]
    mov     r2, #0xA0
@@load:
    ldr     r0, [r1, r2]
    str     r0, [sp, #0x38]
    b       0x02245A68
.if org() != 0x02245A68
    .error "Task_GetExp patch must be exactly 50 bytes"
.endif
.endif

.close
