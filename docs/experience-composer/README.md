# Experience Composer

The Experience Builder is available from **Main Menu → Workshop → Experience Builder**. Workshop is the single home for Experience Builder, Mission Studio, Map Editor, and Asset Library; playback and credits remain under Extras.

The Builder separates simulation-affecting capabilities from local presentation replacements. Selecting a gameplay module shows its behavior, enabled state, version, dependencies, contributed data files, source, license, and typed parameters. **Browse Asset Library** opens the searchable comparison workspace directly, and **Copy Pack Folder Path** provides the selected presentation-pack destination without requiring users to memorize it.

## Gameplay profiles

The default **World War III** profile enables the five completed built-in
factions and the complete reusable capability portfolio. Players who want the
standard base simulation plus the AI assistant can select **AI Assistant
Only**, or they can choose another preset and customize individual capability
and faction packs. Dependencies are enabled automatically; disabling a
dependency also disables components that require it.

The catalog does not include Red Alert 2 or Yuri's Revenge game content. A few
modules cite or adapt GPL-compatible architecture from the separate OpenRA Red
Alert 2 project; the original factions, maps, art, audio, and proprietary data
are not shipped.

Built-in packs are part of the OpenRA AI game package. Their manifests, rules,
weapons, sequences, previews, and other declared data are copied into the
installed mod by the normal packager. Turning one on only changes the selected
local file set and restarts the mod; it does not contact a server or download
the source mod again. Source, author, version, and license metadata remain
visible in Experience Builder so the origin of reused systems stays auditable.

This distinction is important:

- **Installed and disabled**: built-in capability/faction packs ship with the
  game and are ready to enable offline.
- **Imported**: external community capability packs are validated, copied into
  the user's OpenRA support directory, and mounted from there. They are not in
  the base installer unless they have been deliberately promoted to a built-in
  pack for a release.
- **Active**: only packs selected by the current profile contribute gameplay
  data. Their dependency closure and exact files determine the fingerprint.

Gameplay changes restart the mod. The selected component IDs, versions, and manifest file sets produce a deterministic gameplay fingerprint. Multiplayer peers must use the same gameplay fingerprint.

Module parameters are declared beside their component in the catalog. Boolean, bounded integer, and enumerated choice controls are generated from that schema. Parameter values are validated, persisted in settings, included in the gameplay fingerprint, and read by the runtime capability. The initial modules expose practical controls for factions, units, weapons, economy, AI, effects, and balance.

The built-in catalog is defined in
`engine/openra/mods/ra/experiences.yaml`. A component can contribute rule,
weapon, sequence, cursor, chrome, voice, notification, or music definitions.
The selected file set is resolved before OpenRA loads its default rules.

Imported capability packs are data-only: compiled assemblies, executable code,
scripts, path traversal, and undeclared files are rejected. Valid imports are
copied under the RA experience-pack area in the OpenRA support directory,
assigned a mounted namespace, fingerprinted, and can be removed through the
manager. Importing is therefore a separate, explicit action from enabling a
built-in pack.

## Presentation packs

Presentation packs replace assets without changing simulation rules. Players may use different presentation packs in multiplayer.

On first launch, the game creates:

```text
<OpenRA support directory>/ExperiencePacks/ra/
```

On a standard Windows installation this is normally under `%APPDATA%/OpenRA/ExperiencePacks/ra/`.

Each immediate child folder is one pack. The Builder can create, duplicate, rename, and delete these packs. New packs are valid while empty, so creators can assemble them incrementally without hand-writing a manifest.

```text
my-pack/
  pack.yaml
  assets/
    mouse.shp
    sidebar.png
    custom-click.wav
```

Replacement paths are OpenRA virtual filenames, not source paths. For example, replacing `mouse.shp` changes the RA cursor sheet because the standard cursor definitions reference that virtual filename. The replacement must preserve the expected frame count and layout unless a future gameplay component also changes the cursor definition.

Packs are deliberately data-only. They may contain supported image, sprite, palette, audio, and video formats, but no DLLs, scripts, executables, archives, or YAML below the assets folder. Every file must be declared by `Replaces`; undeclared and missing files invalidate the pack. Symbolic links and junctions are rejected.

Assets not declared by the pack automatically fall back to the normal game presentation.

## Asset Library

The native Asset Browser loaders and preview renderers are reused behind a redesigned **Asset Library** workspace. It provides search-first navigation, source and type filters, automatic palette selection, original/candidate sprite comparison, and original/candidate audio playback.

To create a replacement:

1. Select or create an editable presentation pack in Experience Builder.
2. Open Asset Library and select the asset that should be replaced.
3. Choose **Set as Original** to lock the virtual target path.
4. Select a compatible mounted asset and choose **Use Candidate**, or choose **Import File** and enter the full path to an external file.
5. Return to Experience Builder to inspect or remove the exact replacement mapping, then apply and restart.

Sources and targets must use the same format. Files are copied into the managed pack, declared in `Replaces`, fingerprinted, and validated automatically. Imported files remain data-only and are limited to supported presentation formats and 256 MB per file.

## Licensing fields

`Author` and `License` are mandatory. These fields document provenance but do not grant permission. Pack creators must still have the right to redistribute every included file. Do not include Command & Conquer music files.

## Verification

Run:

```powershell
./scripts/verify-experience-composer.ps1
```

The verifier builds the modified engine into an isolated local output directory and runs the complete RA YAML, sequence, map, and Fluent checks without overwriting the binaries used by an open game.
