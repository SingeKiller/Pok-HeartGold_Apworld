ScriptHost:LoadScript("scripts/data.lua")
ScriptHost:LoadScript("scripts/logic.lua")

DATA.location_sections = DATA.location_sections_by_lang[Tracker.ActiveVariantUID]
    or DATA.location_sections_by_lang["en"]
DATA.plan_sections = DATA.plan_sections_by_lang and (DATA.plan_sections_by_lang[Tracker.ActiveVariantUID]
    or DATA.plan_sections_by_lang["en"]) or {}

Tracker:AddItems("items/items.json")
Tracker:AddMaps("maps/maps.json")
Tracker:AddLocations("locations/locations.json")
Tracker:AddLayouts("layouts/tracker.json")
Tracker:AddLayouts("layouts/broadcast.json")

if PopVersion and Archipelago then
    ScriptHost:LoadScript("scripts/follow.lua")
    ScriptHost:LoadScript("scripts/autotracking.lua")
    ScriptHost:LoadScript("scripts/spoiler.lua")
end
