# Rebuilding a screen from source (rung 1)

The rebuild is the product as its code says it looks. It is faithful when a person who uses the product would not notice a difference at video size, and every value can be traced to a file and line.

## Read before you write

For each screen in the flow, read (read only, never run the product for this rung):

- **Views**: the component or view file and the ones it calls. Note the structure top to bottom, every label and placeholder as written, icon names, empty and error states.
- **Theme**: colour tokens (light and dark: pick the one the product ships by default or the one the founder uses), fonts and weights, sizes, radii, paddings, spacings, shadows, materials and blurs.
- **Behavior**: what each key or click does, the order of states (empty, preview, working, done), and every animation with its duration and curve. A state the code never shows is not shown.
- **Copy**: strings files and catalogs (`tokens.py` lists them). Use the shipped language unless the founder asks for another.
- **Sample data in the code** (fixtures, previews, seed files): prefer it. When there is none, invent neutral demo records (a fictional person, company and domain like `example.com`) and say they are demo data.

Write `SOURCE.md` next to `index.html`: one row per value with its file and line, and a short list of stand-ins (drawn icons for system symbol sets, an approximated system material, demo data, a video annotation such as the keystroke overlay).

## Native apps (macOS, iOS, Android)

- Window chrome, menu bar and notch, phone outline: the kit's classes. They are generic shapes; draw no logos, wallpapers or system artwork.
- System symbols and icons: draw a simple shape of the same size and weight, or use the product's own bundled icon files. Name the stand-in in `SOURCE.md`.
- System materials (blur, vibrancy): approximate with `backdrop-filter` blur, saturation and brightness, matched to how the material looks over what is behind it. Run the render check: a contrast failure usually means the material is too light.
- Point sizes map to CSS pixels one to one at the logical size; `flow.py` renders at 2x.
- Fonts: the product's bundled font (its file name gives the family) loaded from the repo or from Google Fonts when it is published there under the OFL; never bundle a font into the plugin.

## Web apps

- Rung 0 often fits: the marketing site's own page, or a component preview, rendered as is.
- Otherwise rebuild the page from its components with the real CSS tokens (`css_vars`), or record it (rung 2) when the project's rules allow running its dev server.

## Flows

- One action at a time, at the product's own pace: use the code's durations; for a pace the code does not fix (how fast a person types, how long a fill takes), pick a believable one and note it.
- Keyboard-driven UI: `key` steps with `at` on the focused element, so the camera follows and the overlay shows the keys.
- End on the result held for a beat (1 to 2 s), so a viewer sees what changed.
- Check the contact sheet against `SOURCE.md` before the polish.
