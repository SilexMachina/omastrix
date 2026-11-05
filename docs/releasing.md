# Versions and release readiness

The first authorized public release is **0.5.0-preview.1**, an experimental
prerelease. Stable 0.5.0 remains subject to the acceptance checklist below.
Incomplete real-hardware coverage is disclosed in preview notes; it does not
become a claim of stable support. Further releases and history rewrites require
maintainer approval.

## Single source and SemVer

`manifest.json`'s `version` is the single source of the current plugin version.
Use strict SemVer without a leading `v`, with `-dev.N` for working prereleases
`-preview.N` for public testing and `-rc.N` for release candidates. Increment `N` numerically when
cutting a new prerelease. `0.4.0-dev.1` sorts below `0.4.0`, which sorts below
`0.5.0-dev.1`; preparing `0.5.0` does not claim a prior `0.4.0` release.
Before 1.0, minor versions may change interfaces; patch versions are for
compatible fixes. At and after 1.0, major/minor/patch mean incompatible API
changes, compatible additions, and compatible fixes respectively. The plugin's
contract includes command/JSON interfaces, manifest/settings and documented
lifecycle behavior. Do not reinterpret old internal cuts/commits as published
releases or fabricate dates for them.
Engine commits/build tags and Open WebUI versions are independent of the plugin
version. A plugin bump must not modify `engine-pin.json`.

`CHANGELOG.md` begins with a version-matching `Unreleased` section and real change
notes. Older unreleased sections remain unreleased; they are not claimed tags.
Add user-visible notes there throughout development rather than only at release.

## Offline metadata tool

From the repository root:

```sh
python3 tools/release.py version
python3 tools/release.py check
python3 tools/release.py bump 0.4.0-dev.2 --note 'Describe the next change.'
```

Bump is a **dry run by default**. Add `--write` only when ready to edit metadata.
It requires a higher SemVer precedence and a nonempty, single-line note (including
rejection of Unicode line separators), updates only the manifest and changelog,
and preserves previous unreleased notes. Every level-two changelog section must
have a strict SemVer heading and an Unreleased marker or valid calendar date;
malformed sections are errors, not silently ignored text.
Build metadata does not make a version newer. `--root PATH` before the command
can target a separate test checkout. No network, Git, installs, services, tags,
or publishing operations are part of the tool.

The tool validates metadata, not release readiness. It permits preparing a
stable candidate version but cannot authorize releasing it. The two metadata
writes are not a transaction; if interrupted or one write fails, inspect both
files and restore consistency before rerunning `check`. `check` also accepts an
actual release section dated `YYYY-MM-DD`, validating the date format/calendar
only; it does not establish that the release happened or was approved.

## Required before stable 0.5.0

The dated [publication audit](publication-audit.md) records one working-tree
review and its scoped evidence; it does not authorize publication or close
unverified release gates.

The requirements below distinguish scoped development-host verification from
still-open release gates; a checked item is not blanket fresh-install acceptance:

- [ ] Full offline tests/syntax/static review pass with recorded output and an
  unchanged approved first-install engine pin.
- [ ] Clean Omarchy/Strix Halo install, including dependency discovery, engine
  build at the pin, useful failure feedback/retry, and RADV device/heap validation.
- [ ] Safe host detection and smaller-memory behavior; unsupported hosts retain
  installation/WebUI/download features while engine startup, model loading and
  GTT changes fail closed. GTT choices cannot overcommit the host.
- [ ] Authorized GTT confirmation/privilege flow, boot-image failure recovery,
  separate reboot decision, and post-reboot live ceiling verification.
- [ ] Engine starts with no model; explicit download never loads; download
  resume/hash failures, fit refusal, load switch confirmation, unload without
  poll-triggered reload, and selected-file deletion preserving unrelated files.
- [ ] Engine/WebUI install and update while stopped, busy/error states, failure
  recovery, and no automatic restart, autostart enablement, downgrade, or global
  Vulkan changes. Review dependency/pin reproducibility, including Open WebUI.
- [ ] Fresh Open WebUI initial account provisioning works with authentication
  on and signup off; verify loopback bootstrap, confirmed network opt-in, secret permissions,
  and occupied-port behavior. Do not weaken auth as a workaround.
- [x] Native UI fixture evidence: six ordinary layouts with sixteen checks each
  plus two unsupported-host policy cases (98 total checks). See the [dated evidence and limits](publication-audit.md#ui-evidence).
- [ ] Authorized live-shell placement/focus and log inspection of the current
  candidate. No shell reload was performed in the resumed review. Fixture tests
  do not close hardware/backend lifecycle or clean-host acceptance.
- [ ] Verify catalog immutable revisions/hashes and model licenses; exercise
  existing-file integrity checks. Undated speed records have been removed;
  future public claims/display require reproducible dated benchmarks.
- [ ] README matches the tested installation path. No promise of a complete
  setup wizard, persistent lifetime ledger, or untested device coverage.
- [ ] Secret/personal-data scan and review of documentation, history, artifacts,
  screenshots, and repository metadata before any public visibility change.

Record acceptance date, hardware/RAM/GTT, OS/shell versions, engine commit,
commands/actions, results, and any waived blockers in the release review. Never
replace missing evidence with a passing-looking transcript.

## Release procedure

1. Obtain explicit approval for the candidate scope and any waived blockers.
2. Prepare the approved version and aggregate accurate user-facing notes. For
   the first release, notes describe actual work without retroactive releases.
3. On the approved release commit, date the release section with its real
   release date and ensure the manifest matches. Review tests/diff and evidence.
4. With authorization, create the matching `v`-prefixed tag
   (`v0.5.0-preview.1` for the initial preview), and attach the same notes to a
   GitHub Release. Mark preview releases as prereleases, not Latest.
   Do not rewrite existing history or reuse a tag for different content.
5. Change visibility only with separate explicit approval. Verify remote
   visibility, tag commit, notes, and a fresh install of that exact release.
6. Keep the default branch aligned with the published preview. Develop unfinished
   work on another branch; Omarchy updates follow default-branch commits rather
   than selecting GitHub release tags. Prepare the next version when work begins.

Users update the plugin with `omarchy plugin update silexmachina.omastrix`.
The native command shows changes and asks for confirmation. A normal Omarchy
system update does not currently update Git-managed plugins automatically.
OmaStrix's engine/WebUI update controls do not update the plugin itself.

This checklist documents future gates; it does not authorize any remote action.
