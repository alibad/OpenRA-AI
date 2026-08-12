# Experience Composer

The Experience Builder is available from **Main Menu → Workshop → Experience Builder**. Workshop is the single home for Experience Builder, Mission Studio, Map Editor, and Asset Library; playback and credits remain under Extras.

The Builder separates simulation-affecting capabilities from local presentation replacements. Selecting a gameplay module shows its behavior, enabled state, version, dependencies, contributed data files, source, and license. **Browse Asset Library** opens the searchable asset preview directly, and **Copy Pack Folder Path** provides the presentation-pack destination without requiring users to memorize it.

## Gameplay profiles

The default **World War III** profile enables every currently integrated and stable reusable capability. Players can select another preset or toggle individual components. Dependencies are enabled automatically; disabling a dependency also disables components that require it.

Gameplay changes restart the mod. The selected component IDs, versions, and manifest file sets produce a deterministic gameplay fingerprint. Multiplayer peers must use the same gameplay fingerprint.

The catalog is defined in `engine/openra/mods/ra/experiences.yaml`. A component can contribute rule, weapon, sequence, cursor, chrome, voice, notification, or music definitions. The selected file set is resolved before OpenRA loads its default rules.

## Presentation packs

Presentation packs replace assets without changing simulation rules. Players may use different presentation packs in multiplayer.

On first launch, the game creates:

```text
<OpenRA support directory>/ExperiencePacks/ra/
```

On a standard Windows installation this is normally under `%APPDATA%/OpenRA/ExperiencePacks/ra/`.

Each immediate child folder is one pack. Copy the creator template, rename the folder to match its `Id`, add replacement files below `assets/`, and select **Refresh** in the Builder.

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

The native Asset Browser loaders and preview renderers are reused behind a redesigned **Asset Library** workspace. It provides search-first navigation, source and type filters, selected-asset context, a larger preview, automatic starting palette selection, and **Copy Asset Name** for exact presentation-pack replacement entries.

## Licensing fields

`Author` and `License` are mandatory. These fields document provenance but do not grant permission. Pack creators must still have the right to redistribute every included file. Do not include Command & Conquer music files.

## Verification

Run:

```powershell
./scripts/verify-experience-composer.ps1
```

The verifier builds the modified engine into an isolated local output directory and runs the complete RA YAML, sequence, map, and Fluent checks without overwriting the binaries used by an open game.
