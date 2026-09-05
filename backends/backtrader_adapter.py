"""Backtrader subprocess adapter for the synthetic, one-minute cash contract."""
from __future__ import annotations

import hashlib
import json
import platform
import sys
from datetime import datetime
from pathlib import Path

import backtrader as bt


def iso(value):
    return value.strftime('%Y-%m-%dT%H:%M:%SZ')


def describe():
    if bt.__version__ != '1.9.78.123':
        raise ValueError('Unreviewed Backtrader version.')
    package = Path(bt.__file__).parent
    files = {str(p.resolve()): hashlib.sha256(p.read_bytes()).hexdigest()
             for p in sorted(package.rglob('*.py'))}
    return {'version': bt.__version__, 'python': platform.python_version(), 'package_files': files}


def main():
    runtime = describe()
    if sys.argv[1:] == ['--describe']:
        print(json.dumps(runtime))
        return
    if sys.argv[1:]:
        raise ValueError('Unsupported adapter arguments.')
    request = json.loads(Path('request.json').read_text())
    if request['data_role'] != 'SYNTHETIC_BACKEND_FIXTURE':
        raise ValueError('Empirical runs are not integrated.')

    class Bars(bt.feed.DataBase):
        def start(self):
            super().start()
            self.rows = iter(request['bars'])

        def _load(self):
            row = next(self.rows, None)
            if row is None:
                return False
            # Backtrader timestamps represent completed bars in this adapter.
            self.lines.datetime[0] = bt.date2num(datetime.fromisoformat(row['end'].replace('Z', '+00:00')))
            for name in ('open', 'high', 'low', 'close', 'volume'):
                getattr(self.lines, name)[0] = row[name]
            self.lines.openinterest[0] = 0
            return True

    class Strategy(bt.Strategy):
        def __init__(self):
            self.entered = self.exited = False
            self.orders = []
            self.fills = []

        def next(self):
            quantity = 0
            if not self.entered and self.data.close[0] >= request['entry_close_at_least']:
                quantity = request['quantity']
                self.entered = True
            elif self.entered and not self.exited and self.position and self.data.close[0] <= request['exit_close_at_most']:
                quantity = -request['quantity']
                self.exited = True
            if quantity:
                self.orders.append({'bar_end': iso(self.data.datetime.datetime()), 'quantity': quantity})
                if quantity > 0:
                    self.buy(size=quantity)
                else:
                    self.sell(size=-quantity)

        def notify_order(self, order):
            if order.status == order.Completed:
                self.fills.append({'bar_end': iso(bt.num2date(order.executed.dt)),
                                   'quantity': order.executed.size, 'price': order.executed.price,
                                   'fee': order.executed.comm})
            elif order.status in (order.Canceled, order.Margin, order.Rejected, order.Expired):
                raise ValueError('Unexpected order failure: ' + order.getstatusname())

    engine = bt.Cerebro(stdstats=False, cheat_on_open=False)
    engine.broker.setcash(request['initial_cash'])
    engine.broker.set_coc(False)
    engine.broker.set_coo(False)
    engine.broker.setcommission(commission=request['fee_per_unit'],
                                commtype=bt.CommInfoBase.COMM_FIXED, stocklike=True, leverage=1)
    engine.broker.set_slippage_fixed(request['slippage_absolute'], slip_open=True,
                                     slip_match=True, slip_out=True)
    engine.adddata(Bars(timeframe=bt.TimeFrame.Minutes, compression=1))
    engine.addstrategy(Strategy)
    strategy = engine.run(preload=False, runonce=False)[0]
    output = {'orders': strategy.orders, 'fills': strategy.fills,
              'cash': engine.broker.getcash(), 'equity': engine.broker.getvalue(),
              'position': strategy.position.size,
              # Submitted orders at EOF have not yet reached the accepted queue.
              'open_orders': sum(order.alive() for order in engine.broker.orders)}
    Path('engine-output.json').write_text(json.dumps(output, indent=2, allow_nan=False) + '\n')
    Path('engine-runtime.json').write_text(json.dumps(runtime, indent=2) + '\n')


if __name__ == '__main__':
    main()
