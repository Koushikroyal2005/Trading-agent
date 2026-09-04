CREATE EXTENSION IF NOT EXISTS timescaledb;
CREATE TABLE IF NOT EXISTS market_data (time TIMESTAMPTZ NOT NULL, symbol VARCHAR(10) NOT NULL, open DOUBLE PRECISION, high DOUBLE PRECISION, low DOUBLE PRECISION, close DOUBLE PRECISION, volume DOUBLE PRECISION, vwap DOUBLE PRECISION, trade_count INTEGER, PRIMARY KEY(time,symbol));
SELECT create_hypertable('market_data','time',if_not_exists=>TRUE);
CREATE INDEX IF NOT EXISTS idx_market_symbol_time ON market_data(symbol,time DESC);
CREATE TABLE IF NOT EXISTS indicator_values (time TIMESTAMPTZ NOT NULL, symbol VARCHAR(10) NOT NULL, values JSONB NOT NULL);
SELECT create_hypertable('indicator_values','time',if_not_exists=>TRUE);
CREATE TABLE IF NOT EXISTS strategies (id BIGSERIAL PRIMARY KEY,name VARCHAR(80) UNIQUE,type VARCHAR(80),parameters_json JSONB,performance_score DOUBLE PRECISION DEFAULT 0,win_rate DOUBLE PRECISION DEFAULT 0,total_trades INTEGER DEFAULT 0,created_at TIMESTAMPTZ DEFAULT now(),last_used TIMESTAMPTZ);
CREATE TABLE IF NOT EXISTS trades (id UUID PRIMARY KEY,symbol VARCHAR(10),side VARCHAR(8),quantity DOUBLE PRECISION,price DOUBLE PRECISION,strategy_id BIGINT REFERENCES strategies(id),entry_reason TEXT,exit_reason TEXT,pnl DOUBLE PRECISION,risk_reward DOUBLE PRECISION,timestamp TIMESTAMPTZ DEFAULT now(),status VARCHAR(24),execution_time DOUBLE PRECISION);

