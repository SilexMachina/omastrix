# OmaStrix

Local AI for Strix Halo on Omarchy.

OmaStrix puts model downloads, GPU memory, the native
[`halo-box/strix-llama.cpp`](https://github.com/halo-box/strix-llama.cpp) engine,
and Open WebUI in one bar panel.

## Preview status

**Experimental preview software for public testing.** The current version is in
[manifest.json](manifest.json), with changes in [CHANGELOG.md](CHANGELOG.md). Fresh-machine,
reboot/recovery and full catalog acceptance are still in progress. Keep a
recovery path before changing boot/GTT settings. See the
[preview readiness report](docs/publication-audit.md) and
[stable-release checklist](docs/releasing.md).

Inference requires a supported AMD Strix Halo iGPU, amdgpu and Vulkan/RADV.
Other Omarchy machines can install the same plugin, build the engine, use
Open WebUI and download models. They show a prominent **Hardware Unsupported**
warning; engine startup, model loading and GTT changes are disabled. Installing
the engine on another GPU does not establish inference support.

## Install

On an up-to-date Omarchy installation with the plugin shell:

```sh
omarchy plugin add https://github.com/SilexMachina/omastrix --enable
```

Choose a bar placement, then open OmaStrix. Installing the plugin does not
install the engine/WebUI, download weights, start a service, or change GTT.
Those are explicit panel actions.

Before building the native engine, install the build prerequisites:

```sh
omarchy pkg add base-devel git cmake ninja vulkan-headers vulkan-tools spirv-headers shaderc
```

Strix Halo inference also requires Mesa's `vulkan-radeon` driver. Optional
Open WebUI installation requires `uv` (`omarchy pkg add uv` if missing). Engine
installation compiles from source and can take several minutes. No root plugin
process is required; installing system dependencies and changing boot settings
use the platform's authorization prompts.

### Update or remove

```sh
omarchy plugin update silexmachina.omastrix
omarchy plugin remove silexmachina.omastrix
```

Plugin updates follow the repository's default branch and ask for confirmation.
A normal `omarchy update` does not currently update Git-managed plugins. The
panel's engine/WebUI update buttons manage those components separately.

Removing the plugin removes its panel/checkout. It preserves downloaded models,
application installs, user services, settings and chats. Stop OmaStrix services
before removal if you no longer want them running:

```sh
systemctl --user stop omastrix-llama.service omastrix-webui.service
```

## Features

- Install, start and stop the engine and optional Open WebUI independently.
- Install, load, unload and delete GGUF models from a curated library.
- Add a model using its direct GGUF download link.
- See model state, download progress and live GTT memory usage.
- Configure a GTT ceiling appropriate for supported hardware, with confirmation
  and a pending-reboot indicator.
- Check for engine and Open WebUI updates.
- Keep WebUI local, or explicitly allow network access after administrator setup.

Models live in `~/models`. Installing downloads a model; **Load** is a separate
action. The engine runs one model at a time. New WebUI installs listen on
`127.0.0.1:3000`; create the administrator locally before opting into network
access. OmaStrix provides no TLS or firewall policy.

## Documentation

This repository is the canonical home for project documentation.

- [User guide](docs/user-guide.md): setup, controls, storage, troubleshooting.
- [Design](DESIGN.md): architecture and UI/safety contract.
- [Development](docs/development.md): tests and recipe evidence.
- [Releases](docs/releasing.md), [changelog](CHANGELOG.md).
- [Component and model licenses](docs/licenses.md).
- [Contributing](CONTRIBUTING.md), [security](SECURITY.md), [agent rules](AGENTS.md).

Install ID: `silexmachina.omastrix`. To open an enabled panel from the terminal:

```sh
omarchy-shell silexmachina.omastrix open
```

## License

[MIT](LICENSE). The engine, Open WebUI and model weights retain their own
licenses. Qwen3.8-Flash-Next has separate commercial-use conditions; review the
[license summary](docs/licenses.md#qwen38-flash-next-userbusiness-review-required)
before commercial use.
