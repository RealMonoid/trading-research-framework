"""Explicit local dependency installation/build; never downloads market data."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LEAN = ROOT / 'backends/lean'
BINARY_DIR = LEAN / 'bin/Release/net10.0'


def file_hashes(paths):
    return {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(paths)}


def sources():
    return [LEAN / 'Program.cs', LEAN / 'ResearchBackend.csproj', LEAN / 'packages.lock.json']


def binaries():
    return [p for p in BINARY_DIR.rglob('*') if p.is_file() and p.name != 'build-receipt.json']


def resolve_executable(value):
    found = shutil.which(value)
    if not found and Path(value).is_file():
        found = os.path.abspath(value)
    if not found:
        raise ValueError('Executable unavailable: ' + value)
    # Resolving a POSIX venv's python symlink would silently select base Python.
    return os.path.abspath(found)


def prepare_lean(dotnet):
    dotnet = resolve_executable(dotnet)
    environment = dict(os.environ, DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1')
    subprocess.run([dotnet, 'restore', str(LEAN / 'ResearchBackend.csproj'), '--locked-mode'],
                   cwd=ROOT, env=environment, check=True)
    before = file_hashes(sources())
    subprocess.run([dotnet, 'build', str(LEAN / 'ResearchBackend.csproj'), '-c', 'Release',
                    '--no-restore', '--nologo'], cwd=ROOT, env=environment, check=True)
    if file_hashes(sources()) != before:
        raise ValueError('Sources changed during build.')
    receipt = {'sources': before, 'binaries': file_hashes(binaries()),
               'dotnet_info': subprocess.check_output([dotnet, '--info'], text=True)}
    (BINARY_DIR / 'build-receipt.json').write_text(json.dumps(receipt, indent=2) + '\n', encoding='utf-8')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--backend', choices=('backtrader', 'lean', 'both'), required=True)
    parser.add_argument('--python', default=sys.executable, help='Prefer a dedicated virtual environment.')
    parser.add_argument('--dotnet', default='dotnet', help='.NET 10 SDK executable.')
    args = parser.parse_args()
    if args.backend in ('backtrader', 'both'):
        subprocess.run([resolve_executable(args.python), '-m', 'pip', 'install', '--require-hashes',
                        '--only-binary=:all:', '-r', str(ROOT / 'backends/requirements-backtrader.txt')], check=True)
    if args.backend in ('lean', 'both'):
        prepare_lean(args.dotnet)


if __name__ == '__main__':
    main()
