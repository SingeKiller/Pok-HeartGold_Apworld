-- diag_elms_lab_scene_var.lua
--
-- Live diagnostic: continuously reads and displays VAR_SCENE_ELMS_LAB
-- (Elm's Lab's own room-state variable, include/constants/vars.h:
-- VAR_SCENE_ELMS_LAB = 0x4108) on screen every frame, so you can watch
-- its real value change (or fail to change) as you walk around/interact
-- with the aide/try the exit door.
--
-- Uses the exact same dynamic address-resolution scan client.py's own
-- _locate_save_addresses does (see that function's docstring) --
-- SaveData.arrayHeaders[]'s own signature (5 consecutive SaveArrayHeader
-- records with id 0,1,2,3,4), verified against a plausible-looking Bag,
-- so this does not depend on any hardcoded/guessed RAM address.
--
-- Usage: BizHawk > Tools > Lua Console > Open Script > this file.
-- Leave it running; a small overlay in the top-left shows the live
-- value. Also prints to the Lua console whenever it changes.

local DOMAIN = "ARM9 System Bus"

local SAVE_ARRAY_HEADER_SIZE = 16
local SIGNATURE_CHUNK_COUNT = 5
local DYNAMIC_REGION_SIZE = 35 * 0x1000
local SAVE_COUNTER_SIZE = 4
local BAG_CHUNK_ID = 3
local FLAGS_CHUNK_ID = 4

local FLAGS_ARRAY_OFFSET = 736 -- NUM_VARS(0x170) * 2 -- vars[] byte size, flags[] follows immediately
local VAR_SCENE_ELMS_LAB_ID = 0x4108
local VAR_BASE = 0x4000
local VAR_SCENE_ELMS_LAB_INDEX = VAR_SCENE_ELMS_LAB_ID - VAR_BASE -- 0x108, index into vars[]

local SCAN_START = 0x02298000
local SCAN_LENGTH = 0x10000

memory.usememorydomain(DOMAIN)

-- `base` is the absolute address to check (either SCAN_START + a scan
-- offset while searching, or a previously-found array_headers_address
-- being revalidated -- see array_headers_still_valid below).
local function looks_like_array_headers(base)
    for chunk_id = 0, SIGNATURE_CHUNK_COUNT - 1 do
        local record_id = memory.read_s32_le(base + chunk_id * SAVE_ARRAY_HEADER_SIZE)
        if record_id ~= chunk_id then
            return false
        end
    end
    return true
end

-- Cheap (5 reads) re-check that a previously-found array_headers_address
-- is still valid, instead of trusting it forever -- a save reload/soft
-- reset can move it, the same address-drift client.py's own
-- _array_headers_still_valid guards against.
local function array_headers_still_valid(array_headers_address)
    return looks_like_array_headers(array_headers_address)
end

local function chunk_offset(array_headers_address, chunk_id)
    local record_address = array_headers_address + chunk_id * SAVE_ARRAY_HEADER_SIZE
    return memory.read_u32_le(record_address + 8) -- SaveArrayHeader.offset: int32 id, u32 size, u32 offset, u16 crc, u16 slot
end

local function bag_looks_plausible(bag_address)
    for i = 0, 7 do
        local item_id = memory.read_u16_le(bag_address + i * 4)
        local quantity = memory.read_u16_le(bag_address + i * 4 + 2)
        if item_id ~= 0 then
            if item_id > 536 or quantity > 999 then
                return false
            end
        end
    end
    return true
end

-- Returns (array_headers_address, vars_array_address), or nil on failure
-- -- both are cached by the caller and array_headers_address is cheaply
-- revalidated every frame, so a save reload doesn't leave a stale
-- vars_array_address silently displaying garbage.
local function find_addresses()
    local needed = SAVE_ARRAY_HEADER_SIZE * SIGNATURE_CHUNK_COUNT
    for offset = 0, SCAN_LENGTH - needed, 4 do
        local array_headers_address = SCAN_START + offset
        if looks_like_array_headers(array_headers_address) then
            local dynamic_region_base = array_headers_address - SAVE_COUNTER_SIZE - DYNAMIC_REGION_SIZE

            local bag_chunk_offset = chunk_offset(array_headers_address, BAG_CHUNK_ID)
            local bag_address = dynamic_region_base + bag_chunk_offset

            if bag_looks_plausible(bag_address) then
                local flags_chunk_offset = chunk_offset(array_headers_address, FLAGS_CHUNK_ID)
                -- flags_array_address (client.py's own) = dynamic_region_base + flags_chunk_offset + FLAGS_ARRAY_OFFSET
                -- vars[] sits right before flags[], i.e. at flags_array_address - FLAGS_ARRAY_OFFSET.
                local vars_array_address = dynamic_region_base + flags_chunk_offset
                return array_headers_address, vars_array_address
            end
        end
    end
    return nil, nil
end

local array_headers_address = nil
local vars_array_address = nil
local last_value = nil

while true do
    if array_headers_address ~= nil and not array_headers_still_valid(array_headers_address) then
        array_headers_address = nil
        vars_array_address = nil
    end

    if vars_array_address == nil then
        array_headers_address, vars_array_address = find_addresses()
    end

    if vars_array_address == nil then
        gui.text(10, 10, "VAR_SCENE_ELMS_LAB: save data not found yet...")
    else
        local address = vars_array_address + VAR_SCENE_ELMS_LAB_INDEX * 2
        local value = memory.read_u16_le(address)
        gui.text(10, 10, string.format("VAR_SCENE_ELMS_LAB = %d  (addr 0x%08X)", value, address))
        if value ~= last_value then
            console.log(string.format("[diag] VAR_SCENE_ELMS_LAB changed: %s -> %d", tostring(last_value), value))
            last_value = value
        end
    end

    emu.frameadvance()
end
