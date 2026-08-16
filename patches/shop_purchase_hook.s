; patches/shop_purchase_hook.s
;
; *** NOT WORKING YET -- DO NOT WIRE INTO patch_gen.py/output_patch.py. ***
; Live-tested twice against the real US HeartGold ROM (2026-08-17): the
; game boots and plays completely normally, right up through a real
; purchase's full flow, then FREEZES the instant execution reaches this
; hook (both with a naive rom.append_to_arm9() placement AND with a
; proper decompress/append/recompress + SDK_COMPRESSED_STATIC_END-synced
; placement -- ruling out the "appended code never actually gets loaded"
; theory that motivated the second attempt). Root cause not yet found;
; every offset/address below IS independently confirmed correct (BLX
; target address hand-decoded and matches exactly; MartData field offsets
; matched two different real purchases exactly). Suspects for a future
; session, roughly in order of likelihood: (1) a genuine encoding/
; interworking bug in this file's own ARM code (needs a real disassembler
; to inspect the actual assembled bytes in context, not hand-decoding);
; (2) something about r0-r3/r12 being live across this exact call site in
; a way this session's manual Thumb decode of ov03_02257F24 missed --
; the decode was done by hand from a raw hex dump, not a real
; disassembler, so a wrong instruction read anywhere upstream of the
; hook site would corrupt every conclusion after it; (3) BLX(1)
; interworking from an overlay back into the main ARM9 image specifically
; (untested combination -- patches/ground_item_hook.s's own scaffold,
; the only prior ARM-code-injection attempt in this project, was never
; actually wired to a call site, so this is the first time *any* hook in
; this project has been live-executed at all).
;
; Shopsanity proof of concept: hooks ov03_02257F24, a shop-menu purchase-
; acknowledgement handler inside ARM9 overlay 3 (shop_menu.c), live-
; confirmed at RAM address 0x02257F24 against the real US HeartGold ROM
; (2026-08-17 -- see docs/scope.md). The hook sits right before the
; function writes data->unk298=4 and returns TASK_MART_4, i.e.
; immediately after a real purchase has fully completed (item already
; added to the bag, money already deducted, per MartData_PerformTransaction
; -- so this can never fire on a cancelled/failed purchase). If the item
; just bought matches SHOPSANITY_ITEM_ID, sets one flag bit in
; SaveVarsFlags.flags[] -- the exact same check-detection mechanism every
; other location type in this project already uses.
;
; MartData struct field offsets (include/overlay_03.h), live-confirmed
; against the real ROM across two separate real purchases (Antidote
; id=18/cost=100, Potion id=17/cost=300 -- both matched item/cost exactly)
; plus reading the 4 pointer-sized fields immediately preceding the
; already-confirmed `unk264` field:
;   +0x260  SaveVarsFlags *varsFlags
;   +0x284  u16 item
; SaveVarsFlags.flags[] sits at +0x2E0 within *varsFlags
; (save_layout.py: FLAGS_ARRAY_OFFSET = VARS_ARRAY_SIZE = 0x2E0).
;
; Call site: overlay 3, Thumb code, 0x02257FDC -- displaces "mov r1,#0xA6"
; + "mov r0,#4" (4 bytes total), replaced with a 32-bit Thumb BLX into
; this file's ARM hook function (appended to the end of the main ARM9
; image, same append mechanism patches/ground_item_hook.s already proved
; out). The hook re-executes the effect of both displaced instructions
; itself before returning, so vanilla behavior (data->unk298=4; return
; TASK_MART_4) is unaffected whether or not the shopsanity item was
; bought this time.
;
; r4 = MartData* for the whole of ov03_02257F24 (confirmed: PUSH {r4,lr}
; at function entry immediately followed by `mov r4, r0`, never
; reassigned before this hook's own call site) -- never touched by this
; hook, so it's still valid on return for the function's own remaining
; body (LDR r4,[sp]... / POP {r4,pc}).

.nds
.create "__HOOK_OUTPUT_PATH__", __HOOK_LOAD_ADDRESS__

.arm

SHOPSANITY_ITEM_ID    equ 18    ; ITEM_ANTIDOTE for tonight's live proof-of-concept test (already
                                  ; confirmed purchasable this session) -- swap to a not-normally-sold
                                  ; item (e.g. ITEM_LEFTOVERS=234) once wiring a real dedicated slot
SHOPSANITY_FLAG_ID    equ 2900  ; FLAG_UNK_B54 -- deep inside the confirmed-unused 2752-2911 run
SHOPSANITY_FLAG_BYTE  equ (SHOPSANITY_FLAG_ID / 8)
SHOPSANITY_FLAG_BIT   equ (SHOPSANITY_FLAG_ID % 8)
VARSFLAGS_OFFSET      equ 0x260
ITEM_OFFSET           equ 0x284
FLAGS_ARRAY_OFFSET    equ 0x2E0

ShopPurchaseHook:
    ldr r2, =ITEM_OFFSET               ; ARM LDRH immediate offsets only reach
    ldrh r1, [r4, r2]                  ; 0-255, so 0x284 needs a register offset
    ldr r0, =SHOPSANITY_ITEM_ID
    cmp r1, r0
    bne ShopPurchaseHook_restore
    ldr r0, [r4, #VARSFLAGS_OFFSET]    ; r0 = data->varsFlags
    ldrb r2, [r0, #(FLAGS_ARRAY_OFFSET + SHOPSANITY_FLAG_BYTE)]
    orr r2, r2, #(1 << SHOPSANITY_FLAG_BIT)
    strb r2, [r0, #(FLAGS_ARRAY_OFFSET + SHOPSANITY_FLAG_BYTE)]
ShopPurchaseHook_restore:
    mov r1, #0xA6                       ; re-execute the two displaced Thumb
    mov r0, #4                          ; instructions' effect exactly
    bx lr

.pool
.close

; Second output: the 4-byte Thumb call-site patch itself (a BLX to
; ShopPurchaseHook above), assembled separately since it must be placed
; inside overlay 3 at a fixed address, not appended to the main image.
.create "__CALLSITE_OUTPUT_PATH__", 0x02257FDC

.thumb
blx ShopPurchaseHook

.close
