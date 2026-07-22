"""IDX daily screener.

Price/volume data comes from Yahoo Finance.  Broker and foreign-flow scores are
only calculated when the corresponding CSV files are supplied; they are never
inferred from EOD prices.
"""
from pathlib import Path
import numpy as np
import pandas as pd
import yfinance as yf

BASE_DIR = Path(__file__).resolve().parent
UNIVERSE_FILE = BASE_DIR / "idx_universe.csv"
BROKER_FILE = BASE_DIR / "broker_summary.csv"
FOREIGN_FILE = BASE_DIR / "foreign_flow.csv"
RESULT_FILE = BASE_DIR / "hasil_screener.csv"
DIAGNOSTICS_FILE = BASE_DIR / "universe_diagnostics.csv"
MIN_AVG_TRANSACTION_VALUE = 3_000_000_000
MIN_PRICE = 50
MIN_HISTORY = 60

# Starter universe: liquid Indonesian equities. Replace/extend it with
# idx_universe.csv (one required column: Ticker) to screen your own IDX universe.
DEFAULT_TICKERS = """AALI ACES ADHI ADMR ADRO AGII AKRA AMMN ANTM ARTO ASII
BBCA BBNI BBRI BBTN BBYB BCAS BDMN BEST BMRI BOGA BRIS BRMS BSDE BTPS BUKA
BUMI CTRA DEWA DILD ERAA EXCL GGRM GJTL HMSP HRUM ICBP INCO INDF INDY INKP
INTP ISAT ITMG JSMR JPFA JPP JPRS KAEF KBAG KBLF KLBF KMTR KPIG KRAS
LSIP MAPI MBMA MDKA MEDC MIKA MNCN MTEL MYOR PANI PGAS PGEO PGAS PNLF
PTBA PTPP PWON RAJA RALS SCMA SDRA SGRO SIDO SMDR SMGR SMRA SRTG SSIA
TAPG TBIG TCPI TINS TLKM TOWR TPIA UNTR UNVR WIFI WIKA WSKT""".split()


def load_universe():
    if UNIVERSE_FILE.exists():
        frame = pd.read_csv(UNIVERSE_FILE)
        if "Ticker" not in frame.columns:
            raise ValueError("idx_universe.csv wajib memiliki kolom bernama 'Ticker'.")
        tickers = frame["Ticker"].dropna().astype(str).str.upper().str.strip()
    else:
        tickers = pd.Series(DEFAULT_TICKERS)
        print("idx_universe.csv tidak ditemukan; memakai starter liquid universe.")
    return sorted({ticker if ticker.endswith(".JK") else f"{ticker}.JK" for ticker in tickers})


def calculate_rsi(close, period=14):
    change = close.diff()
    gain = change.clip(lower=0).rolling(period).mean()
    loss = -change.clip(upper=0).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))


def get_fundamental_score(ticker):
    try:
        info = yf.Ticker(ticker).info
        score = 50
        pe, pb = info.get("trailingPE"), info.get("priceToBook")
        growth, margin = info.get("revenueGrowth"), info.get("profitMargins")
        if pe is not None and 0 < pe < 20: score += 15
        if pb is not None and 0 < pb < 3: score += 10
        if growth is not None and growth > 0: score += 15
        if margin is not None and margin > 0: score += 10
        return min(score, 100)
    except Exception:
        return 50


def _load_flow_file(path, required):
    if not path.exists():
        return None
    frame = pd.read_csv(path)
    missing = set(required) - set(frame.columns)
    if missing:
        print(f"{path.name} diabaikan: kolom kurang {sorted(missing)}")
        return None
    frame["Ticker"] = frame["Ticker"].astype(str).str.upper().str.replace(".JK", "", regex=False)
    return frame


def broker_score(ticker, broker_data):
    if broker_data is None: return np.nan, "Tidak ada broker summary"
    data = broker_data[broker_data["Ticker"] == ticker.replace(".JK", "")]
    if data.empty: return np.nan, "Tidak ada broker summary"
    buy, sell = data["BuyValue"].sum(), data["SellValue"].sum()
    gross = buy + sell
    if gross <= 0: return np.nan, "Broker summary tidak valid"
    net_ratio = (buy - sell) / gross
    concentration = data.groupby("Broker")["BuyValue"].sum().max() / buy if buy > 0 else 0
    score = 50 + (30 if net_ratio >= .20 else 15 if net_ratio >= .05 else -20 if net_ratio <= -.20 else -10 if net_ratio <= -.05 else 0)
    score += 20 if concentration >= .30 and net_ratio > 0 else 0
    return max(0, min(100, score)), f"Net broker {net_ratio:+.1%}"


def foreign_score(ticker, foreign_data):
    if foreign_data is None: return np.nan, "Tidak ada foreign flow"
    data = foreign_data[foreign_data["Ticker"] == ticker.replace(".JK", "")]
    if data.empty: return np.nan, "Tidak ada foreign flow"
    buy, sell = data["ForeignBuyValue"].sum(), data["ForeignSellValue"].sum()
    gross = buy + sell
    if gross <= 0: return np.nan, "Foreign flow tidak valid"
    ratio = (buy - sell) / gross
    score = 50 + (40 if ratio >= .20 else 20 if ratio >= .05 else -30 if ratio <= -.20 else -15 if ratio <= -.05 else 0)
    return max(0, min(100, score)), f"Net foreign {ratio:+.1%}"


def analyze_stock(ticker, broker_data, foreign_data):
    data = yf.download(ticker, period="1y", auto_adjust=True, progress=False)
    if getattr(data.columns, "nlevels", 1) > 1: data.columns = data.columns.get_level_values(0)
    data = data[["Open", "High", "Low", "Close", "Volume"]].dropna()
    if len(data) < MIN_HISTORY: return None, "riwayat kurang dari 60 hari"
    close, high, volume = data["Close"], data["High"], data["Volume"]
    avg_value_20 = (close * volume).rolling(20).mean().iloc[-1]
    active_ratio = (volume.tail(60) > 0).mean()
    latest_close = close.iloc[-1]
    if latest_close < MIN_PRICE: return None, f"harga < Rp{MIN_PRICE:,.0f}"
    if avg_value_20 < MIN_AVG_TRANSACTION_VALUE: return None, "rata-rata nilai transaksi 20 hari < Rp3 miliar"
    if active_ratio < .90: return None, "frekuensi perdagangan rendah"

    sma20, sma50, rsi = close.rolling(20).mean(), close.rolling(50).mean(), calculate_rsi(close)
    relative_volume = volume.iloc[-1] / volume.rolling(20).mean().iloc[-1]
    high_20 = high.rolling(20).max().iloc[-2]
    day_range = data["High"].iloc[-1] - data["Low"].iloc[-1]
    close_position = (latest_close - data["Low"].iloc[-1]) / day_range if day_range else .5
    latest_rsi = rsi.iloc[-1]
    technical = (25 if latest_close > sma20.iloc[-1] else 0) + (25 if sma20.iloc[-1] > sma50.iloc[-1] else 0)
    technical += 25 if 50 <= latest_rsi <= 70 else 15 if 45 <= latest_rsi < 50 else 0
    technical += 25 if latest_close > high_20 else 0
    pv_flow = (35 if relative_volume >= 2 else 25 if relative_volume >= 1.5 else 15 if relative_volume >= 1.2 else 0)
    pv_flow += 25 if close_position >= .8 else 15 if close_position >= .6 else 0
    green_days = (close.pct_change().tail(5) > 0).sum()
    pv_flow += 20 if green_days >= 4 else 10 if green_days >= 3 else 0
    pv_flow += 20 if latest_close * volume.iloc[-1] >= 10e9 else 10 if latest_close * volume.iloc[-1] >= 3e9 else 0
    broker, broker_note = broker_score(ticker, broker_data)
    foreign, foreign_note = foreign_score(ticker, foreign_data)
    reasons = []
    if latest_close > high_20: reasons.append("breakout high 20 hari")
    if relative_volume >= 1.5: reasons.append(f"volume {relative_volume:.1f}x rata-rata 20 hari")
    if close_position >= .8: reasons.append("close dekat high")
    if sma20.iloc[-1] > sma50.iloc[-1]: reasons.append("SMA20 di atas SMA50")
    return {"Ticker": ticker.replace(".JK", ""), "Harga Terakhir": round(latest_close, 0), "RSI": round(latest_rsi, 1), "Rel. Volume": round(relative_volume, 2), "Rata2 Nilai Transaksi 20H": round(avg_value_20, 0), "Fundamental": round(get_fundamental_score(ticker), 1), "Teknikal": technical, "Price-Volume Flow": pv_flow, "Broker Flow": broker, "Foreign Flow": foreign, "Status Broker": broker_note, "Status Foreign": foreign_note, "Alasan": ", ".join(reasons) or "Tidak ada sinyal kuat"}, None


def main():
    tickers = load_universe()
    broker_data = _load_flow_file(BROKER_FILE, ["Ticker", "Broker", "BuyValue", "SellValue"])
    foreign_data = _load_flow_file(FOREIGN_FILE, ["Ticker", "ForeignBuyValue", "ForeignSellValue"])
    results, diagnostics = [], []
    for number, ticker in enumerate(tickers, 1):
        print(f"[{number}/{len(tickers)}] Memeriksa {ticker}...")
        try:
            result, reason = analyze_stock(ticker, broker_data, foreign_data)
            if result: results.append(result); diagnostics.append({"Ticker": ticker.replace(".JK", ""), "Status": "LOLOS", "Keterangan": ""})
            else: diagnostics.append({"Ticker": ticker.replace(".JK", ""), "Status": "DIFILTER", "Keterangan": reason})
        except Exception as error:
            diagnostics.append({"Ticker": ticker.replace(".JK", ""), "Status": "ERROR", "Keterangan": str(error)})
    pd.DataFrame(diagnostics).to_csv(DIAGNOSTICS_FILE, index=False)
    screener = pd.DataFrame(results)
    if screener.empty: print("Tidak ada saham yang lolos filter."); return
    # Default keeps the original 15/35/50 formula; broker and foreign scores are
    # displayed separately until the user assigns them a weight in the dashboard.
    screener["Skor Akhir"] = (screener["Fundamental"]*.15 + screener["Teknikal"]*.35 + screener["Price-Volume Flow"]*.50).round(1)
    screener.sort_values("Skor Akhir", ascending=False).to_csv(RESULT_FILE, index=False)
    print(f"\nSelesai: {len(screener)}/{len(tickers)} saham lolos. Lihat hasil_screener.csv dan universe_diagnostics.csv")

if __name__ == "__main__": main()
