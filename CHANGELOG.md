# Changelog

Versioned change tracking begins with this development prerelease. Earlier
manifest versions `0.1.0`, `0.2.0` and `0.3.0` identified internal development
cuts, not published releases; their commits remain in Git history. The first
planned release is 0.5.0.

## [0.5.0-preview.2] - Unreleased

- Fresh engine installs select the newest published Halo build; enable WebUI installation when its service has not been created yet.

## [0.5.0-preview.1] - 2026-11-05

First public preview for testing on Omarchy. Stable-release hardware and recovery
acceptance is still in progress.

### Included

- Native strix-llama.cpp installation, explicit service controls and updates.
- A themed two-pane panel with bordered actions, keyboard navigation, scrolling
  and feedback beside the affected component.
- GGUF catalog downloads, direct-file links, progress, integrity checks, fit
  estimates, confirmed model switching and selected-file deletion.
- Separate Open WebUI installation, local administrator setup, and confirmed
  network access after administrator creation. Fresh installs default to loopback.
- GTT monitoring and supported-host ceiling choices with explicit authorization.
- Versioned documentation, offline tests and GitHub Actions checks.

### Unsupported hardware

- The same plugin keeps installation, Open WebUI and model downloads available.
- A prominent red hardware warning appears beside the title.
- Engine Start is red and disabled after installation. Backend and generated
  launcher guards also refuse unsupported engine startup; model loading and
  GTT changes remain unavailable.
- Engine installation on an unsupported host does not claim Strix GPU validation.

### Preview limitations

- Fresh-machine Strix Halo setup, privileged GTT/reboot recovery, complete
  lifecycle acceptance and pinned-engine completions for every catalog recipe
  remain open. Fit values are estimates and no unverified speed claims are shown.
- Build dependencies must be installed separately; no complete setup wizard yet.
- Open WebUI network access has no TLS/firewall management and currently requires
  a local SQLite administrator account. Existing host settings are preserved.
- Persistent lifetime token accounting is pending.
- Plugin updates follow the default branch through `omarchy plugin update`;
  there is no automatic plugin update notification or separate preview channel.

Install with `omarchy plugin add https://github.com/SilexMachina/omastrix --enable`.
See the README for prerequisites, update/removal commands and testing guidance.

## [0.4.0-dev.3] - Unreleased

- Default Open WebUI to this device, add confirmed network access after administrator setup, and harden preset, deletion and installer safety.

## [0.4.0-dev.2] - Unreleased

- Keep Refresh visually steady during automatic status polling.

- Preserve model-action keyboard focus during polling; refuse deletion during active downloads; verify legacy WebUI migration and tolerate malformed engine metadata.

## [0.4.0-dev.1] - Unreleased

### Changed

- Redesign the panel with aligned System rows, shared bordered action buttons,
  a scrollable model table, and layouts that follow Omarchy's theme.
- Show errors and Confirm/Cancel controls beside the affected service or model.
  Remove the last-action footer and routine reassurance messages.
- Consolidate project documentation in this repository: user guide, design,
  development, contribution/security policies, and release checklist.
- Adopt SemVer with the manifest as version source. Add tested metadata
  check/bump commands and an offline GitHub Actions workflow.
- Pin catalog downloads to immutable revisions. Check sizes, SHA-256 values,
  parameter provenance, and measurement metadata. Remove unsupported speed
  claims and performance labels.
- Wire asynchronous engine installation to the approved first-install pin.

### Fixed

- Align service action columns and resize buttons after live font changes.
- Keep keyboard navigation separate from link-editor input; handle Escape once
  and scroll focused controls into view.
- Return process failures consistently, including failed subprocesses and
  background jobs; keep job errors available to the panel.
- Serialize engine/WebUI jobs and model-file mutations. Refuse competing
  operations while weights or application files are in use.
- Validate model paths, download-state identifiers, and installer destinations;
  reject symlink redirection and non-HTTPS download redirects.
- Verify existing model-file integrity and wait for observed router unload.
  Treat malformed or transitional model/service state conservatively.
- Preserve GTT configuration after a failed boot-image rebuild and constrain
  ceiling choices to the host's available RAM.
- Validate engine source/build/device checks before publishing installed files.
- Reject malformed changelog sections and multiline bump notes before writes.

### Development baseline

Earlier work provides host/GTT monitoring, independent engine and Open WebUI
services, update controls, catalog downloads, explicit load/unload, confirmed
selected-file deletion, and direct-GGUF link addition. Status polling includes
`autoload=false` to keep unloaded models unloaded.

### Known limits

Release acceptance and remaining issues are tracked in the
[publication audit](docs/publication-audit.md) and
[release checklist](docs/releasing.md). Persistent lifetime token accounting is
pending.
