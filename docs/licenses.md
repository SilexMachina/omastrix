# Licenses and publication scope

Audit date: **2026-11-04**. Scope: distributing OmaStrix plugin source,
configuration and documentation, **without model weights, engine binaries or
Open WebUI packages**. This checklist records the reviewed source texts and
conditions requiring attention before release or commercial use.

## Separate licenses

OmaStrix's [LICENSE](../LICENSE) is MIT, copyright © 2026 SilexMachina;
[manifest.json](../manifest.json) declares MIT. Preserve that copyright and the
permission notice in copies or substantial portions of the plugin, including
its full license/disclaimer. This license does **not** relicense separately
obtained models, strix-llama.cpp or Open WebUI.

The [engine installer](../bin/omastrix-engine-install) fetches/builds upstream
source separately; [the optional WebUI installer](../bin/webui.py) installs
`open-webui==0.13.0` separately. Model downloads are described by
[catalog.json](../catalog.json). The upstream conditions below distinguish
those uses from a future distribution that actually includes their artifacts.

## All six catalog recipes

Python checked **6/6 unique recipes**, their pinned API revisions and required
file URL revisions. Retrieved **6/6 quantizer model cards**, **6/6 named upstream
model cards**, and **6/6 actual upstream LICENSE texts**; no weights or packages
were downloaded or installed. These counts describe evidence coverage, not
compatibility testing or legal clearance.

This is a license cross-reference, not a replacement recipe catalog. Every
source below uses a full immutable revision; the short revisions are reading aids.

| Catalog recipe | Quantizer revision/card | Named upstream license text |
| --- | --- | --- |
| `qwen35-4b` — Qwen3.5-4B | `e87f176479d0`.[7] | Apache-2.0; Qwen/Qwen3.5-4B at `851bf6e806ef`.[23] |
| `qwen35-9b` — Qwen3.5-9B | `3885219b6810`.[9] | Apache-2.0; Qwen/Qwen3.5-9B at `c20223623576`.[26] |
| `qwen36-35b-a3b` — Qwen3.6-35B-A3B | `a483e9e6cbd5`.[11] | Apache-2.0; Qwen/Qwen3.6-35B-A3B at `995ad96eacd9`.[29] |
| `qwen38-27b` — Qwen3.8-27B | `4ca720788d1e`.[13] | Apache-2.0; Qwen/Qwen3.8-27B at `1d4bf0f2ff60`.[32] |
| `qwen38-flash-next` — Qwen3.8-Flash-Next | `766911a6b736`.[15] | **Qwen Community License 1.0**, not Apache/MIT; Qwen/Qwen3.8-Flash-Next at `de4b8e4d43b9`.[35] |
| `deepseek-v4-flash` — DeepSeek-V4-Flash-0731 | `fbbb5b93fb78`.[17] | MIT; deepseek-ai/DeepSeek-V4-Flash-0731 at `7872f01b1d1f`.[38] |

**Provenance limit:** the quantizer cards name upstream repositories but do not
pin the upstream source commit used to make the GGUFs.[7][11][15] Their upstream
heads were resolved during this audit and the cards/licenses then fetched at
those immutable commits. This establishes the reviewed texts, **not** the
historical upstream revision used for quantization. The retained API snapshots
record both sets of revisions.

**Missing quantizer-side notice:** none of the six pinned API file listings
contained a filename including `license`. In particular, Flash-Next's card says
`license: other`, `license_name: qwen-community-1.0`, `license_link: LICENSE`,
but that relative target returned HTTP 404 at its catalog revision.[15]
The failed [exact LICENSE URL](https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/raw/766911a6b7369840a91dbcd95f9f997acaab6cd6/LICENSE)
is recorded in the retrieval manifest. The official upstream license was
successfully retrieved; do not present the broken quantizer link as a complete
redistribution notice or substitute for the upstream text.

### Apache-2.0 models: concrete conditions

The four Apache texts include **Copyright 2026 Alibaba Cloud**. For
redistribution of the models or derivative works, §4 requires a copy of the
license, prominent change notices in modified files, retention of relevant
source-form copyright/patent/trademark/attribution notices, and readable NOTICE
attributions **if** the upstream distribution includes a NOTICE file.[23][26][29]
The fourth model has the same license text and notice.[32]

§3 includes a patent grant and patent-litigation termination condition; §6 does
not grant general trademark rights, apart from describing origin and reproducing
NOTICE content.[23] Do not imply endorsement. No standalone NOTICE filename was
listed in the six reviewed upstream model API snapshots; that observation is
not proof that no attribution exists elsewhere or in unexamined artifacts.

For a future GGUF mirror or bundled model release, carry the actual upstream
license/notice materials and identify quantization modifications rather than
assuming the plugin's MIT file covers them. This audit does not certify a
complete redistribution package.

### DeepSeek model

The upstream card explicitly applies MIT to **the repository and model
weights**.[39] The actual license names **Copyright (c) 2023 DeepSeek** and
requires its copyright and permission notice in copies or substantial portions;
retain the full license/disclaimer if distributing that model.[38]

### Qwen3.8-Flash-Next: user/business review required

The metadata identifier is `qwen-community-1.0`; the actual title is **Qwen
Community License 1.0**. Its “Software” expressly includes weights, parameters,
configuration, inference code and documentation, and its permission covers use,
distribution, sale, deployment, hosting, fine-tuning and derivative works subject
to the following conditions.[15][35]

- **Notices:** include **Copyright (c) 2026 Qwen** and the permission notice in
  copies or substantial portions of that Software.[35]
- **Large commercial products/services:** if using the Software or derivatives
  for a commercial product/service with **more than 100,000,000 monthly active
  users OR US$20,000,000 monthly revenue** (or equivalent currency), the
  respective model name must be **prominently displayed in its user interface**.
  This clause is an attribution condition, not a blanket ban above a threshold.[35]
- **Separate commercial license:** if the licensee **or any affiliate conducts
  a “Model as a Service” or “AI Work Assistant” business**, a separate license
  from Qwen is required **before using the Software or derivatives for any
  commercial purpose**. Do not read this as restricted only to selling access
  to this particular model.[35]
- **Narrow internal-use exception:** that separate-license requirement does not
  apply to internal use only if the Software, **its outputs and underlying model
  capabilities are not made available to any third party**.[35]
- **Definitions matter:** “Model as a Service” includes third-party inference
  or fine-tuning access with meaningful control of inputs, parameters or training
  data; mere relay to models hosted by other third parties is excluded. “AI Work
  Assistant” means an independent product primarily for AI-assisted coding or
  office productivity. The text excludes single-purpose tools, assistants
  primarily for other domains, and assistant features of products whose primary
  purpose is not AI-assisted coding/office productivity.[35]
- **Other conditions:** use must comply with applicable laws/regulations and
  must not infringe third-party intellectual-property rights. License questions
  are directed to `model-business@notice.qwencloud.com`.[35]

Assess the publisher's and users' actual business/affiliate arrangements before
commercial adoption. Shipping only an installer does not establish that later
model use is exempt; equally, this text is not a finding that OmaStrix itself
falls within the defined businesses. Keep the model-specific warning visible
in publication/setup material; resolve uncertain commercial uses with Qwen or
appropriate review before claiming unrestricted commercial availability.

## Engine: pinned fork, separate upstream notices

[engine-pin.json](../engine-pin.json) selects
`halo-box/strix-llama.cpp@69946438aa2c432ba365e40bec35c38f6e1de5bb`.
Its root license is **MIT**, **Copyright (c) 2023–2026 The ggml authors**;
copies/substantial portions must include that copyright and permission notice.[20]

The pinned tree also has dependency-specific licenses; root MIT is not a
complete dependency inventory.[43] Examples relevant if engine source/binaries
are later copied or bundled:

- `licenses/LICENSE-jsonhpp` and `vendor/cpp-httplib/LICENSE` are MIT notices;
  preserve their respective copyright/permission texts.[46][49]
- `vendor/hash/xxhash/LICENSE` is BSD-2-Clause: retain its copyright, conditions
  and disclaimer in source; reproduce them in documentation/materials for
  binary redistribution.[52]
- `vendor/hash/sha256/LICENSE` declares Igor Pavlov's code public domain;
  bundled UI `big-integer/LICENSE` contains the Unlicense/public-domain
  dedication and disclaimer.[51][47]

The evidence includes all **9 explicitly named engine LICENSE files** found
in the fetched recursive tree. This is not a full scan of embedded header
notices or a built dependency SBOM. For this plugin-only scope, keep upstream
identification and links; **before bundling engine artifacts**, inventory the
actual build and preserve all applicable notices instead of copying only the
plugin's MIT license. An explicit engine update needs a review of its own revision.

## Optional Open WebUI: deployment and branding

The configured first-install version is **0.13.0**. The upstream `v0.13.0` tag
resolved to `c38885a1a737da4968f157092f304f3b5481d0bf`; the following are the
actual files at that commit, not a floating license page.[21]

- **Source redistribution:** retain the copyright, conditions and disclaimer.
  **Binary redistribution:** reproduce them in documentation/other materials.
  The current copyright is **2023– Open WebUI Inc. [Created by Timothy Jaeryang
  Baek]**. Names of copyright holders/contributors cannot endorse/promote derived
  products without prior written permission.[41]
- **Branding condition applies to deployment as well as distribution:** do not
  alter/remove/obscure/replace Open WebUI branding, except where the text permits
  it: **at most 50 individual end users with direct application access within
  any rolling 30-day period**, specific prior written permission, or an executed
  enterprise license expressly allowing the modification. This is **not** a
  general 50-user cap on unmodified Open WebUI use.[41]
- **Historical notices remain:** `LICENSE_NOTICE` distinguishes earlier MIT,
  subsequent BSD-3-Clause and later Open WebUI License contributions;
  `LICENSE_HISTORY` supplies the earlier license texts. Retain those materials
  when distributing covered code; do not relabel the whole current application
  as MIT.[54][53]
- **Dependencies have their own notices:** the encryption WebAssembly
  `THIRD_PARTY_LICENSES.txt` explicitly scopes itself to that artifact and its
  build dependencies; it is not an all-application dependency clearance.[55]

OmaStrix's integration is not permission to rebrand the Open WebUI application.
No upstream package was installed or inspected here: tag-source notices were
reviewed, **not** every license inside a PyPI wheel/transitive dependency.
Recheck any explicitly updated WebUI version and any future bundled package.

## Publication checklist and remaining gaps

- [x] Keep plugin MIT distinct from models, engine and WebUI.
- [x] Cover all six recipes with pinned quantizer cards and actual named-upstream
  license texts; preserve exact retrieval links and metadata.
- [x] Document Apache/MIT notices, Flash-Next use/business restrictions and
  Open WebUI deployment/branding terms.
- [x] Fetch pinned-engine license files and WebUI license/history/notice files.
- [ ] Resolve the quantizer's missing Flash-Next LICENSE link and historical
  base-revision provenance **before claiming a complete GGUF redistribution audit**.
- [ ] Release owner reviews Flash-Next commercial/affiliate applicability and
  makes its separate terms apparent to users; do not advertise every recipe as
  unrestricted Apache/MIT.
- [ ] Verify the exact publication payload remains plugin-only and includes the
  plugin LICENSE. If upstream code, weights or binaries are added, perform an
  artifact-specific notices/dependency review; this checklist does not clear them.

Scratch evidence (not part of the plugin distribution):
`$TMPDIR/omastrix-license-audit-bpxz1osr/`. `checklist.json` contains the
Python-counted per-recipe results; `retrieval.json` records URLs, status/errors,
byte counts and SHA-256 digests; `ledger.json` stores citation IDs and verified
verbatim quotations. `*-README.md`, `*-base-LICENSE`, `*-api.json`,
`engine-*` and `webui-*` retain the fetched text/metadata. All six upstream cards
are retained even where only the license is cited here. Scratch retention is
not permanent; archive reviewed evidence separately if required for release.

## Sources

[7] https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/raw/e87f176479d0855a907a41277aca2f8ee7a09523/README.md — qwen35-4b-README.md
[9] https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/raw/3885219b6810b007914f3a7950a8d1b469d598a5/README.md — qwen35-9b-README.md
[11] https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/raw/a483e9e6cbd595906af30beda3187c2663a1118c/README.md — qwen36-35b-a3b-README.md
[13] https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/raw/4ca720788d1e01f1bff70c033e0d0028fd02e502/README.md — qwen38-27b-README.md
[15] https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/raw/766911a6b7369840a91dbcd95f9f997acaab6cd6/README.md — qwen38-flash-next-README.md
[17] https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF/raw/fbbb5b93fb787c21338159b0af3318bb3f4d9768/README.md — deepseek-v4-flash-README.md
[20] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/LICENSE — engine-LICENSE
[21] https://api.github.com/repos/open-webui/open-webui/git/ref/tags/v0.13.0 — webui-tag.json
[23] https://huggingface.co/Qwen/Qwen3.5-4B/raw/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/LICENSE — qwen35-4b-base-LICENSE
[26] https://huggingface.co/Qwen/Qwen3.5-9B/raw/c202236235762e1c871ad0ccb60c8ee5ba337b9a/LICENSE — qwen35-9b-base-LICENSE
[29] https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/995ad96eacd98c81ed38be0c5b274b04031597b0/LICENSE — qwen36-35b-a3b-base-LICENSE
[32] https://huggingface.co/Qwen/Qwen3.8-27B/raw/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/LICENSE — qwen38-27b-base-LICENSE
[35] https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/de4b8e4d43b917e7706784d8bb445c9af86a3540/LICENSE — qwen38-flash-next-base-LICENSE
[38] https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/raw/7872f01b1d1fe23eabc4c98b48bffcef5a386062/LICENSE — deepseek-v4-flash-base-LICENSE
[39] https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/raw/7872f01b1d1fe23eabc4c98b48bffcef5a386062/README.md — deepseek-v4-flash-base-README.md
[41] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE — webui-LICENSE
[43] https://api.github.com/repos/halo-box/strix-llama.cpp/git/trees/69946438aa2c432ba365e40bec35c38f6e1de5bb?recursive=1 — engine-recursive-tree.json
[46] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/licenses/LICENSE-jsonhpp — engine-licenses__LICENSE-jsonhpp
[47] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/tools/ui/src/lib/vendors/big-integer/LICENSE — engine-tools__ui__src__lib__vendors__big-integer__LICENSE
[49] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/cpp-httplib/LICENSE — engine-vendor__cpp-httplib__LICENSE
[51] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/hash/sha256/LICENSE — engine-vendor__hash__sha256__LICENSE
[52] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/hash/xxhash/LICENSE — engine-vendor__hash__xxhash__LICENSE
[53] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE_HISTORY — webui-LICENSE_HISTORY
[54] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE_NOTICE — webui-LICENSE_NOTICE
[55] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/src/lib/encryption/vendor/THIRD_PARTY_LICENSES.txt — webui-src__lib__encryption__vendor__THIRD_PARTY_LICENSES.txt
