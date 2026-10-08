# Changelog

## Unreleased

- Design brief. No release tag.
- Cut 0.1: host probe, GTT pill, empty panel. No model download. Live `silentd.local-models` pill stays.
- Panel row matches Audio and Network type size. GTT Max is 64 / 96 / 110 GB boxes. While a new ceiling differs from this session, `GTT Change Pending Reboot` stays to the right of the boxes.
- Engine install is per-user under `~/.local/share/omastrix`. The panel starts and stops that service. Logon start is off until turned on. Start does not load a model.
- The engine row names strix-llama.cpp, then Installed: Yes or No, then Version: without the commit hash, then Status: when it is installed.
- The panel is two bordered panes. System holds the engine, GTT, and Open WebUI controls. Models is a table: name, status, parameters, size, RAM, engine, notes.
- Setup does not download a model. Starter library is six click-to-install rows. The pill always shows GTT used and ceiling.
- The library shows only models that fit this machine. Too-large rows are behind a control, with the shortfall noted.
