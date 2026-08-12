# `legacy/` — the pages as they shipped at c9a0d91

Frozen artefacts of the pipeline retired at cutover. **They are
served, and they will lie**: the numbers are cutover-day numbers and
will never move again. Each carries one archive banner saying so,
inserted at freeze time and nowhere else in the file.

## Provenance

SHA-256 of each page **as it shipped, before the banner was
inserted**. Strip the single `<div id="cutover-archive-banner">…</div>`
and its following newline+indent, and the hash returns:

| page | sha256 (pre-banner) |
| --- | --- |
| `parisxxl.html` | `6aaaf0fd0fdb4b5c6eb1600ebd1b3fea5bc6aa870f135038cf8a9baf2b2cd0fc` |
| `bordeaux.html` | `844fc9362644c9814f87449b3e21f2b75ac682cf722c21815d3613ec22689769` |
| `epk.html` | `d97e2b23bed24419ef308530dad0493645a9168e03dad63caae0537688a5d883` |
| `bordeaux_oct.html` | `88d72f6cd9199844dfbab5fc35f848c07329723a5dce064e7fcdd768eb184a36` |
| `geneve.html` | `702496c57f77502383c3733d3404501e3f5ae62b633df7e0e4047b2946607a1d` |
| `rennes.html` | `96bfc9b8a77b842c7cacfd56e5e2cce3214f3cc3636e42d7adb4d3d5a53ac7c8` |

These pages keep their original `<!-- shared:… -->` build
stamp. It is evidence of what built them, and it is meaningful
only against commit `c9a0d91` — the shared assets it hashes have
moved on since.

`event_config.csv` points at none of these files, which is why
every page check excludes them: not because they are old, but
because nothing builds them (CUTOVER §6.3).
