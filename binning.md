#!/usr/bin/env bash
set -euo pipefail

# ---- resolve repo root (one level above bin/) ----
ROOT="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"

# ---- make code discoverable ----
export PYTHONPATH="$ROOT/src/main/python${PYTHONPATH:+:$PYTHONPATH}"

# optional venv activation
[[ -f "$ROOT/.venv/bin/activate" ]] && source "$ROOT/.venv/bin/activate"

# ---- run the Typer CLI ----
exec python -m psdata.lifecycle_retention.clean_fy "$@"

\### “Set up a `bin` at the top level” ― what that means and how to do it

In CitSource projects “**bin directory**” usually means *one or more tiny
shell scripts* checked into `bin/` at the repo root.
They exist so that **everywhere** you run—your laptop, a Batch job, a Docker
container—invokes the script **the same way** and automatically picks up the
right virtual-env, Gradle class-path, or other env vars.

Below is the minimal recipe to create a `bin/clean_fy` launcher for your
PeopleSoft-archive cleaner.

---

## 1 Create the directory and script

```bash
# from repo root (…/external-services/acctgateway/data-mesh/psdata/peoplesoft_data_archive_partitions)
mkdir -p bin
touch bin/clean_fy
chmod +x bin/clean_fy
```

### `bin/clean_fy`  (copy-paste)

```bash
#!/usr/bin/env bash
#
# Wrapper to run the clean-fy Python script consistently
# Picks up Citsource virtual-env if one is present.

set -euo pipefail

# If a virtual-env exists under .venv/ activate it
if [[ -f ".venv/bin/activate" ]]; then
  source ".venv/bin/activate"
fi

# Default path to the module
MODULE="psdata.lifecycle_retention.clean_fy"

# Propagate any flags the user passes
python -m "$MODULE" "$@"
```

---

## 2 (Option) Have Gradle build the venv when you run tests

Add to `build.gradle` (only once):

```groovy
tasks.register('createVenv') {
    doLast {
        exec {
            commandLine 'python', '-m', 'venv', '.venv'
        }
        exec {
            commandLine '.venv/bin/pip', 'install', '--upgrade', 'pip', '-r', 'requirements.txt'
        }
    }
}
tasks.named('test').configure { dependsOn 'createVenv' }
```

Now `./gradlew test` will build the venv, and your `bin/clean_fy` script
activates it automatically.

---

## 3 Use it locally

```bash
# from repo root
./bin/clean_fy --project cig-accounting-dev-1 --year 2015 --dry-run
```

No need to remember long `python -m psdata…` invocations.

---

## 4 Make Docker pick it up

Update your `Dockerfile` (or `Dockerfile.pre`):

```dockerfile
COPY bin/clean_fy /usr/local/bin/clean_fy
RUN chmod +x /usr/local/bin/clean_fy
ENTRYPOINT ["clean_fy"]
```

Now **inside the container** the same command works:

```bash
docker run --rm psdata/lifecycle-retention:soft \
           --project cig-accounting-dev-1 --year 2015 --dry-run
```

---

## 5 Commit

```
git add bin/clean_fy
git commit -m "Add top-level bin/clean_fy wrapper"
git push
```

CI will rebuild the Docker image; Batch jobs can call `clean_fy` directly.

---

### Why this matters

* **Single entry-point**: humans, Batch, GitHub-Actions, and Docker all use
  `clean_fy` instead of duplicating long module paths.
* **Environment ready**: if a virtual-env, proxy export, or other setup is
  required, the wrapper does it; nobody else has to remember.
* **Easily extended**: need `bin/clean_fy_hard`?—just add another tiny shell
  that sets `--mode hard`.

That satisfies the suggestion “set up a bin at the top level” from the call
transcript.
