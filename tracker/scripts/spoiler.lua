-- Loaded in every variant (flag aphintgame, PopTracker 0.26.2+).
-- On connect, every location of this slot is scouted WITHOUT creating hints
-- (LocationScouts with sendAsHint = 0). Each check carries a "?" item; click
-- it to show what is there, click again to hide it.

SCOUTED = {}

local function overlay(obj, text)
    if obj.SetOverlay then
        obj:SetOverlay(text)
    end
end

local function short(text)
    if #text > 14 then
        return string.sub(text, 1, 13) .. "."
    end
    return text
end

local function owner_name(slot)
    if slot == Archipelago.PlayerNumber then
        return nil
    end
    if Archipelago.GetPlayerAlias then
        local ok, alias = pcall(function() return Archipelago:GetPlayerAlias(slot) end)
        if ok and alias then
            return alias
        end
    end
    return "P" .. tostring(slot)
end

local function show(location_id)
    local obj = Tracker:FindObjectForCode("reveal_" .. location_id)
    if obj == nil then
        return
    end
    local info = SCOUTED[location_id]
    if info == nil then
        overlay(obj, "...")
        return
    end
    local text = info.item_name
    if info.owner then
        text = text .. " @" .. info.owner
    end
    overlay(obj, short(text))
end

local function on_scout(location_id, location_name, item_id, item_name, item_player)
    SCOUTED[location_id] = { item_name = item_name, owner = owner_name(item_player) }
    local obj = Tracker:FindObjectForCode("reveal_" .. location_id)
    if obj ~= nil and obj.Active then
        show(location_id)
    end
end

local function on_reveal_toggled(code)
    if string.sub(code, 1, 7) ~= "reveal_" then
        return
    end
    local location_id = tonumber(string.sub(code, 8))
    local obj = Tracker:FindObjectForCode(code)
    if obj == nil or location_id == nil then
        return
    end
    if obj.Active then
        show(location_id)
    else
        overlay(obj, "")
    end
end

local function on_clear_spoiler(slot_data)
    SCOUTED = {}
    local ids = {}
    for location_id, _ in pairs(DATA.location_sections) do
        local obj = Tracker:FindObjectForCode("reveal_" .. location_id)
        if obj ~= nil then
            obj.Active = false
            overlay(obj, "")
        end
        ids[#ids + 1] = location_id
    end
    -- Only locations that exist in this seed can be scouted.
    if Archipelago.MissingLocations and Archipelago.CheckedLocations then
        local present = {}
        for _, id in ipairs(Archipelago.MissingLocations) do present[id] = true end
        for _, id in ipairs(Archipelago.CheckedLocations) do present[id] = true end
        local filtered = {}
        for _, id in ipairs(ids) do
            if present[id] then
                filtered[#filtered + 1] = id
            end
        end
        ids = filtered
    end
    if Archipelago.LocationScouts and #ids > 0 then
        Archipelago:LocationScouts(ids, 0)
    end
end

Archipelago:AddClearHandler("hgss_spoiler_clear", on_clear_spoiler)
Archipelago:AddScoutHandler("hgss_spoiler_scout", on_scout)
ScriptHost:AddWatchForCode("hgss_spoiler_reveal", "*", on_reveal_toggled)
