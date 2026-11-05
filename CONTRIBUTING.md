# Contributing

OmaStrix is in private development with no published release. Access to the
repository does not authorize publication, tags, releases, or machine changes.

- Read [Design](DESIGN.md), [development](docs/development.md), and
  [operating safety](AGENTS.md) before changing behavior.
- Keep changes focused. Include isolated tests for tooling/backend changes and
  update the current [changelog](CHANGELOG.md) section for user-visible changes.
- Follow Omarchy's shared UI components/theme. Provide evidence for light/dark,
  narrow-screen, keyboard, busy, failure, and confirmation states when changing UI.
- Do not run real installs/downloads/model actions, privileged GTT operations,
  service restarts, or reboots without explicit approval for that test.
- Follow the [recipe evidence requirements](docs/development.md#recipes-and-evidence).
  No dated reproducible benchmark evidence means no public speed claim.
- Keep docs canonical in this repo and link instead of duplicating specifications.
- Do not include credentials, prompts/chat history, private endpoints, machine
  configuration, or unrelated personal documents in patches or issue reports.

For a bug, provide the version/commit, environment, reproduction steps, expected
versus observed behavior, and a redacted error. Use [SECURITY.md](SECURITY.md) for
security-sensitive reports. Release decisions follow [the release guide](docs/releasing.md).
