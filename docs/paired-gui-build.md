# Windows GUI package pairing

The downstream `main.yml` builds and tests the Control Panel at the committed
`src_assets/common/sunshine-control-panel` gitlink, including its native stylus
plugin. Packaging uses those local binaries and checks the packaged GUI against
the build output. There is no alternate artifact-download input in this workflow.

For local paired staging, run `scripts/fetch-paired-gui.ps1 -Destination <fresh-path>`
from the Sunshine checkout. Omit `RunId` to discover a matching build, or pass
`-RunId <id>` to validate a specific build. Configure with `FETCH_GUI=OFF` and
`GUI_DIR=<fresh-path>` and `SUNSHINE_PREFER_LOCAL_GUI=OFF` to use the verified
bundle without a local build taking precedence. The script requires a successful
Panel `build.yml` run matching the gitlink and a non-expired
`sunshine-gui-windows-x64` artifact; it records provenance in `paired-build.json`.
GitHub artifact access requires an authenticated `gh` session or an appropriate
`GH_TOKEN`.
