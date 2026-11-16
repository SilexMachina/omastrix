# Component and model licenses

Scope: distributing OmaStrix plugin source,
configuration and documentation, **without model weights, engine binaries or
Open WebUI packages**. This summary identifies applicable source texts and
conditions requiring attention before redistribution or commercial use.

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

The six recipes below link to pinned quantizer cards and named upstream license
texts. These references do not establish compatibility or legal clearance.

This is a license cross-reference, not a replacement recipe catalog.
Model cards and license-file links below use full immutable revisions; the short
revisions are reading aids. The WebUI tag lookup separately identifies its commit.

| Catalog recipe | Quantizer revision/card | Named upstream license text |
| --- | --- | --- |
| `qwen35-4b` — Qwen3.5-4B | `e87f176479d0`.[1] | Apache-2.0; Qwen/Qwen3.5-4B at `851bf6e806ef`.[9] |
| `qwen35-9b` — Qwen3.5-9B | `3885219b6810`.[2] | Apache-2.0; Qwen/Qwen3.5-9B at `c20223623576`.[10] |
| `qwen36-35b-a3b` — Qwen3.6-35B-A3B | `a483e9e6cbd5`.[3] | Apache-2.0; Qwen/Qwen3.6-35B-A3B at `995ad96eacd9`.[11] |
| `qwen38-27b` — Qwen3.8-27B | `4ca720788d1e`.[4] | Apache-2.0; Qwen/Qwen3.8-27B at `1d4bf0f2ff60`.[12] |
| `qwen38-flash-next` — Qwen3.8-Flash-Next | `766911a6b736`.[5] | **Qwen Community License 1.0**, not Apache/MIT; Qwen/Qwen3.8-Flash-Next at `de4b8e4d43b9`.[13] |
| `deepseek-v4-flash` — DeepSeek-V4-Flash-0731 | `fbbb5b93fb78`.[6] | MIT; deepseek-ai/DeepSeek-V4-Flash-0731 at `7872f01b1d1f`.[14] |

**Provenance limit:** the quantizer cards name upstream repositories but do not
pin the upstream source commit used to make the GGUFs.[1][3][5] Their upstream
license references below identify immutable commits. They establish the cited
texts, **not** the historical upstream revision used for quantization.

**Quantizer-side notices:** Flash-Next's pinned card says
`license: other`, `license_name: qwen-community-1.0`, `license_link: LICENSE`,
but does not include the license text itself.[5] Use the official upstream
license.[13] A card's license metadata is not a complete redistribution notice
or a substitute for the applicable license text.

### Apache-2.0 models: concrete conditions

The four Apache texts include **Copyright 2026 Alibaba Cloud**. For
redistribution of the models or derivative works, §4 requires a copy of the
license, prominent change notices in modified files, retention of relevant
source-form copyright/patent/trademark/attribution notices, and readable NOTICE
attributions **if** the upstream distribution includes a NOTICE file.[9][10][11]
The fourth model has the same license text and notice.[12]

§3 includes a patent grant and patent-litigation termination condition; §6 does
not grant general trademark rights, apart from describing origin and reproducing
NOTICE content.[9] Do not imply endorsement. Check the actual artifacts being
redistributed for NOTICE files and other required attributions.

For a future GGUF mirror or bundled model release, carry the actual upstream
license/notice materials and identify quantization modifications rather than
assuming the plugin's MIT file covers them. These references are not a complete
redistribution package.

### DeepSeek model

The upstream card explicitly applies MIT to **the repository and model
weights**.[15] The actual license names **Copyright (c) 2023 DeepSeek** and
requires its copyright and permission notice in copies or substantial portions;
retain the full license/disclaimer if distributing that model.[14]

### Qwen3.8-Flash-Next: user/business review required

The metadata identifier is `qwen-community-1.0`; the actual title is **Qwen
Community License 1.0**. Its “Software” expressly includes weights, parameters,
configuration, inference code and documentation, and its permission covers use,
distribution, sale, deployment, hosting, fine-tuning and derivative works subject
to the following conditions.[5][13]

- **Notices:** include **Copyright (c) 2026 Qwen** and the permission notice in
  copies or substantial portions of that Software.[13]
- **Large commercial products/services:** if using the Software or derivatives
  for a commercial product/service with **more than 100,000,000 monthly active
  users OR US$20,000,000 monthly revenue** (or equivalent currency), the
  respective model name must be **prominently displayed in its user interface**.
  This clause is an attribution condition, not a blanket ban above a threshold.[13]
- **Separate commercial license:** if the licensee **or any affiliate conducts
  a “Model as a Service” or “AI Work Assistant” business**, a separate license
  from Qwen is required **before using the Software or derivatives for any
  commercial purpose**. Do not read this as restricted only to selling access
  to this particular model.[13]
- **Narrow internal-use exception:** that separate-license requirement does not
  apply to internal use only if the Software, **its outputs and underlying model
  capabilities are not made available to any third party**.[13]
- **Definitions matter:** “Model as a Service” includes third-party inference
  or fine-tuning access with meaningful control of inputs, parameters or training
  data; mere relay to models hosted by other third parties is excluded. “AI Work
  Assistant” means an independent product primarily for AI-assisted coding or
  office productivity. The text excludes single-purpose tools, assistants
  primarily for other domains, and assistant features of products whose primary
  purpose is not AI-assisted coding/office productivity.[13]
- **Other conditions:** use must comply with applicable laws/regulations and
  must not infringe third-party intellectual-property rights. License questions
  are directed to `model-business@notice.qwencloud.com`.[13]

Flash-Next has commercial-use conditions beyond MIT or Apache-2.0. Check the
terms against your intended use, including the defined business categories and
internal-use exception. Resolve uncertain commercial uses with Qwen or qualified
legal advice; obtaining the model through an installer does not exempt its use.

## Engine: pinned fork, separate upstream notices

The reproducible baseline in [engine-pin.json](../engine-pin.json) is
`halo-box/strix-llama.cpp@69946438aa2c432ba365e40bec35c38f6e1de5bb`.
Normal engine installation now selects the newest published Halo build; the
following notices refer to this recorded baseline.
Its root license is **MIT**, **Copyright (c) 2023–2026 The ggml authors**;
copies/substantial portions must include that copyright and permission notice.[7]

The pinned tree also has dependency-specific licenses; root MIT is not a
complete dependency inventory.[17] Examples relevant if engine source/binaries
are later copied or bundled:

- `licenses/LICENSE-jsonhpp` and `vendor/cpp-httplib/LICENSE` are MIT notices;
  preserve their respective copyright/permission texts.[18][20]
- `vendor/hash/xxhash/LICENSE` is BSD-2-Clause: retain its copyright, conditions
  and disclaimer in source; reproduce them in documentation/materials for
  binary redistribution.[22]
- `vendor/hash/sha256/LICENSE` declares Igor Pavlov's code public domain;
  bundled UI `big-integer/LICENSE` contains the Unlicense/public-domain
  dedication and disclaimer.[21][19]

The linked notices are not a full inventory of embedded header
notices or a built dependency SBOM. For this plugin-only scope, keep upstream
identification and links; **before bundling engine artifacts**, inventory the
actual build and preserve all applicable notices instead of copying only the
plugin's MIT license. An explicit engine update needs a review of its own revision.

## Optional Open WebUI: deployment and branding

The configured first-install version is **0.13.0**. The upstream `v0.13.0` tag
resolved to `c38885a1a737da4968f157092f304f3b5481d0bf`; the following are the
license materials at that commit.[8]

- **Source redistribution:** retain the copyright, conditions and disclaimer.
  **Binary redistribution:** reproduce them in documentation/other materials.
  The current copyright is **2023– Open WebUI Inc. [Created by Timothy Jaeryang
  Baek]**. Names of copyright holders/contributors cannot endorse/promote derived
  products without prior written permission.[16]
- **Branding condition applies to deployment as well as distribution:** do not
  alter/remove/obscure/replace Open WebUI branding, except where the text permits
  it: **at most 50 individual end users with direct application access within
  any rolling 30-day period**, specific prior written permission, or an executed
  enterprise license expressly allowing the modification. This is **not** a
  general 50-user cap on unmodified Open WebUI use.[16]
- **Historical notices remain:** `LICENSE_NOTICE` distinguishes earlier MIT,
  subsequent BSD-3-Clause and later Open WebUI License contributions;
  `LICENSE_HISTORY` supplies the earlier license texts. Retain those materials
  when distributing covered code; do not relabel the whole current application
  as MIT.[24][23]
- **Dependencies have their own notices:** the encryption WebAssembly
  `THIRD_PARTY_LICENSES.txt` explicitly scopes itself to that artifact and its
  build dependencies; it is not an all-application dependency clearance.[25]

OmaStrix's integration is not permission to rebrand the Open WebUI application.
The tag-source notices do not cover every license inside a PyPI wheel or
transitive dependency.
Recheck any explicitly updated WebUI version and any future bundled package.

## Redistribution limits

The plugin's MIT license does not cover separately obtained components or
models. Resolve missing notices and quantization provenance before redistributing
GGUFs. Assess Flash-Next's commercial/affiliate terms before commercial use.
If upstream code, weights or binaries are bundled, inventory the actual artifacts
and preserve all applicable notices. This summary is not legal clearance.

## Sources

[1] https://huggingface.co/unsloth/Qwen3.5-4B-GGUF/raw/e87f176479d0855a907a41277aca2f8ee7a09523/README.md
[2] https://huggingface.co/unsloth/Qwen3.5-9B-GGUF/raw/3885219b6810b007914f3a7950a8d1b469d598a5/README.md
[3] https://huggingface.co/unsloth/Qwen3.6-35B-A3B-GGUF/raw/a483e9e6cbd595906af30beda3187c2663a1118c/README.md
[4] https://huggingface.co/unsloth/Qwen3.8-27B-GGUF/raw/4ca720788d1e01f1bff70c033e0d0028fd02e502/README.md
[5] https://huggingface.co/unsloth/Qwen3.8-Flash-Next-GGUF/raw/766911a6b7369840a91dbcd95f9f997acaab6cd6/README.md
[6] https://huggingface.co/unsloth/DeepSeek-V4-Flash-0731-GGUF/raw/fbbb5b93fb787c21338159b0af3318bb3f4d9768/README.md
[7] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/LICENSE
[8] https://api.github.com/repos/open-webui/open-webui/git/ref/tags/v0.13.0
[9] https://huggingface.co/Qwen/Qwen3.5-4B/raw/851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a/LICENSE
[10] https://huggingface.co/Qwen/Qwen3.5-9B/raw/c202236235762e1c871ad0ccb60c8ee5ba337b9a/LICENSE
[11] https://huggingface.co/Qwen/Qwen3.6-35B-A3B/raw/995ad96eacd98c81ed38be0c5b274b04031597b0/LICENSE
[12] https://huggingface.co/Qwen/Qwen3.8-27B/raw/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0/LICENSE
[13] https://huggingface.co/Qwen/Qwen3.8-Flash-Next/raw/de4b8e4d43b917e7706784d8bb445c9af86a3540/LICENSE
[14] https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/raw/7872f01b1d1fe23eabc4c98b48bffcef5a386062/LICENSE
[15] https://huggingface.co/deepseek-ai/DeepSeek-V4-Flash-0731/raw/7872f01b1d1fe23eabc4c98b48bffcef5a386062/README.md
[16] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE
[17] https://api.github.com/repos/halo-box/strix-llama.cpp/git/trees/69946438aa2c432ba365e40bec35c38f6e1de5bb?recursive=1
[18] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/licenses/LICENSE-jsonhpp
[19] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/tools/ui/src/lib/vendors/big-integer/LICENSE
[20] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/cpp-httplib/LICENSE
[21] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/hash/sha256/LICENSE
[22] https://raw.githubusercontent.com/halo-box/strix-llama.cpp/69946438aa2c432ba365e40bec35c38f6e1de5bb/vendor/hash/xxhash/LICENSE
[23] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE_HISTORY
[24] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/LICENSE_NOTICE
[25] https://raw.githubusercontent.com/open-webui/open-webui/c38885a1a737da4968f157092f304f3b5481d0bf/src/lib/encryption/vendor/THIRD_PARTY_LICENSES.txt
