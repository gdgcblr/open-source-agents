# WorkWise AI

WorkWise AI is a personalized work/business opportunity intelligence platform. It analyzes
developments (market, policy, industry, technology, etc.) against a user's profile, and turns
relevant ones into concrete, explainable strategies, financial scenarios, action plans, and
outcome tracking.

This is a working, end-to-end prototype: Spring Boot backend, Angular frontend, PostgreSQL
database, all orchestrated with Docker Compose. See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md)
and [docs/DATABASE_MODEL.md](docs/DATABASE_MODEL.md) for design details.

## Tech stack

- **Backend**: Java 21, Spring Boot 3.3.4, Spring Data JPA, Flyway, PostgreSQL
- **Frontend**: Angular 17 (standalone components), TypeScript, SCSS
- **Database**: PostgreSQL 16
- **Deployment**: Docker Compose (postgres + backend + frontend/nginx)

## Quick start (Docker Compose)

```bash
cp .env.example .env
docker compose up --build
```

- Frontend: http://localhost:4200
- Backend API: http://localhost:8080/api
- Swagger UI: http://localhost:8080/swagger-ui.html

The database is seeded with two demo profiles (a textile trader in Surat and a software engineer
in Bengaluru) and a handful of developments explicitly labeled `DEMONSTRATION DATA`, so the
relevance engine, financial calculator, and strategy comparison can be explored immediately
without configuring any external AI provider or real data source. Use the **persona switcher** in
the top-right of the app to flip between the two demo users.

## Running locally without Docker

### Backend

Prerequisites: Java 21, Maven 3.8+, a running PostgreSQL 16 instance.

```bash
cd backend
# create a database matching .env (default: workwise / workwise / workwise)
mvn spring-boot:run
```

Flyway applies the schema and demo-data migrations automatically on startup
(`src/main/resources/db/migration`).

Run the backend test suite (unit tests + Testcontainers-backed integration tests — requires a
working local Docker installation):

```bash
cd backend
mvn test
```

> If Testcontainers fails with "Could not find a valid Docker environment" / a Docker API version
> error, see [Troubleshooting](#troubleshooting) below.

### Frontend

Prerequisites: Node 18+, npm.

```bash
cd frontend
npm install
npm start   # ng serve --proxy-config proxy.conf.json, proxies /api to http://localhost:8080
```

Run the frontend unit tests:

```bash
cd frontend
npx ng test --watch=false --browsers=ChromeHeadless
```

Build for production:

```bash
cd frontend
npx ng build
```

## Configuration

All configuration is environment-variable driven. See [.env.example](.env.example) for the full
list. Key variables:

| Variable | Purpose |
|---|---|
| `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASSWORD` | PostgreSQL connection |
| `WORKWISE_AI_PROVIDER` | `mock` (default, deterministic, no API key needed) or `llm` |
| `WORKWISE_LLM_API_URL`, `WORKWISE_LLM_API_KEY`, `WORKWISE_LLM_MODEL` | Only used when `WORKWISE_AI_PROVIDER=llm` |

The **mock AI provider** is deterministic and rule-based — it never calls an external service and
requires no credentials, so the whole demo workflow (profile → feed → analysis → strategies →
financial scenarios → action plan → outcome) works out of the box.

## Demo-user authentication (prototype only)

Requests are scoped to a demo user via the `X-Demo-User-Id` header, read by
`com.workwise.ai.common.auth.DemoUserFilter`. This is **not real authentication** — it exists so
the prototype can demonstrate per-user data isolation and the persona switcher without building a
full identity provider. See the Javadoc on `DemoUserFilter` / `CurrentUser` for details.

## Project structure

```
workwise-ai/
  backend/    Spring Boot modular monolith (see docs/ARCHITECTURE.md for module breakdown)
  frontend/   Angular SPA (core/ for models+services+interceptor, features/ for pages)
  docs/       Architecture, database model, and implementation checklist
  docker-compose.yml
  .env.example
```

## Troubleshooting

**Testcontainers: "Could not find a valid Docker environment" / API version error.**
Some Docker Engine versions reject the old Docker API version that older `testcontainers-bom`
releases probe with. This project pins `testcontainers-bom` to `1.21.4` in
[backend/pom.xml](backend/pom.xml), which resolved this in testing. If you still hit it, check
`docker version --format '{{.Server.APIVersion}}'` and consider bumping the bom further.

**Angular build output path.** The Angular 17 `application` builder outputs to
`dist/frontend/browser` (not `dist/<app-name>/browser` from older builders) — this is already
reflected in [frontend/Dockerfile](frontend/Dockerfile).

**Frontend can't reach the backend in dev.** `npm start` runs `ng serve --proxy-config
proxy.conf.json`, which proxies `/api` to `http://localhost:8080`. Make sure the backend is
running on port 8080 first.

## Known limitations

- Demo-user auth is a prototype mechanism, not production authentication/authorization.
- The RSS source adapter's corroboration heuristic (used to promote evidence state) is a simple
  title-similarity check across sources, not a sophisticated NLP pipeline.
- The real LLM provider is implemented against a generic HTTP+JSON contract but has not been
  validated against a live third-party LLM endpoint in this environment.
- No scheduled/background job triggers ingestion automatically; it is invoked via
  `POST /api/ingestion/run`.
