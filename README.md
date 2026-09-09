# Minify++ XML Conformance

Independent XML conformance evidence for Minify++. The harness pins W3C XML Conformance Test Suite, extracts an explicitly eligible corpus, minifies each case in bounded batches, and applies strict XML parsing and canonical namespace-aware tree comparison. Upstream sources are acquired on demand and are never committed.

```sh
make deps
make smoke test
make sync extract run
make dashboard
```

Use `python3 tools/conformance.py extract --limit 1000` for iteration. Result JSON records the exact upstream revision, extraction exclusions, minifier identity, raw non-pass evidence and timestamped history.

## Contract

The eligible contract deliberately excludes doctypes, entity-dependent inputs and source-rejected negative tests. Minify++ remains a conservative lexical transformer rather than a validating XML implementation. Canonical comparison preserves namespaces, attributes, text and processing instructions. Comments are intentionally treated as removable minification trivia.

Statuses are `pass`, `semantic-difference` or `token-difference`, `parser-rejected`, `source-rejected`, and `minify-error`. Only transformed failures fail the run. Any confirmed product defect must be minimized into Minify++'s permanent suite before a corrected complete result is published.

## Evidence policy

A smoke run proves the harness is wired correctly, not corpus conformance. Public claims require a fresh complete extraction and run at the recorded revision. Eligibility totals and every exclusion category must be published alongside the pass count. The dashboard is generated from a completed immutable result; it is not live during execution.
