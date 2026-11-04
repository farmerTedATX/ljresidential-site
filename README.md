# LJ Residential website

Static rebuild of ljresidentialgroup.com, moved off Luxury Presence and hosted on Netlify.
It looks the same as the old site, minus home search. There is no backend.

## Layout

- `site/` is what Netlify publishes. Every page is plain HTML, and every image, video, font,
  stylesheet, script and PDF is in `site/assets/`, so nothing loads from Luxury Presence.
- `site/js/site.js` holds the only new code:
  - **Forms** (Let's Connect, newsletter, home valuation) post to Netlify Forms instead of
    Luxury Presence. Submissions show up in Netlify under Forms, as `contact`, `newsletter`
    and `home-valuation`.
  - **Saved data:** testimonials and featured properties used to come from Luxury Presence's
    API. The answers were saved in `site/data/api.json` and are served from there.
  - **Home valuation:** step 1 no longer needs Google Maps. Any address that starts with a
    house number unlocks Continue.
- `source/mirror/` is the raw HTML saved from the live site on 2026-11-04, and
  `source/mirror/api-rec.json` holds the recorded API answers.
- `tools/build.py` turns `source/mirror/` into `site/`.

## Editing content

Edit the HTML in `site/` directly. For example, the footer address is in each page's footer.
To change a testimonial or a featured property, edit `site/data/api.json`.

## Rebuilding from the mirror

This only works while the old CDNs are still up:

    python3 -I tools/build.py source/mirror .cache site
