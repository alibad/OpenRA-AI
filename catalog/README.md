# Generated copy: do not edit here

`factions.json` in this folder is a copy of the one master faction catalog, `RTSAI-Mod/catalog/factions.json`
(moved there on 23 October 2026). The desktop engine (`SharedFactionCatalog`) and the AI companion read this copy, so
it stays byte-identical to the master.

Edit the master, then refresh the copies from the RTSAI-Mod checkout:

```sh
python tools/sync-faction-catalog.py          # writes this copy and checks every other one
python tools/sync-faction-catalog.py --check  # exits 1 if this copy (or any other) differs from the master
```
