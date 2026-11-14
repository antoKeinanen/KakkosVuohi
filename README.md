# KakkosVuohi

A Telegram bot that estimates the blood alcohol concentration (EBAC) of its users from the drinks they log. In groups it lists every member's EBAC in permilles or in Finnish standard drinks (12.0 grams). The bot's texts are in Finnish. Try it at [@kakkos_vuohi_bot](https://t.me/kakkos_vuohi_bot).

KakkosVuohi replaces BläkkisVuohi (`@blakkisvuohibot`, [source](https://gitlab.com/ultsi-projects/blakkisvuohi)), the earlier Node.js bot, which has been shut down. It is a rewrite in **Python 3.11+** with [aiogram 3](https://docs.aiogram.dev/) and **SQLite**. The commands, the texts and the alcohol math are the same as in BläkkisVuohi 4.x. The stack changed, and so did how much personal data the bot keeps and how it protects it.

Thanks Yago for the [Telegram Bot API framework for NodeJS](https://github.com/yagop/node-telegram-bot-api) that the earlier versions were built on.

## Running it

You need a bot token from [@BotFather](https://t.me/BotFather) and a secret key (`python -c "import secrets; print(secrets.token_urlsafe(48))"`).

**Docker** (recommended). The token and the key are read from secret files, not from the environment:

```sh
cp .env.example .env && $EDITOR .env           # ADMIN_ID, TIMEZONE... (no secrets in here)
mkdir -p secrets && chmod 700 secrets
printf %s "<token from BotFather>" > secrets/bot_token
python3 -c "import secrets; print(secrets.token_urlsafe(48), end='')" > secrets/secret_key
sudo chown 10001:10001 secrets/* && sudo chmod 400 secrets/*   # the container runs as uid 10001
docker compose up -d --build
```

Instead of building locally, you can use the prebuilt image: GitHub Actions (`.github/workflows/docker.yml`) runs the checks and, on every push to `master`, publishes `ghcr.io/<owner>/<repo>:latest` (also `:sha-<commit>`, and `:1.2.3` / `:1.2` for `v1.2.3` tags). Pull requests only build. Set `image:` in `docker-compose.yml` to that name and use `docker compose pull`. A new package is private by default; make it public under the package settings if needed.

The container runs as an unprivileged user, with a read-only root filesystem, without capabilities, and with the data and the keys on two separate volumes.

**Locally** (with [uv](https://docs.astral.sh/uv/)): uncomment `BOT_TOKEN` and `SECRET_KEY` in `.env`, then

```sh
uv run blakkisvuohi
```

### Configuration

All settings are environment variables (or in `.env`, or secret files in `/run/secrets`). See [`.env.example`](.env.example).

| Variable | |
|---|---|
| `BOT_TOKEN` | **required.** Bot token from BotFather |
| `SECRET_KEY` | **required.** At least 32 characters, see below |
| `DATABASE_PATH`, `KEY_DATABASE_PATH` | The encrypted data and the keys: two different SQLite files |
| `RETENTION_DAYS` | Drinks older than this are deleted. Default `7` |
| `ACCOUNT_RETENTION_DAYS` | Accounts not used for this long are deleted. Default: `RETENTION_DAYS` |
| `PURGE_HOUR` | Local hour of the daily purge. Default `12` |
| `ADMIN_ID` | Telegram id of the admin. Admin commands are disabled without it |
| `TIMEZONE` | Times in messages and the purge hour, default `Europe/Helsinki` |
| `LOG_LEVEL` | `DEBUG` `INFO` `WARNING` `ERROR` |
| `BOT_MODE` | `polling` (default) or `webhook` |
| `WEBHOOK_URL`, `WEBHOOK_SECRET`, `HOST`, `PORT` | webhook mode only |

### Webhook mode

Put the bot behind an HTTPS reverse proxy, set `BOT_MODE=webhook`, `WEBHOOK_URL=https://…` and a random `WEBHOOK_SECRET`. The bot registers the webhook itself on startup. Telegram sends the secret with every update (`X-Telegram-Bot-Api-Secret-Token`) and requests without it are rejected with 401. `GET /healthz` can be used as a health check.

Webhook mode is not meant for hosts with an ephemeral filesystem such as Heroku. Use a VPS or a platform with persistent volumes.

## Security

The bot keeps little personal data (a nickname, weight, height, gender, the drinks and the groups a user has joined), and it is protected in layers. The goal is two-fold: make a breach unlikely to yield anything, and make it small if it happens anyway.

### 1. Keep less, and for a short time

* **Drinks are kept for a week** (`RETENTION_DAYS`). Nothing older is read, and the purge deletes it.
* **Accounts that have not been used for a week are deleted completely**, so nobody's data lingers because they stopped using the bot. They sign up again if they come back. The bot cannot warn them first: it does not store Telegram ids, so it has no way to message somebody who is not talking to it.
* Weight and height are stored to the nearest 5 kg / 5 cm (`PROFILE_STEP` in `constants.py`; set it to 1 for exact values). It changes the estimates by about 3 % at most.
* No creation time and no raw Telegram ids. Besides the drinks (with their times, for a week), the only record of use is the *day* of the latest use, which expires accounts.
* The only things that outlive the retention period are two counters of how many drinks and how much alcohol have ever been recorded. They are not linked to anybody.

### 2. Everything that remains is encrypted, per user

* Telegram user and chat ids are stored as an **HMAC-SHA-256** under `SECRET_KEY` (BläkkisVuohi used an unsalted SHA-256 that could be brute forced, because Telegram ids are small numbers).
* The nickname, body data and **all drinks of a user are encrypted with AES-256-GCM under that user's own random key**. Each ciphertext is bound to its owner and purpose, so it cannot be moved between users or reused as another kind of data, and is padded to a fixed block size so that its length does not reveal how many drinks someone has.
* The per-user keys are stored **wrapped** (encrypted) under a master key derived from `SECRET_KEY`, **in a different database file** than the data.
* Deleting an account destroys the key first. From that moment the data is unreadable, **also in any copy of the data database** (a backup, a stolen file) - "crypto-shredding".
* The one thing that is queryable is which pseudonymous user is in which pseudonymous group, which is what group listings need.

### 3. The daily purge

At `PURGE_HOUR` (noon by default, in `TIMEZONE`) the bot deletes expired drinks and accounts, removes leftovers (data without a key, keys without data), and rewrites both database files so that no trace of deleted rows is left (`secure_delete`, WAL checkpoint, `VACUUM`). If the bot was down at noon, it purges at startup instead. `/admin_purge` runs it on demand. The same rules are applied when reading, so data past the retention period is ignored even if a purge has failed.

### What a leak gives away

| Scenario | An attacker gets |
|---|---|
| A copy of the data database (backup, SQL injection, stolen file) | Pseudonyms, the group membership graph, and ciphertext of fixed block sizes. No keys: nothing readable. |
| The data database *and* the key database, but not `SECRET_KEY` | The same: the keys are wrapped under the master key |
| Everything on the server, including `SECRET_KEY` from memory | At most one week of data of the people who used the bot during that week |

No scheme can protect data from an attacker who controls the running process, which is why the first layer matters most.

### Other protections

| BläkkisVuohi 4 | KakkosVuohi |
|---|---|
| Webhook secret was the bot token in the URL | Unguessable path **and** Telegram's secret-token header, checked in constant time; no access log; no version disclosure |
| Texts were sent as Markdown with nicknames and chat titles pasted in (formatting injection, broken messages) | HTML parse mode, **every user-controlled value is escaped** |
| Whole updates (user messages) logged at debug level | Message contents are not logged, and errors reported to the admin do not include the user's input |
| No limits on input or request rate; negative or zero amounts were accepted in some flows | Strict ASCII-only input parsing and range checks, a per-user rate limit, caps on batch sizes and drinks per user |
| Hardcoded admin id | Configuration |
| Account deletion was three independent queries | Key destroyed, then data removed, then the files flushed |
| – | Database files `0600` in `0700` directories, only `message` and `callback_query` updates requested, authorisation enforced in one middleware from per-handler flags, secrets from files |
| – | The bot **refuses to start with a different `SECRET_KEY`** than the databases were created with |

### Keys, backups and the host

**`SECRET_KEY`.** Everything derives from it. Keep it in a secret file or a secret manager, never in the repository, and not on the same backup as the data. It cannot be rotated in place: changing it makes all stored data unreadable (the bot refuses to start). Since only a week of data exists, rotating means stopping the bot, deleting both database files and starting with the new key; users sign up again.

**Backups.** There is little reason to back this bot up: it holds one week of data that people can re-enter in a minute. If you do:

* Back up only the `data` volume, **never** `keys`, and not to the same place. A backup of the data alone is worthless to a thief, and the account of a user who is deleted later cannot be restored from it, which is what makes deletion real.
* Encrypt the backups and keep them no longer than the retention period, so that deleted accounts age out of them. For example (requires `sqlite3` and [`age`](https://age-encryption.org/)):

  ```sh
  sqlite3 data.sqlite3 ".backup '/tmp/data.bak'"
  age -r "$AGE_PUBLIC_KEY" -o "backups/data-$(date +%F).sqlite3.age" /tmp/data.bak && shred -u /tmp/data.bak
  find backups -name '*.age' -mtime +7 -delete
  ```

**The host.** Not something the repository can do for you, but it matters:

* Allow outbound connections only to `api.telegram.org` (and DNS). A compromised bot then cannot send data anywhere else. Docker alone cannot restrict by domain; use the host firewall or an egress proxy.
* Inbound: nothing in polling mode; only your reverse proxy's HTTPS port in webhook mode. SSH with keys only, automatic security updates.
* If you suspect a compromise: revoke the bot token with BotFather, replace `SECRET_KEY` and the databases as described above.

Users can download everything stored about them with `/data` and delete it from the settings of `/start`.

## Development

```sh
uv sync                  # creates .venv with everything
uv run pytest            # tests
uv run ruff check src tests && uv run ruff format src tests
```

The tests drive the real dispatcher with synthetic Telegram updates against a fake Bot API session (`tests/harness.py`), so everything from access control to the multi-step conversations, the menu and the purge is covered without a network. `tests/golden_alcomath.json` holds values produced by the original JavaScript implementation of the alcohol math; the Python port is checked to match them.

Layout:

```
src/blakkisvuohi/
  app.py            building the dispatcher; polling / webhook; starting the purge
  config.py         settings
  security.py       pseudonyms, per-user keys, sealing and wrapping
  scheduler.py      the daily purge
  alcomath.py       the Widmark based math
  db/               the two SQLite databases
    codec.py          the encrypted layout (the only place that knows it)
    vault.py          the users' keys          users.py drinks.py groups.py stats.py  repositories
    retention.py      the purge                database.py  connections, migrations
  handlers/         commands (one module per area); access rules are flags on the handlers
  menu/             the /start inline keyboard menu: engine.py (generic) and tree.py (the screens)
  middlewares.py    rate limit, access control, activity, announcements
  strings.py        all texts (Finnish)
```

Because everything personal is encrypted, there is no SQL over the data: group listings and statistics decrypt the (few) accounts they need in Python.

To change the database schema, **append** a migration to `DATA_MIGRATIONS` / `KEY_MIGRATIONS` in `db/database.py`; never edit one that has been released. New announcements go to the end of the list in `announcements.py`.

## Differences from BläkkisVuohi 4

Nothing was removed. Things that changed on purpose:

* **Data is kept for a week**, and accounts expire after a week without use (see Security). Statistics therefore cover at most that week: `/stats 30` means "the last 7 days", and the `/start` statistics offer 1, 3 and 7 day ranges. The "everyone together has recorded N drinks" figure still counts all time, from the anonymous counters.
* Weight and height are stored to the nearest 5; "Käyttäjä luotu" is no longer shown, as it is no longer stored.
* Times in messages follow `TIMEZONE` instead of the server's timezone.
* `/start` menu: the "Oma juoma" and "Jälkikellotus" inputs and account creation validate their input like the matching commands do (no zero or negative amounts, the gender must be Mies/Nainen, height 120-240 cm everywhere). The old menu stored whatever was typed as the gender, e.g. the button label "Mies", which the math did not recognise as male: men who signed up through the menu were calculated with the female formula.
* `/start` menu: the quick pick buttons really leave out late-clocked drinks (that was the intent), and one confirmation of "Kumoa" undoes exactly one drink.
* `/annokset` in groups lists one user per line (it printed them comma separated).
* Notifications of new announcements are retried until they were really delivered (in a group the user may never have opened the bot).
* `/juoma` "Oma": the prompt for the percentage removes the keyboard.

## Data from BläkkisVuohi

KakkosVuohi starts with an empty database and has no importer. With a one week retention there would be little to import.
