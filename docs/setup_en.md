# Pokémon HeartGold Setup Guide

## Required Software

- [Archipelago](https://github.com/ArchipelagoMW/Archipelago/releases)
- A US Pokémon HeartGold ROM. The Archipelago community cannot provide
  this. `SoulSilver`, other regions, and other revisions will be rejected
  when you patch your game -- the client will tell you if your ROM doesn't
  match.
- [BizHawk](https://tasvideos.org/BizHawk/ReleaseHistory) version 2.10 or
  later
- The [`ndspy`](https://github.com/RoadrunnerWMC/ndspy) Python library
  (used to read/patch the ROM). If you installed Archipelago from the
  official Windows release (the common case -- a frozen/portable build),
  it has no `pip`-accessible environment to install into, so this world
  cannot import `ndspy` unless you add it manually:

  1. Download `ndspy`'s source (e.g. `pip download ndspy --no-deps -d .`
     from any machine with Python/pip, then unzip/extract the wheel, or
     clone [its repo](https://github.com/RoadrunnerWMC/ndspy)) to get a
     plain `ndspy/` folder (pure Python, no compiled files needed).
  2. Copy that `ndspy/` folder into your Archipelago install's `lib/`
     folder, next to the `worlds/` folder already there (e.g.
     `C:\ArchipelagoWhatever\lib\ndspy\`).
  3. Restart the Archipelago Launcher. Pokémon HeartGold should now
     appear in `Generate Template Options` / `Option Creator`.

  (If you built/installed Archipelago from source into your own venv
  instead, a plain `pip install ndspy` into that venv is enough --
  skip the manual copy above.)

  `ndspy` is GPLv3-licensed; this project only depends on it as an
  external tool you install yourself, it is never bundled inside
  `pokemon_heartgold.apworld`.

### Configuring BizHawk

Once you have installed BizHawk, open `EmuHawk.exe` and change the following settings:

- Go to `Config > Customize`. On the Advanced tab, disable (if it is not already) `Auto Save Ram`. Having this option
enabled may not allow BizHawk to properly save for NDS games.
- Under `Config > Customize`, check the "Run in background" option to prevent disconnecting from the client while you're
tabbed out of EmuHawk.
- Open an `.nds` file in EmuHawk and go to `Config > Controllers…` to configure your inputs. If you can't click
`Controllers…`, load any `.nds` ROM first.
- Consider clearing keybinds in `Config > Hotkeys…` if you don't intend to use them. Select the keybind and press Esc
 to clear it.


## Generating and Patching a Game

1. Add `pokemon_heartgold.apworld` to your `custom_worlds` folder in your Archipelago install. It should not be in
   `lib/worlds`.
2. Create your options file (YAML). You can make one by choosing `Generate Templates`
   from the Archipelago Launcher. From there, you can edit the `.yaml` in any text editor.
3. Follow the general Archipelago instructions
   for [generating a game on your local installation](https://archipelago.gg/tutorial/Archipelago/setup/en#on-your-local-installation).
   This will generate an output file for you. Your patch file will have the `.apheartgold` file extension and will be
   inside the output file.
4. Open `ArchipelagoLauncher.exe`
5. Select "Open Patch" on the left side and select your patch file.
6. If this is your first time patching, you will be prompted to locate your vanilla ROM.
7. A patched `.nds` file will be created in the same place as the patch file.
8. On your first time opening a patch with BizHawk Client, you will also be asked to locate `EmuHawk.exe` in your
   BizHawk install.

If you're playing a single-player seed, and you don't care about autotracking or hints, you can stop here, close the
client, and load the patched ROM in any emulator. However, for multiworlds and other Archipelago features, continue
below using BizHawk as your emulator.

## Connecting to a Server

By default, opening a patch file will do steps 1-5 below for you automatically. Even so, keep them in your memory just
in case you have to close and reopen a window mid-game for some reason.

1. Pokémon HeartGold uses Archipelago's BizHawk Client. If the client isn't still open from when you patched your
game, you can re-open it from the launcher.
2. Ensure EmuHawk is running the patched ROM.
3. In EmuHawk, go to `Tools > Lua Console`. This window must stay open while playing.
4. In the Lua Console window, go to `Script > Open Script…`.
5. Navigate to your Archipelago install folder and open `data/lua/connector_bizhawk_generic.lua`.
6. The emulator and client will eventually connect to each other. The BizHawk Client window should indicate that it
connected and recognized Pokémon HeartGold.
7. To connect the client to the server, enter your room's address and port (e.g. `archipelago.gg:38281`) into the
top text field of the client and click Connect.

You should now be able to receive and send items. You'll need to do these steps every time you want to reconnect. It is
perfectly safe to make progress offline; everything will re-sync when you reconnect.

## Common Issues

1. **Problem**: "No handler was found for this game." in the client. **Solution**: Update to at least BizHawk version 2.10.
2. **Problem**: The client says my ROM doesn't match. **Solution**: Make sure you're patching a US Pokémon HeartGold
   ROM, not SoulSilver, another region, or another revision.
3. **Problem**: Pokémon HeartGold never shows up in `Generate Template Options` / `Option Creator`, even after
   installing the `.apworld`. **Solution**: this almost always means `ndspy` isn't importable by Archipelago -- see
   "Required Software" above. Check your `logs/Launcher_*.txt` for a `ModuleNotFoundError: No module named 'ndspy'`
   to confirm.
