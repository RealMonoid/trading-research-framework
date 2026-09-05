"""Contract regressions by default; --engines also executes both actual engines."""
import argparse
import copy
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from jsonschema import Draft202012Validator, FormatChecker
from run_backend_fixture import ROOT, FIXTURE, read, validate_request, run_backend, fingerprint
from check_research_fingerprint import verify_fingerprint, build_fingerprint_check


class ContractTests(unittest.TestCase):
    def test_rejects_unsupported_and_malformed_inputs(self):
        mutations = [
            lambda x: x.update(data_role='MARKET_DATA'),
            lambda x: x.update(fill_model='QUEUE_FILL'),
            lambda x: x.update(instrument_model='CONTINUOUS_FUTURES'),
            lambda x: x.update(timezone='America/New_York'),
            lambda x: x.update(live=True),
            lambda x: x.update(quantity=0.5),
            lambda x: x.update(slippage_absolute=float('nan')),
            lambda x: x['bars'][1].update(end=x['bars'][0]['end']),
            lambda x: x['bars'][1].update(low=200),
            lambda x: x['bars'][1].update(volume=-1),
        ]
        for mutate in mutations:
            request = read(FIXTURE)
            mutate(request)
            with self.assertRaises(ValueError):
                validate_request(request)

    def test_complete_fingerprint_detects_configuration_change(self):
        request = read(FIXTURE)
        original = fingerprint({'configuration': {'fee': 1}}, request, {'cash': 9970})
        validator = Draft202012Validator(read(ROOT / 'schemas/research_fingerprint.schema.json'),
                                        format_checker=FormatChecker())
        validator.validate(original)
        verify_fingerprint(original, 'test')
        candidate = fingerprint({'configuration': {'fee': 0}}, request, {'cash': 9970})
        result = build_fingerprint_check({'decision_id': 'backend-test', 'fingerprint_guard': {
            'mode': 'PRESERVE_EFFECTIVE', 'baseline_fingerprint_ref': original['fingerprint_id'],
            'baseline_fingerprint_sha256': original['fingerprint_sha256']}}, original, candidate,
            checked_at=original['created_at'])
        self.assertEqual('CHANGE_PROPOSED', result['overall_status'])
        self.assertFalse(result['candidate_may_become_effective'])

    def test_preserves_existing_output(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp)
            with self.assertRaisesRegex(ValueError, 'already exists'):
                run_backend('backtrader', target)
            self.assertEqual([], list(target.iterdir()))

    def test_missing_engine_is_not_a_pass(self):
        with tempfile.TemporaryDirectory() as temp:
            with patch('run_backend_fixture.resolve_executable', side_effect=ValueError('missing')):
                with self.assertRaises(ValueError):
                    run_backend('lean', Path(temp) / 'absent')
            self.assertFalse((Path(temp) / 'absent/engine-output.json').exists())


def engine_tests(python, dotnet, output):
    base = read(FIXTURE)
    expected = read(FIXTURE.with_name('next_open.expected.json'))
    cases = [('next-open', base, expected), ('repeat', base, expected)]
    zero = copy.deepcopy(base)
    zero.update(fee_per_unit=0, slippage_absolute=0)
    zero_expected = copy.deepcopy(expected)
    zero_expected['fills'][0].update(price=110, fee=0)
    zero_expected['fills'][1].update(price=98, fee=0)
    zero_expected.update(cash=9976, equity=9976)
    cases.append(('zero-cost', zero, zero_expected))
    no_signal = copy.deepcopy(base)
    no_signal['entry_close_at_least'] = 200
    empty = {'orders': [], 'fills': [], 'cash': 10000, 'equity': 10000, 'position': 0, 'open_orders': 0}
    cases.append(('no-signal', no_signal, empty))
    last_signal = copy.deepcopy(no_signal)
    last_signal['bars'][-1].update(open=200, high=202, low=199, close=201)
    pending = copy.deepcopy(empty)
    pending.update(orders=[{'bar_end': '2026-01-05T09:07:00Z', 'quantity': 2}], open_orders=1)
    cases.append(('last-bar-remains-unfilled', last_signal, pending))
    future = copy.deepcopy(base)
    future['bars'][-1].update(open=900, high=1000, low=800, close=950)
    cases.append(('future-change-preserves-past', future, expected))
    summary = []
    for name, request, target in cases:
        actuals = []
        for backend in ('backtrader', 'lean'):
            directory = output / (name + '-' + backend)
            receipt = run_backend(backend, directory, python, dotnet, request, target)
            if receipt['status'] != 'PASS':
                raise AssertionError(f'{name}/{backend} failed; inspect {directory}')
            actuals.append(read(directory / 'engine-output.json'))
        if actuals[0] != actuals[1]:
            raise AssertionError('Cross-engine mismatch: ' + name)
        summary.append({'case': name, 'both_match_independent_expected': True})
        print('PASS actual engines: ' + name, flush=True)
    # A deliberately wrong oracle must fail even when an engine ran successfully.
    wrong = copy.deepcopy(expected)
    wrong['cash'] += 1
    for backend in ('backtrader', 'lean'):
        receipt = run_backend(backend, output / ('wrong-oracle-' + backend), python, dotnet, base, wrong)
        if receipt['status'] != 'FAIL' or receipt['returncode'] != 0:
            raise AssertionError('False conformance was accepted.')
    (output / 'comparison.json').write_text(json.dumps({
        'claim': 'SYNTHETIC_BACKEND_CONFORMANCE_ONLY', 'cases': summary,
        'wrong_oracle_rejected_by_both': True}, indent=2) + '\n', encoding='utf-8')


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--engines', action='store_true')
    parser.add_argument('--python')
    parser.add_argument('--dotnet')
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = unittest.TextTestRunner(verbosity=2).run(unittest.defaultTestLoader.loadTestsFromTestCase(ContractTests))
    if not result.wasSuccessful():
        raise SystemExit(1)
    if args.engines:
        if args.output is None or args.output.exists():
            raise SystemExit('--engines requires a new --output directory.')
        engine_tests(args.python, args.dotnet, args.output.resolve())
    else:
        print('Backend contract checks only; actual engine execution was not requested.')
