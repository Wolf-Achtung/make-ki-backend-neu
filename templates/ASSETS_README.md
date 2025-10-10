# Assets – Path conventions

**Goal:** one unified way to reference logos/icons from templates and HTML emails.

## Where to place files

```
public/assets/                      # recommended (served by frontend/webserver)
   ki-sicherheit-logo.webp
   ki-sicherheit-logo.png
   tuev-logo.webp
   tuev-logo-transparent.webp
   ki-ready-2025.webp
   dsgvo.svg
   eu-ai.svg
```

If you prefer the backend to read directly from the repo, you can also put them into
`<backend>/templates/assets/` and set the env var:

```
ASSETS_BASE_URL=/assets            # default in gpt_analyze (can be changed)
```

## How templates reference assets

All images are referenced via the placeholder `{{ASSETS_BASE}}` – for example:

```html
<img src="{{ASSETS_BASE}}/ki-ready-2025.webp" alt="KI-Ready 2025">
```

`gpt_analyze.py` fills `{{ASSETS_BASE}}` from the environment variable `ASSETS_BASE_URL`
(default: `/assets`). This keeps frontend, backend and PDF service aligned.
