# GUI redesign — decisions waiting for the owner

The owner asked (2026-09-28): run the whole GUI track to the end; collect every
non-blocking decision here, with the default that was taken, and review them the
next day. **Nothing here blocked the work.** Each item says what was done; answer
"keep" or give the change.

| # | Batch | Question | Default taken |
|---|---|---|---|
| D1 | foundation | Six light-mode colours of plan §2.2 failed the plan's own 4.5:1 contrast rule and were darkened minimally: faint `#7a7e85→#696c72`, accent_text `#c7430f→#c5420f`, gauge `#0e7fa6→#0d7599`, ok `#2f9e44→#257d36`, warn `#b07d00→#926800`, danger `#d6336c→#cb3067`. | Darkened as listed. The light `LAB` of the wordmark differs imperceptibly from the logo board. |
| D2 | foundation | Space Grotesk ships as the variable font from google/fonts (the designer's static set has no SemiBold 600). A test checks that 600 and 700 really render heavier. | Variable font. |
| D3 | foundation | Light-mode values nobody drew: toggle off-track `#b9b3aa`; wake opacity 0.30 on light (the board uses 0.30, the plan text said 35 %). | As listed. |
| D4 | foundation | `error` and `danger_hover`: dark `#ff5c7a` / `#ff7490`, light `#cb3067` / `#b52a5b`. White text on the dark `danger` is only 2.97:1, so dark danger buttons use the dark `on_accent` text. | As listed. |
| D5 | foundation | Commit attribution: the implementer's environment required "Co-Authored-By: Claude Fable 5" rather than "Claude Opus 5.5" on its three commits. | Left as committed. |
| D6 | foundation | Found while building: an app-wide style-sheet rule has always overridden the font family and size that panels set in code. Fixed only where this batch needed it. A sweep of all panels is a candidate. | Left for the screen batches, which rebuild those panels anyway. |
