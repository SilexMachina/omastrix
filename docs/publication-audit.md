# Preview readiness — 0.5.0-preview.1

The maintainer authorized the first public preview on 2026-11-05. This preview
opens installation testing on other Omarchy machines while preserving the
Strix Halo requirement for inference and GTT changes. It is experimental;
remaining stable-release acceptance is listed below.

## Scope

- One plugin build and install ID: `silexmachina.omastrix`.
- Unsupported hosts keep engine installation, WebUI and model downloads.
  The title carries a prominent hardware warning and engine Start is red/disabled.
  Backend/launcher guards also refuse unsupported startup. GPU verification is
  reported as unavailable when installation occurs on unsupported hardware.
- Engine pin unchanged: `69946438aa2c432ba365e40bec35c38f6e1de5bb`.
- WebUI first-install version: 0.13.0 on Python 3.11. New installs use loopback;
  stopped-service network opt-in requires confirmation and an existing local
  SQLite administrator. The generated wrapper rechecks before network startup.
- Preset publication uses atomic replacement with pinned directory descriptors
  and no-follow traversal. Deletion checks service-probe success and the selected
  router entry. Installer paths share checked operation locking; launch failures
  persist with the PID cleared. Build environments exclude unrelated credentials.

## Verification evidence

Offline tests isolate HOME and fake external build/package/service tools; they
do not install software or exercise real inference. Native UI fixtures use the
installed Omarchy kit with a synthetic backend and an offscreen window adapter.

Native rendering and interactions passed eight layouts: six ordinary layouts
with sixteen checks each, plus normal and compact/enlarged unsupported-hardware
policy cases (98 total checks). Screenshots were inspected; compact warnings wrap
below the title rather than collapsing into a narrow column. The checks include
keyboard/editing, contextual feedback, confirmation, scrolling, button bounds,
WebUI network controls and unsupported-host action restrictions.

The combined preview candidate passed 196 offline tests, metadata checks, Python
compilation, installer shell syntax, installed Omarchy manifest validation and
whitespace checks. Native fixture checks passed as described above. Independent
review and exact-commit remote verification are separate publication steps.
GitHub Actions runs the portable suite on Python 3.12/3.14 and Node 22. Local
success does not by itself establish remote CI success.

## Catalog and licensing

All six recipes and ten required files were checked against their pinned Hugging
Face API metadata: immutable revisions, sizes, LFS SHA-256, parameters and context
lengths matched. No weights were downloaded for this check. Source inspection at
the engine pin found the declared architectures and recipe options; this does not
establish successful Vulkan inference or memory fit at those contexts.

Undated speed claims were removed. Actual license texts and applicable conditions
are summarized in [licenses.md](licenses.md). Qwen3.8-Flash-Next's commercial
conditions and Open WebUI's branding conditions require attention. No model
weights, engine binaries or WebUI distribution are included in the plugin repo.

## Publication data review

The pre-preview review scanned all 22 existing local commits and their objects
(89 blobs, 36 trees), plus the then-current working payload, for token/private-key
patterns, literal credentials, credential URLs and machine-private addresses.
No credential/private-address matches were found; email matches were public
noreply identities and upstream attribution. The final candidate is scanned again
before publication: 36 working files and all 89 historical blobs matched no
credential patterns or inherited credential values. This is scoped pattern/manual
review, not a guarantee that
all sensitive data can be detected. Models, chats, environments, databases and
local screenshots are excluded from the distribution.

Earlier versions 0.1.0–0.3.0 were internal development cuts. Versioned unreleased
notes began at 0.4.0-dev.1; no retroactive releases/tags are claimed. The first
public tag is `v0.5.0-preview.1`. Git history is retained without rewriting.

## Preview.2 follow-up

Testing reported by the maintainer on a second, unsupported Omarchy machine
confirmed plugin installation, engine compilation after manually adding build
dependencies, engine update, and model download/deletion. Inference remained
correctly unavailable. Hardware/OS specifics and fresh WebUI browser acceptance
are not yet recorded.

Two issues from that test prompted targeted fixes: normal first installation now
resolves the newest published Halo build to an exact commit, and a confirmed
missing WebUI unit is treated as installable. Missing-unit discovery distinguishes
exact `LoadState=not-found` / `ActiveState=inactive` from a failed user-service bus
or ambiguous output. The worker accepts that same safe first-install state.
Dependency installation remains manual in this preview update. The combined
follow-up suite passes 210 offline tests and 98 native fixture checks. These
checks do not replace real first-account/browser acceptance on the test machine.

## Preview.3 follow-up

The OmaStrix System row now checks for and installs plugin updates using the
native updater's noninteractive `--yes` path. Checks are manual and cached;
ordinary status polling stays offline. The backend requires the installed Git
checkout, protects local changes/divergent history, serializes requests, and
runs a detached worker that survives the plugin reload. Completion requires a
successful native exit plus installed HEAD/FETCH_HEAD/version readback. Timeout
and abandoned-worker failures remain visible beside the controls.

The combined suite passes 228 offline tests, including 17 isolated updater
cases using local Git repositories and a fake native command. Native UI fixtures
pass 104 checks across eight layouts, including check/update progress, scoped
errors, refreshed version and unsupported-host behavior. These tests do not
restart real services or run the real self-update on the development checkout.

## Remaining before stable 0.5.0

- Fresh Omarchy/Strix Halo setup, dependency/build acceptance and RADV heap checks.
- Privileged GTT changes, failed boot-image rebuild recovery and post-reboot checks.
- Full model download/resume/integrity/load/switch/unload/delete acceptance, and
  dated completions for every recipe on the first-install engine pin.
- Real fresh WebUI browser/account/bootstrap/network/occupied-port acceptance.
- Stopped-service engine/WebUI update/recovery and smaller-memory host testing.
- Compositor-specific live-shell focus/placement checks for the final candidate.
- Final release-owner license review and reproducible evidence for future speed claims.

The [release guide](releasing.md) owns the stable acceptance checklist. Preview
users should report hardware, Omarchy/plugin/engine versions, steps and redacted
errors. Use the [security policy](../SECURITY.md) for sensitive reports.
