# OmaStrix

Design brief. Strix Halo on Omarchy, local models, one plugin.

Author: SilentD. Display name: **OmaStrix**. Install id: `silexmachina.omastrix`. That is the folder `omarchy plugin add` creates. Changing it later means every install path changes.

This file is the spec. Implementation follows it. The live bar pill `silentd.local-models` stays until OmaStrix does that job and SilentD says swap.

## What it is

OmaStrix composes, manages, and monitors the stack that already runs local models well on a Strix Halo Omarchy host.

That stack, named so the plugin does not invent a second one:

- One engine: native `halo-box/strix-llama.cpp`, Vulkan, RADV. Not Docker, not Ollama, not stock llama.cpp as the daily binary, not a container toolkit.
- One server on `127.0.0.1:8080`. A router with presets, one model loaded.
- GGUFs on local disk, pinned by revision and SHA-256.
- A GTT ceiling high enough for the model and low enough that the desktop still has RAM.
- A recipe per model: context, serve flags, optional extra files. The flags that matter on this iGPU are `-fa on`, `--load-mode none`, `-fit off` when context is explicit, and `-c` from the recipe.
- Loopback only. Remote use is a later front door, discussed before it exists.

A person with a fresh Omarchy install on a Strix Halo machine adds the plugin, runs core setup, and has a working local model. After that, the same panel is the command center: what is loaded, what fits, what is generating, what it cost in tokens.

## Who it is for

Omarchy on Strix Halo only. Ryzen AI Max 300 class, gfx1151, unified memory. Memory is soldered and varies by machine (this box is 128 GB; others are smaller). The plugin reads the machine in front of it. It does not assume 128 GB or this box's 110 GiB GTT number.

Detection fails closed. Maintained list: amdgpu present, device is a Strix Halo iGPU (8060S and the smaller Max iGPUs, gfx1151 / STRIX_HALO). PCI `1002:1586` is the 8060S on this box, not the whole family. Anything else gets one screen: this plugin is for Strix Halo. No NVIDIA path, no discrete Radeon path, no "best effort" llama.cpp.

Users of this plugin are expected to have an AI agent on the machine. The repo and the installed copy both carry instructions that agent can read. See **Agents**.

## What a new user does

1. `omarchy plugin add <repo url> --enable`
2. Open OmaStrix on the bar.
3. **Set up OmaStrix.** One wizard. Ends with a real completion from a small model.
4. Open the catalog. Click a recommended model to download it. Click load when it fits.

Adding the plugin only copies files and checks the manifest. Omarchy does not run plugin code at install. Setup is a button. The plugin process never runs as root. A step that needs a password opens a terminal and uses Omarchy's own prompt, and the prompt names the step.

## Core setup

Ordered. Each step shows what it found and what it is about to do. A failed step stops there with the reason. A finished step is not repeated.

1. **Host.** Strix Halo or stop. Show GPU name, MemTotal, current GTT, whether `/dev/dri` and `/dev/kfd` exist.
2. **Memory ceiling.** Show current GTT, the recommended ceiling, and leftover RAM if a model pins that ceiling. Leftover is MemTotal minus the ceiling, never "128 minus GTT". The reserve we trust is about 14 GiB of MemTotal left unpinable, because that is what kept a desktop alive on the 128 GB box. The wizard applies that reserve to the machine it is on. It does not copy 110 GiB onto a 64 GB machine. It does not offer 118 GiB on a 128 GB machine. It does not set `amd_iommu=off`.
   The change is two files, the same pattern already used here: a Limine drop-in under `/etc/limine-entry-tool.d/` and a modprobe file under `/etc/modprobe.d/`, then `limine-mkinitcpio`. The user confirms. Reboot is a separate confirm. The wizard does not reboot by itself. After reboot it checks `/proc/cmdline` and `mem_info_gtt_total` before calling the step done.
3. **Build tools.** `omarchy pkg` installs what the Vulkan build needs: compiler, cmake, ninja, vulkan-headers, vulkan-tools, spirv-headers. Configure fails without spirv-headers.
4. **Engine.** Clone `halo-box/strix-llama.cpp` at a pinned tag or commit recorded in this repo. Build Vulkan/RADV. Install wrappers in `~/.local/bin`. Do not export `VK_DRIVER_FILES` or `AMD_VULKAN_ICD` into the session. Omarchy ships an NVIDIA ICD for Hyprland and Steam even when no NVIDIA GPU is present; a session-wide pin hides it.
   Verify with `llama-cli --list-devices`. Expect RADV and a heap about the size of the GTT ceiling. That check is the pass/fail for this step.
5. **Proof model.** Download one small dense instruct GGUF, under about 5 GB, pinned revision, size and SHA-256 checked. First candidate to evaluate is a small Qwen3 instruct, because this fork already parses that family. The filename is not locked in this brief. The proof model exists to produce one completion. It is not the daily recommendation.
6. **Serve and prove.** Start the router on `127.0.0.1:8080`, one slot, the proof model loaded with its recipe. Send one short completion. Show the answer and the measured speed. Core setup is done.

Downloads do not load. The proof load is the one exception, and it is the last step of setup, after the user has watched the earlier steps.

## Catalog and recipes

The catalog is a file in the repo, versioned with the plugin. Refreshing recommendations means updating the plugin (or an explicit refresh that replaces that file after a check). We curate it. We do not vendor someone else's 40-card registry.

A recipe has:

- id, display name, publisher, quant
- tags: Coding, Web, Vision, General, Fast, Long context. A model can carry more than one. Vision means an optional projector exists. The projector is not downloaded or attached unless the user turns that on.
- size on disk
- pinned URL, revision, SHA-256 per file. Multi-shard recipes name the shard to pass and require the others beside it.
- a measurement, when we have one: machine class, context, tokens/sec, date. A number from a Ryzen AI Max+ 395 / 128 GB box is labeled that way. It is not shown as the speed of every Strix Halo. No measurement, no speed number. An estimate we did not measure is a lie.
- fit: weight, rough KV at the recipe context, anything else the recipe pins (projector, draft model)
- serve: context, flags, optional files and whether they default off

Click downloads. The plugin checks size and SHA-256, resumes a partial file, and leaves the running server alone. Click loads, with the recipe. Unfit rows stay visible and disabled, with the reason in numbers: GTT free, weight, KV, desktop reserve. Load refuses the same way if the picture changed since the panel opened.

Tiers follow the live machine. A model that does not fit is still listed, so the user can see what a larger Strix Halo box is for. It cannot be started.

Personal picks from this box (abliterated twins, a sidecar on another port, tailnet addresses) stay out of the public catalog unless SilentD later puts them there on purpose.

## Command center

The panel after setup:

- Engine up or down. One button to start or stop the router. After a reboot nothing is listening until this runs.
- Which model is loaded. Load and unload. One model at a time. Unload is explicit. Choosing another model unloads the current one first, and the panel says that before it does it.
- Inferring. A loaded slot with `is_processing` is generating. The bar pill shows it. The panel shows it.
- RAM and GTT. Used, ceiling, available, and leftover if the recommended ceiling is fully pinned. Same arithmetic as setup. A load that does not fit is refused before the server is asked, with those numbers.
- Tokens since this load, and lifetime tokens for that model. The engine's counters reset when the process dies. OmaStrix keeps the lifetime number itself, in `~/.local/state/omastrix/`, added from the engine while the model is loaded. If a build does not expose a count, the panel says the count is unavailable. It does not invent one.
- The recipe in force: context, flags, which optional files are on.

The bar pill stays short. Name, a generating mark, GTT. Urgent color when the engine is down or a load failed. The panel is the command center. Middle-click refreshes. Right-click is not a hidden settings dump.

## What it will not do

- Install Docker, Ollama, LM Studio, or a second llama.cpp.
- Bind the server to `0.0.0.0`.
- Edit kernel cmdline without a confirm, reboot without a confirm, or disable IOMMU.
- Run setup because the plugin was added or updated.
- Download a catalog model because setup finished.
- Attach a projector or a draft model because the file is on disk.
- Open WebUI, or rewire Hermes, in the same release as the wizard. Those are later, and each one waits for a yes.
- Pretend to be a general local-AI plugin. Sero's Local AI covers discrete cards and containers. OmaStrix covers this host class and this engine.

## How it is built

Same shape as a panel that has to stay honest under a theme swap: a backend prints state, a view function turns state into rows, QML draws the rows.

| Piece | Role |
|---|---|
| `bin/omastrix` | Verbs. Detect, setup steps, download, load, unload, snapshot. Prints JSON. |
| View module | Pure functions. Snapshot in, screen out. No side effects. Tested without the panel. |
| `Panel.qml` | Draws the screen. Sends a verb. Does not compute fit. |
| `catalog.json` | The recipes. |
| `AGENTS.md` | Instructions for an agent on the machine. |

State: `~/.local/state/omastrix/` (ledger, setup progress, download status).

Settings that are per-user and not a recipe: `~/.config/omastrix/`.

Bar placement and the refresh interval live in `~/.config/omarchy/shell.json`, like any other widget.

The backend is the only thing that talks to the server, sysfs, and the package manager. The panel polls `omastrix snapshot`. Faster while setup is running, while the panel is open, or while a model is generating. Slow while the pill is idle.

Load goes through the router the way this binary already accepts, not through a path that this fork swallows. The recipe names the call. If a future engine pin changes the call, the recipe and the backend change together, and the panel does not grow a special case.

## Look

Omarchy's own panels are the bar. Agents is the reference: a hero line, section headers, meters, monospace rows, a keyboard cursor, theme color, no private palette. `omarchy dev ui-preview` is the component gallery.

The panel uses the shell UI kit (`qs.Ui`, `qs.Commons`): `Panel`, `PanelHero`, `PanelSectionHeader`, `PanelActionButton`, `Color`, `Style`. Colors come from `Color` and from the bar facade (`foreground`, `background`, `accent`, `urgent`, font). No hex palette in our QML. Light themes have to work. Tokyo Night and Nord are not the only skins.

Theme change already rewrites `colors.toml` and `shell.toml` and the `Color` singleton rebinds. We do not cache a color at startup. If a third-party widget cannot import `qs.Ui` — first spike, before any custom drawing — we read the same theme files `Color.qml` reads and watch the current-theme path. We still do not invent a palette.

Keyboard: `j`/`k` move, Enter acts, Esc closes, the same way other Omarchy panels do. Mouse works. The panel is usable without it.

The pill uses the bar's font and foreground. It does not draw its own chrome.

## Agents

Two copies of the same instructions:

- `AGENTS.md` at the root of the repo, for an agent working on OmaStrix.
- The same file installed where an agent on a user's machine can find it without cloning the repo: the plugin directory, plus `omastrix help` printing the short contract.

The contract says:

- This is Strix Halo on Omarchy. One engine. One server at `http://127.0.0.1:8080/v1`. One model loaded.
- `omastrix snapshot` is the state. Read that before claiming a model is loaded, a download finished, or GTT changed.
- Verbs: status, setup status, download, load, unload, fit. Download does not load. Load of an unfit recipe fails with the numbers.
- Do not install Docker or a second engine. Do not bind the server off loopback. Do not set `amd_iommu=off`. Do not raise GTT except through the wizard's formula, and only after the user confirms. Do not pass a projector or a draft file unless the user asked.
- Where models, the engine tree, and the ledger live.

An agent opening a coding session pointed at the endpoint is a later slice. Until then the agent reads the contract and uses the verbs. We do not rewrite the agent's own config as a side effect of setup.

## Shipping it

SilentD has not shipped an open source project before. The mechanics, in the order they actually happen:

The private repo is [SilexMachina/omastrix](https://github.com/SilexMachina/omastrix). `qc-onyx` `gh` is logged in as LimetreeLabs, an admin of that org. The install line, once a release exists, is `omarchy plugin add https://github.com/SilexMachina/omastrix`. There is no release yet, so that command is not for use.

The repo stays **private** until he says it is public. The manifest author can still say SilentD. The install id is `silexmachina.omastrix`.

**License:** MIT. Same as the current pill, same as the usual Omarchy plugin.

**Version:** a git tag, `v0.1.0` and up. `manifest.json` `version` matches the tag. Users update with `omarchy plugin update`, which fast-forwards the checkout. There is no separate installer to maintain.

**Release notes:** `CHANGELOG.md` in the repo, dated, written as what changed for a person using the panel. A GitHub Release is that same text attached to the tag. No notes, no tag.

**Engine pin:** a tag or commit hash in the repo, updated on purpose. Setup never builds floating `main`.

The remote exists and is private. Tags come at cut 0.5, and only with notes. He still has to say when it becomes public.

Issues on GitHub are for bugs and recipe requests. A short `CONTRIBUTING.md` says how to add a recipe: a measurement on real Strix Halo hardware, or the row ships without a speed number.

## Order of work

| Cut | Done when |
|---|---|
| 0.1 | Repo layout, manifest validates, host probe, themed empty panel, pill, `AGENTS.md`. Old pill still on the bar. |
| 0.2 | Core setup through one proof completion on this machine, including the GTT offer with a confirm and a reboot he starts. |
| 0.3 | Catalog, click-to-download with hash check, load/unload with the recipe, unfit reason before the load. |
| 0.4 | Inferring mark, tokens since load, lifetime ledger. |
| 0.5 | First tagged release. Public only if he says so. |
| Later | Open an agent on the endpoint without editing its config. Optional front door for other machines. More measured recipes, including smaller Strix Halo SKUs when we have a number from one. |

Each cut is usable on this box before the next one starts. A cut that needs a reboot or a password stops and asks.

## Still his

- When the repo becomes public.
- Which small GGUF is the proof model, once we have named a file and checked it loads.
- Which catalog rows ship in 0.3. Measurements we already have from this 395 / 128 GB box can be labeled and included. They are not a promise for every Strix Halo.
