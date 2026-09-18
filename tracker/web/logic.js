// Reachability logic for the web tracker, a JavaScript port of
// tracker/scripts/logic.lua (itself a port of regions.py/rules.py/
// locations.py). DATA is the generated data (tracker_gen.py); `has(code)`
// tells whether an item is owned. The graph is solved once per state.

function createLogic(DATA, has, options) {
  function regionOf(entry) {
    return options.soulsilver && entry.ss_region ? entry.ss_region : entry.region;
  }

  function excluded(region) {
    if (!options.johto_only) return false;
    const table = options.soulsilver ? DATA.johto_only_excluded_ss : DATA.johto_only_excluded_hg;
    return table[region] === true;
  }

  function rulePasses(rule, events) {
    for (const code of rule.items) if (!has(code)) return false;
    for (const badge of rule.badges) if (!has("badge_" + badge)) return false;
    for (const event of rule.events) {
      const skip = options.magnet_train && event === "power_plant_restored";
      if (!skip && !events[event]) return false;
    }
    return true;
  }

  function solve() {
    const reachable = {};
    const events = {};
    let origin = options.origin || "new_bark";
    if (excluded(origin) || DATA.regions[origin] === undefined) origin = "new_bark";
    reachable[origin] = true;
    let changed = true;
    while (changed) {
      changed = false;
      const queue = Object.keys(reachable);
      for (let head = 0; head < queue.length; head++) {
        const src = queue[head];
        for (const dst of DATA.regions[src] || []) {
          if (reachable[dst] || DATA.regions[dst] === undefined || excluded(dst)) continue;
          const rule = DATA.exit_rules[src + ">" + dst];
          if (rule === undefined || rulePasses(rule, events)) {
            reachable[dst] = true;
            queue.push(dst);
            changed = true;
          }
        }
      }
      for (const [name, entry] of Object.entries(DATA.events)) {
        if (!events[name] && reachable[regionOf(entry)]) {
          events[name] = true;
          changed = true;
        }
      }
    }
    return { reachable, events };
  }

  const state = solve();

  // Mirrors create_locations' rule precedence (one extra rule at most).
  function loc(key) {
    const entry = DATA.locations[key];
    if (entry === undefined) return false;
    if (!state.reachable[regionOf(entry)]) return false;
    if (entry.type === "hidden_item" && options.hidden_items_require_dowsing_machine) {
      return has("dowsing_mchn");
    }
    if (entry.items) return entry.items.every((code) => has(code));
    if (entry.regions) return entry.regions.every((region) => state.reachable[region]);
    if (entry.events) return entry.events.every((event) => state.events[event]);
    if (entry.power_plant && !options.magnet_train) return state.events["power_plant_restored"] === true;
    return true;
  }

  return { loc, state };
}

if (typeof module !== "undefined") module.exports = { createLogic };
