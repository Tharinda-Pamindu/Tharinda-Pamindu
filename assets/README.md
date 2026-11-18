These panels follow the layout and motion language of the Meghamittal0920 profile (hero with typed prompt and cycling roles, ninja-way feature rows, torch-lit tech chips, swinging registration badge with a mission dashboard, connect cards), rebuilt around Tharinda's own portrait (`photo.png`) and details. No artwork, characters, GIFs or personal data from that profile are included.

`scripts/build_profile.py` generates every SVG here. Edit text and layout in that script, then run:

```sh
pip install pillow fonttools
python scripts/build_profile.py            # fetch fresh GitHub stats, then build
python scripts/build_profile.py --offline  # reuse scripts/profile-data.json
```

- Fonts: Space Grotesk and JetBrains Mono (SIL OFL 1.1), vendored in `scripts/vendor/fonts`, subset to the characters each panel uses and embedded.
- Icons: Simple Icons (CC0), vendored in `scripts/vendor/icons.json`. The Java cup and line icons are drawn in the script.
- Motion: CSS and SMIL only, so it plays inside GitHub's `<img>` sandbox. A `prefers-reduced-motion` rule shows the finished static layout.
- Freshness: `.github/workflows/profile.yml` runs daily. It rebuilds the 3D contribution village (`profile-3d-contrib/`) and these panels with live stats, and commits only when something changed. `snake.yml` keeps the contribution snake on the `output` branch.
