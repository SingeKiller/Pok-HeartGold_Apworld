; patches/exp_share.s
;
; Global Exp. Share + Exp. multiplier, patched in place into ARM9 overlay 12
; (the battle engine, load address 0x022378C0). Same bytes on HeartGold and
; SoulSilver US: the overlay only differs by 7 bytes between the two, none
; of them in the ranges below.
;
; Assembled offline with armips (see rom/expshare.py, which embeds the
; resulting bytes: players never need armips). Build variables, passed with
; -equ on the armips command line:
;   GLOBAL      1 = every party member gains Exp. (modern style), 0 = vanilla
;   MULTIPLIER  percent applied to every Exp. gain (100 = vanilla)
;   IN / OUT    decompressed overlay 12 in, patched copy out
;
; Decomp references: src/battle/battle_command.c, BtlCmd_CalcExpGain (1222)
; and Task_GetExp (5992).

.nds
.thumb

; The division helper BtlCmd_CalcExpGain calls is ARM code: vanilla reaches
; it with BLX (second halfword 0xE8xx), so every call below is `blx`. A
; plain `bl` here jumped into it in Thumb state and froze the game at the
; first Exp. gain (player report, 2026-09-18).
DIV         equ 0x020F2998
MASK_OF     equ 0x020726C0 ; MaskOfFlagNo
GET_MON     equ 0x0206E540 ; GetMonData
IS_EGG      equ 76         ; MON_DATA_IS_EGG

.create OUT, 0x022378C0
.incbin IN

; ---------------------------------------------------------------------------
; BtlCmd_CalcExpGain, after `totalExp = baseExp * level / 7` (r0, u16).
; Register state here: r5 = BattleContext, [sp,#0] = Exp. Share holders,
; [sp,#4] = participants still standing, r4 free (callee-saved).
; Writes ctx->gainedExp (+0x9C) and ctx->partyGainedExp (+0xA0), then joins
; the function epilogue at 0x0223E80E. Everything from 0x0223E808 on (the
; non-enemy exit, the epilogue and the literal pool earlier code still uses)
; is left alone.
.org 0x0223E79C
    ldr     r1, =MULTIPLIER
    mul     r0, r1
    mov     r1, #100
    blx     DIV
    add     r4, r0, #0                  ; r4 = scaled total
.if GLOBAL == 1
    ; Participants split the full amount, everyone else gets half of it.
    ldr     r1, [sp, #4]
    blx     DIV
    mov     r1, #0x9C
    bl      clamp_store
    lsr     r0, r4, #1
    mov     r1, #0xA0
    bl      clamp_store
    b       0x0223E80E
.else
    ; Vanilla split, on the scaled total.
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

; ctx[r1] = max(r0, 1), like vanilla's "if (x == 0) x = 1".
clamp_store:
    cmp     r0, #0
    bne     @@store
    mov     r0, #1
@@store:
    str     r0, [r5, r1]
    bx      lr
.pool
; 0x0223E808 (the non-enemy exit) is still a live branch target.
.if org() > 0x0223E808
    .error "CalcExpGain patch overflows into vanilla code still in use"
.endif

.if GLOBAL == 1
; ---------------------------------------------------------------------------
; Task_GetExp, party slot scan: a slot qualifies when it holds an Exp. Share
; or took part. Globally, every slot qualifies (fainted mons and Eggs are
; filtered out further down).
.org 0x022458F4
    b       0x0224591A                  ; was: beq 0x0224591A

; Task_GetExp, the per-mon amount. Replaces 50 bytes, from the participant
; test to the Exp. Share add (0x02245A36-0x02245A67). r5 = party slot,
; r6 = Pokemon, [sp,#0x24] = BattleContext (stored at 0x02245A34),
; [sp,#0x44] = fainted battler's side, [sp,#0x38] = amount, already 0.
; HP > 0 and level < 100 were checked just before.
.org 0x02245A36
    add     r0, r5, #0
    bl      MASK_OF
    ldr     r1, [sp, #0x44]
    lsl     r2, r1, #2
    ldr     r1, [sp, #0x24]
    add     r2, r1, r2
    add     r2, #0xA4
    ldr     r2, [r2]                    ; ctx->unk_A4[side], participant mask
    tst     r0, r2
    beq     @@not_participant
    mov     r2, #0x9C                   ; gainedExp
    b       @@load
@@not_participant:
    add     r0, r6, #0
    mov     r1, #IS_EGG
    mov     r2, #0
    bl      GET_MON
    cmp     r0, #0
    bne     0x02245B3E                  ; Egg: same exit as a fainted mon (no Exp., no EVs)
    ldr     r1, [sp, #0x24]
    mov     r2, #0xA0                   ; partyGainedExp
@@load:
    ldr     r0, [r1, r2]
    str     r0, [sp, #0x38]
    b       0x02245A68                  ; on to the Lucky Egg check
.if org() != 0x02245A68
    .error "Task_GetExp patch must be exactly 50 bytes"
.endif
.endif

.close
