ScriptHost:LoadScript("scripts/data.lua")
ScriptHost:LoadScript("scripts/logic.lua")

DATA.location_sections = DATA.location_sections_by_lang[Tracker.ActiveVariantUID]
    or DATA.location_sections_by_lang["en"]

Tracker:AddItems("items/items.json")
Tracker:AddMaps("maps/maps.json")
Tracker:AddLocations("locations/locations.json")
Tracker:AddLayouts("layouts/tracker.json")
Tracker:AddLayouts("layouts/broadcast.json")

if PopVersion and Archipelago then
    ScriptHost:LoadScript("scripts/autotracking.lua")
    ScriptHost:LoadScript("scripts/spoiler.lua")
end
