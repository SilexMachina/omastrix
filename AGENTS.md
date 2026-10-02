# OmaStrix — agent contract

Read this before changing the machine for OmaStrix. The spec is `DESIGN.md`. This file is the operating contract.

## What this is

OmaStrix is an Omarchy bar plugin for Strix Halo hosts only. Install id: `silexmachina.omastrix`. One engine, when a later cut installs it: native `halo-box/strix-llama.cpp`, Vulkan RADV, one server on `127.0.0.1:8080`. This cut does not install that engine and does not start a server.

The live control pill on this machine is still `silentd.local-models`. Do not remove it. Do not put OmaStrix on the bar unless SilentD asked for that swap.

## State

`bin/omastrix snapshot` prints one JSON object. Read it before claiming this machine is Strix Halo, or claiming a GTT number. Fields: `strix_halo`, `gpu_name`, `pci`, `gtt_used_gib`, `gtt_total_gib`, `gtt_default`, `mem_total_gib`, `pill`.

`gtt_default` is true when `/proc/cmdline` has no `ttm.pages_limit`, or the value is at or under the stock ~16.3M pages. The pill then ends in `!`.

## Verbs that do not exist yet

Download, load, unload, and setup are not in this cut. Do not invent them. Do not download a GGUF because the library list names one. Do not start or stop `llama-server`. Qwen3.6-35B-A3B may already be loaded on port 8080. Leave it.

## Do not

- Install Docker, Ollama, LM Studio, or a second llama.cpp.
- Bind a server to `0.0.0.0`.
- Set `amd_iommu=off`.
- Raise GTT, edit `/proc` or the boot line, or reboot. The GTT write is a later wizard step and waits for a confirm.
- Pass a projector or a draft file.
- Publish the repo. It stays private until SilentD says public.
- Treat a speed number as true unless `DESIGN.md` names the machine, context, and date it was measured on.
