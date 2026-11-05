# Development

Read [AGENTS.md](../AGENTS.md) for operating safety and [DESIGN.md](../DESIGN.md)
for boundaries/UI behavior. This page owns development and test procedure, not
a second feature specification.

## Source map

Runtime code is `Panel.qml`, `bin/omastrix`, `bin/library.py`, `bin/webui.py`, and
`bin/omastrix-engine-install`. Data/configuration shipped by the plugin is
`manifest.json`, `catalog.json`, and `engine-pin.json`. See Design for their roles.
`View.js` owns pure presentation helpers and `ActionButton.qml` supplies shared
action styling. `tools/release.py` is offline metadata tooling, not an
installer/release publisher.

## Tests and review

From the checkout root:

```sh
python3 -m unittest discover -s tests -v
python3 tools/release.py check
python3 -m compileall -q bin tools tests
python3 -m py_compile bin/omastrix
bash -n bin/omastrix-engine-install
git diff --check
```

Python 3 and Node.js are required for the full offline suite. `tests/test_view.py`
integrates the Node presentation tests (`tests/view.test.cjs`) with unittest.
Release-tool tests alone need only Python 3. Tests must isolate HOME,
filesystem paths, network, and process/service interactions. Temporary test
files belong under the environment's `TMPDIR` when set. No test should download
weights, install packages, call live model actions, or start/restart services.
Write and observe a failing test before changing tooling/backend behavior.

`.github/workflows/check.yml` is configured to run these offline tests on Python
3.12/3.14 with Node.js 22 and check metadata plus Python/shell syntax, including
explicit compilation of the extensionless `bin/omastrix`. Its whitespace step
checks the checked-out commit as well as the working diff; `git diff --check`
alone is a no-op on a clean CI checkout. The workflow does not install/run the
inference stack or establish QML/hardware acceptance. A locally passing command
is not a claim that GitHub Actions has run successfully.

Unit tests and syntax checks do not prove QML rendering, theme imports, hardware
fit, pinned-fork API compatibility, or fresh-install safety. Manual acceptance
requires an explicitly authorized host/session; record environment, date,
commands/actions, and outcomes. QML changes on an integrated host may require
`omarchy restart shell`; do not run it without permission or confuse it with an
engine service restart. Open an integrated panel with
`omarchy-shell silexmachina.omastrix open`, not an invented shell-call endpoint.

Review the final diff, ensure no secrets/local paths or undated speed claims were
added, and update the current changelog section. Do not commit or push as an
automatic consequence of review.

## Native UI checks

On an Omarchy development host with Quickshell and QtTest installed:

```sh
python3 tests/qml_smoke.py
```

The native harness runs six ordinary synthetic-fixture cases: dark/light, narrow,
compact, enlarged font, and compact with enlarged font. Two additional hardware-policy
cases cover unsupported hosts at normal and compact/enlarged sizes. Test screen widths range
from 600 to 1280 px; enlarged-font cases use an 18 px base font. The adapter
applies the installed popup's themed padding and border insets.

Each ordinary case runs sixteen behavioral checks: real Qt text entry, Tab/j/k,
disabled controls, contextual accessible names, service transitions, scoped and
recurring errors, confirmation/cancel, Escape, scroll-to-focus, and model/GTT
bounds and overlap. The isolated HOME and fixture backend keep real services and
models outside the test. Screenshots and logs are saved under `TMPDIR`.

Compositor placement and focus ownership require a live-shell check. Record that
separately from fixture results in the [publication audit](publication-audit.md#ui-evidence).

## Recipes and evidence

`catalog.json` is canonical for the model list; do not maintain a duplicate table.
A proposed recipe needs:

- Unique ID, accurate model/quant identity, context, conservative KV estimate,
  required files, one primary shard, and explicit serve flags.
- Paths contained under `~/models`, exact expected byte counts and trusted
  SHA-256 values, plus an immutable source revision where available.
- Recorded load and completion on supported Strix Halo hardware: date, hardware
  and memory/GTT class, engine commit, recipe flags/context, and outcome.
- Optional projector/draft files disabled by default; never treat an image
  generator as a text-model recipe.

A speed claim additionally needs the benchmark command/workload, prompt/decode
phase distinction, relevant token counts, measured result, and dated evidence.
Do not infer speed from model size or another host. Missing evidence means no
public speed claim, not an estimated one. Undated legacy speed records were
removed pending reproducible benchmarks. Catalog URLs are now pinned to immutable
Hugging Face revisions, with expected hashes/sizes checked against remote file
metadata without fetching weights. `tests/test_catalog.py` enforces revision,
path/hash/size, and measurement-metadata requirements. Do not confuse those checks
with end-to-end integrity/load acceptance on actual weights.

## Documentation ownership

- README: scope and development entry point.
- Design: architecture and UI/safety contract.
- User guide: setup limitations, workflow, paths, troubleshooting.
- Release guide: SemVer mechanics, readiness, approvals.
- AGENTS: short operating rules; CONTRIBUTING/SECURITY: contributor/reporting policy.
- Changelog: user-visible changes, never a fabricated sequence of releases.

Link these files from external notes. Do not move unrelated personal documents
into the repository or copy machine credentials/configuration into examples.
