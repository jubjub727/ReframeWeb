---
name: baml-testing
description: Testing BAML projects — testset/test blocks, the assert.* set, running and filtering with baml test, and the token-free pattern for LLM functions (feed captured JSON through Fn$parse or baml.json.from_string<T> so parsing and orchestration run deterministically with no API key). Load when writing or debugging BAML tests, or when asked how to test an LLM function without spending tokens.
---

# Testing BAML

## testset / test

```baml
testset "greeting" {
  test "greets by name" {
    let g = greet("ana");
    assert.equal(g.message, "hi ana");
  }
  test "decodes a captured reply" {
    let g = baml.json.from_string<Greeting>(#"{ "name": "bo", "message": "hi bo" }"#);
    assert.equal(g.name, "bo");
  }
}

testset "by_n" {                          // testsets nest; tests can be generated in a loop
  for (let n in [1, 2, 3]) {
    test ("generated " + baml.unstable.string(n)) {
      assert.is_true(n > 0);
    }
  }
}
```

```bash
baml test --list                # prints  greeting::greets by name  (<testset>)
baml test -i "greeting::*"      # run one suite; -i "suite::case" for one case
```

Asserts are function calls (no `assert` keyword), and this is the whole set:
`assert.equal(actual, expected)`, `assert.is_true(cond)`, `assert.not_null(v)`,
`assert.contains(haystack, needle)`. A failed assert is a **panic** — it is not
catchable with `catch`; that's what makes it a test failure.

## LLM functions without tokens

An LLM function compiles into a plain function **plus companions** —
`classify$parse`, `classify$render_prompt`, `classify$build_request`,
`classify$stream`. (They no longer appear in `baml run --list`, which shows just
`classify(...) -> Intent [llm]`, but they are all callable.) The two that matter
for tests:

**`Fn$parse(raw: string) -> T`** runs the real output parser on a captured
reply — same coercion/validation a live call applies, no API key needed:

```baml
testset "intent_parsing" {
  test "parses a captured model reply" {
    let r = classify$parse(#"{ "kind": "support", "confidence": 0.94 }"#);
    assert.equal(r.confidence, 0.94);
  }
}
```

**`Fn$render_prompt(args...)`** returns the exact prompt (with
`{{ ctx.output_format }}` expanded into the schema text) — assert on it to
pin prompt wording without calling a model:

```bash
baml run -e 'classify$render_prompt("hi")'    # inspect interactively
```

For multi-stage pipelines, feed each stage cached JSON via
`baml.json.from_string<StageType>(...)` so orchestration logic runs
deterministically end-to-end. Keep one tiny live smoke test (a real `classify`
call) out of the default suite and run it explicitly when keys are available.

## What to test where

| Layer | How |
|---|---|
| Pure functions / classes | direct calls + `assert.*` in a `testset` |
| LLM output parsing | `Fn$parse(captured_reply)` |
| Prompt wording / schema | `Fn$render_prompt(...)` |
| Pipeline orchestration | stage inputs from `baml.json.from_string<T>` |
| The bridge surface | `baml run --function fn --output-format json -- fn --json-args '...'` from the host's test suite |

Run `baml fmt` before finishing; remember `assert.equal` panics on the first
mismatch, so put independent checks in separate `test` blocks to see all
failures in one run.
