# Reuse, licensing, and credits policy

Credit is required when a license requires attribution, but credit by itself
does not grant permission. Every imported work needs an actual license or a
separate permission from the rights holder. Making the game free does not cure
missing permission, a non-commercial restriction, trademark confusion, or an
incompatible redistribution term.

The implementation therefore separates four things:

1. GPL-compatible code may be adapted with its copyright notices, source offer,
   license text, and corresponding-source obligations preserved.
2. Architectures, balance relationships, role grammars, and mission patterns
   may inform original implementations; story text, character identities,
   dialogue, geography, and media are not copied.
3. Sprites, voxels, icons, cursors, fonts, sounds, voices, music, movies, logos,
   and names remain blocked until an exact file, author, license, and hash are
   recorded in `assets/*.json`.
4. Presentation packs created by users stay local. A pack becoming technically
   loadable does not make its contents distributable.

The currently accepted directional vehicle record is
`assets/red-sea-directional-vehicles.json`. It identifies project-original
generator sources, exact shipped hashes, the repository license and credit,
structural audit evidence, cardinal handedness, and a live 32-transition turn.

Before distributing a build, regenerate the inventory and run:

```powershell
./scripts/verify_openra_reuse.ps1
```

This is an engineering policy, not a substitute for legal advice about a
specific third-party asset, trademark, jurisdiction, or distribution channel.
