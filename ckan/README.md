# CKAN modlists

One CKAN metapackage per KSP install the simulator is used with. Installing one gives that install exactly these mods
(and their dependencies, such as ModuleManager).

| File | For |
|---|---|
| `stock.ckan` | Stock KSP 1.12.5: kRPC 0.7.0, HullcamVDS Continued, Kerbcast, JustReadTheInstructions, Kerbal Engineer Redux, MechJeb2 |

Install, in a fresh KSP 1.12.5 instance:

```sh
ckan install -c ckan/stock.ckan          # command line
```

or in the CKAN window: File → Install from .ckan…

kRPC must stay at 0.7.0: the Python client in `.venv` is pinned to it.

To save an install as a new variant: in CKAN, File → Export modpack (or copy the instance's
`CKAN/installed-<instance>.ckan`), then set `identifier`, `name` and `abstract`, replace `author` (CKAN puts the
account name there, and the repo is public) and drop `release_date` before committing.
