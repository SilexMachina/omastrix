# Setup and use

## Setup status

This is a public preview. Install/update/removal commands are in the
[README](../README.md#install). A complete setup wizard and clean-machine
acceptance remain pending; see the [preview readiness report](publication-audit.md).

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
  SPIR-V headers. The installer reports missing dependencies before building.
- Optional Open WebUI: `uv` and network access to resolve its Python packages.
- GTT configuration: Limine tooling, `pkexec`, and a bootable recovery path.

Engine Install checks the newest published Halo build and compiles that exact
commit. Discovery failures are reported without installing an older baseline.
Existing installations are preserved until Update is explicitly selected.
`engine-pin.json` remains a reproducible development baseline. Optional Open WebUI first install selects
`open-webui==0.13.0` on Python 3.11; Check/Update is explicit and independent of
the plugin version. Node.js is needed for development tests.

## System controls

**Install** builds or installs the missing component. **Start** runs it;
**Stop** shuts it down. Stopping the engine releases its loaded model.
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

GTT is system RAM available to the GPU. The panel shows live usage and ceiling,
with supported ceiling choices based on the host's memory.

Changing the ceiling requires confirmation and a privilege prompt. It writes
boot/module configuration and rebuilds the boot image. **GTT change pending
reboot** remains visible until the configured ceiling matches the live session.
Reboot separately when ready, then check the reading.

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
File mutations are serialized; wait for an active download before loading or
deleting model files.

All catalog models remain visible. A model that exceeds the memory budget
shows its shortfall and has Load disabled. Fit estimates include weights,
context memory, and a desktop reserve; memory demand can still vary by workload.

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
Middle-click the bar pill to refresh status.

## Storage

| Location | Purpose |
| --- | --- |
| `~/models` | GGUF files. |
| `~/.config/omastrix/` | Engine record/environment, generated presets, added models, WebUI environment. |
| `~/.local/share/omastrix/` | Engine build/wrappers and separate Open WebUI installation/data. |
| `~/.local/state/omastrix/` | Job state and logs. |
| `~/.config/systemd/user/omastrix-llama.service` | Engine user unit. |
| `~/.config/systemd/user/omastrix-webui.service` | Open WebUI user unit. |

## Network and account safety

The engine binds to `127.0.0.1:8080`. New Open WebUI installs default to
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
SQLite database; custom `DATABASE_URL` configurations fail closed. Fresh-account
end-to-end acceptance remains part of the release checklist.

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
