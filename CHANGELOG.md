# Changelog

## Unreleased

- Design brief. No release tag.
- Cut 0.1: host probe, GTT pill, empty panel. No model download. Live `silentd.local-models` pill stays.
- Panel row matches Audio and Network type size. GTT Max is 64 / 96 / 110 GB boxes. While a new ceiling differs from this session, `GTT Change Pending Reboot` stays to the right of the boxes.
- Engine install is per-user under `~/.local/share/omastrix`. The panel starts and stops that service. Logon start is off until turned on. Start does not load a model.
- The engine row names strix-llama.cpp, then Installed: Yes or No, then Version: without the commit hash, then Status: when it is installed.
- The panel title is OmaStrix. The line under it is Local AI for Strix Halo.
- Open WebUI is installed and controlled as its own user service. The hand install under `~/.local/share/open-webui` is not that service.
- The model table has an Action column: Install, Load, Unload, and Delete.
- Check for updates names the newest published strix-llama.cpp build. Update installs that build when the program is stopped.
- Add model takes a direct link to one .gguf file. It adds a row and does not download.
- An installing row shows a progress bar and the bytes received.
- Setup does not download a model. Starter library is six click-to-install rows. The pill always shows GTT used and ceiling.
- The library shows only models that fit this machine. Too-large rows are behind a control, with the shortfall noted.
