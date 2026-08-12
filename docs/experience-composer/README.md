# Experience Composer

The Experience Composer is available from the Red Alert main menu under **Experience**. It separates simulation-affecting capabilities from local presentation replacements.

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

Each immediate child folder is one pack. Copy the creator template, rename the folder to match its `Id`, add replacement files below `assets/`, and select **Refresh** in the Composer.

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

## Licensing fields

`Author` and `License` are mandatory. These fields document provenance but do not grant permission. Pack creators must still have the right to redistribute every included file. Do not include Command & Conquer music files.

## Verification

Run:

```powershell
./scripts/verify-experience-composer.ps1
```

The verifier builds the modified engine into an isolated local output directory and runs the complete RA YAML, sequence, map, and Fluent checks without overwriting the binaries used by an open game.
