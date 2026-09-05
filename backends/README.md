# Local Backtrader and LEAN integration

Both adapters execute the actual engines through the same synthetic request and
normalized order/fill/accounting result. This protects backend selection from
being based on library reputation, incompatible defaults, or a higher simulated
profit. The independent expected result is fixed before running either engine.

## Supported boundary

The current integration is an engineering harness, not an empirical research
entry point. The command accepts only the bundled synthetic fixture. It exposes
no market-data path, arbitrary algorithm, optimizer, broker connection, cloud
upload, credential, or live mode. The test module also constructs explicit
synthetic variants. A source-specific strategy and real-data adapter, their
research-stage admission checks, and instrument-specific acceptance tests remain
future work under roadmap priority 2. No market-data fitness or executable edge
has been established by these runs.

The shared contract is checked by `validate_request` in
`scripts/run_backend_fixture.py`. Unsupported fields and conventions fail.

| Convention | Explicit initial implementation |
|---|---|
| Instrument | One synthetic cash asset, USD, multiplier 1, whole units, leverage 1 |
| Data | Seven locally constructed one-minute OHLCV bars, 2026-01-05, UTC, synthetic always-open session |
| Signal | One long entry on the first completed close at/above the entry threshold; one exit on a subsequent completed close at/below the exit threshold while invested |
| Execution | Full market-order fill at the following bar's open; no fill without a following bar |
| Costs | Absolute adverse price slippage per unit; fixed fee per filled unit on each side |
| Timestamps | `bar_end` is the end of the bar delivering the event, not an assertion of exchange execution latency; fills use that bar's open |
| Accounting | Cash, marked equity, position, and open orders (including submitted orders awaiting acceptance) |
| Reproducibility | Fixed package locks, compiled-source/build receipt, runtime and dependency hashes, immutable run directory, full before/after synthetic fingerprint |

Backtrader has preloading, vectorized execution, and cheat timing disabled.
Its slippage is explicitly allowed outside the OHLC range; this is a stipulated
synthetic model, not a liquidity estimate. LEAN uses its real algorithm manager,
data feed, transaction handler and backtesting brokerage. Its explicit
`NextBarOpenFill` model implements the same convention instead of assuming the
default market-order semantics agree. `AbsoluteSlippage` returns a price amount;
LEAN's `ConstantSlippageModel` takes a fraction of price and is not equivalent.
This initial comparison verifies the adapters and the selected model together,
not every native fill model supplied by either engine.

Unsupported: stop/limit/bracket orders, partial fills, order-book queues, futures
contract mapping and rolls, exchange calendars, corporate actions, short borrow,
FX conversion, capacity, and portfolio/risk sizing. These need the later
strategy's requirements and evidence. Synthetic volume does not constrain fills.

## Reproducible local setup

Requirements: Python 3.12 or later and the .NET 10 SDK for LEAN's build. Once
built, LEAN needs the .NET 10 runtime. No Docker, LEAN CLI, QuantConnect account,
paid service, or market-data subscription is used by this integration.

Install the existing framework requirements in the framework Python environment.
Prefer a dedicated virtual environment for Backtrader:

```powershell
python -m venv .venv-backends
python scripts/prepare_backends.py --backend both --python .venv-backends/Scripts/python.exe
```

On Linux/macOS use `.venv-backends/bin/python`. If `dotnet` is not on PATH, pass
`--dotnet /absolute/path/to/dotnet` (or the Windows executable path). The setup
command installs only the pinned Backtrader wheel, restores LEAN with
`--locked-mode`, builds the local harness, and records the exact source and
output hashes. Restore/build can access package repositories; fixture execution
uses local inputs. No SDK installer is run by the repository script.

```powershell
python scripts/run_backend_fixture.py --backend backtrader --python .venv-backends/Scripts/python.exe --output artifacts/backend-runs/backtrader-001
python scripts/run_backend_fixture.py --backend lean --output artifacts/backend-runs/lean-001
python scripts/test_backends.py --engines --python .venv-backends/Scripts/python.exe --output artifacts/backend-runs/comparison-001
```

Use a new output directory for every run. A missing dependency, stale or changed
LEAN build, process failure, changed fingerprint, or incorrect result cannot
yield `PASS`. Default framework checks run the dependency-free contract tests;
the backend CI job separately installs and executes both engines on Linux and
Windows. A skipped engine run must not be described as conformance evidence.

## Expected result and evidence

For `next_open.json`, the entry decision occurs at 09:02 and buys two units at
the next bar's open of 110 plus 0.5 slippage. The exit decision occurs at 09:05
and sells at the next open of 98 minus 0.5. Each fill costs 2 in fees. Thus
`10000 + 2 * (97.5 - 110.5) - 2 - 2 = 9970`; final position and open orders are
zero. The jumps distinguish next-open execution from filling on the signal's
close. This arithmetic is written in `next_open.expected.json`, not calculated
from either engine's result.

The engine suite also tests a second identical run, zero costs, absent signals,
a final-bar signal that must remain unfilled, and a later-price change that must
leave earlier completed trades unchanged. A deliberately wrong expected result
must fail for each engine even though its process succeeds.

Each run retains the request, expected output, source/dependency manifest,
runtime identity, stdout/stderr, raw engine output, complete synthetic
fingerprints and the existing fingerprint comparator's report. The receipt
binds these artifacts and permits only `SYNTHETIC_BACKEND_CONFORMANCE_ONLY`.
This is engineering evidence; it is not an outcome-evidence contract, a passed
market pipeline-integrity assessment, a routed Research Case, or capital
authorization. A later real case must retain its own complete fingerprint,
data-fitness assessment and all normal research gates.

Receipts are local provenance, not authenticated attestations against a hostile
producer, modified runtime or undisclosed external state. Review the dependency
locks and effective runtime on changes. Preparation and engine calls are
separate so fixture runs do not silently install or update software.

## Dependency record and remaining boundary

- Backtrader `1.9.78.123`, wheel SHA-256 recorded in
  `requirements-backtrader.txt`, GPL-3.0-or-later. It is installed separately and
  executed as a subprocess; no third-party source or wheel is vendored here.
- LEAN NuGet packages `2.5.18042`, package source commit
  `abeb0a0627ec484b92291c45c3f2553726c26199`, Apache-2.0. The full transitive graph
  and package integrity hashes are in `lean/packages.lock.json`. Explicit patched
  .NET dependencies replace legacy vulnerable transitive versions.
- The upstream graph still includes DotNetZip `1.16.0`, reported by NuGet as
  affected by [GHSA-xhg6-9j5j-w4vf](https://github.com/advisories/GHSA-xhg6-9j5j-w4vf).
  The warning remains visible. This adapter uses generated plain CSV, not
  externally supplied ZIP files; arbitrary archive ingestion is outside its
  supported boundary. Reassess this dependency before enabling external data
  or archive input. This limitation is not a claim that the whole dependency
  graph is security-audited.

Primary implementation references:
[Backtrader broker configuration](https://www.backtrader.com/docu/broker/),
[LEAN engine source at the package revision](https://github.com/QuantConnect/Lean/tree/abeb0a0627ec484b92291c45c3f2553726c26199),
[LEAN engine package](https://www.nuget.org/packages/QuantConnect.Lean.Engine/2.5.18042).
