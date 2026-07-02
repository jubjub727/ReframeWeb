---
name: baml-bridges
description: Calling BAML from the outside world — a host language (Python), the shell, CI, or another process. Load when wiring BAML functions into existing code, choosing between the subprocess bridge / generated SDK / packed binary, writing a generator block, or debugging baml generate / baml_sdk import errors. The subprocess bridge (`baml run`) is the primary pattern; the generated Python SDK is secondary and needs a version-matched baml_core.
---

# Bridges — calling BAML from outside

Three ways to call a BAML function from a host, in order of preference:

| Pattern | When | Cost |
|---|---|---|
| **Subprocess bridge** — `baml run` as a child process | Default. Zero host deps, survives CLI upgrades, great for agents/scripts/CI | recompiles per call (fast, but not for hot loops) |
| **Generated SDK** — `baml generate` → `import baml_sdk` | Hot paths, long-lived processes | needs `baml_core` pinned to the CLI's version |
| **Packed binary** — `baml pack` | Shipping a self-contained executable | build step |

## The subprocess bridge (primary)

Every function gets an auto-CLI derived from its signature. The post-`--` tokens
start with the function name (it's a subcommand), and `--json-args` belongs to the
subcommand — **not** to `baml run` itself:

```bash
baml run --function greet --output-format json -- greet --name ana
baml run --function handle --output-format json -- handle \
  --json-args '{"req": {"method": "GET", "path": "/health", "body": null}}'
baml run -e 'add(2, 3)'                      # quick expression eval
```

- `--json-args <SOURCE>` takes an inline string, `@path/to/file`, or `-` for stdin.
  It is **required** for class/list/map/union parameters; scalar params can use
  per-field flags (`--name ana`) instead.
- Discover a function's exact flags with `baml run -f <fn> -- <fn> --help` —
  it prints the signature and the derived options.
- The top-level output flag is `--output-format <debug|json>` (default `debug`,
  a struct repr like `user.Greeting {name: "ana", ...}`). Pass `json` when a
  program consumes the output.
- Scalar returns print bare values in both formats (`5`); only `json` is
  machine-stable for classes.

> Caveat (verified on 0.11.3-nightly): `--output-format json` fails with
> `failed to serialize output` when the returned class has an **enum or
> literal-union typed field** (`kind "a" | "b"` / `kind MyEnum`) — and the
> process still exits 0, so check stderr. Until fixed, make bridged return
> types use plain `string`/`int`/`float` fields, or stringify inside BAML:
> `baml.json.stringify(value.to_json())` has the same limitation, so prefer
> plain-field classes at the bridge boundary.

A minimal Python caller:

```python
import json, subprocess

def call_baml(fn: str, args: dict):
    out = subprocess.run(
        ["baml", "run", "--function", fn, "--output-format", "json",
         "--", fn, "--json-args", json.dumps(args)],
        capture_output=True, text=True, check=True)
    return json.loads(out.stdout)
```

## Scripts and argv

`baml run <fn> -- a b c` (positional-target form) passes raw args through.
`baml.sys.argv()` layout: index 0 is the baml binary path, index 1 the target
name, **your args start at index 2** — slice, don't hardcode:

```baml
function main() -> null {
  let args = baml.sys.argv().slice(2, baml.sys.argv().length());
  log.info({ "args": args })
  null
}
```

`baml.toml` supports a `[scripts]` table (`dev = "-f main"`) so `baml run` has
a default target. Always create the project with `baml init` — it writes the
required `[package]` table for you:

```toml
[package]
name = "proj"
```

(Hand-written `[project]` is a first-run error: the key is `[package]`.)

## The generated Python SDK (secondary)

A `generator` block lives in a `.baml` file, not TOML. This exact block is
verified against the shipped CLI — `naming_convention` is **required** and only
`"preserve-case"` works for `python/pydantic` (`"language"` panics the codegen):

```baml
generator target {
  output_type "python/pydantic"
  output_dir "."                       // relative to the dir holding baml.toml, NOT baml_src/
  naming_convention "preserve-case"
  default_client_mode "sync"
}
```

`baml generate` emits a `baml_sdk/` package. Functions are exported **at the top
level** (plus `_async` variants) — there is no `sync_client` module and no `b`
client object:

```python
from baml_sdk import greet, classify, classify_async

g = greet("ana")          # returns a pydantic model; BAML snake_case carries over
```

**Version pinning is mandatory**: `baml_sdk` inlines compiled bytecode that the
PyPI `baml_core` must be able to load. A stable `baml_core` (e.g. 0.11.2) cannot
load bytecode from a nightly CLI (`Unexpected variant tag` panic at import). Match
them:

```bash
pip install baml-core           # when the CLI is a stable release
pip install --pre baml-core     # when the CLI is a nightly (gets 0.11.3.devYYYYMMDDNN)
```

Re-run `baml generate` after every schema or function change. If imports panic
right after a CLI upgrade, regenerate and re-pin before debugging anything else.

## Packed binaries

`baml pack <fn>` builds a standalone executable with that function as the sole
entry point; repeatable `-f` flags build a multiplexing binary where each
function is a subcommand. Use it to ship a bridge target with no `baml` on the
host's PATH.

## From inside BAML, reaching out

The reverse bridge is `baml.sys.shell(cmd, null)` → `ShellOutput { stdout,
stderr, exit_code }` + `.ok()`. Keep domain logic in BAML and capability
(DBs, crypto, HTTP serving, concurrency) in a thin host entrypoint speaking JSON over stdin/stdout.
