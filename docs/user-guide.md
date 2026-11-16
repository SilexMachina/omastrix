# Setup and use

## Setup status

This is a public preview. Install/update/removal commands are in the
[README](../README.md#install). A complete setup wizard is not yet available.
Fresh-install, reboot/recovery and full catalog coverage remain preview limitations.

On unsupported hardware, the same panel shows a prominent warning. Engine
installation, WebUI and model downloads remain available for testing. Engine
startup, model loading and GTT changes remain disabled. Engine installation
there skips Strix GPU acceptance and does not claim inference support.

### Requirements

- Omarchy's plugin shell and a working user systemd session.
- For inference/GTT: a supported Strix Halo iGPU, amdgpu, `/dev/dri`, and Vulkan/RADV.
  Other hosts can test installation, WebUI and model downloads.
- Python 3, Git, curl, `lspci`, `ss`, and `systemctl`.
- Engine build tools: C/C++ compiler, CMake, Ninja, Vulkan headers/tools, and
  SPIR-V headers. **Install** offers to install missing system packages.
- Optional Open WebUI: `uv` and network access to resolve its Python packages.
  **Install** offers to install `uv` when needed.
- Package installation: Omarchy's package manager and a working `pkexec`
  authorization prompt.
- GTT configuration: Limine tooling and a bootable recovery path.

Engine Install checks the newest published Halo build and compiles that exact
commit. Discovery failures are reported without installing an older baseline.
Existing installations are preserved until Update is explicitly selected.
`engine-pin.json` records a reproducible engine baseline. Optional Open WebUI first install selects
`open-webui==0.13.0` on Python 3.11; Check/Update is explicit and independent of
the plugin version.

## Bar icon

The chip-and-S logo shows model activity:

- **Empty:** gray, with the chip and S at equal brightness; no model is loaded.
- **Ready:** green; a model is loaded and idle.
- **Active:** the theme accent with four small corner marks; the engine is
  processing an inference request.

The icon keeps a fixed size and does not blink. Hover for the status in words;
click to open the panel for memory readings and controls. Initial or unavailable
readings use the neutral gray icon with a checking/unavailable tooltip, without
claiming a model is idle. Stopped or uninstalled engines show Empty. Unsupported
hardware details remain inside the panel.

The recommended installation places the icon directly in the bar's right-hand
section. To move an existing icon there:

```sh
omarchy bar move silexmachina.omastrix --section right
```

## System controls

**Install** builds or installs the missing component. If prerequisites are
missing, review the package list and choose **Confirm**, then authorize the
system package installation. OmaStrix continues setup in the background and
shows installation progress. **Cancel** leaves packages unchanged; denied or
failed authorization reports an error beside that component. A failed package
installation does not start the build. Retry **Install** after resolving it.

**Start** runs the component; **Stop** shuts it down. Stopping the engine releases
its loaded model.
**Open** launches the component's browser interface while it is running.

The **OmaStrix** row checks and updates the plugin itself. Choose **Check updates**,
then **Update** when a newer revision is available. The app uses Omarchy's native
updater without the terminal diff viewer. It preserves engine/WebUI services and
models; the panel may close briefly while Omarchy reloads plugins. Local checkout
changes or divergent history block an update and are reported beside the row.
Checks are manual; normal status polling does not contact GitHub. Git-managed
installation is required.

For strix-llama.cpp and Open WebUI, **Check updates** refreshes the available version beside the component name.
To apply an update, stop that component and choose **Update**. Start it again
when ready. The engine uses published Halo build tags; Open WebUI uses stable
Python-package versions. Each has its own version, independent of OmaStrix.

### GPU memory

GTT limits how much shared system RAM the GPU may use. Physical RAM remains
shared with the CPU and desktop. The panel shows live usage and ceiling, with
supported choices based on the kernel's reported system memory.

Firmware's dedicated VRAM / UMA framebuffer reservation reduces that reported
memory. A large graphics-memory preset can therefore hide the larger GTT
choices. For Linux GTT use, consider the lowest dedicated reservation supported
by your device vendor, often 512 MiB or 1 GiB, instead of a large fixed carve-out.
Record the original BIOS setting and keep a recovery path. OmaStrix does not
change BIOS settings. The 110 GiB option requires at least 124 GiB of reported
system RAM; a disabled choice explains the requirement and detected amount.

Changing the ceiling requires confirmation and a privilege prompt. It writes
boot/module configuration and rebuilds the boot image. **GTT change pending
reboot** remains visible until the configured ceiling matches the live session.
Reboot separately when ready, then check the reading. Current GTT changes
execute code from the user-owned plugin checkout with administrator approval;
protect that checkout and review updates before granting the prompt. See the
[authorization boundary](../SECURITY.md#gtt-authorization-boundary).

## Models

1. **Start** strix-llama.cpp.
2. Choose a model and select **Install** to download its files into `~/models`.
3. Select **Load** when the download finishes. Switching models asks for
   confirmation before unloading the current one.
4. Use the engine interface at `http://127.0.0.1:8080`, or start and open
   OmaStrix's optional Open WebUI at `http://127.0.0.1:3000`.

**Unload** releases the model while keeping the engine running. **Delete** asks
for confirmation, unloads that model if needed, and removes its recipe files.
Other files in the same directory, including optional sidecars, are preserved.
Downloads and file mutations are serialized per model and shared file path.
You can download one model while loading or deleting another whose files do not
overlap. Wait for the selected model's active operation before changing its files.

Unchanged files reuse recorded SHA-256 verification. Replacements, edits and
changed file identities trigger another hash check. For an explicit verification
without downloading, run this from the checkout, using the model's catalog ID:

```sh
bin/omastrix library-verify qwen35-4b
```

Verification runs in the background and records its result under
`~/.local/state/omastrix/`. Large models can take time to hash.

All catalog models remain visible. A model that exceeds the memory budget
shows its shortfall and has Load disabled. Fit compares weights and estimated
context memory with the smaller of the GTT ceiling and physical RAM after the
desktop reserve. The reserve is kept outside that budget once. Other workloads,
runtime overhead and context usage can still affect whether a model loads.

Models carry their own licenses. **Qwen3.8-Flash-Next** has additional conditions
for commercial MaaS and AI-assistant businesses, including affiliate activity.
Review [component and model licenses](licenses.md) before commercial use.

### Add a model

Paste a direct HTTPS link to one complete `.gguf` file and choose **Add model**.
Hugging Face file-page links are converted to download links. Repository pages,
projectors, and individual split shards are refused.

Add records a row and inspects remote metadata. **Install** and **Load** remain
separate actions. User-added models use estimated context memory; a locally
computed checksum establishes local file integrity, while publisher authenticity
requires a trusted source checksum.

### Feedback and keyboard

Actions use bordered buttons. Errors stay beside the affected service or model
until dismissed or retried. Confirmations provide **Confirm** and **Cancel**.

Tab/Shift+Tab and j/k move through controls; Enter/Space activate the focused
button. The link editor accepts normal text. Escape leaves the editor, cancels
a pending confirmation, or closes the panel. Scroll to reach lower rows.
Middle-click the bar icon to refresh status.

## Storage

| Location | Purpose |
| --- | --- |
| `~/models` | GGUF files. |
| `~/.config/omastrix/` | Engine record/environment, generated presets, added models, WebUI environment. |
| `~/.local/share/omastrix/` | Engine build/wrappers and separate Open WebUI installation/data. |
| `~/.local/state/omastrix/` | Job state and logs. |
| `~/.config/systemd/user/omastrix-llama.service` | Engine user unit. |
| `~/.config/systemd/user/omastrix-webui.service` | Open WebUI user unit. |

`~/models` may be a symlink to a larger drive. OmaStrix resolves the model root
and confines each model's files beneath it; symlinks inside model paths are
refused. User-directory ancestors such as `$HOME`, `~/.config` and `~/.local`
may also be symlinked. OmaStrix's own config, data and state directories and
managed descendants must remain regular directories and files.

Successful engine and WebUI updates retain the current and one previous managed
version. Cleanup preserves versions referenced by running processes, modified
or unrecognized files, and older trees without a managed inventory. Those older
trees may need manual review before deletion; failed updates do not trigger cleanup.

### Full removal

Removing only the plugin preserves application data. The following additional
steps permanently remove the engine/WebUI installations, settings, credentials,
Open WebUI chats and job state. Back up anything you need first.

```sh
systemctl --user disable --now omastrix-llama.service omastrix-webui.service
omarchy plugin remove silexmachina.omastrix --yes
rm -f ~/.config/systemd/user/omastrix-llama.service ~/.config/systemd/user/omastrix-webui.service
systemctl --user daemon-reload
rm -rf ~/.local/share/omastrix ~/.config/omastrix ~/.local/state/omastrix
```

Models remain in `~/models` or its symlink target. Delete only the model files
you no longer need; that directory may contain files used by other applications.
System build tools and graphics packages remain installed because other
applications may depend on them.

## Network and account safety

The engine router binds to `127.0.0.1:8080`; model workers also listen on
loopback. This preview does not configure engine API authentication. Browser
pages with access to loopback and local processes can issue direct engine
requests. Keep these ports private and avoid forwarding them. WebUI's login
covers its own interface. See the [engine API boundary](../SECURITY.md#engine-api-access).

New Open WebUI installs default to
**This device** (`127.0.0.1:3000`), with authentication enabled and general signup
disabled. Start it and open the local page to create the first administrator.

To allow other devices, stop Open WebUI, choose **Local network** under Access,
and confirm. This selects `0.0.0.0:3000` (all IPv4 interfaces, including VPN
interfaces). OmaStrix checks for an administrator before saving that choice and
again when its generated wrapper starts. Start the service when ready. Choose
**This device** while stopped to restrict access again. Neither choice restarts
the service. Existing installations retain their configured host.

OmaStrix provides no TLS or firewall rules. Keep port 3000 private and restrict
access to trusted clients. Network enablement currently requires the local
SQLite database; custom `DATABASE_URL` configurations fail closed.

OmaStrix manages its own Open WebUI copy. Unrelated installations remain
independent. Keep environment files and databases private.

## Troubleshooting

Run `bin/omastrix snapshot` from the checkout for current JSON state. This can
refresh generated presets and local status records.

Inspect the affected component's log under `~/.local/state/omastrix/` or its user
unit's journal. Resolve the reported cause: missing build dependency, occupied
port, unavailable GPU memory, invalid link, or corrupt download. Preserve running
workloads while investigating.

Bug reports should include the plugin and engine versions, OS/shell version,
hardware/RAM/GTT, redacted error, and reproduction steps. Remove prompts,
credentials, signed URLs, and private paths before sharing. Use the
[security process](../SECURITY.md) for sensitive findings.
