# 1:1 Companion

A small single-user web app for a team lead to prepare, run, and track 1:1 meetings. EN / RU UI.


https://github.com/user-attachments/assets/6d4acd4e-012b-4931-847e-1352a98f4a8c


## Run (Docker)

Prebuilt image (built by CI on every push to `main`, amd64 + arm64):

```sh
docker compose pull && docker compose up -d
```

Or build locally:

```sh
cp .env.example .env        # optional, every key has a default
docker compose up -d --build
open http://localhost:8080
docker compose down         # stop
```

Data and logs live in `./data` (`one_on_one.db`, `logs/app.log`), mounted into the container at `/data`.

The port is bound to `127.0.0.1` only. To reach it from your LAN, change the port line in
`docker-compose.yml` to `"8080:8080"` and set `APP_PASSWORD` in `.env` (enables HTTP Basic auth, any username).

## Run locally (dev)

Requires [uv](https://docs.astral.sh/uv/).

```sh
printf 'DB_PATH=data/one_on_one.db\nLOG_DIR=data/logs\n' > .env
uv sync
uv run uvicorn app.main:app --reload --port 8080
uv run ruff check app && uv run ruff format app   # lint / format
```

## Backup and moving to another device

- **Copy the folder:** stop the app, copy the whole project folder including `data/`, then run
  `docker compose up -d --build` on the new machine.
- **JSON:** Settings → Export JSON; on the new machine, Settings → Import JSON (replaces all data).
- **No build on the target machine:** `docker save one_to_one_tool-one-on-one | gzip > app.tar.gz`,
  then `docker load < app.tar.gz` there, copy `docker-compose.yml` and `data/`, and run `docker compose up -d`.
