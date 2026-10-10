# Releasing Choice

This document is the plan for how Choice reaches teachers, parents, and other non-developers. It describes what we ship, how each artifact is built in **GitHub Actions** from **tagged releases**, and what still needs to be built in the product first.

Choice is AGPL-3.0. Anyone who runs a modified version over a network must offer corresponding source. Release artifacts should make that obligation clear and easy to satisfy.

---

## How releases work (overview)

1. A maintainer updates `CHANGELOG.md` and bumps `choice/__init__.py` and `pyproject.toml` on `main`.
2. A git tag `vX.Y.Z` is pushed (for example `v0.5.0`).
3. GitHub Actions workflow **`release.yml`** (to be added) runs on `push: tags: v*`:
   - Runs the full test suite (Python + Node layout tests where applicable).
   - Builds all release outputs below.
   - Attaches them to the GitHub Release for that tag.
   - Publishes to PyPI (trusted publishing) when the tag is stable (optional pre-release tags can skip PyPI).

Every downloadable file gets a **SHA-256 checksum** in `SHA256SUMS.txt` on the release page. An **SBOM** (CycloneDX or SPDX JSON) is generated for container and Windows builds.

---

## 1. PyPI

### Name on PyPI

The project name **`choice` is already taken** on PyPI (unrelated package, “Easy request and response GUI for Python”, last published as 0.1). We should **not** fight for that name.

**Recommended PyPI name:** `choice-swipe` (available at time of writing).

Alternatives if branding changes: `choice-pile`, `swipe-choice`, `pile-choice` (all were unclaimed when checked). The **console command** can stay `choice` via `[project.scripts]` even when the distribution name is `choice-swipe`.

### What gets published

- **Wheel** (`choice_swipe-*.whl`) and **sdist** (`choice_swipe-*.tar.gz`) built with `python -m build`.
- **Bundled static UI:** `choice/web/*` is already declared in `[tool.setuptools.package-data]`; verify wheels contain `app.js`, `app.css`, `index.html`, icons, and service worker after `pip install`.
- **Dependencies:**
  - Runtime: stdlib only for core use.
  - **Optional extra `images`:** `Pillow>=10,<12` (pin upper bound in release branch; document why in changelog).
  - Document that photo folders and WebP thumbnails need `pip install "choice-swipe[images]"`.
- **Entry point:** `choice = choice.cli:main` (unchanged user experience: `python -m choice` and `choice` after install).

### Supported Python versions

| Version | Policy |
|--------|--------|
| **3.11** | Minimum (matches `requires-python` and Ruff `py311` today). |
| **3.12** | Supported; CI must test on 3.12. |
| **3.13** | Supported when Pillow and CI runners are green. |
| **3.14+** | Best-effort after upstream support; not a release blocker for 0.5.x. |

Classifiers in `pyproject.toml` should list supported versions explicitly. Drop 3.11 only after a announced deprecation window.

### PyPI workflow steps (Actions)

1. `checkout` → `setup-python` (matrix 3.11, 3.12) → `pip install build` → `python -m build`.
2. `twine check dist/*`.
3. Attach `dist/*` to GitHub Release.
4. `pypa/gh-action-pypi-publish` with **OIDC trusted publishing** (no long-lived API tokens in the repo).

---

## 2. Docker

### Image goals

- **Multi-arch:** `linux/amd64` and `linux/arm64` (Apple Silicon servers, Raspberry Pi class devices).
- **Pinned base:** `python:3.12-slim-bookworm` (or digest-pinned equivalent).
- **Pinned Pillow** in the image (not optional there): exact version in `requirements-docker.txt` generated at release time.
- **Non-root user** inside the container; read-only root filesystem where practical.

### Layout and volumes

| Mount | Purpose |
|-------|---------|
| `/config/choice.toml` | Main config file (file or dir mount). |
| `/data/decks` | Deck folders, plugins, `deck.json`, media. |
| `/data/state` | Per-deck state (`.choice-state` or `[state] dir` target). |
| `/data/secrets` | Optional `secrets_file` (never bake secrets into the image). |

Environment variables (convention for compose):

- `CHOICE_CONFIG=/config/choice.toml`
- `CHOICE_HOST=127.0.0.1` (default **inside** the container — see networking below)
- `CHOICE_PORT=8741`
- `CHOICE_BASE_PATH` (optional reverse-proxy prefix)
- `CHOICE_TITLE` (optional instance name)

### Default networking story

**Default:** process listens on **127.0.0.1 only inside the container**. That is safe but not useful until the operator publishes a port.

**Recommended patterns in docs:**

1. **Same machine:** `docker run -p 127.0.0.1:8741:8741 …` — browser on the host opens `http://127.0.0.1:8741/`.
2. **LAN (explicit):** compose file sets `CHOICE_HOST=0.0.0.0` and documents `--lan` equivalent; firewall and “anyone on the network can swipe” warning must match the CLI today.
3. **Reverse proxy:** Traefik/Caddy with TLS; `CHOICE_BASE_PATH` for path-based routing (Sky / Spicy pattern).

### Compose examples (to ship in `deploy/compose/`)

- `compose.local.yml` — loopback publish, single volume for a demo deck.
- `compose.lan.yml` — `0.0.0.0` + commented firewall note.
- `compose.dual.yml` — two services, different `CHOICE_BASE_PATH` and configs (reference deployment).

### Docker workflow steps (Actions)

1. `docker/build-push-action` with `platforms: linux/amd64,linux/arm64`.
2. Tags: `ghcr.io/<org>/choice:vX.Y.Z`, `:X.Y`, `:latest` (only on stable tags).
3. SBOM: `anchore/sbom-action` or BuildKit attestations.
4. Sign: **cosign** keyless OIDC for GHCR (optional but recommended).

---

## 3. Windows single executable

### Recommendation: **PyInstaller** first, Nuitka later if needed

| | PyInstaller | Nuitka |
|---|-------------|--------|
| Time to first ship | Weeks | Often months of edge cases |
| AGPL compliance | Straightforward (bundle source offer in installer) | Same, but build complexity |
| Pillow / stdlib | Well trodden | Good but fussy on Windows |
| One-file exe | Supported (`--onefile`) | Supported |
| Code size | Larger | Often smaller/faster |

`choice/web_paths.py` already checks `sys._MEIPASS` for frozen bundles — align PyInstaller spec with `choice/web` as datas.

### Target behavior (product + installer)

1. User double-clicks **`Choice.exe`** (name TBD).
2. App starts embedded Python + `choice.cli:main` with:
   - Config and state under `%LOCALAPPDATA%\Choice\` (or user-picked folder on first run).
   - `--open` to launch default browser to the printed URL.
3. **First-run setup wizard** (see §5) — not “edit choice.toml in Notepad”.
4. **Tray icon:** quit, open in browser, “open data folder”, optional “start with Windows”.
5. **Autostart:** optional shortcut in Startup folder or registry key; off by default; plain-language consent.

### Code signing and SmartScreen

| Option | Rough cost (2026, order of magnitude) | Effect |
|--------|----------------------------------------|--------|
| **No signing** | $0 | SmartScreen “Windows protected your PC” until reputation builds; fine for devs, harsh for parents. |
| **Standard code signing (OV)** | ~$200–400/year | Removes unknown-publisher warning after install; reputation still grows. |
| **EV code signing** | ~$400–700/year + hardware token | Faster SmartScreen trust; best for widely distributed exe. |

**Plan:** ship unsigned builds on GitHub for early adopters; document SmartScreen “More info → Run anyway”. Add **optional signed builds** from a protected Actions environment when the project has a cert. Store cert in GitHub **environments** / Azure Key Vault — never in the repo.

### Windows workflow steps (Actions)

1. `windows-latest` runner, Python 3.12, `pip install .[images] pyinstaller`.
2. Run PyInstaller spec → `dist/Choice/Choice.exe` (or onefile).
3. Zip with `LICENSE`, `AGPL-3.0.txt`, `SOURCE.txt` (link to tag + offer of source).
4. SHA-256 in `SHA256SUMS.txt`.
5. Optional: `signtool` step when secrets exist.

---

## 4. Linux click-to-run and macOS

### Recommendation: **Flatpak** for “install like an app”; **AppImage** for portable demos

| | AppImage | Flatpak |
|---|----------|---------|
| Audience | Power users, USB stick demos | Families, school laptops (Flathub) |
| Sandboxing | Loose | Strong (portal for files) |
| Updates | Manual | Flathub delta updates |
| Effort | Lower | Higher (manifest + portals) |

**Ship both eventually:** AppImage on the GitHub Release for quick try-out; Flatpak as the supported “installed app” path if we pursue Flathub.

### Linux artifact

- Bundle CPython + Pillow + Choice into AppImage via `appimagetool` or **briefcase**-style layout.
- Default: bind **127.0.0.1**, open browser via `xdg-open` (same as `--open`).
- Document **Firejail / Wayland** quirks only if tests show issues.

### macOS notes (not a blocker for 0.5)

- No signed `.app` in the first wave unless someone sponsors Apple Developer ($99/year).
- Document: `python -m pip install choice-swipe[images]` + `choice` CLI, or Docker.
- Later: **py2app** or Briefcase; notarization required for smooth Gatekeeper.

### Workflow (Actions)

- `ubuntu-latest` job: build AppImage, attach to release.
- Separate workflow file or manual `workflow_dispatch` for Flatpak/Flathub submission.

---

## 5. First-run experience (product direction)

Today, setup is a **web wizard** for sources/decks (`showSetup`, `choice.toml` editing). That is still too close to “admin UI”, not “parent sets up for kids”.

### Goals

- **No config file editing** on first run.
- Plain language: “Who is this for?”, “What are you sorting?”, “Photos / story / quiz / food preferences”.
- **Starter decks** included in the install (or downloaded once, checksum verified):

| Starter | Use case | Format |
|---------|----------|--------|
| **Adventure** | Choose-your-own-adventure | `story` or branching `jsonl` (extend examples) |
| **Quiz** | Classroom review | `jsonl` or `csv` with score fields |
| **Food** | Likes, dislikes, allergies | Simple cards + labels; no medical claims in copy |

- **Sharing on the home network:** wizard step explains “Only people on your Wi‑Fi can join” with a **single explicit toggle** (maps to `--lan` / `0.0.0.0`). Default remains **this device only**.
- **People / kid profiles:** optional step linking to existing People feature (`users.json`) with “no password, just a name” messaging.

### Wizard surfaces

| Platform | Where it lives |
|----------|----------------|
| Web (now) | Extend `ChoiceDialog` wizard; trigger on empty library or `?setup=1`. |
| Windows exe | Same web UI on first launch + tray “Setup again”. |
| Docker | Entrypoint opens browser once if `/config/choice.toml` missing; seed from templates. |

### Gaps (see §7)

First-run templates, LAN copy, and kid-safe defaults are **mostly product work**, not packaging.

---

## 6. Release hygiene

### Repository rules (tool-neutral)

Add or enforce via **`.gitattributes`**, **`.gitignore`**, and **CONTRIBUTING** (short, human-readable):

**Never commit**

- Agent / LLM session exports, prompts, transcripts, `.cursor/`, `.aider*`, `uploads/` working notes.
- Virtualenvs, `__pycache__`, `.pytest_cache`, `node_modules`, local `choice.toml` / secrets.
- Generated state under `examples/**/.choice/` or test fixture `state/` (already partially gitignored).

**Allowed dotfiles**

- `.gitignore`, `.gitattributes`, `.editorconfig`, `.github/` only (no other dot-directories in tree without review).

**Every tag release includes**

- `CHANGELOG.md` section for that version (Keep a Changelog style).
- `SHA256SUMS.txt` for zip, exe, AppImage, wheel, sdist, bundle.
- **Git source archive:** `git archive` zip (today’s `scripts/make_release_zip.sh`) plus optional `git bundle` for full history.
- **SBOM** for Docker image and Windows exe (Python deps + Pillow version).
- **AGPL:** `LICENSE` in repo; Windows zip includes `LICENSE` + short `AGPL-NOTICE.txt` (“you may request source for this version at …”).

### Branch and tag policy

- `main` is always releasable; tags are immutable.
- Pre-release tags `vX.Y.Z-rc.N` build artifacts but may skip PyPI `latest`.

---

## 7. Gaps in the codebase (phased)

What blocks each target, in a sensible build order.

### Phase A — Packaging foundation (blocks PyPI + honest 1.0)

| Gap | Blocks |
|-----|--------|
| Rename distribution to **`choice-swipe`** (or chosen name); document on README | PyPI |
| `MANIFEST.in` / wheel audit test that every `choice/web` asset is present | PyPI, PyInstaller |
| Lockfile or `requirements-lock.txt` for reproducible CI | Docker, SBOM |
| GitHub Actions: test matrix + `release.yml` skeleton | All |
| No `pyproject` dynamic version from git tag yet | Cleaner releases |

### Phase B — Container (blocks Docker compose docs)

| Gap | Blocks |
|-----|--------|
| `Dockerfile` + healthcheck hitting `/api/health` | Docker |
| Official env var mapping (`CHOICE_*`) in `cli.py` | Docker, compose |
| Documented volume layout; entrypoint script | Docker |
| Non-root USER in image | Production hygiene |

### Phase C — First-run product (blocks family-friendly story)

| Gap | Blocks |
|-----|--------|
| Wizard flows for **story / quiz / food** without TOML | Windows exe marketing, schools |
| Bundled **starter decks** in package data | First-run |
| LAN toggle with safety copy in wizard | Home sharing |
| Simpler “instance” concept (title + data dir) for non-config users | Sky/Spicy pattern for families |

### Phase D — Windows exe (blocks double-click audience)

| Gap | Blocks |
|-----|--------|
| PyInstaller spec + CI job | Windows exe |
| Tray app wrapper (separate small module or `pystray`) | Tray, autostart |
| Default data dir under `%LOCALAPPDATA%` | First-run |
| `--open` default on frozen build | Double-click UX |
| Code signing pipeline (optional secret) | SmartScreen |

### Phase E — Linux / macOS polish

| Gap | Blocks |
|-----|--------|
| AppImage recipe | Linux click-to-run |
| Flatpak manifest + file portals for folder picks | Flathub |
| macOS app bundle | Mac teachers |

### Phase F — Release automation completeness

| Gap | Blocks |
|-----|--------|
| SBOM generation in CI | Compliance, schools |
| Cosign for container | Supply chain |
| Flathub / Microsoft Store | Optional distribution |

---

## Quick reference: artifacts per GitHub Release tag

| Artifact | Built by | Consumer |
|----------|----------|----------|
| `choice-swipe-*-py3-none-any.whl` | `python -m build` | `pip install` |
| `choice-swipe-*.tar.gz` | sdist | packagers |
| `choice-X.Y.Z.zip` | `git archive` | Windows manual install (current path) |
| `choice-X.Y.Z.bundle` | `git bundle` | offline git clone |
| `Choice-X.Y.Z-win64.zip` | PyInstaller | parents, teachers |
| `Choice-X.Y.Z-x86_64.AppImage` | AppImage tool | Linux try-out |
| `ghcr.io/.../choice:X.Y.Z` | Docker buildx | homelab, NAS |
| `SHA256SUMS.txt` | CI script | everyone |
| `sbom.json` | CI | compliance |

---

## Maintainer checklist (each release)

1. Changelog entry merged.
2. Version bump in `choice/__init__.py` and `pyproject.toml`.
3. `git tag -s vX.Y.Z` (signed tags encouraged).
4. Push tag; wait for green Actions.
5. Verify GitHub Release assets and checksums.
6. Smoke-test: `pip install` wheel, `docker pull` + compose local, Windows zip on a VM if exe changed.
7. Announce: what changed, who it is for, AGPL reminder for redeployers.

---

*This is a living plan. Update it when the first `release.yml` lands or when the PyPI name is registered.*
