-- Archipelago autotracking: items received light up, checked locations
-- are cleared (a gym badge check also lights up its leader), and the
-- seed's options and goal come from slot_data.

local function set_toggle(code, value)
    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil then
        obj.Active = value
    end
end

local function clear_sections()
    for _, path in pairs(DATA.location_sections) do
        local section = Tracker:FindObjectForCode(path)
        if section ~= nil then
            section.AvailableChestCount = section.ChestCount
        end
    end
end

local function on_clear(slot_data)
    clear_sections()
    for _, code in ipairs(DATA.tracked_items) do
        set_toggle(code, false)
    end
    for _, code in ipairs(DATA.leaders) do
        set_toggle(code, false)
    end

    local options = (slot_data and slot_data.options) or {}
    DEXSANITY_LOGIC = slot_data and slot_data.dexsanity_logic or nil
    OPTIONS.soulsilver = options.game_version == 1
    OPTIONS.johto_only = options.johto_only == 1 or options.johto_only == true
    OPTIONS.magnet_train = not (options.magnet_train == 0 or options.magnet_train == false)
    OPTIONS.hidden_items_require_dowsing_machine = options.hidden_items_require_dowsing_machine == 1
        or options.hidden_items_require_dowsing_machine == true
    OPTIONS.require_flash = options.require_flash == 1 or options.require_flash == true
    OPTIONS.origin = "new_bark"
    if slot_data and slot_data.randomize_start_location and slot_data.starting_town then
        OPTIONS.origin = slot_data.starting_town
    end

    set_toggle("opt_dexsanity", options.dexsanity == 1 or options.dexsanity == true)
    set_toggle("opt_kanto", not OPTIONS.johto_only)
    set_toggle("opt_trainersanity", options.trainersanity == 1 or options.trainersanity == true)
    set_toggle("opt_legendarysanity", options.legendarysanity == 1 or options.legendarysanity == true)
    set_toggle("opt_bicycle", options.randomize_bicycle == 1 or options.randomize_bicycle == true)
    set_toggle("opt_power_plant_tm", not OPTIONS.magnet_train)
    set_toggle("opt_soulsilver", OPTIONS.soulsilver)
    set_toggle("opt_heartgold", not OPTIONS.soulsilver)

    -- Goal banner stages: 0 unknown, 1 Elite Four, 2 Red, 2 + n for n badges.
    local goal = Tracker:FindObjectForCode("goal")
    if goal ~= nil then
        local stage = 0
        local kind = slot_data and slot_data.goal
        if kind == 0 then
            stage = 1
        elseif kind == 1 then
            stage = 2
        elseif kind == 2 then
            local count = tonumber(slot_data.goal_badge_count) or 16
            if OPTIONS.johto_only and count > 8 then
                count = 8
            end
            stage = 2 + math.max(1, math.min(16, count))
        end
        goal.CurrentStage = stage
    end

    -- Checks this seed does not have (Dexsanity species absent from its wild
    -- tables, trainers or species left out by trainersanity_count /
    -- dexsanity_count): neither missing nor checked on the server. Shown as
    -- done so they stay out of the way.
    if Archipelago.MissingLocations and Archipelago.CheckedLocations then
        local present = {}
        for _, id in ipairs(Archipelago.MissingLocations) do present[id] = true end
        for _, id in ipairs(Archipelago.CheckedLocations) do present[id] = true end
        for id, _ in pairs(DATA.location_sections) do
            if not present[id] then
                local section = Tracker:FindObjectForCode(DATA.location_sections[id])
                if section ~= nil then
                    section.AvailableChestCount = 0
                end
            end
        end
    end

    -- Already checked locations, when the server reports them.
    if Archipelago.CheckedLocations then
        for _, location_id in ipairs(Archipelago.CheckedLocations) do
            on_location(location_id)
        end
    end
    invalidate_logic()
end

local function on_item(index, item_id, item_name, player_number)
    local code = DATA.item_codes[item_id]
    if code ~= nil then
        set_toggle(code, true)
    end
    invalidate_logic()
end

function on_location(location_id, location_name)
    local path = DATA.location_sections[location_id]
    if path == nil then
        return
    end
    local section = Tracker:FindObjectForCode(path)
    if section ~= nil then
        section.AvailableChestCount = 0
    end
    local leader = DATA.leader_locations[location_id]
    if leader ~= nil then
        set_toggle(leader, true)
    end
end

Archipelago:AddClearHandler("hgss_clear", on_clear)
Archipelago:AddItemHandler("hgss_item", on_item)
Archipelago:AddLocationHandler("hgss_location", on_location)
