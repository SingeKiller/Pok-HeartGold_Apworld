; patches/ground_item_hook.s
;
; Task C14 -- ground-item ("ground_item" location type) check mechanism,
; proof of concept. Read docs/architecture.md, "## C14 -- Ground item check
; mechanism (proof of concept)" FIRST -- this file only implements the part
; of that design that could actually be built and safely applied in this
; task's session; the section above explains in detail what is genuinely
; proven vs. still blocked, and why.
;
; This file assembles two small, self-contained ARM functions that
; implement this project's "AP protocol" struct (documented below and in
; docs/architecture.md) in RAM:
;
;   HeartGoldAP_Init                    -- writes the struct's magic/version
;                                           header and zeroes the rest.
;   HeartGoldAP_RecordGroundItemCheck   -- r0 = the Archipelago location id
;                                           (16-bit) of a ground-item check
;                                           that was just triggered; records
;                                           it into the protocol struct for
;                                           the (future) BizHawk client to
;                                           read.
;
; Neither function is called by anything yet: the real in-game hook point
; (patching `ScrCmd_GiveItem`'s dispatch slot in `gScriptCmdTable`, see
; docs/architecture.md) needs a ROM address this task could not safely
; determine (no symbol/map file ships with the decomp, and an automated
; signature-scan of the real retail ROM found no reliable candidate -- see
; docs/architecture.md for the full account). This patch is therefore
; scaffolding: it proves the armips + patch_gen.py + rom/ pipeline can
; assemble real ARM code, append it to the ARM9 binary without touching the
; DS "secure area", and leave the resulting ROM structurally valid -- ready
; to be wired to a real hook call site the moment one is known (either from
; a future match-build of the decomp, or from manual reverse engineering
; with proper disassembler tooling).
;
; -- AP protocol struct (also documented in docs/architecture.md) ----------
;
; Fixed location: __PROTOCOL_ADDRESS__ (EWRAM scratch space near the very
; top of the DS's 4 MiB EWRAM region, 0x02000000-0x023FFFFF -- the same
; general convention ljtpetersen/platinum_archipelago uses for its own
; `AP_STRUCT_PTR_ADDRESS` near-top-of-EWRAM marker; see docs/architecture.md
; for why this is "conventionally safe" rather than exhaustively proven
; unused for HGSS specifically).
;
;   offset  size  field
;   0x00    4     magic       ASCII "HGAP" (little-endian word 0x50414748)
;   0x04    2     version     protocol version, currently 1
;   0x06    2     reserved0   always 0
;   0x08    4     last_check_sent   AP location id of the most recent
;                                   ground-item check triggered (0 = none)
;   0x0C    4     check_sent_seq    incremented every time last_check_sent
;                                   is written; lets a client tell a new
;                                   event apart from re-reading the same one
;   0x10    2     local_item_id     native HG/SS item id to actually grant
;                                   for the pending pickup if it's a local
;                                   item; 0 if not applicable/remote
;   0x12    2     is_remote         1 if the pending pickup belongs to
;                                   another player's world; 0 otherwise
;   -> total size: 0x14 (20) bytes
;
; This code targets ARM (32-bit) mode; the appended tail of the ARM9 binary
; it will live in is plain code space (not a THUMB-only region), matching
; how the rest of this project's decomp reference marks most of its own ARM9
; functions as ARM by default (THUMB is opted into per-file, e.g.
; asm/overlay_38_thumb.s, asm/overlay_93_thumb_1.s).

.nds
.create "__OUTPUT_PATH__", __HOOK_LOAD_ADDRESS__

.arm

AP_PROTOCOL_ADDRESS equ __PROTOCOL_ADDRESS__
AP_PROTOCOL_MAGIC   equ 0x50414748 ; "HGAP", little-endian word

HeartGoldAP_Init:
    push {r0, r1, lr}
    ldr r0, =AP_PROTOCOL_ADDRESS
    ldr r1, =AP_PROTOCOL_MAGIC
    str r1, [r0, #0x00]        ; magic
    mov r1, #1
    strh r1, [r0, #0x04]       ; version = 1
    mov r1, #0
    strh r1, [r0, #0x06]       ; reserved0 = 0
    str r1, [r0, #0x08]        ; last_check_sent = 0
    str r1, [r0, #0x0C]        ; check_sent_seq = 0
    strh r1, [r0, #0x10]       ; local_item_id = 0
    strh r1, [r0, #0x12]       ; is_remote = 0
    pop {r0, r1, lr}
    bx lr

; r0 (in): Archipelago location id of the ground-item check just triggered.
; Not yet called from anywhere -- see this file's header comment.
HeartGoldAP_RecordGroundItemCheck:
    push {r1, r2, lr}
    ldr r1, =AP_PROTOCOL_ADDRESS
    str r0, [r1, #0x08]        ; last_check_sent = r0
    ldr r2, [r1, #0x0C]
    add r2, r2, #1
    str r2, [r1, #0x0C]        ; check_sent_seq += 1
    pop {r1, r2, lr}
    bx lr

.pool
.close
