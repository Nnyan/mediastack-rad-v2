# Changelog

## [2.3.1] - 2026-04-25

See commit history for changes.

## [2.3.0] - 2026-04-25

See commit history for changes.

## [2.2.16] - 2026-04-25

See commit history for changes.

## [2.2.15] - 2026-04-25

See commit history for changes.

## [2.2.14] - 2026-04-25

See commit history for changes.

## [2.2.13] - 2026-04-25

See commit history for changes.

## [2.2.12] - 2026-04-25

See commit history for changes.

## [2.2.11] - 2026-04-25

See commit history for changes.

## [2.2.10] - 2026-04-25

See commit history for changes.

## [2.2.9] - 2026-04-25

See commit history for changes.

## [2.2.8] - 2026-04-25

See commit history for changes.

## [2.2.7] - 2026-04-25

See commit history for changes.

## [2.2.6] - 2026-04-25

See commit history for changes.

## [2.2.5] - 2026-04-25

See commit history for changes.

## [2.2.4] - 2026-04-25

See commit history for changes.

## [2.2.3] - 2026-04-25

See commit history for changes.

## [2.2.2] - 2026-04-25

See commit history for changes.

## [2.2.1] - 2026-04-25

See commit history for changes.

## [2.2.0] - 2026-04-25

See commit history for changes.

## [2.1.0] - 2026-04-25

See commit history for changes.

All notable changes to MediaStack-RAD are documented here.

## [2.0.0] - 2026-04-21

Complete rewrite. Every piece of the v1 prototype was replaced based
on lessons learned during real-world deployment.

### Fixed

- **Duplicate env var bug** — Traefik's `CF_DNS_API_TOKEN` was silently
  overridden by a second empty copy. `docker compose` uses the last
  definition when keys are duplicated; no error is shown. The new
  validator (`validators.py`) detects this at compose-write time and
  the health checker detects it in the running container. This was the
  root cause of all DNS-01 cert failures during initial setup.

- **DNS-01 propagation timeouts** — Traefik's default propagation wait
  time is too short for Cloudflare. Fixed by adding `LEGO_DNS_TIMEOUT=300`
  to the Traefik environment and `delayBeforeCheck: 60` to `traefik.yml`.
  Both are now defaults in the generator and the health checker warns
  if they're below threshold.

- **Traefik API version error (`client version 1.24 is too old`)**
  — caused by `tecnativa/docker-socket-proxy` which does its own version
  negotiation. Removed the proxy entirely; Traefik now mounts the Docker
  socket directly with `ro` flag.

- **SPA catch-all intercepting API routes** — the `/{full_path:path}`
  route was registered before some API routes in `main.py`, causing API
  calls to silently return `index.html`. Fixed by construction (catch-all
  is always last) and enforced by an import-time assertion that fails fast
  if the order is ever broken.

- **Ghost containers blocking deploys** — after a failed recreate, Docker
  leaves a stopped container with a scrambled name (e.g. `12abc_sabnzbd`)
  that claims the original service name. Fixed by detecting and removing
  ghost containers in the health checker with auto-fix capability.

- **Dockerfile missing new modules** — v1 listed each backend Python file
  individually in `COPY` statements. Any new module not added to the list
  was silently omitted from the image. Fixed by `COPY backend/*.py`.

- **`readarr:develop` has no amd64 build** — the `:develop` tag is
  arm64-only. Catalog now uses `:latest` for Readarr.

- **`cloudflared` requires explicit `command:`** — the default entrypoint
  alone doesn't run the tunnel. Generator now always includes
  `command: tunnel --no-autoupdate run`.

- **Traefik YAML indent errors** — `delayBeforeCheck` and `provider`
  must be indented under `dnsChallenge`, not at the same level. The
  generator always produces correct YAML; the validator catches mistakes
  in hand-edited files before Traefik tries to load them.

- **Stale `_acme-challenge` TXT records** — leftover from failed ACME
  attempts poison subsequent propagation checks. Added
  `scripts/cleanup-acme.sh` and a button in the Traefik tab. The
  health checker detects this condition in the `check_cloudflare_token`
  step by watching for the two-value error pattern in Traefik logs.

- **SABnzbd + qBittorrent port collision** — both default to 8080.
  Generator remaps SABnzbd to 8085 on the host and sets `WEB_PORT=8085`.

- **socket-proxy publicly exposed via Traefik labels** — the proxy had
  a `Host(socket-proxy.nyrdalyrt.com)` label, effectively exposing
  the Docker socket to the internet. Removed entirely.

### Added

- **Health checker** — 9 checks running every 30 seconds in the
  background. Surfaces issues in real-time with auto-fix for ghost
  containers and ACME permissions.

- **Setup checklist** — live to-do list that tracks setup progress.
  Items check themselves off as the system detects completion.

- **Validators module** — YAML syntax validation, duplicate env key
  detection, compose structural checks (network references, port
  conflicts, `network_mode: host` + ports), Traefik-specific config
  validation. All run before writes and surfaced in the Health tab.

- **Install script** — `install.sh` sets up the entire environment
  in one command. Idempotent — safe to rerun for upgrades.

- **Cleanup script** — `scripts/cleanup-acme.sh` lists and deletes
  stale `_acme-challenge` TXT records from Cloudflare.

- **Pre-flight healthcheck** — `scripts/healthcheck.sh` runs without
  RAD being present. Useful for diagnosing bare-metal issues.

- **Traefik config generator** — `generator.py` now produces
  `traefik.yml` as well as `docker-compose.yml`. The generated Traefik
  config includes correct `delayBeforeCheck`, resolver list, and HTTP →
  HTTPS redirect by default.

- **Setup checklist** — new Checklist tab in the dashboard.

- **CI smoke tests** — GitHub Actions workflow runs 3 backend smoke
  tests on every push: duplicate env key detection, compose generator
  validation, and SPA route ordering assertion.

- **`LEGO_DNS_TIMEOUT=300`** — set in every generated Traefik deployment
  as a default. Not configurable in traefik.yml (it's an env var that
  LEGO reads directly).

### Changed

- Generator uses a single shared Docker network (`mediastack`) for all
  services instead of project-name-prefixed networks.

- Traefik labels now include `tls=true` and `tls.certresolver=letsencrypt`
  so routers issue certs automatically. v1 labels left these unset,
  which caused every router to stay in "pending" state.

- Removed `tecnativa/docker-socket-proxy` from the generated stack.

- Health check interval configurable via `RAD_HEALTH_INTERVAL` env var.

- WebSocket stats hub now fan-out to all connected clients instead of
  per-container streams, reducing Docker API calls.

## [1.0.0] - 2026-04-19

Initial working deployment. React prototype replaced with FastAPI +
Vue 3. Wildcard cert via Traefik DNS-01. All basic *arr services running.
External HTTPS access confirmed via Cloudflare DNS.
