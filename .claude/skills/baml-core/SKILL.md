---
name: baml-core
description: Everything for writing BAML (the baml_language rewrite). Load when working in .baml files or answering any BAML question. BAML is a statically-typed, expression-oriented language with first-class LLM functions — basically TypeScript with snake_case methods, `name type` class fields, and a `client:`/`prompt:` DSL that desugars into ordinary functions. This skill explains pretty much every part of the language with compiler-verified examples; for any stdlib name or signature not shown, run `baml describe`.
---

# baml

BAML is a **statically-typed, expression-oriented language with first-class LLM functions**. Think of it as **two halves in one `.baml` file**:

1. **The language** — functions, classes, enums, unions, generics, closures, optional chaining, control flow, a stdlib. Basically TypeScript, with consistent twists: methods/stdlib are `snake_case`, the last expression in a block is its value, and class fields are `name type` (no colon).
2. **The DSL** — a function becomes an LLM call by giving it a `client:` and a `prompt:` instead of a normal body. **It desugars into the language**: the compiler emits a plain function plus companions (`$render_prompt`, `$build_request`, `$parse`, `$stream`). Downstream there's no "LLM function," just functions with metadata.

**If a stdlib name or signature isn't shown below, run `baml describe` instead of guessing** — that's what it's for.

## Install + the agent loop

```bash
brew tap boundaryml/baml && brew install baml   # binary is `baml-cli` (alias to `baml`)

baml init                       # new project here (writes the required baml.toml + baml_src/)
baml run --list                 # compile + list callable functions
baml run main                   # run a function by name (bare `baml run` just prints help
                                #   unless baml.toml has a [scripts] default)
baml run -e 'add(2, 3)'         # quick eval (recompiles the whole project — also a syntax check)
baml describe baml.json         # list helpers under a module  ← use for ANYTHING you're unsure of
baml describe Array             # full method list + docs for a type (Array, Map, String, Int, Float)
baml test --list                # list testsets::cases
baml test -i "suite::case"      # run one case
baml fmt baml_src/main.baml     # formatter — run before finishing
baml generate                   # regenerate the host-language (Python) client
```

## Project layout & namespaces

No `import` statements — the CLI walks the project root and loads every `.baml` file (skipping dotfiles, `node_modules`, `target`). Files conventionally live in `baml_src/`.

**Namespaces are opt-in via `ns_<name>/` directory names** — only those contribute to the namespace path; regular folders are pure organization. A file in `ns_game/ns_ai/` is in namespace `game.ai`. Reference a symbol by its short last component **or** its full path — both resolve: `baml.env.get_or_panic("K")` ≡ `env.get_or_panic("K")`, and your own `game.Board.new()` works from anywhere. The literal prefix `root.` is reserved for stdlib internals — not available in user code.

---

# The language

## Types & literals

```baml
type UserId = string;                  // top-level type aliases END WITH ;
type Metadata = map<string, json>;
type Tree = json | Tree[];             // recursive aliases are allowed (through a container)

// literals: 1  -42  3.14  true  false  null  "text"  #"raw multiline"#  [1,2,3]  {"a":1}
let x = 1;                             // inferred int (fresh literal widens)
let one: 1 = 1;                        // annotation preserves the literal type
```

Primitives: `int`, `float`, `bool`, `string`, `null`, `unknown`. Media: `image`, `audio`, `uint8array`. Composite: `T[]`, `map<K, V>`, `T?` (optional/nullable), unions `A | B | null`, function types `(x: int) -> int`, literal types `"open" | "closed"` / `1 | 2 | 3`.

`json` is a structural alias for `null | bool | int | float | string | json[] | map<string, json>`. No implicit coercion: `int + float -> float` is the only widening; `"n=" + 5` does **not** compile — use `baml.unstable.string(5)`. `null` is the unit value.

## Variables, blocks & expressions

```baml
function block_demo(flag: bool) -> int {
  let x = 10;
  x = x + 1;                           // reassignment; compound ops: += -= *= /= %=
  let from_block = { let a = 1; let b = 2; a + b };   // a BLOCK is an expression — last line is its value
  let from_if    = if (flag) { 1 } else { 2 };        // IF is an expression (needs `else` to be a value)
  x + from_block + from_if
}
```

Operators: arithmetic `+ - * / %`, comparison `== != < <= > >=`, logical `&& || !`, string concat `+`. **No ternary `?:`** — use an `if`/`else` expression. `if`, blocks, and `match` are expressions; `while`/`for` are statements.

## Functions, methods, closures

```baml
function add(a: int, b: int) -> int { a + b }      // trailing expression is the return value

function abs(x: int) -> int {
  if (x < 0) { return -x; };                        // early return needs `return` + a trailing `;`
  x
}

function log_msg(msg: string) -> null {             // returns nothing -> `-> null`, trailing `null`
  log.info({ "msg": msg })
  null
}

function apply(f: (x: int) -> int, x: int) -> int { f(x) }   // higher-order

function scale_all(factor: int, xs: int[]) -> int[] {        // lambda + closure (captures `factor`)
  let scale = (x: int) -> int { x * factor };
  xs.map(scale)
}
```

## Classes, enums, generics

**Class fields are `name type` — no colon, no comma.** Colons appear only in parameters, `let` annotations, map literals, struct construction, and `match` bindings.

```baml
class Point {
  x int                                              // field: `name type`
  y int

  function new(x: int, y: int) -> Point {            // factory: no `self`, called as Point.new(...)
    Point { x: x, y: y }                             // construction literal DOES use `:`
  }
  function translate(self, dx: int, dy: int) -> Point {   // method: explicit `self` first
    Point { x: self.x + dx, y: self.y + dy }
  }
}

let p = Point.new(1, 2).translate(5, 5);             // p.x == 6
p.x = 10;                                            // fields are read/written with `.`

enum Color { Red, Green, Blue }                      // variants; refer to as Color.Red

class Box<T> {                                       // generics
  value T
  function of(v: T) -> Box<T> { Box<T> { value: v } }
}
let b = Box<int>.of(3);                              // b.value == 3
```

> The formatter (`baml fmt`) currently rewrites fields with a colon (`x: int,`); both forms compile, but write `x int` to match the language and the stdlib source.

## Control flow

```baml
function loops(xs: int[]) -> int {
  let sum = 0;
  for (let x in xs) {                  // for-in REQUIRES `let`; iterates VALUES (TS's for...of)
    if (x < 0) { continue; };          // statement-style `if` ends with `;`
    if (x > 100) { break; };
    sum += x;
  }                                    // a `for` block has NO trailing `;`
  for (let i = 0; i < 3; i += 1) { sum += i; }   // C-style for — also requires `let`
  let n = 0;
  while (n < 3) { n += 1; }
  sum + n
}

function classify_num(x: int) -> string {
  match (x) {                          // parens around the scrutinee; `match` is an expression
    0          => "zero",
    1 | 2 | 3  => "small",
    _          => "other",             // `_` wildcard
  }
}

function describe_json(v: json) -> string {
  match (v) {
    null                     => "null",
    let s: string            => "str:" + s,                     // `let x: T =>` BINDS the narrowed value
    let xs: json[]           => "arr:" + baml.unstable.string(xs.length()),
    let o: map<string, json> => "obj",
    _                        => "other",
  }
}
```

## Optional chaining & null-coalescing

```baml
function opt(u: User?, items: int[]?, cb: ((x: int) -> int)?) -> string {
  let name = u?.name;                  // short-circuits to null if u is null
  let head = items?.[0];               // optional index
  let r    = cb?.(42);                 // optional call
  u?.name ?? "Anonymous"               // ?? null-coalescing
}
```

## Collections & strings

Instance methods are `snake_case` (verify the full set with `baml describe Array` / `Map` / `String`):

```baml
function collections(xs: int[], m: map<string, int>) -> int {
  // Array: map filter(.collect()) find reduce some every flat_map slice concat
  //        reverse join sort sort_by includes index_of push pop shift unshift at length splice
  let doubled = xs.map((x: int) -> int { x * 2 });
  let big     = xs.filter((x: int) -> bool { x > 2 }).collect();   // filter returns an Iterator -> .collect()
  let total   = xs.reduce((acc: int, x: int) -> int { acc + x }, 0);
  let first   = xs.at(0) ?? 0;          // .at / .get return T? — prefer over xs[0]/m[k], which PANIC out of bounds

  // Map: get set has keys values delete get_or_insert clear length
  //      KEYS MUST BE string — map<int, V> compiles but PANICS at runtime
  m.set("seen", (m.get("seen") ?? 0) + 1);
  total + first + (m.get("seen") ?? 0)
}

function strings(s: string) -> string {
  // String: trim to_lower_case to_upper_case replace replace_all split lines
  //         includes starts_with ends_with index_of char_at substring matches (regex)
  //         length / char_count (both CODEPOINTS) — byte length is .to_utf8().length()
  //         repeat to_utf8 / string.from_utf8
  s.trim().to_lower_case().replace_all("  ", " ")
}
```

Gaps a TS dev will hit: `.filter` returns an **Iterator** — chain `.collect()` for a `T[]`; no `.remove_at` (use `.splice`). Pitfalls: `char_at(i)` silently returns `""` out of bounds (it never throws or returns null); `"ab".split("")` pads with leading/trailing empties (`["","a","b",""]`). Empty literals infer their element type on first mutation (`let xs = []; xs.push(1)` makes `xs: int[]`).

## Numbers

`int` and `float` carry real math (`baml describe Int` / `Float` for the full set, including trig):

```baml
function numbers(x: int, y: float) -> float {
  let a = (-7).abs().max(3).clamp(0, 100).pow(2);   // Int: abs min max clamp pow isqrt ilog ...
  let b = y.sqrt().round().max(float.pi());          // Float: sqrt pow log floor ceil round + trig
  let n = int.parse("42");                           // statics: int.parse float.parse int.random ...
  b + a.max(n) + x                                    // int + float -> float
}
```

## JSON

```baml
class Email { id string  from string  subject string  body string }

function load(raw: string) -> Email[]   { baml.json.from_string<Email[]>(raw) }            // string -> T
function dump(emails: Email[]) -> string { baml.json.stringify_pretty(emails.to_json()) }  // value -> json -> string
```

`baml.json` (run `baml describe baml.json`): `from_string<T>`, `from_json<T>`, `parse` (`string -> json`), `stringify`, `stringify_pretty`, `to_json`, `to_string`. On a concretely-typed value call `value.to_json()`; for an abstract `T` use `baml.json.to_json<T>(v)`. Keep wire data as `json` at the boundary, then narrow with `from_json` before domain logic.

## Errors — `throw` / `catch` / `catch_all`

```baml
class BadInput { message string }

function require_non_empty(v: string) -> string throws BadInput {   // `throws T` is part of the SIGNATURE
  if (v.trim().length() == 0) { throw BadInput { message: "empty" }; };
  v.trim()
}

function safe(v: string) -> string {
  require_non_empty(v) catch (e) { BadInput => "untitled" }   // arms are TYPE-ONLY: `T =>`, or `_ =>` wildcard
}
```

- `throw` any value (a class gives callers a typed shape to match). `catch` is an **expression** attached to a call; each arm yields a value compatible with the success path.
- **`catch` is non-exhaustive** — types you don't match propagate to the caller as if the catch weren't there. Re-throw inside an arm with `throw e;`.
- **`catch_all`** requires every inferred throw type be covered (use `_ =>` to cover all at once) — for when you want the compiler to enforce exhaustiveness.
- Arms match the thrown *type* only — `catch (e) { T => v }`, **not** `_: T =>`, no `instanceof`, no destructuring.
- Runtime **panics** (divide-by-zero, index out of bounds, missing map key, failed `assert`, `baml.sys.panic(...)`) are not in the inferred throw set and are not caught by ordinary `catch`/`catch_all`.

## Other stdlib — files, HTTP, system, env, input, logging, asserts

```baml
function fetch_json(url: string) -> json {
  let res = baml.http.fetch(url);                    // Response: .ok() .status_code .text() .bytes()
  if (!res.ok()) { throw "HTTP " + baml.unstable.string(res.status_code); };
  baml.json.parse(res.text())
}

function read_or_default(path: string) -> string {
  if (baml.fs.exists(path)) { baml.fs.read(path) } else { "" }   // also baml.fs.write(path, text)
}
```

- `baml.sys.argv()` (CLI args), `baml.sys.shell(cmd, null)` → `ShellOutput { stdout/stderr: uint8array, exit_code }` + `.ok()`; also `baml.sys.sleep(ms)`, `baml.sys.now_ms()`, `baml.sys.panic(msg)`.
- `baml.env.get(name) -> string?` / `baml.env.get_or_panic(name) -> string`. Env is under `baml.env`.
- `baml.io.println(text)` prints plain text; `baml.io.input(prompt) -> string` reads a line (use the full `baml.io.` path).
- `log.info/debug/warn/error(data)` for structured logging (arg is a map).
- Stdlib throws typed errors from `baml.errors.*` (`InvalidArgument`, `ParseError`, `Io`, `Timeout`, …) — match them in `catch` arms; `baml describe baml.errors` lists them all.
- Asserts (function calls, no `assert` keyword): `assert.equal(actual, expected)`, `assert.is_true(cond)`, `assert.not_null(v)`, `assert.contains(haystack, needle)`. That's the whole set.

---

# The DSL — the LLM layer

A function with a `client:` and a `prompt:` is an LLM call. Everything above still applies; this is declarative sugar on top.

## Clients

```baml
client<llm> Fast {                     // client names are UpperCamelCase
  provider openai
  options {                            // inside options: NO colons, NO commas — whitespace-separated
    model "gpt-4o-mini"
    api_key env.OPENAI_API_KEY
    temperature 0.2
  }
}

client<llm> Sonnet {
  provider anthropic
  options { model "claude-sonnet-4-6"  api_key env.ANTHROPIC_API_KEY  max_tokens 4096 }   // Anthropic needs max_tokens
}
```

Use `env.VAR` for keys, never hardcode. Providers include `openai`, `anthropic`, `google-ai-gemini`, `vertex`, `bedrock`, `azure-openai`, `ollama`.

## LLM functions — the return type drives parsing

```baml
class Intent {
  kind "billing" | "support" | "sales" | "spam" | "other"
  confidence float
  rationale string
}

function classify(email: Email) -> Intent {
  client: Fast                         // `client:` and `prompt:` both take a colon, each on its own line
  prompt: #"
    Classify the user's email.
    From: {{ email.from }}
    Subject: {{ email.subject }}
    Body: {{ email.body }}

    {{ ctx.output_format }}            {# ALWAYS include for structured output — injects the schema #}
  "#
}

// Shorthand client for demos/tests — `provider/model` string + env auth:
function classify_quick(text: string) -> Intent {
  client: "openai/gpt-4o-mini"
  prompt: #"Classify: {{ text }}  {{ ctx.output_format }}"#
}
```

- The return type (class / enum / literal union) is the schema. Declare it and let BAML validate + retry on malformed JSON. Prefer typed shapes over free-form `json`; make a field `T?` only when the model may legitimately omit it.
- Prompts are block strings `#"..."#` (no escape processing) with Jinja — inside `{{ }}`/`{% %}` it is Jinja syntax, not BAML: `{{ value }}`, `{{ method(x) }}`, `{% for x in xs %}…{% endfor %}`, `{% if c %}…{% endif %}`, `{# comment #}`, plus `{{ ctx.output_format }}` and `_.role(...)` / `_.media(...)` helpers.
- Compiles to a plain `classify(email) -> Intent` **plus** companions: `classify$render_prompt`, `classify$build_request`, `classify$parse`, `classify$stream` (callable everywhere, though `baml run --list` shows only `classify(...) -> Intent  [llm]`). **`classify$parse(raw: string) -> Intent`** runs just the parser on an already-captured reply.

## Pipelines — compose typed functions

```baml
class Result { intent Intent  reply string }

function triage(email: Email) -> Result {            // NO client: — plain orchestration
  let intent = classify(email);                      // typed values flow stage-to-stage, compiler-checked
  let reply  = draft(email, intent);
  Result { intent: intent, reply: reply }
}

function route(text: string) -> string {             // cheap classifier -> expensive handler
  match (classify_intent(text).kind) {
    "spam" => "ignored",
    _      => handle(text),
  }
}
```

Pass typed values between stages, not JSON strings. `for/in` is sequential — for real concurrency, fan out in the host (`asyncio.gather`).

## Host code — Python via `baml generate`

A `generator` block (in a `.baml` file, **not** TOML) emits the **`baml_sdk`** package:

```baml
generator target {
  output_type "python/pydantic"
  output_dir "."                       // relative to the dir holding baml.toml, NOT baml_src/
  naming_convention "preserve-case"    // REQUIRED; "language" is not supported for python/pydantic
  default_client_mode "sync"
}
```
```python
from baml_sdk import classify          # top-level exports (+ classify_async); no client object
intent = classify(email)               # BAML name -> same snake_case in Python
```

Run `baml generate` after any schema/function change, and pin `baml_core` to the CLI's version (`pip install --pre baml-core` when the CLI is a nightly — a stable baml_core cannot load nightly bytecode). For capabilities BAML lacks (DBs, crypto, HTTP serving, concurrency — raw TCP/UDP does exist at `baml.net`), use a thin **shell bridge**: `baml.sys.shell` to a host entrypoint with a JSON `op`/`payload` protocol — keep domain logic in BAML, capability in the bridge.

## Testing — `testset` / `test`, decode cached JSON

```baml
testset "intent" {
  test "parses a captured reply" {
    let raw = #"{ "kind": "support", "confidence": 0.94, "rationale": "asks to cancel" }"#;
    let r = baml.json.from_string<Intent>(raw);      // same parsing the runtime applies to a live reply
    assert.equal(r.kind, "support");
  }
}

testset "by_n" {                                     // testsets nest and can be generated in a loop
  for (let n in [1, 2, 3]) {
    test ("generated " + baml.unstable.string(n)) {
      assert.is_true(n > 0);
    }
  }
}
```

Run `baml test -i "intent::*"`. Feed each pipeline stage cached JSON via `baml.json.from_string<StageType>(...)` (or `Fn$parse(raw)`) to exercise parsing/orchestration deterministically — no tokens, no flakiness.

---

# How BAML differs from TypeScript

The muscle memory carries over; these are the traps.

**Semantics:**
- **`for (let x in xs)` iterates VALUES, not keys** (TS's `for...of`); `for` always requires `let` (also the C-style `for (let i = 0; …; …)`). Bare `for (x in xs)` is a syntax error.
- **Last expression is the return value** (Rust-style). `return x;` is early-exit only; a trailing `;` discards a value.
- **`null` is the unit value** — functions returning nothing declare `-> null` with a trailing `null` (or `return null;`).
- **`match`/`catch`/`if`/blocks are expressions**, not statements — every arm yields a value. `catch` is non-exhaustive (unmatched types rethrow); `catch_all` is exhaustive. Arms are **type-only** (`T =>` / `_ =>`, not `_: T =>`, no `instanceof`).
- **No implicit string coercion** — `"n=" + 5` won't compile; use `baml.unstable.string(5)`. Only numeric widening is `int + float -> float`.
- **Indexing panics on miss** — `a[0]` / `m[k]` crash out of bounds; use `.at(i)` / `.get(k)`, which return `T?`. Panics aren't caught by `catch`.

**Syntax:**
- **Class fields are `name type`** — no colon, no comma. Colons are for parameters, `let`, map literals, struct construction, and `match` bindings.
- Methods and your own functions are **`snake_case`**; classes, enums, and `client<llm>` names are **`UpperCamelCase`**.
- Top-level `type` aliases end with **`;`**. A statement-style `if` ends with `;`, but a `for`/`while` block does not.
- Multiline strings are **block strings `#"..."#`** (no escapes) — a normal `"..."` breaks prompts.
- `client<llm>` `options { ... }` are **whitespace-separated, no colons or commas** — unlike everything else.

**Stdlib:**
- `.length()` on a string counts **codepoints** (same as `.char_count()`); byte length is `.to_utf8().length()`.
- `.filter` yields an Iterator — finish with `.collect()`. There IS `.sort()`/`.sort_by()`, `String.repeat`, rich number math, `int.parse`/`float.parse`, `to_utf8`/`from_utf8`, and `s.matches(pattern)` for regex.
- Stdlib symbols resolve by short name (`assert.equal`, `log.info`) or full path (`baml.fs.read`, `baml.io.input`); when in doubt use the full `baml.*` path.
- The LLM `function` (`client:` + `prompt:` + `{{ ctx.output_format }}`) has no TS analog — it desugars into a normal function plus parse/stream companions.

**Anything not shown here: `baml describe <name>` — don't invent stdlib names.**
