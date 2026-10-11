# This legacy spec packaged a prebuilt payload.zip from build/installer_stub.
# It did not build the application from source and could therefore reproduce a
# stale installer. Use packaging/build_windows.ps1 for a clean source build.
raise SystemExit(
    "AnimeVault-Setup.spec is intentionally disabled because it could package "
    "stale application payloads. Run packaging/build_windows.ps1 instead."
)
