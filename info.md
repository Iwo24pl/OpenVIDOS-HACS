Control Vidos X intercoms / door stations from Home Assistant: doorbell
notifications **with per-channel attribution** (device ring picture log,
hardware-verified; optional LAN ring detection as a second source), open
door/gate, status and lock state, on-demand camera snapshots over the
device's reverse-engineered `quii://` video port, and association of camera
entities from other integrations with the device. The protocol layer is a
1:1 replication of the official app's local CGI protocol (commands, beans
and auth reverse-engineered from `com.vidos.vidosx` — see
`docs/APP_PARITY.md`). Works fully locally - no cloud account needed.
