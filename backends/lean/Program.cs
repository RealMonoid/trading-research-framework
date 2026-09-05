using System.Globalization;
using System.Reflection;
using Newtonsoft.Json;
using QuantConnect;
using QuantConnect.Algorithm;
using QuantConnect.Configuration;
using QuantConnect.Data;
using QuantConnect.Data.Market;
using QuantConnect.Lean.Engine;
using QuantConnect.Logging;
using QuantConnect.Orders;
using QuantConnect.Orders.Fees;
using QuantConnect.Orders.Fills;
using QuantConnect.Orders.Slippage;
using QuantConnect.Securities;
using QuantConnect.Util;

// Local synthetic harness only. No caller-provided algorithm, live job or remote feed.
public static class Program
{
    public static int Main(string[] args)
    {
        if (args.Length != 0) throw new ArgumentException("Use the framework runner.");
        Config.Set("live-mode", "false");
        Config.Set("algorithm-language", "CSharp");
        Config.Set("algorithm-type-name", nameof(SyntheticAlgorithm));
        Config.Set("algorithm-location", Assembly.GetExecutingAssembly().Location);
        Config.Set("close-automatically", "true");
        Config.Set("data-provider", "DefaultDataProvider");
        Config.Set("api-handler", "QuantConnect.Api.Api");
        Config.Set("setup-handler", "ConsoleSetupHandler");
        Config.Set("data-feed-handler", "FileSystemDataFeed");
        Config.Set("transaction-handler", "BacktestingTransactionHandler");
        Config.Set("real-time-handler", "BacktestingRealTimeHandler");
        Config.Set("result-handler", "BacktestingResultHandler");
        Config.Set("log-handler", "ConsoleLogHandler");
        Initializer.Start();
        using var system = Initializer.GetSystemHandlers();
        var job = system.JobQueue.NextJob(out var assembly);
        if (job is not QuantConnect.Packets.BacktestNodePacket)
            throw new InvalidOperationException("Only a local backtest job is permitted.");
        using var handlers = Initializer.GetAlgorithmHandlers();
        var manager = new AlgorithmManager(false, job);
        system.LeanManager.Initialize(system, handlers, job, manager);
        OS.Initialize();
        try
        {
            new QuantConnect.Lean.Engine.Engine(system, handlers, false)
                .Run(job, manager, assembly, WorkerThread.Instance);
            return manager.State == AlgorithmStatus.Completed ? 0 : 1;
        }
        finally { OS.Dispose(); }
    }
}

public class SyntheticBar : TradeBar
{
    public override SubscriptionDataSource GetSource(SubscriptionDataConfig config, DateTime date, bool live)
    {
        if (live) throw new InvalidOperationException("Live data is disabled.");
        return new SubscriptionDataSource(Path.GetFullPath("bars.csv"), SubscriptionTransportMedium.LocalFile);
    }

    public override BaseData Reader(SubscriptionDataConfig config, string line, DateTime date, bool live)
    {
        if (live) throw new InvalidOperationException("Live data is disabled.");
        var cells = line.Split(',');
        var start = DateTime.ParseExact(cells[0], "yyyy-MM-ddTHH:mm:ss", CultureInfo.InvariantCulture);
        if (start.Date != date.Date) return null;
        return new SyntheticBar
        {
            Symbol = config.Symbol, Time = start, Period = TimeSpan.FromMinutes(1),
            Open = decimal.Parse(cells[1], CultureInfo.InvariantCulture),
            High = decimal.Parse(cells[2], CultureInfo.InvariantCulture),
            Low = decimal.Parse(cells[3], CultureInfo.InvariantCulture),
            Close = decimal.Parse(cells[4], CultureInfo.InvariantCulture),
            Volume = decimal.Parse(cells[5], CultureInfo.InvariantCulture)
        };
    }
}

// Explicit bar-model convention: next bar open after a completed-bar decision.
// This overrides LEAN's immediate market-price default; it is not queue evidence.
public class NextBarOpenFill : FillModel
{
    public override OrderEvent MarketFill(Security asset, MarketOrder order)
    {
        var fill = new OrderEvent(order, asset.LocalTime.ConvertToUtc(asset.Exchange.TimeZone), OrderFee.Zero);
        var bar = asset.GetLastData() as TradeBar;
        if (bar == null || bar.EndTime <= order.Time) return fill;
        fill.Status = OrderStatus.Filled;
        fill.FillQuantity = order.Quantity;
        fill.FillPrice = bar.Open + Math.Sign(order.Quantity) * asset.SlippageModel.GetSlippageApproximation(asset, order);
        return fill;
    }
}

public class PerUnitFee(decimal amount) : FeeModel
{
    public override OrderFee GetOrderFee(OrderFeeParameters parameters) =>
        new(new CashAmount(Math.Abs(parameters.Order.Quantity) * amount, "USD"));
}

public class AbsoluteSlippage(decimal amount) : ISlippageModel
{
    public decimal GetSlippageApproximation(Security asset, Order order) => amount;
}

public class SyntheticAlgorithm : QCAlgorithm
{
    private Symbol symbol;
    private dynamic request;
    private bool entered, exited;
    private readonly List<object> orders = new();
    private readonly List<object> fills = new();

    public override void Initialize()
    {
        request = JsonConvert.DeserializeObject(File.ReadAllText("request.json"));
        if ((string)request.data_role != "SYNTHETIC_BACKEND_FIXTURE")
            throw new InvalidOperationException("Empirical runs are not integrated.");
        SetTimeZone(TimeZones.Utc);
        SetStartDate(2026, 1, 5);
        SetEndDate(2026, 1, 5);
        SetCash((decimal)request.initial_cash);
        SetBenchmark(_ => 100m);
        var security = AddData<SyntheticBar>("SYNTH", Resolution.Minute, TimeZones.Utc, false, 1m);
        symbol = security.Symbol;
        security.SetFeeModel(new PerUnitFee((decimal)request.fee_per_unit));
        security.SetSlippageModel(new AbsoluteSlippage((decimal)request.slippage_absolute));
        security.SetFillModel(new NextBarOpenFill());
    }

    public override void OnData(Slice data)
    {
        if (!data.Bars.TryGetValue(symbol, out var bar)) return;
        decimal quantity = 0;
        if (!entered && bar.Close >= (decimal)request.entry_close_at_least)
        { quantity = (decimal)request.quantity; entered = true; }
        else if (entered && !exited && Portfolio[symbol].Invested && bar.Close <= (decimal)request.exit_close_at_most)
        { quantity = -(decimal)request.quantity; exited = true; }
        if (quantity != 0)
        {
            MarketOrder(symbol, quantity, asynchronous: true);
            orders.Add(new { bar_end = Time.ToString("yyyy-MM-ddTHH:mm:ss'Z'"), quantity });
        }
    }

    public override void OnOrderEvent(OrderEvent ev)
    {
        if (ev.Status == OrderStatus.Filled || ev.Status == OrderStatus.PartiallyFilled)
            fills.Add(new { bar_end = ev.UtcTime.ToString("yyyy-MM-ddTHH:mm:ss'Z'"),
                quantity = ev.FillQuantity, price = ev.FillPrice, fee = ev.OrderFee.Value.Amount });
        if (ev.Status == OrderStatus.Invalid || ev.Status == OrderStatus.Canceled)
            throw new InvalidOperationException("Unexpected order failure: " + ev);
    }

    public override void OnEndOfAlgorithm()
    {
        File.WriteAllText("engine-output.json", JsonConvert.SerializeObject(new {
            orders, fills, cash = Portfolio.Cash,
            equity = Portfolio.TotalPortfolioValue, position = Portfolio[symbol].Quantity,
            open_orders = Transactions.GetOpenOrders().Count
        }, Formatting.Indented));
    }
}
