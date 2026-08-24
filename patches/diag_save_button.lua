-- diag_save_button.lua
--
-- Diagnostic script for a real bug report (2026-08-17): with
-- randomize_start_location on, pressing Save from the pause menu does
-- nothing at all -- no save prompt opens. Traced as far as possible via
-- decomp alone: Task_StartMenu_HandleSelection_Save calls
-- ov01_021F6A9C(fieldSystem, 1, NULL), an overlay-01 function not yet
-- decompiled to C. Its ASM shows it reads a SysTask pointer at
-- fieldSystem+0xD8, gets that task's data block, and only does anything
-- if data[1] == 1 (silently no-ops otherwise) -- exactly matching "Save
-- does nothing".
--
-- This breaks on the function's own real, decomp-confirmed entry address
-- (0x021F6A9C, "thumb_func_start ov01_021F6A9C" in
-- asm/overlay_01_021F6830.s) and reads r0 (fieldSystem, ARM calling
-- convention) directly from the CPU registers at that exact moment -- no
-- guessed pointer needed, same technique already used successfully this
-- project (shop_menu.c's ov03_02257F24 investigation).
--
-- How to use: load this script in BizHawk (Tools > Lua Console > Script >
-- Open Script) BEFORE opening the pause menu, get in-game on a
-- randomize_start_location save, open the pause menu, and select Save.
-- Copy/paste whatever prints to the console back.

local BREAK_ADDRESS = 0x021F6A9C

local function on_break()
    local regs = emu.getregisters()
    local fieldSystem = regs["ARM9 r0"]
    if fieldSystem == nil then
        console.log("[diag_save] could not read ARM9 r0")
        return
    end

    local task_ptr = memory.read_u32_le(fieldSystem + 0xD8, "ARM9 System Bus")
    console.log(string.format("[diag_save] ov01_021F6A9C hit: fieldSystem=%08X task_ptr=%08X", fieldSystem, task_ptr))

    if task_ptr == 0 then
        console.log("[diag_save] task_ptr is NULL -- the task this function needs doesn't exist yet.")
        return
    end

    -- SysTask_GetData's own return is task_ptr + a fixed header size this
    -- project hasn't had to derive before -- print a small window of raw
    -- bytes right after task_ptr so the real header size/data[1] can be
    -- read back by eye, rather than guessing the offset here.
    local dump = {}
    for i = 0, 0x1F do
        local ok, byte = pcall(memory.read_u8, task_ptr + i, "ARM9 System Bus")
        dump[#dump + 1] = ok and string.format("%02X", byte) or "??"
    end
    console.log("[diag_save] bytes at task_ptr..+0x1F: " .. table.concat(dump, " "))
end

event.onmemoryexecute(on_break, BREAK_ADDRESS, "ARM9 System Bus")
console.log("diag_save_button.lua loaded -- open the pause menu and select Save now.")

-- Keep the script's own Lua coroutine alive -- BizHawk's event callbacks
-- are believed to persist once registered, but this costs nothing and
-- removes any doubt (code review, 2026-08-17).
while true do
    emu.frameadvance()
end
