# Changelog

Versions marked Unreleased are available from the default branch and have not
been published as separate GitHub releases.

## [0.5.0-preview.4] - Unreleased

- Install missing dependencies after confirmation and continue component setup automatically.

## [0.5.0-preview.3] - Unreleased

- Check for and install OmaStrix updates directly from the panel.
- Preserve local changes and show update progress and errors beside the controls.

## [0.5.0-preview.2] - Unreleased

- Select the newest published Halo build for fresh engine installations.
- Enable Open WebUI installation when its service has not been created yet.

## [0.5.0-preview.1] - 2026-11-05

- Initial public preview for Omarchy.
- Native strix-llama.cpp installation, service controls and updates.
- GGUF catalog downloads, direct-file links, progress, integrity checks,
  memory-fit estimates, model switching and selected-file deletion.
- Separate Open WebUI installation with local administrator setup and optional
  network access. Fresh installs default to loopback.
- GTT monitoring and supported-host ceiling choices with explicit authorization.
- Themed panel with keyboard navigation and inline feedback.
- Installation, WebUI and downloads on unsupported hardware, with a prominent
  warning and disabled engine startup, model loading and GTT changes.

See the [user guide](docs/user-guide.md) for preview limitations and operation.
