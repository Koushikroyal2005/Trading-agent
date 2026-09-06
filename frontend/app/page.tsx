"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";

type Tick = { time: string; price: number };
type MarketBar = { timestamp: string; close: number };
type MarketHistory = { bars: MarketBar[]; data_source: string };
type MarketQuote = { symbol: string; price: number; timestamp: string; data_source: string };
type Agent = { name: string; state: string; processed: number; failures: number; last_execution_ms: number; last_error?: string };
type Position = { symbol: string; quantity: number; average_price: number; current_price: number };
type Portfolio = { cash: number; equity: number; buying_power: number; daily_pnl: number; positions: Position[] };
type Performance = { total_return: number; realized_pnl: number; win_rate: number; sharpe_ratio: number; max_drawdown: number; trade_count: number; closed_trades: number };
type SystemStatus = { running: boolean; auto_trade: boolean; emergency_stopped: boolean; cycles: number; learned_closed_trades: number };
type DataStats = { orders: number; events: number; market_bars: number; indicator_sets: number };

const apiBase = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const names = ["data", "knowledge", "cot", "strategy", "risk", "execution", "rl", "validation"];

function mergeTick(current: Tick[], next: Tick): Tick[] {
  const unique = current.filter(point => point.time !== next.time);
  return [...unique, next].sort((left, right) => Date.parse(left.time) - Date.parse(right.time)).slice(-60);
}

export default function Home() {
  const [ticks, setTicks] = useState<Tick[]>([]);
  const [symbol, setSymbol] = useState("AAPL");
  const [connected, setConnected] = useState(false);
  const [message, setMessage] = useState("Connecting to the paper-trading API…");
  const [source, setSource] = useState("unknown");
  const [portfolio, setPortfolio] = useState<Portfolio | null>(null);
  const [performance, setPerformance] = useState<Performance | null>(null);
  const [system, setSystem] = useState<SystemStatus | null>(null);
  const [stats, setStats] = useState<DataStats | null>(null);
  const [agents, setAgents] = useState<Agent[]>([]);
  const [apiKey, setApiKey] = useState("");
  const lastMarketTickAt = useRef(0);

  useEffect(() => {
    const timer = window.setTimeout(() => setApiKey(localStorage.getItem("vector-api-key") || ""), 0);
    return () => window.clearTimeout(timer);
  }, []);
  const headers = useMemo(() => ({ "Content-Type": "application/json", ...(apiKey ? { "X-API-Key": apiKey } : {}) }), [apiKey]);

  const request = useCallback(async (path: string, options: RequestInit = {}) => {
    const response = await fetch(`${apiBase}${path}`, { ...options, headers: { ...headers, ...(options.headers || {}) } });
    if (!response.ok) throw new Error(`${response.status} ${await response.text()}`);
    return response.json();
  }, [headers]);

  const refresh = useCallback(async () => {
    try {
      const [nextPortfolio, nextPerformance, nextAgents, nextSystem, nextStats] = await Promise.all([
        request("/api/v1/portfolio"), request("/api/v1/performance"), request("/api/v1/agents/status"), request("/api/v1/orchestrator/status"), request("/api/v1/data/stats"),
      ]);
      setPortfolio(nextPortfolio); setPerformance(nextPerformance); setAgents(nextAgents); setSystem(nextSystem); setStats(nextStats);
    } catch (error) { setMessage(error instanceof Error ? `API error: ${error.message}` : "API unavailable"); }
  }, [request]);

  useEffect(() => {
    const initial = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(refresh, 10_000);
    return () => { window.clearTimeout(initial); window.clearInterval(timer); };
  }, [refresh]);

  useEffect(() => {
    let cancelled = false;
    const loadHistory = async () => {
      try {
        const history = await request(`/api/v1/market/history?symbol=${encodeURIComponent(symbol)}&days=30`) as MarketHistory;
        if (cancelled) return;
        const loaded = history.bars
          .filter(bar => Number.isFinite(Number(bar.close)))
          .map(bar => ({ time: bar.timestamp, price: Number(bar.close) }))
          .slice(-60);
        setTicks(loaded);
        setSource(history.data_source || "unknown");
        setMessage(history.data_source === "alpaca" ? `Loaded ${loaded.length} verified ${symbol} bars` : `Loaded ${loaded.length} ${symbol} fallback bars`);
      } catch (error) {
        if (!cancelled) setMessage(error instanceof Error ? `History unavailable: ${error.message}` : "History unavailable");
      }
    };
    void loadHistory();
    return () => { cancelled = true; };
  }, [request, symbol]);

  useEffect(() => {
    const wsBase = apiBase.replace(/^http/, "ws");
    const query = apiKey ? `?api_key=${encodeURIComponent(apiKey)}` : "";
    let disposed = false;
    let socket: WebSocket | undefined;
    let reconnectTimer: number | undefined;
    const connect = () => {
      socket = new WebSocket(`${wsBase}/ws/market${query}`);
      socket.onopen = () => { setConnected(true); setMessage("Connected to the Alpaca paper-trading API"); };
      socket.onclose = () => {
        setConnected(false);
        if (!disposed) reconnectTimer = window.setTimeout(connect, 2_000);
      };
      socket.onerror = () => socket?.close();
      socket.onmessage = event => {
        try {
          const data = JSON.parse(event.data) as MarketQuote | { type: string };
          if ("symbol" in data && data.symbol === symbol && Number.isFinite(Number(data.price))) {
            lastMarketTickAt.current = Date.now();
            setSource(data.data_source || "unknown");
            setTicks(current => mergeTick(current, { time: data.timestamp, price: Number(data.price) }));
            setMessage("Live Alpaca market data");
          }
        } catch { /* Ignore malformed or non-market messages and keep the connection alive. */ }
      };
    };
    connect();
    return () => { disposed = true; if (reconnectTimer) window.clearTimeout(reconnectTimer); socket?.close(); };
  }, [apiKey, symbol]);

  useEffect(() => {
    let cancelled = false;
    const pollQuote = async (initial = false) => {
      const streamIsFresh = Date.now() - lastMarketTickAt.current < 75_000;
      if (!initial && streamIsFresh) return;
      try {
        const quote = await request(`/api/v1/market/quotes?symbol=${encodeURIComponent(symbol)}`) as MarketQuote;
        if (cancelled) return;
        setSource(quote.data_source || "unknown");
        setTicks(current => mergeTick(current, { time: quote.timestamp, price: Number(quote.price) }));
        if (!initial) setMessage("Live stream delayed · verified quote polling active");
      } catch (error) {
        if (!cancelled && !initial) setMessage(error instanceof Error ? `Quote unavailable: ${error.message}` : "Quote unavailable");
      }
    };
    void pollQuote(true);
    const timer = window.setInterval(() => void pollQuote(), 30_000);
    return () => { cancelled = true; window.clearInterval(timer); };
  }, [request, symbol]);

  const chart = useMemo(() => {
    if (ticks.length < 2) return "";
    const prices = ticks.map(point => point.price); const min = Math.min(...prices)-.1; const max = Math.max(...prices)+.1;
    return ticks.map((point,index) => `${(index/(ticks.length-1))*100},${82-((point.price-min)/(max-min))*70}`).join(" ");
  }, [ticks]);
  const last = ticks.at(-1)?.price;
  const change = ticks.length > 1 ? (last! / ticks[0].price - 1) * 100 : 0;

  async function runAnalysis() {
    setMessage("Running analysis-only agent pipeline…");
    try {
      const result = await request("/api/v1/orchestrator/run", { method: "POST", body: JSON.stringify({ symbol, timeframe: 15, execute: false }) });
      setMessage(`${result.decision.action} · ${Math.round(result.decision.confidence*100)}% · ${result.data_source} · no order submitted`); await refresh();
    } catch (error) { setMessage(error instanceof Error ? error.message : "Analysis failed"); }
  }

  async function setAuto(enabled: boolean) {
    if (enabled && !window.confirm("Enable automated Alpaca PAPER orders? Safety gates remain active, but this can place paper trades.")) return;
    try { const result = await request("/api/v1/orchestrator/auto-trade", { method: "POST", body: JSON.stringify({ enabled }) }); setSystem(result); setMessage(enabled ? "Auto paper trading enabled with safety gates" : "Auto paper trading disabled"); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Unable to change auto-trade state"); }
  }

  async function emergencyStop() {
    try { const result = await request("/api/v1/orchestrator/emergency-stop", { method: "POST" }); setSystem(result); setMessage(`Emergency stop active · ${result.cancelled_orders} open orders cancelled`); }
    catch (error) { setMessage(error instanceof Error ? error.message : "Emergency stop failed"); }
  }

  function saveKey(value: string) { setApiKey(value); localStorage.setItem("vector-api-key", value); }
  const money = (value?: number) => value === undefined ? "—" : value.toLocaleString(undefined, { style: "currency", currency: "USD" });

  return <main>
    <header className="topbar"><div className="brand"><span className="brandmark">V</span><div><strong>VECTOR</strong><small>AGENTIC PAPER TRADING</small></div></div><div className="market-state"><span className="pulse"/> {source === "alpaca" ? "VERIFIED DATA" : "FALLBACK DATA"} <span className="muted">{source.toUpperCase()} · PAPER ONLY</span></div><div className="top-actions"><span className={connected ? "live" : "offline"}>{connected ? "LIVE" : "OFFLINE"}</span><span className="avatar">MR</span></div></header>
    <section className="shell"><aside><nav aria-label="Primary navigation"><a className="active" href="#market"><span>Market desk</span></a><a href="#portfolio"><span>Portfolio</span></a><a href="#agents"><span>Agent monitor</span></a><a href="#settings"><span>Settings</span></a></nav><div className="risk-card"><small>SYSTEM STATE</small><strong>{system?.emergency_stopped ? "STOPPED" : system?.auto_trade ? "AUTO PAPER" : "ANALYSIS"}</strong><p>{stats ? `${stats.market_bars} persisted bars` : "Waiting for database"}</p></div></aside>
    <div className="workspace"><section className="hero" id="market"><div><p className="eyebrow">MARKET INTELLIGENCE</p><h1>Paper trading, with guardrails.</h1><p>{message}</p></div><div className="controls"><div className="toggle-control"><span>Auto trade</span><button className={system?.auto_trade ? "toggle on" : "toggle"} onClick={() => setAuto(!system?.auto_trade)} aria-label="Toggle automatic paper trading" aria-pressed={Boolean(system?.auto_trade)}><i/></button></div><button className="stop" onClick={emergencyStop}>Emergency stop</button><button className="cycle" onClick={runAnalysis}>Run analysis</button></div></section>
    <section className="metrics"><article><small>ALPACA EQUITY</small><strong>{money(portfolio?.equity)}</strong><span>{money(portfolio?.daily_pnl)} today</span></article><article><small>REALIZED P&amp;L</small><strong>{money(performance?.realized_pnl)}</strong><span>{performance ? `${(performance.total_return*100).toFixed(2)}% return` : "—"}</span></article><article><small>OPEN POSITIONS</small><strong>{portfolio?.positions.length ?? "—"}</strong><span>{money(portfolio ? portfolio.positions.reduce((total, position) => total + Math.abs(position.quantity * position.current_price), 0) : undefined)} gross exposure</span></article><article><small>CLOSED-TRADE SHARPE</small><strong>{performance?.sharpe_ratio.toFixed(2) ?? "—"}</strong><span>{performance?.closed_trades ?? 0} completed round trips</span></article></section>
    <div className="grid"><section className="panel chart-panel"><div className="panel-head"><div><select value={symbol} onChange={event => setSymbol(event.target.value)} aria-label="Symbol"><option>AAPL</option><option>MSFT</option><option>SPY</option></select><strong>{money(last)}</strong><span className={change >= 0 ? "positive" : "negative"}>{change >= 0 ? "+" : ""}{change.toFixed(2)}%</span></div><div className="timeframes"><span className="tag">{source.toUpperCase()}</span></div></div><div className="chart">{chart ? <svg viewBox="0 0 100 88" preserveAspectRatio="none" role="img" aria-label="Verified market price trend"><polyline points={chart} fill="none" stroke="currentColor" strokeWidth="1.2" vectorEffect="non-scaling-stroke"/></svg> : <p className="empty">Loading verified Alpaca history…</p>}</div><div className="indicators"><span>BARS <b>{stats?.market_bars ?? 0}</b></span><span>EVENTS <b>{stats?.events ?? 0}</b></span><span>ORDERS <b>{stats?.orders ?? 0}</b></span><span>CYCLES <b>{system?.cycles ?? 0}</b></span></div></section>
    <section className="panel agents" id="agents"><div className="panel-title"><div><small>AGENT NETWORK</small><h2>Decision pipeline</h2></div><span>{connected ? "CONNECTED" : "DISCONNECTED"}</span></div>{names.map(name => { const agent=agents.find(item => item.name===name); return <div className="agent" key={name}><span className={`dot ${agent?.state || "idle"}`}/><div><strong>{name} agent</strong><small>{agent ? `${agent.processed} processed · ${agent.failures} failures${agent.last_error ? ` · ${agent.last_error}` : ""}` : "Awaiting status"}</small></div><em>{agent ? `${agent.last_execution_ms.toFixed(0)}ms` : "—"}</em></div>; })}</section>
    <section className="panel positions" id="portfolio"><div className="panel-title"><div><small>ALPACA PAPER BOOK</small><h2>Open positions</h2></div><span>{portfolio ? "SYNCED" : "WAITING"}</span></div><div className="table"><div className="row heading"><span>SYMBOL</span><span>SIDE</span><span>SIZE</span><span>UNREALIZED</span></div>{portfolio?.positions.length ? portfolio.positions.map(position => { const pnl=position.quantity*(position.current_price-position.average_price); return <div className="row" key={position.symbol}><strong>{position.symbol}</strong><span>{position.quantity >= 0 ? "LONG" : "SHORT"}</span><span>{Math.abs(position.quantity)}</span><b className={pnl >= 0 ? "positive" : "negative"}>{money(pnl)}</b></div>; }) : <p className="empty">No open paper positions.</p>}</div></section>
    <section className="panel thesis" id="settings"><small>LOCAL API ACCESS</small><blockquote>Dashboard values now come from Alpaca and the project database. No demonstration portfolio or performance numbers are shown.</blockquote><label className="key-label">API key<input type="password" value={apiKey} onChange={event => saveKey(event.target.value)} placeholder="Leave blank only on localhost"/></label><p>Auto trading defaults to off. Scheduled analysis continues collecting data while execution remains gated.</p></section></div></div></section>
  </main>;
}
