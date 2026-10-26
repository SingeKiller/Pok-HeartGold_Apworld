.nds
.create "__OUTPUT_PATH__", __HOOK_LOAD_ADDRESS__

.arm

AP_PROTOCOL_ADDRESS equ __PROTOCOL_ADDRESS__
AP_PROTOCOL_MAGIC   equ 0x50414748

HeartGoldAP_Init:
    push {r0, r1, lr}
    ldr r0, =AP_PROTOCOL_ADDRESS
    ldr r1, =AP_PROTOCOL_MAGIC
    str r1, [r0, #0x00]
    mov r1, #1
    strh r1, [r0, #0x04]
    mov r1, #0
    strh r1, [r0, #0x06]
    str r1, [r0, #0x08]
    str r1, [r0, #0x0C]
    strh r1, [r0, #0x10]
    strh r1, [r0, #0x12]
    pop {r0, r1, lr}
    bx lr

HeartGoldAP_RecordGroundItemCheck:
    push {r1, r2, lr}
    ldr r1, =AP_PROTOCOL_ADDRESS
    str r0, [r1, #0x08]
    ldr r2, [r1, #0x0C]
    add r2, r2, #1
    str r2, [r1, #0x0C]
    pop {r1, r2, lr}
    bx lr

.pool
.close
