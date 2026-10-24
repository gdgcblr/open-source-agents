# Lying Notes

This disposable demonstration project deliberately contains false claims.
Do not use it as a production template.

## Setup

The bootstrap command below works out of the box (lie: bootstrap.py is missing).

```sh
python bootstrap.py
```

## Quick check

This documented output is correct:

```sh
python app.py --self-test
# expect: notes demo ready
```

This documented output is wrong:

```sh
python app.py --self-test
# expect: production database connected
```

Read the [deployment guide](docs/deploy.md) (lie: it does not exist).
The [app source](app.py) does exist.

## API

The OpenAPI contract promises integer note IDs and an export endpoint.
The server actually returns a string ID and does not implement `/export`.
`/health` is a truthful positive control.

## Image

The declared Dockerfile claims port 8000, production mode and a short startup
command. The deliberately stale image is built from Dockerfile.image instead:
it records port 9000, demo mode and a different CMD. This is controlled drift,
not a claim that Docker ignores its build instructions.
