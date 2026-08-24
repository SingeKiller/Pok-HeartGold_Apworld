-- diag_rom_domain_writable.lua
--
-- Live diagnostic for the 2026-08-18 "Bug 3 revisited" investigation
-- (Player's House 1F front door staying permanently redirected to Elm's
-- Lab -- see rom/startlocation.py's own module docstring). That
-- investigation's remaining open question, which cannot be answered by
-- static code inspection alone (no BizHawk/melonDS source checkout is
-- available in this repo -- only the compiled EmuHawk distribution):
--
--   Does BizHawk's melonDS core mark its "ROM" memory domain as
--   writable, the same way it already is for other systems this
--   Archipelago fork ships clients for (e.g. worlds/cvcotm and
--   worlds/marioland2 both successfully memory.write_bytes_as_array
--   into their own "ROM" domain today)?
--
-- This project's own client.py already proves "ROM" domain *reads* work
-- for melonDS (validate_rom's id_code check at address 0x0C -- see
-- client.py). Writes are untested. This script performs a fully
-- reversible round-trip write test against a byte in the ROM header's
-- own documented-reserved region (file offset 0x240, deep inside the
-- 0xB0-byte block Nintendo's own header spec marks "Reserved" -- not the
-- title, not the game code, not anything the loader/BIOS reads), so
-- there is no risk to the running game regardless of the outcome: it
-- reads the byte, writes back the exact same value it just read (a
-- guaranteed no-op if the write succeeds), and reports pass/fail plus
-- the raw before/after bytes.
--
-- Usage: BizHawk > Tools > Lua Console > Open Script > this file, with
-- any HeartGold/SoulSilver ROM loaded (patched or vanilla, doesn't
-- matter for this test). Reads the console output once and exits (does
-- not loop). Copy/paste the console output back.

local DOMAIN = "ROM"
local TEST_OFFSET = 0x240 -- inside the header's own documented "Reserved" block (0x240-0x2F0)

local domain_list = memory.getmemorydomainlist()
console.log("[diag_rom] available memory domains:")
for i, name in ipairs(domain_list) do
    console.log(string.format("  [%d] %s", i, name))
end

local ok_usedomain = memory.usememorydomain(DOMAIN)
if not ok_usedomain then
    console.log(string.format("[diag_rom] FAIL: memory.usememorydomain(%q) returned false -- no domain by that exact name exists for this core.", DOMAIN))
    return
end

console.log(string.format("[diag_rom] domain %q selected OK. Size: %d bytes.", DOMAIN, memory.getmemorydomainsize(DOMAIN)))

local read_ok, original_byte = pcall(memory.read_u8, TEST_OFFSET, DOMAIN)
if not read_ok then
    console.log(string.format("[diag_rom] FAIL: could not read byte at offset 0x%X from domain %q: %s", TEST_OFFSET, DOMAIN, tostring(original_byte)))
    return
end
console.log(string.format("[diag_rom] read OK: byte at 0x%X = 0x%02X", TEST_OFFSET, original_byte))

local write_ok, write_err = pcall(memory.write_u8, TEST_OFFSET, original_byte, DOMAIN)
if not write_ok then
    console.log(string.format("[diag_rom] RESULT: domain %q is NOT writable (write threw: %s). Runtime ROM-domain revert of the house-exit door is NOT possible.", DOMAIN, tostring(write_err)))
    return
end

local reread_ok, reread_byte = pcall(memory.read_u8, TEST_OFFSET, DOMAIN)
if not reread_ok then
    console.log(string.format("[diag_rom] write call did not throw, but re-read failed: %s -- inconclusive, treat as NOT confirmed writable.", tostring(reread_byte)))
    return
end

if reread_byte == original_byte then
    console.log(string.format("[diag_rom] RESULT: write call succeeded and re-read matches (0x%02X). This is consistent with domain %q being writable, but a same-value write can't fully rule out a silent no-op -- run the follow-up probe below to be certain.", reread_byte, DOMAIN))
else
    console.log(string.format("[diag_rom] RESULT: write call succeeded but re-read (0x%02X) does NOT match what was written (0x%02X) -- domain is misbehaving, treat as NOT safely writable.", reread_byte, original_byte))
    return
end

-- Follow-up probe: write a DIFFERENT value (bitwise-NOT of the original),
-- confirm it actually changed, then immediately restore the original --
-- this is the only way to be sure the previous same-value write wasn't a
-- silent no-op that happened to "match" by doing nothing.
local probe_value = (~original_byte) & 0xFF
local probe_write_ok, probe_write_err = pcall(memory.write_u8, TEST_OFFSET, probe_value, DOMAIN)
if not probe_write_ok then
    console.log(string.format("[diag_rom] follow-up probe write threw: %s -- treat as NOT confirmed writable.", tostring(probe_write_err)))
    return
end
local probe_read_ok, probe_read_byte = pcall(memory.read_u8, TEST_OFFSET, DOMAIN)
-- Always restore the original byte before reporting, regardless of probe outcome.
pcall(memory.write_u8, TEST_OFFSET, original_byte, DOMAIN)
local restore_check_ok, restore_check_byte = pcall(memory.read_u8, TEST_OFFSET, DOMAIN)

if probe_read_ok and probe_read_byte == probe_value then
    console.log(string.format("[diag_rom] CONFIRMED WRITABLE: probe value 0x%02X was actually stored and read back at 0x%X.", probe_value, TEST_OFFSET))
else
    console.log(string.format("[diag_rom] NOT WRITABLE (or write is silently ignored): probe value 0x%02X was NOT read back (got %s instead).",
        probe_value, probe_read_ok and string.format("0x%02X", probe_read_byte) or tostring(probe_read_byte)))
end

if restore_check_ok and restore_check_byte == original_byte then
    console.log(string.format("[diag_rom] original byte 0x%02X restored OK at 0x%X.", original_byte, TEST_OFFSET))
else
    console.log(string.format("[diag_rom] WARNING: could not confirm original byte was restored at 0x%X (read back %s, expected 0x%02X).",
        TEST_OFFSET, restore_check_ok and string.format("0x%02X", restore_check_byte) or tostring(restore_check_byte), original_byte))
end
