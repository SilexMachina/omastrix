# Operating rules

Read [DESIGN.md](DESIGN.md), [development](docs/development.md), and the relevant
code before editing. Keep project documentation in this repository; do not
maintain a competing spec in external agent notes.

- The maintainer authorized the first public prerelease, `0.5.0-preview.1`.
  Keep main installable for preview users. Further tags/releases and history
  rewrites require authorization; never publish unrelated data or credentials.
- Unsupported hardware keeps the panel, engine installation, WebUI and model
  downloads available. Show the prominent hardware warning. Engine startup,
  model loading and GTT changes require supported Strix Halo hardware in both
  the backend and UI; installation alone must not claim GPU verification.
- Inspect `bin/omastrix snapshot` before asserting live model, service, or GTT
  state. Snapshot can refresh local presets/state; it must not download or load.
- Never install, update, download, load, unload, delete, change GTT, reboot, or
  start/stop/restart a service merely to verify an edit. Obtain authorization for
  those actions. A restart loses the loaded model. Do not enable linger.
- Normal engine Install resolves the newest published Halo build tag, then builds
  that exact commit. Fail clearly if discovery fails; do not silently install an
  older pin. Keep `engine-pin.json` as the reproducible baseline, unchanged unless
  approved. Never downgrade an existing installation. Use the OmaStrix full-path
  wrapper, not a `PATH` binary or another engine checkout.
- Keep RADV settings process-local in `~/.config/omastrix/llama.env`; never export
  `VK_DRIVER_FILES` globally. Keep llama on `127.0.0.1:8080`.
- Adding a model does not download. Downloading does not load. Never scan
  `~/models` with `--models-dir`. Poll model-scoped routes with `autoload=false`.
  Load uses the pinned fork's `/props?model=` flow, not `/models/load`.
- Confirm replacement loads and deletions. Delete only the selected recipe's
  files inside `~/models`, preserving unrelated files and optional sidecars.
- GTT changes require confirmation and privilege escalation, not root plugin
  execution. Do not offer 118 GiB, disable IOMMU, or copy a large host's ceiling
  onto a smaller one. Reboot is a separate user decision.
- Do not touch unrelated Open WebUI installs, secrets, agent configuration, or
  the existing `silentd.local-models` pill without approval.
- No fabricated verification or benchmark claims. Publish speed only with dated,
  reproducible hardware/engine/recipe evidence. Label fresh-install gaps.
- Use offline isolated tests first. No global Git identity changes. Review the
  diff and update the current changelog section with user-visible changes.
