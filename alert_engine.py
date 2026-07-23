"""Mesin alert intraday IDX untuk dijalankan oleh GitHub Actions.

Data berasal dari Yahoo Finance dan hanya dipakai sebagai indikator riset.
Tidak ada order beli/jual yang dikirim oleh modul ini.
"""
from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from urllib.parse import urlencode
from urllib.request import Request, urlopen

import pandas as pd
import yfinance as yf

import screener

BASE_DIR = Path(__file__).resolve().parent
STATE_FILE = BASE_DIR / "alert_state.json"
JAKARTA_TZ = "Asia/Jakarta"
MIN_TRANSACTION_VALUE = 1_000_000_000
VOLUME_MULTIPLE = 3.0
NORMAL_LOOKBACK = 20


def _normalise_columns(data: pd.DataFrame) -> pd.DataFrame:
    if getattr(data.columns, "nlevels", 1) > 1:
        data.columns = data.columns.get_level_values(0)
    return data


def download_intraday(ticker: str) -> pd.DataFrame:
    """Ambil candle 30 menit terakhir yang Yahoo masih sediakan (maks. ~60 hari)."""
    data = yf.download(
        ticker,
        period="60d",
        interval="30m",
        auto_adjust=True,
        progress=False,
        prepost=False,
    )
    data = _normalise_columns(data).dropna(subset=["Open", "High", "Low", "Close", "Volume"])
    if data.empty:
        return data
    index = pd.to_datetime(data.index)
    if index.tz is None:
        index = index.tz_localize("UTC")
    data.index = index.tz_convert(JAKARTA_TZ)
    return data


def add_intraday_metrics(data: pd.DataFrame) -> pd.DataFrame:
    """Tambah VWAP harian, posisi close candle, dan volume normal per slot jam."""
    frame = data.copy()
    frame["TradingDate"] = frame.index.date
    frame["Slot"] = frame.index.strftime("%H:%M")
    typical_price = (frame["High"] + frame["Low"] + frame["Close"]) / 3
    value = typical_price * frame["Volume"]
    frame["VWAP"] = value.groupby(frame["TradingDate"]).cumsum() / frame["Volume"].groupby(frame["TradingDate"]).cumsum().replace(0, pd.NA)
    candle_range = frame["High"] - frame["Low"]
    frame["ClosePosition"] = ((frame["Close"] - frame["Low"]) / candle_range.where(candle_range != 0, 1)).clip(0, 1)

    # Untuk tiap candle, bandingkan dengan slot 30 menit yang sama pada hari-hari sebelumnya.
    frame["NormalVolume"] = (
        frame.groupby("Slot", group_keys=False)["Volume"]
        .apply(lambda item: item.shift(1).rolling(NORMAL_LOOKBACK, min_periods=10).mean())
    )
    frame["VolumeMultiple"] = frame["Volume"] / frame["NormalVolume"].replace(0, pd.NA)
    return frame


def make_signal(ticker: str, candle: pd.Series) -> dict | None:
    """Nilai satu candle; hasil None berarti aturan alert belum terpenuhi."""
    value = float(candle["Close"] * candle["Volume"])
    multiple = candle.get("VolumeMultiple")
    if pd.isna(multiple) or multiple < VOLUME_MULTIPLE or value < MIN_TRANSACTION_VALUE:
        return None

    if candle["Close"] > candle["VWAP"] and candle["ClosePosition"] >= 0.80:
        direction, label = "BUY", "🟢 BELI KUAT"
    elif candle["Close"] < candle["VWAP"] and candle["ClosePosition"] <= 0.20:
        direction, label = "SELL", "🔴 JUAL KUAT"
    else:
        return None

    timestamp = candle.name
    return {
        "key": f"{timestamp.strftime('%Y-%m-%d')}:{ticker}:{direction}",
        "ticker": ticker.replace(".JK", ""),
        "direction": direction,
        "time": timestamp.strftime("%H:%M WIB"),
        "label": label,
        "multiple": float(multiple),
        "value": value,
        "price": float(candle["Close"]),
        "vwap": float(candle["VWAP"]),
    }


def format_message(signal: dict) -> str:
    relation = "di atas" if signal["direction"] == "BUY" else "di bawah"
    close_note = "dekat high" if signal["direction"] == "BUY" else "dekat low"
    return (
        f"{signal['label']} — {signal['ticker']}\n"
        f"{signal['time']} · Volume {signal['multiple']:.1f}× normal\n"
        f"Nilai transaksi candle Rp{signal['value']:,.0f}\n"
        f"Harga Rp{signal['price']:,.0f}, {relation} VWAP Rp{signal['vwap']:,.0f}; close {close_note}.\n\n"
        "Indikator riset, bukan rekomendasi beli/jual."
    )


def send_telegram(token: str, chat_id: str, message: str) -> None:
    request = Request(
        f"https://api.telegram.org/bot{token}/sendMessage",
        data=urlencode({"chat_id": chat_id, "text": message}).encode("utf-8"),
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        method="POST",
    )
    with urlopen(request, timeout=20) as response:
        result = json.loads(response.read().decode("utf-8"))
    if not result.get("ok"):
        raise RuntimeError(result.get("description", "Telegram menolak pesan."))


def load_state() -> set[str]:
    if not STATE_FILE.exists():
        return set()
    try:
        return set(json.loads(STATE_FILE.read_text(encoding="utf-8")).get("sent", []))
    except (json.JSONDecodeError, OSError):
        return set()


def save_state(keys: set[str]) -> None:
    # Simpan hanya 14 hari terakhir agar file tetap kecil.
    today = datetime.now().strftime("%Y-%m-%d")
    cutoff = (pd.Timestamp(today) - pd.Timedelta(days=14)).strftime("%Y-%m-%d")
    recent = sorted(key for key in keys if key.split(":", 1)[0] >= cutoff)
    STATE_FILE.write_text(json.dumps({"sent": recent}, indent=2), encoding="utf-8")


def run_alerts() -> int:
    token = os.getenv("TELEGRAM_BOT_TOKEN", "").strip()
    chat_id = os.getenv("TELEGRAM_CHAT_ID", "").strip()
    if not token or not chat_id:
        raise RuntimeError("TELEGRAM_BOT_TOKEN dan TELEGRAM_CHAT_ID belum diisi pada GitHub Secrets.")

    sent_keys = load_state()
    sent_count = 0
    for ticker in screener.load_universe():
        try:
            data = add_intraday_metrics(download_intraday(ticker))
            if data.empty:
                continue
            signal = make_signal(ticker, data.iloc[-1])
            if signal is None or signal["key"] in sent_keys:
                continue
            send_telegram(token, chat_id, format_message(signal))
            sent_keys.add(signal["key"])
            sent_count += 1
            print(f"Alert terkirim: {signal['key']}")
        except Exception as error:
            print(f"{ticker}: dilewati ({error})")
    save_state(sent_keys)
    print(f"Selesai. {sent_count} alert baru terkirim.")
    return sent_count


if __name__ == "__main__":
    run_alerts()
