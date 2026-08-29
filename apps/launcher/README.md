# Local launcher

The product launcher is deliberately small and auditable. It verifies and
installs OpenRA's supported Red Alert quick-install content when needed,
installs an optional `.oramap`, starts the observation-only spoken companion in
the background, enables the engine bridge, and launches directly into a
human-versus-bot skirmish:

```powershell
./scripts/setup.ps1
./apps/launcher/Start-OpenRAAI.ps1 -Map ./generated/missions/riyadh-crossing-42.oramap
```

Use `-NoSpeech` for text-only companion logs or `-NoVoiceHotkeys` to keep spoken
alerts without push-to-talk. During a normal match, hold `Ctrl+Space` on Windows
or `Option+Space` on macOS to ask a question,
press `Ctrl+Enter` to accept a proposal or `Ctrl+Backspace` to reject it, click the
banner's voice control or press `Ctrl+Shift+M` to switch spoken audio off or on, and
press `Ctrl+Shift+A` to toggle AUTO delegation. Remap these controls under
**Settings > Hotkeys > AI Assistant**. Text insights remain active
while voice is off. Speech and
in-flight model responses are discarded when interrupted. The watcher exits
when OpenRA exits.

The portable Windows release includes `Play-OpenRAAI.cmd`, the self-contained
engine, the companion executable, and a sample generated map. Red Alert content
is downloaded from OpenRA's mirror list on first launch and is not bundled in
the release. Official Windows installers require verified Authenticode signatures;
the macOS wrapper and DMG require Developer ID signing and notarization.
