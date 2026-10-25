# Custom block library

One `.ntop` per custom block (a notebook with declared inputs and exactly one output).
Point nTop's **My Blocks** folder at this directory so every block is searchable in any
notebook. Imported blocks do not update by themselves: after changing a block here,
re-import it in notebooks that use it.

Naming: `band-from-profile.ntop`, `bezel-for-stone.ntop`, `prong-head.ntop`,
`chain-link.ntop`, `sprue-attach.ntop`. Each block gets a folder in `ntop/packages/`
with `manifest.json` and a README (nTop community-package layout).

Install the community **Text to Implicit** block here too (Arial Bold lettering):
https://docs.ntop.com/community/packages/ntop/text-to-implicit
