.nds
.create "__HOOK_OUTPUT_PATH__", __HOOK_LOAD_ADDRESS__

.arm

SHOPSANITY_ITEM_ID    equ 18
SHOPSANITY_FLAG_ID    equ 2900
SHOPSANITY_FLAG_BYTE  equ (SHOPSANITY_FLAG_ID / 8)
SHOPSANITY_FLAG_BIT   equ (SHOPSANITY_FLAG_ID % 8)
VARSFLAGS_OFFSET      equ 0x260
ITEM_OFFSET           equ 0x284
FLAGS_ARRAY_OFFSET    equ 0x2E0

ShopPurchaseHook:
    ldr r2, =ITEM_OFFSET
    ldrh r1, [r4, r2]
    ldr r0, =SHOPSANITY_ITEM_ID
    cmp r1, r0
    bne ShopPurchaseHook_restore
    ldr r0, [r4, #VARSFLAGS_OFFSET]
    ldrb r2, [r0, #(FLAGS_ARRAY_OFFSET + SHOPSANITY_FLAG_BYTE)]
    orr r2, r2, #(1 << SHOPSANITY_FLAG_BIT)
    strb r2, [r0, #(FLAGS_ARRAY_OFFSET + SHOPSANITY_FLAG_BYTE)]
ShopPurchaseHook_restore:
    mov r1, #0xA6
    mov r0, #4
    bx lr

.pool
.close

.create "__CALLSITE_OUTPUT_PATH__", 0x02257FDC

.thumb
blx ShopPurchaseHook

.close
