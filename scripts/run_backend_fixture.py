"""Run either genuine backend on a built-in synthetic fixture, retaining evidence.

No empirical-data argument or arbitrary algorithm/configuration is exposed.
This engineering check grants no research-stage or capital status.
"""
from __future__ import annotations

import argparse
import copy
import hashlib
import json
import math
import platform
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from check_research_fingerprint import calculate_fingerprint_sha256, build_fingerprint_check
from prepare_backends import resolve_executable, sources, binaries, file_hashes, BINARY_DIR

ROOT = Path(__file__).resolve().parents[1]
FIXTURE = ROOT / 'backends/fixtures/next_open.json'
CONVENTIONS = {
    'schema_version': '1.0.0', 'data_role': 'SYNTHETIC_BACKEND_FIXTURE',
    'instrument': 'SYNTH', 'currency': 'USD', 'timezone': 'UTC',
    'session': 'SYNTHETIC_ALWAYS_OPEN', 'instrument_model': 'CASH_UNIT_MULTIPLIER_ONE',
    'bar_seconds': 60, 'fill_model': 'NEXT_BAR_OPEN_FULL_FILL'
}
NUMERIC_FIELDS = ('initial_cash', 'quantity', 'entry_close_at_least', 'exit_close_at_most',
                  'fee_per_unit', 'slippage_absolute')


def read(path):
    return json.loads(path.read_text(encoding='utf-8-sig'))


def write(path, value):
    with path.open('x', encoding='utf-8', newline='\n') as stream:
        json.dump(value, stream, indent=2, allow_nan=False)
        stream.write('\n')


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_request(request):
    if not isinstance(request, dict) or set(request) != set(CONVENTIONS) | set(NUMERIC_FIELDS) | {'bars'}:
        raise ValueError('Missing or unsupported backend-contract fields.')
    for key, expected in CONVENTIONS.items():
        if type(request[key]) is not type(expected) or request[key] != expected:
            raise ValueError('Unsupported backend convention: ' + key)
    for key in NUMERIC_FIELDS:
        value = request[key]
        if type(value) not in (int, float) or not math.isfinite(value) or value < 0:
            raise ValueError('Invalid numeric field: ' + key)
    if request['initial_cash'] <= 0 or request['quantity'] <= 0 or int(request['quantity']) != request['quantity']:
        raise ValueError('Positive cash and whole-unit quantity required.')
    previous = None
    if not isinstance(request['bars'], list) or not 2 <= len(request['bars']) <= 1000:
        raise ValueError('Invalid fixture length.')
    for bar in request['bars']:
        if not isinstance(bar, dict) or set(bar) != {'end', 'open', 'high', 'low', 'close', 'volume'}:
            raise ValueError('Invalid bar fields.')
        if not isinstance(bar['end'], str):
            raise ValueError('Bar timestamp must be text.')
        end = datetime.fromisoformat(bar['end'].replace('Z', '+00:00'))
        if end.tzinfo != timezone.utc or end.date().isoformat() != '2026-01-05':
            raise ValueError('Only the synthetic UTC session is supported.')
        if end.second or end.microsecond or end.hour == 0 and end.minute == 0:
            raise ValueError('Bar timestamps must be full minutes after session start.')
        if previous and end - previous != timedelta(minutes=1):
            raise ValueError('Duplicate, missing or unordered minute bars.')
        previous = end
        for key in ('open', 'high', 'low', 'close', 'volume'):
            if type(bar[key]) not in (int, float) or not math.isfinite(bar[key]) or bar[key] <= 0:
                raise ValueError('Invalid bar number.')
        if not bar['low'] <= min(bar['open'], bar['close']) <= max(bar['open'], bar['close']) <= bar['high']:
            raise ValueError('Inconsistent OHLC values.')
        if request['slippage_absolute'] >= bar['open']:
            raise ValueError('Slippage would permit a non-positive execution price.')


def prepare_lean(output, request):
    data = output / 'data'
    (data / 'market-hours').mkdir(parents=True)
    (data / 'symbol-properties').mkdir()
    (data / 'equity/usa/map_files').mkdir(parents=True)
    write(data / 'market-hours/market-hours-database.json', {'entries': {}})
    (data / 'symbol-properties/symbol-properties-database.csv').write_text(
        '# synthetic custom-data defaults only\n', encoding='utf-8')
    with (output / 'bars.csv').open('x', encoding='utf-8') as stream:
        for bar in request['bars']:
            start = datetime.fromisoformat(bar['end'].replace('Z', '+00:00')) - timedelta(minutes=1)
            stream.write(','.join([start.strftime('%Y-%m-%dT%H:%M:%S')] +
                                 [str(bar[k]) for k in ('open', 'high', 'low', 'close', 'volume')]) + '\n')
    config = {'data-folder': str(data), 'results-destination-folder': str(output / 'lean-results'),
              'object-store-root': str(output / 'storage'), 'live-mode': False,
              'close-automatically': True, 'job-user-id': '0', 'api-access-token': '',
              'job-organization-id': '', 'force-exchange-always-open': True}
    write(output / 'config.json', config)
    return config


def fingerprint(manifest, request, expected):
    """Complete synthetic engineering state, never an empirical Research Case."""
    contents = {
        'research_question': 'Does the engine obey the specified synthetic order/accounting contract?',
        'source_strategy': 'Fixed one-entry/one-exit threshold harness; no proprietary or market strategy.',
        'market_and_instruments': {k: request[k] for k in ('instrument', 'currency', 'instrument_model')},
        'time_scope': {k: request[k] for k in ('timezone', 'session', 'bar_seconds')},
        'constructs_and_operationalizations': 'Completed-bar close thresholds; next bar open full fills.',
        'trigger_entry_and_position': {k: request[k] for k in ('entry_close_at_least', 'quantity')},
        'outcomes_targets_and_exits': {'exit_close_at_most': request['exit_close_at_most'], 'expected': expected},
        'conditions_filters_and_exclusions': 'One long round trip, no history, universe search, filters or optimization.',
        'data_sampling_and_observability': {'role': request['data_role'], 'bars': request['bars']},
        'analysis_and_inference': 'Exact comparison with prewritten arithmetic; no market inference.',
        'costs_execution_and_risk': {k: request[k] for k in ('initial_cash', 'fee_per_unit', 'slippage_absolute', 'fill_model')},
        'results_and_continuation': 'Synthetic conformance only. Empirical admission is not implemented here.'
    }
    digest = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    result = {'schema_version': '1.0.0', 'fingerprint_id': 'backend-fixture-fingerprint',
              'created_at': datetime.now(timezone.utc).isoformat(), 'research_id': 'synthetic-backend-fixture',
              'research_version': 1, 'material_specification': {
                  k: {'status': 'DEFINED', 'content': v, 'source_refs': ['backend-fixture-manifest']}
                  for k, v in contents.items()},
              'additional_material_commitments': [], 'protected_artifacts': [
                  {'artifact_ref': 'backend-fixture-manifest', 'role': 'METHOD', 'content_sha256': digest}],
              'completeness': {'all_material_commitments_recorded': True,
                               'all_effective_material_artifacts_protected': True, 'known_gaps': []}}
    result['fingerprint_sha256'] = calculate_fingerprint_sha256(result)
    return result


def run_backend(backend, output, python=None, dotnet=None, request=None, expected=None):
    request = read(FIXTURE) if request is None else request
    expected = read(FIXTURE.with_name('next_open.expected.json')) if expected is None else expected
    validate_request(request)
    output = output.resolve()
    if output.exists():
        raise ValueError('Output directory already exists; retained runs cannot be overwritten.')
    output.mkdir(parents=True)
    write(output / 'request.json', request)
    write(output / 'expected.json', expected)
    files = [Path(__file__), ROOT / 'scripts/prepare_backends.py', ROOT / 'scripts/check_research_fingerprint.py',
             FIXTURE, FIXTURE.with_name('next_open.expected.json'), output / 'request.json', output / 'expected.json']
    if backend == 'backtrader':
        executable = resolve_executable(python or sys.executable)
        entry = ROOT / 'backends/backtrader_adapter.py'
        files += [entry, ROOT / 'backends/requirements-backtrader.txt']
        command = [executable, str(entry)]
        runtime = json.loads(subprocess.check_output(command + ['--describe'], text=True, timeout=30))
        files += [Path(p) for p in runtime['package_files']]
        configuration = {'preload': False, 'runonce': False, 'cheat_on_open': False,
                         'cheat_on_close': False, 'slip_open': True, 'slip_match': True, 'slip_out': True}
    elif backend == 'lean':
        executable = resolve_executable(dotnet or 'dotnet')
        binary = ROOT / 'backends/lean/bin/Release/net10.0/ResearchBackend.dll'
        if not executable or not binary.exists():
            raise ValueError('LEAN runtime/build missing. See backends/README.md.')
        build = read(BINARY_DIR / 'build-receipt.json')
        if build['sources'] != file_hashes(sources()) or build['binaries'] != file_hashes(binaries()):
            raise ValueError('LEAN build is stale or modified. Run prepare_backends.py again.')
        files += binaries() + [BINARY_DIR / 'build-receipt.json']
        files += [ROOT / 'backends/lean/Program.cs', ROOT / 'backends/lean/ResearchBackend.csproj',
                  ROOT / 'backends/lean/packages.lock.json']
        command = [executable, str(binary)]
        runtime = {'dotnet_info': subprocess.check_output([executable, '--info'], text=True),
                   'lean_package': '2.5.18042', 'upstream_commit': 'abeb0a0627ec484b92291c45c3f2553726c26199'}
        configuration = prepare_lean(output, request)
        files += [output / 'config.json', output / 'bars.csv']
        files += [p for p in (output / 'data').rglob('*') if p.is_file()]
    else:
        raise ValueError('Unsupported backend.')
    files += [Path(executable)]
    before = {str(p.resolve()): sha(p) for p in files}
    manifest = {'backend': backend, 'files': before, 'configuration': configuration,
                'request_sha256': sha(output / 'request.json'), 'expected_sha256': sha(output / 'expected.json'),
                'command': command, 'host': platform.platform(), 'python': platform.python_version(), 'runtime': runtime}
    write(output / 'manifest.json', manifest)
    baseline = fingerprint(manifest, request, expected)
    write(output / 'fingerprint.before.json', baseline)
    provenance_hashes = {name: sha(output / name) for name in ('manifest.json', 'fingerprint.before.json')}
    started = datetime.now(timezone.utc).isoformat()
    try:
        completed = subprocess.run(command, cwd=output, text=True, capture_output=True, timeout=120)
        (output / 'stdout.log').write_text(completed.stdout, encoding='utf-8')
        (output / 'stderr.log').write_text(completed.stderr, encoding='utf-8')
        result_path = output / 'engine-output.json'
        actual = read(result_path) if result_path.exists() else None
        after_manifest = copy.deepcopy(manifest)
        after_manifest['files'] = {str(p.resolve()): sha(p) for p in files}
        candidate = fingerprint(after_manifest, read(output / 'request.json'), read(output / 'expected.json'))
        write(output / 'fingerprint.after.json', candidate)
        # Reuse the complete comparator as a function for this engineering harness.
        # This comparison context is not a claim that a research stage was routed.
        comparison = build_fingerprint_check({'decision_id': 'backend-fixture-comparison',
            'fingerprint_guard': {'mode': 'PRESERVE_EFFECTIVE',
                                 'baseline_fingerprint_ref': baseline['fingerprint_id'],
                                 'baseline_fingerprint_sha256': baseline['fingerprint_sha256']}},
            baseline, candidate, checked_at=datetime.now(timezone.utc).isoformat())
        write(output / 'fingerprint-check.json', comparison)
        unchanged = comparison['overall_status'] == 'UNCHANGED'
        runtime_file = output / 'engine-runtime.json'
        runtime_matches = backend != 'backtrader' or (runtime_file.exists() and read(runtime_file) == runtime)
        provenance_unchanged = all(sha(output / name) == digest for name, digest in provenance_hashes.items())
        passed = completed.returncode == 0 and actual == expected and unchanged and runtime_matches and provenance_unchanged
        receipt = {'status': 'PASS' if passed else 'FAIL', 'claim': 'SYNTHETIC_BACKEND_CONFORMANCE_ONLY',
                   'started_at': started, 'ended_at': datetime.now(timezone.utc).isoformat(),
                   'returncode': completed.returncode, 'files_unchanged': unchanged,
                   'fingerprint_status': comparison['overall_status'], 'runtime_matches': runtime_matches,
                   'provenance_unchanged': provenance_unchanged,
                   'manifest_sha256': sha(output / 'manifest.json'),
                   'output_sha256': sha(result_path) if result_path.exists() else None,
                   'matches_independent_expected': actual == expected}
        write(output / 'receipt.json', receipt)
        return receipt
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        write(output / 'receipt.json', {'status': 'FAIL', 'error': str(error), 'started_at': started})
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('backtrader', 'lean'), required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--python', help='Python interpreter with locked Backtrader installed.')
    parser.add_argument('--dotnet', help='Local dotnet executable with .NET 10 runtime.')
    args = parser.parse_args()
    try:
        receipt = run_backend(args.backend, args.output, args.python, args.dotnet)
    except (OSError, ValueError, subprocess.SubprocessError) as error:
        print(str(error), file=sys.stderr)
        return 1
    print(json.dumps(receipt))
    return 0 if receipt['status'] == 'PASS' else 1


if __name__ == '__main__':
    raise SystemExit(main())
