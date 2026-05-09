# Integration Test Harness — REG-9..REG-15

End-to-end smoke tests covering every subsystem the registry depends on.

## Quick start

```bash
docker compose up -d              # bring up the full stack
./scripts/run-integration-tests.sh
docker compose down -v            # tear down + wipe volumes
```

The runner exits non-zero on the first failing subsystem and prints a coloured pass/fail report.

## Dependencies

The runner uses these CLI tools (install via `brew` / `apt` if missing):

| Tool       | Used by                  | Install                |
|------------|--------------------------|------------------------|
| `psql`     | REG-9 Postgres tests     | `brew install postgresql` |
| `redis-cli`| REG-10 Redis tests       | `brew install redis`   |
| `aws`      | REG-11 S3 tests          | `brew install awscli`  |
| `curl`     | REG-12, REG-13, REG-14, REG-15 | system default   |

## Subsystem coverage

| ID      | Subsystem        | What's verified                                           |
|---------|------------------|-----------------------------------------------------------|
| REG-9   | Postgres         | connectivity, migrations applied, packages CRUD round-trip |
| REG-10  | Redis            | PING, sliding-window counter, pub/sub round-trip          |
| REG-11  | S3 (minio)       | bucket exists, put/get/delete, presigned URL signing      |
| REG-12  | Meilisearch      | health, index + search round-trip                         |
| REG-13  | Sigstore staging | Rekor v2 `/api/v1/log` + Fulcio v2 `/api/v2/configuration` |
| REG-14  | TUF metadata     | timestamp.json + 1.root.json + 1.snapshot.json + 1.targets.json |
| REG-15  | WebAuthn         | register/begin + authenticate/begin endpoints             |

## Architecture

```
┌────────────────────────────────────────────────────────────────────┐
│  scripts/run-integration-tests.sh                                  │
│                                                                    │
│  ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐ ┌─────────┐        │
│  │ REG-9   │ │ REG-10  │ │ REG-11  │ │ REG-12  │ │ REG-13  │ …       │
│  │  psql   │ │redis-cli│ │  aws s3 │ │  curl   │ │  curl   │        │
│  └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘ └────┬────┘        │
│       │           │           │           │           │             │
└───────┼───────────┼───────────┼───────────┼───────────┼─────────────┘
        │           │           │           │           │
   ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼─────┐
   │postgres │ │ redis   │ │ minio   │ │meilisrch│ │sigstage  │
   │  :5432  │ │  :6379  │ │  :9000  │ │  :7700  │ │ (https)  │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └──────────┘
```

* **Sigstore** runs against the public staging endpoints (`rekor.sigstage.dev`, `fulcio.sigstage.dev`) — the registry never hosts its own Sigstore.
* **TUF** is served by the registry itself from `/tuf/<role>.json`; no external service needed.
* **WebAuthn** is protocol-only; ceremonies happen in-process between the registry and a hypothetical browser/authenticator.

## Bringing up the stack

`docker-compose.yml` defines six services:

| Service       | Image                       | Purpose                       |
|---------------|-----------------------------|-------------------------------|
| `registry`    | (build from `./Dockerfile`) | the application               |
| `postgres`    | `postgres:17`               | primary persistence           |
| `redis`       | `redis:7-alpine`            | cache + rate-limit counters   |
| `meilisearch` | `getmeili/meilisearch:v1.6` | package full-text search      |
| `minio`       | `minio/minio:latest`        | S3-compatible object store    |
| `minio-init`  | `minio/mc:latest`           | one-shot bucket bootstrap     |

The `minio-init` container creates the `verum-registry-packages` bucket on first run and exits.  The `registry` container waits on `minio-init`'s successful completion (`condition: service_completed_successfully`) before starting, so source-archive uploads never hit `NoSuchBucket`.

## Environment overrides

The runner honours these variables (defaults shown):

```bash
REGISTRY_URL=http://localhost:8080
DATABASE_URL=postgres://verum:verum@localhost:5432/registry
REDIS_URL=redis://localhost:6379
SEARCH_URL=http://localhost:7700
MEILI_MASTER_KEY=verum-search-key
S3_ENDPOINT=http://localhost:9000
S3_BUCKET=verum-registry-packages
AWS_ACCESS_KEY_ID=verumregistry
AWS_SECRET_ACCESS_KEY=verumregistry-dev-secret
```

Pointing at a remote stack is just a matter of overriding these — e.g. against a CI environment:

```bash
REGISTRY_URL=https://staging.vcogs.io \
DATABASE_URL=postgres://ci:ci@db.staging.vcogs.io/registry \
./scripts/run-integration-tests.sh
```

## CI integration

The runner is designed to plug into GitHub Actions / GitLab CI as a single step. Example workflow snippet:

```yaml
- name: Bring up stack
  run: docker compose up -d --wait

- name: Apply migrations
  run: ./scripts/apply-migrations.sh

- name: Integration tests
  run: ./scripts/run-integration-tests.sh

- name: Tear down
  if: always()
  run: docker compose down -v
```

## Adding a new subsystem

1. Add the service to `docker-compose.yml` (with healthcheck + restart policy).
2. Add a `# REG-N — Name` block to `scripts/run-integration-tests.sh` that exits non-zero on failure.
3. Add the row to the **Subsystem coverage** table above.
4. Update `tests/integration/README.md` with the .vr-side counterpart if there is one.
