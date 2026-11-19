local function set_toggle(code, value)
    local obj = Tracker:FindObjectForCode(code)
    if obj ~= nil then
        obj.Active = value
    end
end

local function each_section(location_id, action)
    for _, paths in ipairs({DATA.location_sections, DATA.plan_sections}) do
        local path = paths[location_id]
        if path ~= nil then
            local section = Tracker:FindObjectForCode(path)
            if section ~= nil then
                action(section)
            end
        end
    end
end

local function clear_sections()
    for _, paths in ipairs({DATA.location_sections, DATA.plan_sections}) do
        for _, path in pairs(paths) do
            local section = Tracker:FindObjectForCode(path)
            if section ~= nil then
                section.AvailableChestCount = section.ChestCount
            end
        end
    end
end

local follow_key = nil

local function follow_position(value)
    if FOLLOW == nil or type(value) ~= "table" or type(value.map) ~= "number" then
        return
    end
    local id = value.map
    local grid = FOLLOW.overworld
    if grid ~= nil and FOLLOW.is_overworld[id] and value.x ~= nil and value.z ~= nil then
        local cx, cz = math.floor(value.x / 32), math.floor(value.z / 32)
        if cx >= 0 and cz >= 0 and cx < grid.w and cz < grid.h then
            id = grid.ids[cz * grid.w + cx + 1]
        end
    end
    local code = FOLLOW.plan_of_id[id]
    local tabs = FOLLOW.tabs_by_lang[Tracker.ActiveVariantUID] or FOLLOW.tabs_by_lang["en"]
    local path = code and tabs and tabs[code]
    if path == nil then
        return
    end
    for _, title in ipairs(path) do
        Tracker:UiHint("ActivateTab", title)
    end
end

local function watch_position()
    if FOLLOW == nil or Archipelago.PlayerNumber == nil or Archipelago.PlayerNumber < 1 then
        return
    end
    local team = Archipelago.TeamNumber or 0
    follow_key = FOLLOW.key:gsub("{team}", tostring(team)):gsub("{slot}", tostring(Archipelago.PlayerNumber))
    Archipelago:SetNotify({follow_key})
    Archipelago:Get({follow_key})
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
    OPTIONS.counts = {
        elite_four_badges = slot_data and slot_data.elite_four_badges or nil,
        blue_kanto_leaders = slot_data and slot_data.blue_kanto_leaders or nil,
        red_badges = slot_data and slot_data.red_badges or nil,
    }
    OPTIONS.origin = "new_bark"
    if slot_data and slot_data.randomize_start_location and slot_data.starting_town then
        OPTIONS.origin = slot_data.starting_town
    end

    set_toggle("opt_dexsanity", options.dexsanity == 1 or options.dexsanity == true)
    set_toggle("opt_kanto", not OPTIONS.johto_only)
    set_toggle("opt_trainersanity", options.trainersanity == 1 or options.trainersanity == true)
    set_toggle("opt_legendarysanity", options.legendarysanity == 1 or options.legendarysanity == true)
    set_toggle("opt_shopsanity", options.shopsanity == 1 or options.shopsanity == true)
    for _, name in ipairs({"game_corner_prizes", "apricorn_trees", "bug_contest"}) do
        local value = options[name]
        if value == nil and slot_data then
            value = slot_data[name]
        end
        set_toggle("opt_" .. name, value == 1 or value == true)
    end
    set_toggle("opt_bicycle", options.randomize_bicycle == 1 or options.randomize_bicycle == true)
    set_toggle("opt_power_plant_tm", not OPTIONS.magnet_train)
    set_toggle("opt_soulsilver", OPTIONS.soulsilver)
    set_toggle("opt_heartgold", not OPTIONS.soulsilver)

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
        elseif kind == 4 then
            stage = 19
        elseif kind == 5 then
            stage = 20
        end
        goal.CurrentStage = stage
    end

    if Archipelago.MissingLocations and Archipelago.CheckedLocations then
        local present = {}
        for _, id in ipairs(Archipelago.MissingLocations) do present[id] = true end
        for _, id in ipairs(Archipelago.CheckedLocations) do present[id] = true end
        for id, _ in pairs(DATA.location_sections) do
            if not present[id] then
                each_section(id, function(section) section.AvailableChestCount = 0 end)
            end
        end
    end

    if Archipelago.CheckedLocations then
        for _, location_id in ipairs(Archipelago.CheckedLocations) do
            on_location(location_id)
        end
    end
    invalidate_logic()
    watch_position()
end

local function on_item(index, item_id, item_name, player_number)
    local code = DATA.item_codes[item_id]
    if code ~= nil then
        set_toggle(code, true)
    end
    invalidate_logic()
end

function on_location(location_id, location_name)
    each_section(location_id, function(section) section.AvailableChestCount = 0 end)
    local leader = DATA.leader_locations[location_id]
    if leader ~= nil then
        set_toggle(leader, true)
    end
end

local function on_position(key, value)
    if key == follow_key then
        follow_position(value)
    end
end

Archipelago:AddClearHandler("hgss_clear", on_clear)
Archipelago:AddItemHandler("hgss_item", on_item)
Archipelago:AddLocationHandler("hgss_location", on_location)
if Archipelago.AddSetReplyHandler then
    Archipelago:AddSetReplyHandler("hgss_follow", function(key, value, old) on_position(key, value) end)
end
if Archipelago.AddRetrievedHandler then
    Archipelago:AddRetrievedHandler("hgss_follow", on_position)
end
