-- Reachability logic, a Lua port of regions.py/rules.py/locations.py.
-- DATA comes from scripts/data.lua (generated). The whole graph is solved
-- once per state change and cached: PopTracker evaluates every section's
-- rule after each change, so each call below is a table lookup.

OPTIONS = {
    soulsilver = false,
    johto_only = false,
    magnet_train = true,
    hidden_items_require_dowsing_machine = false,
    origin = "new_bark",
}

local cache = nil

function invalidate_logic()
    cache = nil
end

local function has(code)
    local obj = Tracker:FindObjectForCode(code)
    if obj == nil then
        return false
    end
    if obj.Active ~= nil then
        return obj.Active
    end
    return (obj.AcquiredCount or 0) > 0
end

local function region_of(entry)
    if OPTIONS.soulsilver and entry.ss_region then
        return entry.ss_region
    end
    return entry.region
end

local function excluded(region)
    if not OPTIONS.johto_only then
        return false
    end
    if OPTIONS.soulsilver then
        return DATA.johto_only_excluded_ss[region] == true
    end
    return DATA.johto_only_excluded_hg[region] == true
end

local function rule_passes(rule, events)
    for _, code in ipairs(rule.items) do
        if not has(code) then
            return false
        end
    end
    for _, badge in ipairs(rule.badges) do
        if not has("badge_" .. badge) then
            return false
        end
    end
    for _, event in ipairs(rule.events) do
        local skip = OPTIONS.magnet_train and event == "power_plant_restored"
        if not skip and not events[event] then
            return false
        end
    end
    return true
end

local function solve()
    local reachable = {}
    local events = {}
    local origin = OPTIONS.origin
    if excluded(origin) or DATA.regions[origin] == nil then
        origin = "new_bark"
    end
    reachable[origin] = true
    local changed = true
    while changed do
        changed = false
        local queue = {}
        for region, _ in pairs(reachable) do
            queue[#queue + 1] = region
        end
        local head = 1
        while head <= #queue do
            local src = queue[head]
            head = head + 1
            for _, dst in ipairs(DATA.regions[src] or {}) do
                if not reachable[dst] and DATA.regions[dst] ~= nil and not excluded(dst) then
                    local rule = DATA.exit_rules[src .. ">" .. dst]
                    if rule == nil or rule_passes(rule, events) then
                        reachable[dst] = true
                        queue[#queue + 1] = dst
                        changed = true
                    end
                end
            end
        end
        for name, entry in pairs(DATA.events) do
            if not events[name] and reachable[region_of(entry)] then
                events[name] = true
                changed = true
            end
        end
    end
    return { reachable = reachable, events = events }
end

local function state()
    if cache == nil then
        cache = solve()
    end
    return cache
end

function can_reach(region)
    return state().reachable[region] == true
end

function has_event(name)
    return state().events[name] == true
end

-- Section access rule: "$loc|<location key>". Mirrors create_locations'
-- rule precedence (one extra rule at most, first match wins).
function loc(key)
    local entry = DATA.locations[key]
    if entry == nil then
        return false
    end
    local s = state()
    if not s.reachable[region_of(entry)] then
        return false
    end
    if entry.type == "hidden_item" and OPTIONS.hidden_items_require_dowsing_machine then
        return has("dowsing_mchn")
    end
    if entry.items then
        for _, code in ipairs(entry.items) do
            if not has(code) then
                return false
            end
        end
        return true
    end
    if entry.regions then
        for _, region in ipairs(entry.regions) do
            if not s.reachable[region] then
                return false
            end
        end
        return true
    end
    if entry.events then
        for _, event in ipairs(entry.events) do
            if not s.events[event] then
                return false
            end
        end
        return true
    end
    if entry.power_plant and not OPTIONS.magnet_train then
        return s.events["power_plant_restored"] == true
    end
    return true
end

-- Dexsanity: which species exist and where they live is seed data the pack
-- does not have, so these checks are always shown as available.
function dex()
    return true
end

ScriptHost:AddWatchForCode("hgss_logic_invalidate", "*", invalidate_logic)
