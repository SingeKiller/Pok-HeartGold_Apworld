# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.9.0-hotfix] - 2026-09-17 (tag v0.2.4-hotfix, same world_version, compatible with existing 0.9.0 seeds)

### Fixed
- **Cliff Edge Gate no longer requires Rock Climb.** The gate between
  Cianwood and Route 47 is a plain walk-through (enter, go up the stairs,
  exit on Route 47); only the Secret Potion is needed, as in vanilla. The
  logic used to also require HM08 Rock Climb and the Earth Badge, which
  locked Route 47, Route 48 and their checks behind the late game for no
  reason.
- **Dead seeds through the Magnet Train.** The train needs the Kanto Power
  Plant repaired as well as the Pass (a policeman blocks both stations
  until then), which the logic ignored: it could expect Kanto to be
  reachable early when it was not, and put required items there (a real
  seed placed HM03 Surf on Route 12). The `magnet_train` option now does
  what it promises:
  - on (default), the Kanto Power Plant is considered repaired from the
    very start of your game. The Magnet Train can be used as soon as you
    have the Pass, the Machine Part quest is skipped (Misty and the
    Cerulean Gym Rocket still play out as usual), and the Power Plant
    manager's TM57, only handed over at the end of that quest, is removed
    from the locations. The Route 5 and 6 Underground Path gates and the
    Lavender radio station are open from the start too, as after a real
    repair. Requires the matching client;
  - off, the train only counts once the Power Plant has really been
    repaired, which needs you to be in Kanto already.
- **Whiteout sent you back to New Bark with `randomize_start_location`.**
  Losing a battle before visiting any Pokemon Center woke you up at home
  in New Bark, sometimes with no way back. The client now sets your
  whiteout point to your starting town's Pokemon Center, once per save.
  After your first Pokemon Center visit the game takes over as usual.
- **Finishing the game was never reported to the server**, so "release on
  goal" (and every other goal-based server setting) never triggered for
  HeartGold/SoulSilver players. The client now sends the goal once it is
  reached: Hall of Fame entry for `elite_four`, Red beaten for
  `champion_red`, and the required number of received badges for
  `n_badges`. Client-side fix: it applies to games already in progress
  after simply updating the apworld, no new patch needed.
- **Vermilion Gym could become impossible.** Receiving the Thunder Badge
  before beating Lt. Surge made the game treat the trash can puzzle as
  already solved: every can was empty and an invisible wall blocked the
  way to Surge. The client now hides the Thunder Badge while you are in
  Vermilion City or its gym and Surge is not beaten yet, and gives it back
  as soon as you leave or win. Client-side fix: it applies to games already
  in progress after simply updating the apworld. If you are already stuck
  inside the gym, walk out and back in.
- **The Pass trade chain could break.** The Pokemon Fan Club chairman
  refused to hand over the Lost Item if you already held a Pass (which can
  arrive from the multiworld at any time), and the Copycat in Saffron could
  stop offering her trade after your first talk with her. Both now only
  check whether the trade has already happened. ROM fix: games in progress
  get it by re-opening their .apheartgold file with this version (your save
  is kept).
- **The Copycat's Pass could be expected too early with `magnet_train`
  off.** The Lost Item she wants only appears once the Kanto Power Plant is
  repaired; the logic now requires that repair for her location.
- **The Bell Tower and Lugia monks could block you with the wing in your
  bag.** Neither monk checks your bag: each one only steps aside once the
  NPC who hands that wing over in the game has done so. A Rainbow Wing or
  Silver Wing received from the multiworld therefore opened nothing, while
  the logic counted on it. The logic now requires talking to that NPC
  instead, and knows where he stands in each version: in HeartGold, the
  Radio Tower director (Goldenrod, observation deck) gives the Rainbow Wing
  and the old man in Pewter City gives the Silver Wing; in SoulSilver it is
  the other way round. Both wings are now merely useful items. With
  `johto_only`, whatever the Pewter-side wing opens (Bell Tower 2F and up
  in SoulSilver, Lugia's chamber in HeartGold) is removed from the
  locations. New seeds only.
  **Games already in progress:** go and talk to the NPC who hands out the
  wing in your version (listed above), even if you already hold that wing.
  He gives you his item for the multiworld, and the monk lets you through
  afterwards.
- **HeartGold: the Pewter City old man always gave a real Silver Wing.**
  His script was never patched, so whatever the seed had placed on that
  location was never handed over there. ROM fix: games in progress get it
  by re-opening their .apheartgold file with this version.

## [0.9.0] - 2026-08-24

### Added
- **New option `magnet_train`** (on by default). The Magnet Train between
  Goldenrod and Saffron is the only way into Kanto before the Pokemon
  League, now that the S.S. Aqua's sailor is correctly modeled as refusing
  to sail until the Elite Four and the Champion are beaten. On, the Magnet
  Train Pass alone opens the ride and Kanto can be visited early, exactly
  as in the game. Off, the ride is only counted once you have beaten the
  Elite Four, so nothing you need can be hidden in Kanto before then; you
  can still board the train as soon as you find the Pass, the seed simply
  will not count on it. With the option off the Pass no longer unlocks
  anything by itself and is placed as a merely useful item rather than a
  progression one.
- **New `balanced` mode for `randomize_moves`.** Power and Accuracy are
  drawn together from weighted tiers instead of independently, so a
  200-power move never comes with coin-flip accuracy. Four tiers, from
  reliable (55 to 95 power at 100 accuracy, half the draws) to devastating
  (210 to 250 power at 75 to 85 accuracy, one draw in twenty), with
  accuracy never below 75. Status moves keep 0 power, one-hit-KO moves keep
  their vanilla 30 accuracy, and never-miss moves stay never-miss. PP is
  drawn exactly as `full_random` draws it.

### Changed
- **`randomize_start_location` no longer touches your front door.** Until
  now the option rewired the door of your house so that leaving your
  bedroom put you straight into Elm's Lab. That shortcut was permanent:
  players who came home much later found their own front door still
  leading into the lab. It is gone, and the opening is vanilla from start
  to finish again. You wake up at home, talk to Mom, step outside into New
  Bark Town and walk the twenty or so steps to Elm's Lab yourself. Nothing
  can be skipped by accident either way, since the neighbour still refuses
  to let you leave town before you own a Pokemon. Only the lab's exit door
  is redirected now, which is the point of the option, and that one
  redirection is undone as soon as you have used it (see below).

### Removed
- **`lake_of_rage` as a `starting_town` (breaking change to existing YAML
  files).** The Lake of Rage map has exactly two doors, and both of them are
  on the bank ringed by the water. Reading the game's own collision data
  settles it: the path down from Route 43 opens onto the other shore, the
  one with Pryce and the hidden Full Restore, so there is no door on the map
  that can drop you somewhere you are able to walk away from. A player who
  started there was stranded, and moving the arrival point to the map's only
  other door would have stranded them just the same. Rather than ship a
  start that has to be guessed at, the town is no longer offered. The other
  nine remain. A YAML that still lists `lake_of_rage` under `starting_town`
  will fail to generate: pick another town, or set the option to `random`.

### Fixed
- **Elm's Lab kept sending you to your starting town forever.** With
  `randomize_start_location` on, the lab's exit door was redirected for the
  whole save, so coming home to New Bark later in the run and stepping into
  the lab meant being shipped back across Johto on the way out. The client
  now puts that door back to normal as soon as you have actually used it,
  which it detects by waiting until you are standing somewhere that is
  neither New Bark nor the lab itself, with a starter in hand. Later visits
  behave exactly like vanilla. The fix is applied to the running game
  rather than to the patched ROM file, so it is re-applied each time you
  relaunch BizHawk; keep the client connected and you will never notice.

- **The Magnet Train did not exist as far as the logic was concerned.**
  Each city's station has two versions of its platform map, one with the
  train and one without, and the staircase from the ground floor landed on
  the empty one. The rail link therefore hung off two rooms nothing could
  reach, and the Magnet Train Pass gated nothing. The two versions of each
  platform are now one place, the ride is a real crossing between Johto and
  Kanto again, and it requires the Pass on both ends, as both station
  attendants do.
- **The Secret Potion opened nothing.** Cianwood and Route 47 were joined
  by a connection that does not exist in the game, which walked around the
  Cliff Edge Gate in a single step. With it gone, Route 47, Route 48, the
  Safari Zone approach and the Embedded Tower are genuinely behind the
  Secret Potion.
- **The Radio Tower's shuttered door ignored the Card Key.** The whole
  upper half of the Goldenrod Radio Tower, its elevator and its observation
  deck included, was reachable without it.
- **Twenty-one connections that do not exist in the game were removed.**
  All of them had the same shape: two places joined both by a gatehouse and
  by a direct link the map does not have, so the gatehouse could always be
  walked around. Every one was checked against the game's own maps before
  being removed. The list covers Saffron's four approaches (Routes 5, 6, 7
  and 8), Ecruteak and Routes 38 and 42, Goldenrod and Route 35, Mahogany
  and Route 43, Fuchsia and Routes 15, 18 and 19, Viridian and Route 1, the
  two halves of Route 2 and of Route 16, Route 29 and Route 46, the Ruins
  of Alph and Routes 32 and 36, Violet and Routes 31 and 36, Routes 11 and
  12, and Cianwood and Route 47. Together with the two removed in 0.8.0
  (Azalea and Route 34, Routes 32 and 33), that is every connection of this
  kind the graph had. None of them opened anything on their own, but each
  would have silently cancelled any requirement placed on the building it
  bypassed, which is exactly how the Secret Potion, the Ilex Forest Cut
  check and the Cycling Road Bicycle check ended up doing nothing.
- **Kanto was one key item away from the start of the game.** The Olivine
  sailor checks that the game has been cleared before he ever looks at your
  S.S. Ticket, so the ferry does not sail until the Elite Four and the
  Champion are beaten. The Route 22 gate's policeman is modeled the same
  way, otherwise the ferry would simply have been walked around through
  Viridian.
- **Several key items and badges gated nothing.** The Bell Tower above the
  first floor now needs the Rainbow Wing and the approach to it needs the
  Fog Badge, Lugia's chamber needs the Silver Wing, the Goldenrod Tunnel's
  basement needs the Basement Key, Cerulean Cave needs the Earth Badge,
  Route 19's beach needs the Volcano Badge, and both Cycling Road
  gatehouses need the Bicycle. Seeds must be regenerated to benefit from
  any of the above.
- **Six Johto passages that a character physically blocks were treated as
  open.** None of them is opened by an item or a badge, only by a step of
  the story, so each is now counted as such. The Slowpoke Well opens once
  you have spoken to Kurt, the Azalea Gym once you have beaten Proton at
  the bottom of that well, the Team Rocket hideout under the Mahogany
  souvenir shop once Lance has asked for your help at the Lake of Rage
  (which also needs Surf, since the red Gyarados sits in open water), the
  Mahogany Gym once the hideout is cleared, the Blackthorn Gym once Team
  Rocket has been driven out of the Goldenrod Radio Tower, and the
  Dragon's Den once Clair has been beaten. This closes the two largest
  remaining holes in Johto's logic: the Glacier Badge, and with it
  Whirlpool, now costs the whole Lake of Rage and hideout chain instead of
  a walk into town, and the Rising Badge, and with it Waterfall, costs the
  Radio Tower, then Clair, then the Dragon's Den shrine where the badge is
  actually handed over. Nothing reachable at the very start of the game
  changes. Seeds must be regenerated to benefit.
- **The Lake of Rage was treated as a single shore, and starting there
  could strand you.** The lake has banks on either side of the water, and
  the logic joined them as if you could walk around. A player who started
  at the Lake of Rage with `randomize_start_location` was dropped outside
  the Hidden Power house, on a patch of land ringed by the lake, with no
  way off it without Surf. The two banks are now separate places joined by
  Surf, and the checks that really do sit across the water (the TM43, the
  Choice Specs, the Max Potion, the Red Flute, the Red Scale from the red
  Gyarados and the Hidden Power house's own TM10) need Surf accordingly.
  Starting at the Lake of Rage is a separate matter and is dealt with above,
  under Removed. The hidden Full Restore and Rare Candy on the southern
  shore are unchanged, and so is Lance: he stands on the southern shore
  too, so the requirement to have engaged the red Gyarados before he shows
  up is still carried by the Team Rocket hideout door, exactly as before.
  Seeds must be regenerated to benefit.
- **The Ice Path let you walk straight from Route 44 to Blackthorn.** The
  Ice Path's ground floor is two separate chambers of the same map, and
  Blackthorn's door is in the one you can only reach by going down through
  the boulder puzzle. Blackthorn's Ice Path exit therefore now hangs off
  the second basement, and pushing the boulders into the holes costs
  Strength on the way down only, since a boulder that has fallen through
  does not climb back out. The direct Route 44 to Blackthorn connection that
  walked around the whole cave, which the game's own maps do not have (every
  tile along the seam the two maps share is solid rock), is gone as well, so
  the boulder puzzle is now the crossing it is in the game. Blackthorn, its
  shops and houses, its gym, the Dragon's Den and the shrine where the
  Rising Badge is actually handed over, Route 45, the top half of Route 46
  and the lower Ice Path move behind Strength as a result: 16 places and 47
  checks, the Rising Badge and therefore Waterfall among them. Nothing
  reachable at the very start of the game changes. Seeds must be regenerated
  to benefit.
- **Kanto's own story locks were treated as open, the second half of the
  same census as the six Johto ones above.** The Route 10 Power Plant had
  two disconnected versions of its own map (broken and repaired) both
  hanging directly off Route 10, so nothing stopped the logic from reaching
  the repaired one, and with it TM57, for free; TM57 itself was also
  attached to the wrong one of the two, since the manager only hands it over
  after the warp into the repaired map. Both are fixed: the repaired map is
  now reached only through the broken one, and restoring power is a real
  story gate behind it. Both Underground Path guardhouses (Route 5 and
  Route 6) now require it too, matching their own "closed until the problem
  at the Power Plant is solved" line. The Lavender Radio Tower's EXPN Card,
  which needs power restored before the director will hand it over, is
  modeled the same way, and the two sleeping Snorlax (Route 11 and Route
  12) now require it in turn, since neither will battle unless the Pokeflute
  radio station is already tuned in, which needs the EXPN Card. Route 12 not
  yet having a documented pre-/post-Snorlax split, both of its southward
  exits are gated rather than picking one; today neither the Route 11 nor
  the Route 12 gate actually closes anything additional, since Kanto's route
  mesh already reaches Diglett's Cave, Route 12 and the Route 11/12
  Gatehouse by other paths, but both are still modeled correctly for when
  that changes. Finally, Blue no longer opens the Viridian Gym for free: in
  the game he only does so once seven of Kanto's other eight badges are
  held, and since Earth is the eighth and last one, "seven of a possible
  seven" is exactly "all seven", so the gym now requires Boulder, Cascade,
  Thunder, Rainbow, Soul, Marsh and Volcano together. Nothing reachable at
  the very start of the game changes; sphere 0 is untouched, all of this
  sits deep in Kanto. Seeds must be regenerated to benefit.

## [0.8.0] - 2026-08-22

### Removed
- **`extra_route_blockers` (breaking change to existing YAML files).** The
  option existed only to delete one Route 46 to Route 45 connection from
  the region graph. That connection was itself a modeling error, fixed in
  0.7.1, so the option had become a no-op whose description promised
  something it no longer did. A YAML that still lists this option will
  fail to generate: remove the line.

### Fixed
- **The region graph let the logic believe half of Johto was reachable
  with nothing.** Three separate errors, all found by checking the graph
  against the game's real maps. Azalea Town and Route 34 were joined by a
  connection that does not exist: the only way between them is through
  Ilex Forest, so Cut was treated as opening nothing at all. The Sudowoodo
  was modeled as guarding only the path to Ecruteak, when it actually
  blocks the whole north side of Route 36, National Park and Route 35
  included. And crossing Dark Cave was modeled as needing Strength alone
  when it needs Rock Smash as well. Together these put Goldenrod, Route 34,
  Route 35, National Park and northern Ilex Forest in reach before the
  player owned anything. Sphere 0 goes from 113 regions and three free
  badges (Zephyr, Hive, Plain) down to 65 regions and two (Zephyr, Hive),
  which matches what the game actually allows. Seeds must be regenerated
  to benefit.
- **Route 46 is split at its internal ledge, and Routes 32 and 33 no
  longer touch directly.** Route 46's Dark Cave entrance sits above the
  ledge, so it cannot be reached from Route 29, and its X Speed and three
  trainers are on the far side. Routes 32 and 33 meet only inside Union
  Cave; the direct link between them was an extraction artifact that would
  have silently cancelled any rule placed on the cave.
- **Items could be lost forever when starting a new game.** The client can
  write to save memory before a save file exists, and "New Game" then
  wipes everything it wrote, but its own count of delivered items survived
  that wipe. Anything the server had already sent, `start_inventory`
  included, was counted as delivered and never sent again. The client now
  refuses to touch anything until a save file really exists, and resets
  its delivery progress when it sees the save change, after confirming the
  change over two reads so that a single bad read cannot cause duplicate
  deliveries. `starting_money` had the same defect and is fixed the same
  way.
- **Found items showed "???" instead of their name.** The game has three
  separate item-name tables and picks between them by sentence
  construction; only one of the three was being patched. The "found"
  message uses one of the other two, which is why the placeholder appeared
  first and the correct text second. All three are patched now, each with
  wording that reads correctly in the sentence that uses it.
- **DeathLink fired at the start of battles, at random.** The client was
  reading the fainted-Pokemon counter directly, but the game keeps that
  whole block of statistics encrypted in the save file, and re-encrypts it
  with a fresh key every time any statistic changes. The wild-encounter
  and trainer-battle counters both change exactly when a battle starts,
  which scrambled every value in the block; roughly half the time the new
  scrambled number looked larger than the old one and the client reported
  a death. The counter is now decrypted before being read.
- **A network error while locating save addresses killed the client
  silently.** The address scan ran outside the error handling that protects
  the rest of the loop, so a failed read stopped the client from ever
  updating again, with nothing shown to the player.
- **An unrecognized item name left the original item in the ROM instead of
  reporting the problem.** Generation now fails with a message naming the
  location and the item.

### Fixed (Dexsanity)
- **Dexsanity could lock a key item behind the very Pokemon that key item
  unlocks.** Player report: a seed became unwinnable because the
  Squirtbottle was placed on the Tropius Dexsanity check, Tropius only
  appeared in the Burned Tower, and the Burned Tower is inside Ecruteak,
  which the Squirtbottle itself opens. Two separate defects made that
  invisible to the logic and both are fixed. First, Dexsanity checks
  existed for Pokemon that were never written into the patched ROM at all:
  the species list counted Headbutt-tree tables the patcher does not touch
  and three maps that have no encounter entry to patch, which on a
  Randomized Wild Pokemon "zone_method_mapping" seed meant 59 of about 460
  Dexsanity checks were literally impossible (the reported seed had its
  Super Rod on a Grovyle that existed in no table anywhere). The list of
  what actually reaches the ROM is now stated once, next to the code that
  writes it, and both the patcher and the logic read that same statement,
  so they cannot drift apart again. Implementing Headbutt-table
  randomization later brings those Pokemon back automatically. Second, a
  Dexsanity check's requirements only ever described the tool needed
  (Surf, a fishing rod, nothing at all for grass), never the place: every
  one of them was treated as available from the very first step. Each
  check now requires actually reaching somewhere that Pokemon lives, using
  the cheapest of its locations when it lives in several. The number of
  Dexsanity checks a seed creates now varies from seed to seed, which is
  normal and expected. No client update is needed, and existing seeds are
  unaffected (they must be regenerated to benefit).

## [0.7.1] - 2026-08-19

### Fixed
- **One bad memory read could send dozens of checks you never made, with
  no way to take them back.** Player report: the game froze while picking
  up a hidden item in Ilex Forest, the save was reloaded, and the very
  next client tick sent 52 locations to the multiworld at once. Those
  items were delivered to the other players and those locations marked
  checked server-side, permanently. Root cause: the client trusted every
  savedata read unconditionally, so a read taken while the game was
  frozen or reloading (unstable memory, or cached addresses gone stale
  because the save was reloaded underneath them) was reported as real
  progress. Check reporting now passes three independent guards. The
  located save block must still carry its own fixed Pokedex signature
  word, which is a direct test that the cached addresses still describe
  the running game. The flag and Pokedex reads must not be structurally
  impossible (fill patterns, saturation, bits set in ranges the game
  never uses). And any batch bigger than a normal second of play must be
  read identically twice in a row before it is sent. Connecting the
  client for the first time on an already-advanced save, or reconnecting
  after hours played offline, still works exactly as before: a large
  batch is never refused for being large, it only takes one extra second
  to confirm. A normal single check is still sent immediately, with no
  added delay.
- **Route 45 and Route 46 were connected the wrong way round, handing you
  half of Johto from the first step.** The corniche between them was
  modeled as Route 46 -> Route 45, so the logic believed a brand new save
  could walk from Route 29 up into Route 45, on to Blackthorn, and from
  there through Route 44, Mahogany, Route 42 and Ecruteak. Player spoiler
  logs showed Ecruteak Gym and the Burned Tower in sphere 1, and the
  Squirtbottle gate on Ecruteak (itself correct) was simply walked around
  through Route 42. The real geography is the opposite: Route 45 is the
  mountain route hanging below Blackthorn, Route 46 sits below it again
  just above Route 29, and the ledges only ever let you drop from 45 down
  into 46, never climb back (confirmed for both of Route 46's sections,
  including the northern one reached through Dark Cave). With the edge
  pointing the right way, what a brand new save can reach drops from 197
  regions to 112, and the badges obtainable with zero items from 7 back
  to 3 (Violet, Azalea, Goldenrod).

### Changed
- **`extra_route_blockers` no longer does anything.** Its whole purpose
  was to remove the Route 46 -> Route 45 edge above, which turns out not
  to exist in the real game; correcting it closes that shortcut for
  everyone, whether the option is on or off. The option is kept for now
  so existing YAML files keep loading unchanged, and generation is
  identical either way.

## [0.7.0] - 2026-08-19

### Changed
- **Holding a badge and holding its HM is now all you need to use that HM
  outside battle.** Gym Leaders no longer gate any field ability: beating
  a Leader unlocks nothing by itself, and receiving a badge item unlocks
  its move immediately, wherever in the multiworld that badge was placed.
  A Leader you already hold the badge for is still fightable, and still
  awards whatever item the fill put at their location. Their win cutscene
  now runs exactly once.

### Fixed
- **Gym Leaders could still be re-fought forever, and four of them could
  permanently softlock the mid-game story.** Root cause: one single
  savedata bit (`PlayerProfile.johtoBadges`/`kantoBadges`) was doing two
  incompatible jobs. Every gym script read it through `CheckBadge` to
  decide "already beaten, skip the fight", while the field engine read the
  same bit to authorize Cut, Fly, Surf, Strength, Waterfall, Whirlpool,
  Rock Smash and Rock Climb. Because badges are real AP items that can be
  placed anywhere, the client had to withhold that bit until the Leader
  was actually beaten, which meant a player who beat a Leader *before*
  their badge arrived never got the bit written at all: the Leader stayed
  re-fightable and their whole win branch replayed (for Falkner, that
  re-ran and re-blocked the Elm's Lab Mystery Egg pickup and the Kimono
  Girl chain). Worse, Chuck, Jasmine, Morty and Pryce each add 1 to a
  shared mid-game counter inside that replayable branch, and the game
  tests that counter for strict equality to trigger Team Rocket's takeover
  of Mahogany Town and the Radio Tower. One extra re-win pushed the
  counter past the tested value for good, permanently blocking that
  progression. Fixed by rewriting each gym's own battle guard in the ROM
  to test that Leader's per-gym sentinel flag directly (the same flag the
  badge location's check detection already uses) instead of the badge bit
  -- which restores the guard's original vanilla meaning and frees the bit
  to be written the moment the badge item is received. Blackthorn Gym
  needed no patch (Clair is already flag-gated in vanilla). See
  rom/badgegatedata.py for the full instruction-level writeup.
- **Whitney handed out TM45 (Attract) again on every single visit** once
  her badge hand-over scene had been reached. Same root cause: with the
  vanilla local badge grant neutralized, her script's post-badge branch
  (the one carrying the "already got the TM" check) became unreachable, so
  her badge-and-TM sequence re-entered forever. Her guard now tests her
  own hand-over progress variable instead. If you are mid-seed and stuck
  in this loop, regenerate.
- Corrects the 0.6.7 entry below, which claimed "the Leader is only
  re-fightable until genuinely beaten". That was not accurate: until this
  version a Leader stopped being re-fightable only once the matching badge
  *item* had also been received, which in a multiworld may happen long
  after the fight, or never in the case of a Leader whose badge is placed
  behind their own gym.

### Note
- Seeds generated before this version keep the old behaviour and the bugs
  above. Regenerate the patch to pick this up; the ROM patch and the
  client changed together and are expected to match.

## [0.6.9] - 2026-08-19

### Fixed
- **One full Bag pocket froze the delivery of every later received item,
  permanently.** Root cause: `_apply_received_items` tracked delivery
  progress with a single contiguous counter over `ctx.items_received`, and
  `break`-ed out of its loop without advancing that counter whenever
  `plan_bag_item_write` returned `None`. That return is transient for a
  failed guarded write, but deterministic for a full pocket: nothing the
  client does frees a slot, only the player can. So one item bound for a
  saturated pocket (Mail holds 12, Balls 24, Battle Items 30, Medicine 40)
  stalled the entire queue on every subsequent tick, including items bound
  for pockets with 100 free slots, while Archipelago's core client kept
  announcing each one as "received" with no error shown anywhere. A full
  pocket now only holds back the items bound for that same pocket: the
  scan carries on, and items delivered ahead of the blocked one are
  recorded in a new server-side Datastorage key
  (`pokemon_heartgold_delivered_ahead_{team}_{slot}_{trainer_id}`, a
  bitmask of `items_received` indices merged with the `or` operation) next
  to the existing counter, so a client restart re-delivers none of them
  and loses none of the still-pending ones. A failed guarded write still
  stops the tick and retries, unchanged.

## [0.6.8] - 2026-08-18

### Fixed
- **The BizHawk client's GameWatcher task could die permanently and
  silently.** Real player report. Root cause: `game_watcher`'s own
  trainer-id read (used to make its per-save applied-item-count key
  unique) sat outside the method's `try`/`except bizhawk.RequestFailedError`
  block. `worlds._bizhawk`'s own `_game_watcher` has no catch around
  `game_watcher(ctx)` at all, so a transient BizHawk read failure at that
  exact point (the same condition every other call in this method already
  tolerates) propagated all the way out and killed the GameWatcher task
  for the rest of the session, with no further retries. The read now
  happens inside the existing `try` block, so the same failure is caught
  and simply retried the next tick, like every other bizhawk call here.
- **8 npc_gift locations could hand out their item over and over, forever**
  (real player report): goldenrod_radio_tower_2f_blue_card,
  goldenrod_radio_tower_5f_basement_key, goldenrod_tunnel_warehouse_card_key,
  goldenrod_flower_shop_squirtbottle, route_12_fishing_brother_house_super_rod,
  celadon_condominiums_3f_gb_sounds, celadon_game_corner_coin_case,
  saffron_copycat_house_2f_pass. Root cause: each of these 8 NPCs gates its
  own give-item script branch on the player already possessing the
  *vanilla* original item (`HasItem`/`GetItemQuantity`), not on a savedata
  flag. Item substitution only ever rewrites the `GiveItemNoCheck`
  operands, never this separate gate check, so once a different item is
  substituted in, the player can never actually hold the vanilla item id
  the gate tests for -- the gate always reads "haven't received it yet"
  and re-grants on every single interaction. Fixed by overwriting each
  gate's own check instructions in place with a fresh one-time savedata
  flag gate (see rom/npcgiftgatedata.py), reusing the exact byte span the
  old check occupied so nothing else in that script shifts. If you
  generated a seed before this version and one of these 8 locations is
  duplicating its item, regenerate.

### Known gap (documented, not fixed)
- Player's House 1F's front door stays redirected to Elm's Lab for the
  entire playthrough, even long after picking a starter. This is a
  permanent, static ROM edit applied once at generation time (see
  rom/startlocation.py's own docstring for the investigation into why a
  runtime reversion isn't possible without an ASM hook: the underlying
  `WarpEvent` record is re-read fresh from NitroFS into transient RAM
  every time the map loads, not a persistent savedata struct this client
  could patch and have it stick). Accepted as-is rather than shipping an
  unverified partial fix.

## [0.6.7] - 2026-08-18

### Fixed
- **The other 10 gym badges from 0.6.6 are now fixed too** (Bugsy, Morty,
  Chuck, Jasmine, Pryce, Brock, Misty, Erika, Janine, Sabrina). 0.6.6 fixed
  6 of the 16 gym Leaders' badge-completion/re-fight-forever bug by reusing
  a pre-existing savedata flag already set in that Leader's own win
  sequence; the other 10 had no safe, reusable flag to find (every
  candidate either belonged to that gym's own TM hand-out check or was
  shared with an unrelated event elsewhere in the game). These 10 now get
  a brand-new sentinel flag instead, injected directly into that Leader's
  own vanilla `GiveBadge` script instruction (which already had to be
  overwritten anyway, to stop the vanilla local badge grant now that
  badges are real AP items) -- a plain 4-byte instruction swap, not an ARM
  hook. All 16 gym badges now behave the same way: the Leader is only
  re-fightable until genuinely beaten, and the badge location actually
  completes. If you generated a seed before this version and need these
  10 badges to actually complete, regenerate.

## [0.6.6] - 2026-08-18

### Fixed
- **Gym Leaders were re-fightable forever, replaying their entire win
  cutscene every time** (real player report). Root cause: check-detection
  for a gym Leader assumed defeating them set the same engine flag every
  other trainer battle does, but every Leader is actually fought through a
  bespoke, hand-authored script that never sets that flag on itself. That
  made the client permanently think you hadn't beaten the Leader yet, so
  it never wrote your badge item's bit until you had, which in turn meant
  the Leader's own game logic (which gates the battle on that same bit)
  never saw you as having won -- including Falkner's own scene-progress
  write that unlocks picking up the Mystery Egg at Elm's Lab, which got
  silently re-run (and re-blocked) on every single re-fight.
- **No gym badge location could ever actually complete**, which is worse:
  whatever item any player's world placed at a gym badge location could
  never be delivered to them, for any of the 16 badges, in any seed. Same
  root cause as above.
- Both are now fixed for 6 of the 16 gym Leaders (Falkner, Whitney,
  Lt. Surge, Clair, Blaine, Blue), using a hand-verified, per-Leader
  savedata flag found in that Leader's own win sequence instead. The
  other 10 Leaders' own scripts were checked and don't currently expose a
  safe, reusable signal (their only candidates already belong to that
  same gym's TM hand-out check, or are shared with unrelated events
  elsewhere in the game) -- those 10 remain in their pre-existing broken
  state (re-fightable, check never completes) until a real fix is found.
  If you generated a seed before this version and need gym badge checks
  to actually complete, regenerate.

## [0.6.5] - 2026-08-18

### Fixed
- **Ilex Forest soft-lock.** Real player report: stuck at Ilex Forest with
  no way forward. Root cause: the 12 item locations physically past the
  map's own Cut tree (`ilex_forest_x_attack`, `_antidote`, `_ether`,
  `_antidote_2`, `_super_potion`, `_full_heal`, `_ether_2`,
  `_tinymushroom`, `_repel`, `_big_mushroom`, `_tinymushroom_2`,
  `_tinymushroom_3`) were modeled as part of the same, freely-reachable
  `ilex_forest` region as the Cut Master/HM01 pickup on the near side, so
  the fill could legally strand a progression item behind a check that
  needs Cut+Hive Badge to even reach. `ilex_forest` is now split into two
  regions at the tree (`ilex_forest` / `ilex_forest_north`), with the
  existing Cut+Hive requirement moved onto that internal edge. If you
  generated a seed before this version, regenerate.
- `start_inventory`/`start_inventory_from_pool` items (and other early
  server-tracked grants like the Pokedex/Pokegear unlock from
  `randomize_menu_unlocks`) could silently never arrive on a save that was
  restarted while staying connected to the same slot -- the server-side
  "already applied" guard survived the restart even though the local save
  was genuinely fresh. Both guards are now either fully state-driven
  (start-location flags: compares desired vs. actual bits every tick, safe
  since those flags are monotonic) or use a narrow fresh-save heuristic
  (received-item count: only distrusts the server-stored count before this
  session has counted anything locally itself, and only when the starter
  hasn't been picked yet).

### Changed
- **TM70 (Flash) is no longer randomized** and is now a `progression`
  item instead of `useful`. Flash never gates any exit in this project's
  own logic (see `data_gen/rules.toml`'s `[hm_badges]` header), but it's a
  genuinely useful tool for navigating dark caves, so it's pinned to
  always teach Flash and placed more accessibly by the fill rather than
  risk shuffling it onto an unrelated move.

## [0.6.4] - 2026-08-17

### Fixed
- **0.6.3's own Elm's Lab entrance-position fix was itself broken.** 0.6.3
  moved where the player lands when warping into Elm's Lab (away from the
  door, to stop a "walk straight back out if you hold a direction"
  annoyance) to `(4, 9)` -- untested at release. Further live testing
  found this position left the player effectively unable to progress
  normally in the Lab. Two more candidate positions were tried afterward
  (`(3, 10)`, `(4, 12)`) and both broke the Lab's own aide-greeting scene
  and left the exit door unresponsive, for a root cause never fully
  confirmed -- something about this specific warp record's position data
  is read by more than just where-you-land. Reverted to the exact
  vanilla entrance position: the "walk back out if holding a direction
  through the transition" annoyance from before 0.6.3 is back, but the
  Lab is once again always fully usable. If you generated a seed with
  0.6.3 and are using `randomize_start_location`, regenerate with this
  version.

### Changed
- **Breaking `host.yaml` change**: the single `rom_file` setting is now
  two separate settings, `heartgold_rom_file` and `soulsilver_rom_file`
  (real player report: one shared setting made it impossible to
  configure both a HeartGold and a SoulSilver ROM at the same time, since
  it always defaulted to a "HeartGold"-named file even when pointed at a
  SoulSilver ROM). An existing `rom_file:` entry in your `host.yaml` is
  now ignored -- set `heartgold_rom_file`/`soulsilver_rom_file` instead
  (only the one(s) matching the game_version(s) you actually generate for
  are required).

## [0.6.3] - 2026-08-17

### Fixed
Emergency patch, same day as 0.6.2, following a real live playtest of
`randomize_start_location`.
- **Save button not working at all, and Bag/Save/Options disappearing
  entirely after quitting and relaunching**, on a `randomize_start_location`
  save. Root cause: the previous design spawned the player directly inside
  Elm's Lab (a `sLocation_PlayerRoom` patch) and faked Bag/Trainer Card/
  Save/Options by poking their pause-menu flags directly -- but the real
  save-execution path checks something else entirely, not that flag, so
  Save silently did nothing, and nothing was ever really saved to persist
  those poked flags across a relaunch. Redesigned: the player now wakes up
  and talks to Mom the ordinary way (her real vanilla scene grants Bag/
  Trainer Card/Save/Options for real, exactly like a normal playthrough) --
  only the house's own front door is redirected straight to Elm's Lab
  afterward, reusing the same door-redirect mechanism already proven safe
  for the lab's own exit.
- **Black screen after using the redirected door**, introduced by the fix
  above: the door's warp record encodes both a destination map and an
  entrance-point index into that map's own table; only the map was being
  patched, leaving a stale entrance index that made no sense inside Elm's
  Lab. Both fields are now patched together.
- **Walking straight back out through the door immediately after
  arriving**, if a movement key was still held during the transition: Elm's
  Lab's own entrance data doubled as its exit-approach position, landing
  the player right at the door. Moved to a safer position inside the room.

### Removed
- **`randomize_bag`/`randomize_trainer_card`/`randomize_pokedex`/
  `randomize_options_button`** (all four, added just yesterday in 0.6.2):
  a live playtest found the compiled Start Menu's own icon-confirm
  dispatch breaks whenever any pause-menu icon is unavailable while icons
  after it in the menu's own ring order (Save, Options) are visible --
  selecting one icon could fire a completely different one's action (e.g.
  Options opening Save). This invariant only ever holds in vanilla, where
  every one of these flags is granted together in one uninterrupted scene;
  a randomized, possibly long-delayed unlock necessarily breaks it. No
  client-side fix exists without an ASM hook, which this project avoids on
  principle. Bag/Trainer Card/Pokedex/Save/Options are all once again
  always unconditionally granted by their own real vanilla trigger, like
  before 0.6.2. `randomize_bicycle` is unaffected (a real Bag item, not a
  pause-menu icon) and remains a working toggle.

### Added
- **`remote_items`**: off by default. When on, your own items are never
  written directly into the ROM -- you always receive them from the
  server instead, the same way you already receive other players' items.
  Lets you restart a corrupted save without losing progress (the server
  just resends everything you already found), or share a save file
  between multiple people.

## [0.6.2] - 2026-08-17

### Changed
- **`randomize_menu_unlocks` split into 7 independent toggles** (user
  request): `randomize_bag`, `randomize_trainer_card`, `randomize_pokedex`,
  `randomize_pokegear`, `randomize_save_button`, `randomize_options_button`,
  each pickable on its own instead of from one combined list.
- **Added `randomize_bicycle`**: the Bicycle can now also be turned into a
  real, shufflable AP item instead of always being handed over for free at
  Goldenrod's Bike Shop -- previously a documented gap, never tracked as a
  location at all.
- Rewrote every option added tonight to be shorter and more direct for
  players configuring their own YAML; regenerated the default template
  (`docs/Pokemon HGSS.yaml`) to match.

## [0.6.1] - 2026-08-17

### Fixed
Code review caught these before anything in 0.6.0 shipped -- see
`docs/scope.md`'s "Code review fixes" entry for the full writeup.
- `randomize_menu_unlocks` locations were self-checking: receiving the
  item auto-completed the player's own location for it, with no real
  in-game action, and a genuine vanilla trigger landing at the wrong
  moment could be lost permanently. Detection and gating are now handled
  atomically by the same function.
- `johto_only` combined with `sphere_based_trainer_leveling` crashed
  generation (`KeyError`) after a full multiworld fill.
- `randomize_learnsets`'s ROM write ran unconditionally for every player,
  not just those who enabled it -- now skipped whenever unchanged, and
  degrades gracefully instead of crashing on a future data mismatch.
  Also verified safe on a real SoulSilver ROM (previously unverified).
- A write-guard race in `_apply_start_location_flags` (start-location
  menu-unlock grant) could clobber a flag that changed mid-write.
- A latent crash in `set_rules` if a future exit rule ever targeted an
  edge `extra_route_blockers` removes.

## [0.6.0] - 2026-08-17

### Added
- **`randomize_start_location`'s region graph is now logic-integrated**,
  closing that option's own "known gap": the fill algorithm's own
  reachability now genuinely starts from the chosen `starting_town`
  instead of always assuming New Bark, regardless of this option. All 10
  candidate towns verified completable via real generation + fill.
- **`randomize_menu_unlocks`** option: turn any of Bag/Trainer Card/
  Pokedex/Pokegear/Save button/Options button into a real, shufflable AP
  item instead of always being unlocked for free. Combines cleanly with
  `randomize_start_location`. None selected by default (no effect).
- **`extra_route_blockers`** option: closes the Route 46 -> Route 45
  one-way ledge shortcut for extra difficulty (previously left in as
  vanilla behavior -- it lets a player reach 7 of Johto's 16 badges with
  effectively zero items). Off by default; verified safe in combination
  with every `randomize_start_location` starting town.
- **`randomize_learnsets`** option: randomizes which move each species
  learns at each level-up slot (the level itself stays vanilla). Purely
  cosmetic to this project's own logic -- no region-access rule depends
  on level-up movesets, only on owning HM items.

## [0.5.0] - 2026-08-17

### Added
- **`randomize_start_location`**: skip the New Bark Town origin story and
  spawn directly inside Elm's Lab instead. The real, vanilla 3-way starter
  choice still plays out exactly as normal (Elm's own lab script, not a
  hand-rolled substitute); a new `starting_town` option picks (or
  `random`-rolls) which of 10 towns the lab's exit door leads to instead of
  New Bark. Bag, Trainer Card, Save, Options, Pokédex and Pokégear access
  are all granted automatically once the starter is chosen, and the rival
  is pre-advanced past his first New Bark/Cherrygrove checkpoint so he
  doesn't wait forever for an encounter that will never happen. Off by
  default. Known gap: the region graph still treats New Bark as the fixed
  logical origin regardless of this option -- see `docs/scope.md`.

### Fixed
- **Randomized starters whose display label is a raw decomp identifier**
  (Nidoran-M/F, Mr. Mime, Ho-Oh, Mime Jr., Porygon-Z, and the Deoxys/
  Wormadam/Giratina/Shaymin/Rotom alternate forms) crashed the
  starter-selection text patch with a charmap error whenever
  `randomize_starters` happened to land on one of them. A pre-existing
  bug, never triggered before since no earlier seed had picked one of
  these species; fixed with a small display-name override table plus
  regression tests covering every affected species.

## [0.4.0] - 2026-08-17

### Added
- **`randomize_move_categories`**: shuffle each damaging move's Physical/
  Special category (a real, engine-honored per-move split in Generation
  IV). Status moves are never touched either direction.
- **`randomize_tm_moves`**: shuffle which move each TM (TM01-TM92)
  teaches. HM01-HM08 always keep their vanilla move -- this project's
  region-access rules key off owning the HM item, not whatever move it
  currently teaches.
- **`randomize_type_chart`**: shuffle the type-effectiveness chart's
  resistances/weaknesses/immunities across the vanilla exception table.
  Never touches the two engine-internal marker rows the Foresight/Odor
  Sleuth/Scrappy mechanic depends on.
- **`starting_money`**: set (or `random`-roll, 0-5000) how much money the
  player starts with. Applied once, client-side, guarded by a
  server-stored flag so a later reconnect never re-wipes money the
  player has since earned or spent.
- **`johto_only`**: exclude all of Kanto (180 regions) from the region
  graph -- no location is created there, Kanto's 8 badges are never
  added to the item pool, and `goal_badge_count` is silently capped at 8
  for the `n_badges` goal. Johto's own Elite Four and the post-game Red
  fight on Mount Silver are unaffected.

## [0.3.3] - 2026-08-16

### Added
- **`dexsanity_trigger`** option: choose whether Dexsanity checks fire on
  catching a species (`catch`, default, unchanged) or on merely
  encountering it (`encounter`, reads the Pokedex's `seenSpecies`
  bitfield instead of `caughtSpecies`).
- **`dexsanity_encounter_types`** option: restrict which encounter
  methods (land, surf, rock smash, old/good/super rod, headbutt) count
  toward Dexsanity at all. Defaults to every method (no behaviour
  change).

## [0.3.2] - 2026-08-17

### Fixed
- **Receiving a badge from another location before physically reaching
  that gym could permanently skip the fight.** Every gym Leader's own
  field script gates its battle behind "do you already have my badge",
  so setting the badge bit immediately on receipt (instead of on
  actually beating them) made the Leader think the fight had already
  happened. This silently broke more than the fight itself: Elm's Lab's
  egg-pickup phone call and two Trainersanity-eligible trainers near
  Violet City were also gated on that same battle actually happening.
  Fixed client-side -- the badge bit is now only written once the
  player has genuinely beaten that Leader, no ROM patch needed.

## [0.3.1] - 2026-08-16

### Added
- **Legendarysanity** option: turns catching Ho-Oh (Bell Tower) and Lugia
  (Whirl Islands) into real checks, alongside `trainersanity`/`dexsanity`.
  Off by default -- both stay exactly vanilla (same place, same
  post-Elite Four requirement) when off, matching how other Pokemon
  Archipelago worlds treat static legendary encounters.

## [0.3.0] - 2026-08-16

### Added
- **Real badge randomization.** Badges are now tradeable/shufflable AP
  items instead of a fixed logic milestone: each gym's vanilla `GiveBadge`
  call is neutralized so it can no longer double-grant a badge locally,
  and defeating a Leader is detected the same way any other trainer
  battle is.
- **Trainersanity, made real.** 390 real, fillable trainer-battle
  locations (one per person-event trainer across the game), off by
  default via the `trainersanity` option.
- **A 4th wild-encounter randomization mode**, `zone_method_mapping`:
  assigns one consistent replacement species per (zone, encounter
  method) group instead of randomizing every slot independently, so a
  route's grass encounters read as a single species again.
- **Ho-Oh and Lugia as real, checkable locations.** Both are only
  reachable after defeating the Elite Four/Champion, matching vanilla,
  and losing/fleeing the encounter never blocks anything -- the Pokemon
  simply reappears.
- **Quality-of-life options**: `fast_text_speed` and
  `skip_battle_animations`, applied once per connection and live-
  verified against a real BizHawk session. Both off by default.
- **Reusable TMs** option: a consumed TM reappears in the Bag on the
  client's next poll, no ROM patch needed.
- **DeathLink support.** One of your own Pokemon fainting sends a death;
  receiving one faints your whole party (zeroes current HP), matching a
  vanilla blackout.
- **Convert trade/friendship evolutions** option: rewrites any trade- or
  friendship-based evolution into a plain level-up evolution at a
  configurable level, a single-player accessibility fix.
- The garbled "???" placeholder name shown when picking up another
  player's item is now a real, readable message.

### Changed
- **Renamed the world from "Pokemon HeartGold" to "Pokemon HGSS"**
  (built file is now `pokemon_hgss.apworld`), reflecting that it has
  supported both HeartGold and SoulSilver ROMs since 0.1.1. The patch
  file extension (`.apheartgold`) and local settings key are
  deliberately unchanged for backward compatibility.
- The starter-choice screen now shows the actually-randomized species'
  name instead of always showing Chikorita/Cyndaquil/Totodile -- the
  species you received was always correct, only the on-screen text
  lagged behind.
- Randomized starters are now restricted to species with at least one
  evolution, matching vanilla (each of the three starters has two) --
  previously a randomized starter could land on an already fully-evolved
  species.

### Fixed
- **Region graph logic bugs** found via real tester spoiler-log feedback:
  two missing vanilla HM/item gates (a Surf gate, a Squirtbottle-gated
  Sudowoodo), and a one-way ledge (Route 46 into Route 45) that wrongly
  let players climb back up, both of which let some seeds reach their
  goal at sphere 0/1 with effectively no items owned.

### Planned for a future release
Not implemented yet -- see `docs/scope.md`'s "v3" section for the full
investigation notes on each:
- Trainer level matching (scale your Pokemon's level to a trainer's
  strongest, with a configurable offset) -- blocked on live battle-state
  detection, needs a real ARM code hook this project has no toolchain for.
- Randomized start location and starter kit -- blocked on live player-
  position manipulation, same class of blocker as above.
- Human-readable location display names in the client/spoiler log --
  deprioritized, and a real risk to item-substitution delivery was found
  that needs a dedicated audit pass first.
- An optional extra-difficulty mode that adds artificial route/passage
  blockers beyond the existing HM/badge/item gates -- not yet
  investigated, no blocker identified so far.

## [0.2.0] - 2026-08-12

### Added
- **Universal Tracker (`tracker.apworld`) support.** UT can now re-generate
  a HeartGold slot locally and track it, with no YAML needed from whoever
  is tracking (`ut_can_gen_without_yaml`): `fill_slot_data` publishes every
  world option under a new nested `options` key, and a UT re-run restores
  them before building the region graph. Seeds from 0.1.4 and earlier still
  track correctly -- their flat `goal`/`goal_badge_count` keys are the only
  slot data that affects logic, and are read as a fallback. A tracker re-run
  also skips the ROM-only species/move/trainer randomization, which has no
  bearing on logic.
- **v2 Phase 1: Nuzlocke aids.** `disable_ohko_moves` neutralizes
  Guillotine/Horn Drill/Fissure/Sheer Cold into ordinary 60 power / 100
  accuracy moves. `disable_trapping_abilities` removes Arena Trap, Shadow
  Tag, and Magnet Pull from every Pokémon that has one, replaced with a
  copy of the species' own other ability (or Run Away for mono-ability
  trappers like Wobbuffet). Both off by default, live-verified on real
  HeartGold and SoulSilver ROMs.

### Changed
- The ARM9 recompression step no longer hard-fails a patch if
  `apnds.lz.compress_code` can't shrink the post-secure-area data (rare):
  it now falls back to writing that region uncompressed and zeroing
  `SDK_COMPRESSED_STATIC_END`, matching the game's own boot-time no-op
  path for a zero value there (verified directly against the decomp's
  `crt0.s`, community-suggested).

### Removed
- **QoL options (`fast_text_speed`, `skip_battle_animations`), shipped
  and reverted the same day.** Live BizHawk testing showed neither option
  actually changed anything in-game. The in-word `Options` bitfield
  packing order the write relied on was never independently confirmed
  against a live session before shipping -- see `docs/scope.md` for the
  post-mortem. May return once someone can verify the real bit layout
  live.

## [0.1.4] - 2026-08-11

### Fixed
- **v0.1.3 broke every real install.** `compatible_version` was removed
  from `archipelago.json` to satisfy a manifest-compliance test, but
  nothing stamped it back into the packaged `.apworld` at build time --
  Archipelago's own manifest loader does a raw dict access on that field
  and fails to load the world at all without it (silently falling back to
  `world_version 0.0.0`). `build.py` now stamps `compatible_version` into
  the packaged manifest, matching what Archipelago's native build tool
  does, while the source `archipelago.json` still omits it correctly.
- The new patch-version check (also from v0.1.3) read its own
  `archipelago.json` with a plain filesystem path, which only works for a
  loose dev checkout -- every real `.apworld` is zip-loaded, so every real
  install hit `FileNotFoundError` on `generate_output`. Now reads it
  through the module's own loader instead, verified against an actual
  zipimport-loaded module this time, not just the dev test harness.

## [0.1.3] - 2026-08-11

### Added
- `start_inventory_from_pool` is now supported: items named there are
  removed from this world's item pool and backfilled with filler, so the
  pool still matches the unfilled-location count. Badges cannot be named
  (they are AP event items, not real bag items) and are rejected at YAML
  validation.
- New `game_version` option: declares whether the seed is intended for a
  HeartGold or SoulSilver ROM. Required now that wild-encounter data
  genuinely differs between the two versions (see below) -- the patcher
  refuses to apply a patch to a ROM that doesn't match the declared
  version, with an actionable error instead of silently writing wrong
  data.
- Patch files now record the APWorld version that generated them, and
  applying one with a different installed version raises an actionable
  error instead of a bare `KeyError` if the patch data format has changed
  in between -- community-suggested (2026-08-11), citing a real incident
  on another APWorld.

### Fixed
- `start_inventory` items are now actually delivered to the game. The
  client requested `items_handling = 0b011`, which leaves out the
  `remote_start_inventory` bit, so the server never sent them: the fill
  algorithm counted them as owned while the player never received them,
  which could produce unwinnable seeds when starting with a progression
  item (HMs, rods, Bicycle, S.S. Ticket, ...). Now `0b111`.
- Wild-encounter data was never actually version-aware despite SoulSilver
  support shipping in v0.1.1: 643 fields in the source encounter data (79
  more for headbutt trees) genuinely differ between HeartGold and
  SoulSilver, but only the HeartGold value was ever kept, and
  `randomize_wild_pokemon: vanilla` (the default) wrote it to the ROM
  unconditionally -- so a SoulSilver player with default options got
  their own SoulSilver encounters silently overwritten with HeartGold's
  data on every generation. A second, compounding bug found while fixing
  this: the ROM write path itself always targeted HeartGold's NitroFS
  encounter table regardless of which ROM was being patched, which would
  have made even correctly-resolved SoulSilver data invisible to a real
  SoulSilver cartridge's own game code. Both fixed and live-verified
  against real HeartGold and SoulSilver ROMs.

## [0.1.2] - 2026-08-11

### Fixed
- Generation no longer fails with `FillError: No more spots to place N
  items` when two or more slots share an item link with
  `link_replacement` enabled. The 30 undetectable npc_gift/hm_tm
  locations rejected item link group items, which are delivered to every
  group member and were never the stalled-remote case that restriction
  guards against. Reported and fixed by community contributor
  gerbiljames.

## [0.1.1] - 2026-08-11

### Added
- SoulSilver support: a US SoulSilver ROM is now accepted alongside
  HeartGold (dual-MD5 validation), same world, same options.
- Hidden items are randomized again, reconnected after root-causing and
  fixing the boot issue that previously disabled them (a stale ARM9
  decompression end-marker left over from any size-changing ROM edit --
  see `docs/architecture.md`). Live-confirmed on real HeartGold and
  SoulSilver ROMs via BizHawk (225 hidden_item substitutions each).
- New optional toggles: trainer level scaling (`trainer_level_scaling`),
  move type randomization (`randomize_move_types`), species type
  randomization (`randomize_species_types`).
- A ready-to-edit default YAML options file, `docs/Pokemon HeartGold.yaml`,
  for players who'd rather not generate their own via the Launcher.

### Changed
- Migrated the ROM read/write layer from `ndspy` (GPLv3) to `apnds`
  (MIT), vendored directly in this repository (`apnds/`). The
  `.apworld` now needs **no separate install step at all** -- the
  previous "manually copy ndspy into Archipelago's `lib/` folder"
  workaround is gone.

### Fixed
- Local ground_item/npc_gift/hm_tm/hidden_item locations whose item
  belongs to another player no longer hand over an unearned vanilla item
  when checked (write item id 0 instead, still fires check-detection).
- The 30 npc_gift/hm_tm locations with no detectable vanilla savedata
  flag are now constrained to only ever hold this player's own
  non-progression items, removing a multiworld-integrity risk.
- Fixed a duplicate ROM write in trainer party patching
  (`rom/trainerdata.py`).
- The BizHawk client no longer blindly trusts the first byte-signature
  match when locating Bag/save addresses in memory; it now verifies
  candidates look like real Bag data before trusting them, addressing a
  flakiness report from community testing.
- `client.py`'s `patch_suffix` is now set, so Archipelago's Launcher
  correctly recognizes `.apheartgold` files for "Open Patch".
- `minimum_ap_version` corrected to `0.6.7` (was accidentally set to the
  dev checkout's own version).
- `build.py`'s docstring no longer references unused `make`/`curl`
  tooling; documents Archipelago's native "Build APWorlds" tool as the
  recommended path for real releases.
- `build.py` now fails loudly if a `.apignore`-whitelisted directory
  (e.g. `data/`) is missing entirely at build time, instead of silently
  packaging an incomplete `.apworld`.

## [0.1.0] - 2026-08-11

### Added
- Archipelago world: items, locations, regions, and logic rules for
  Pokémon HeartGold (US).
- Randomization: wild encounters, trainer parties, evolutions
  (method-preserving), base stats (total-preserving), move stats
  (power/PP/accuracy, type-preserving), ground items, NPC gifts, HMs/TMs.
- Real ROM patch pipeline (`generate_output` / `.apheartgold`) producing
  a playable, patched `.nds` from a generated seed.
- BizHawk client (check detection, remote item delivery) via
  Archipelago's generic BizHawk connector.
- Configurable victory condition (Elite Four / Red / N badges).
- Build tooling (`data_gen.py`, `build.py`/`Makefile`) and a build-only
  GitHub Actions workflow.
- Setup guide and game info page for the Archipelago WebHost.

### Known limitations (see `docs/scope.md`)
- Starters are not randomized (no patchable source found in the ROM).
- Hidden items are not randomized (ROM substitution disabled pending an
  unresolved boot issue -- see `docs/architecture.md`).
- Gym badges are not randomized (HGSS represents them as a save-data
  flag, not a bag item).
- Trainersanity/Dexsanity are exposed as YAML options but currently do
  nothing -- no real Locations are created for them yet, so enabling
  them has no effect on generation or gameplay.
