import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from pathlib import Path

st.set_page_config(page_title="IDX Trading Bot", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
SCREENER_FILE = BASE_DIR / "hasil_screener.csv"

st.title("📈 IDX Trading Bot")
st.caption("Dashboard harga, backtest, dan daily stock screener IDX.")
st.info("Versi publik untuk riset pribadi. Bukan rekomendasi beli/jual dan bukan sistem eksekusi order.")

# ===== SIDEBAR: DASHBOARD & BACKTEST =====
st.sidebar.header("Analisis Saham")

ticker_input = st.sidebar.text_input(
    "Kode saham IDX",
    value="BBCA",
    help="Contoh: BBCA, BBRI, TLKM, ASII",
)

period = st.sidebar.selectbox(
    "Periode data",
    ["1y", "2y", "5y", "10y"],
    index=2,
)

initial_cash = st.sidebar.number_input(
    "Modal awal (Rp)",
    min_value=1_000_000,
    value=100_000_000,
    step=1_000_000,
)

fast_period = st.sidebar.number_input(
    "SMA cepat",
    min_value=5,
    max_value=100,
    value=20,
)

slow_period = st.sidebar.number_input(
    "SMA lambat",
    min_value=10,
    max_value=300,
    value=50,
)

commission = st.sidebar.number_input(
    "Fee per transaksi (%)",
    min_value=0.0,
    value=0.25,
    step=0.01,
) / 100

ticker = f"{ticker_input.upper().strip()}.JK"


@st.cache_data(ttl=3600)
def get_stock_data(stock_ticker, selected_period):
    data = yf.download(
        stock_ticker,
        period=selected_period,
        auto_adjust=True,
        progress=False,
    )

    if getattr(data.columns, "nlevels", 1) > 1:
        data.columns = data.columns.get_level_values(0)

    return data.dropna()


def format_rupiah(value):
    return f"Rp {value:,.0f}"


@st.cache_data(ttl=300)
def load_screener_data(file_path, modified_time):
    """Muat hasil terbaru; modified_time membuat cache ikut berubah saat CSV diganti."""
    return pd.read_csv(file_path)


# ===== TAB UTAMA =====
tab1, tab2, tab3 = st.tabs([
    "Dashboard Harga",
    "Backtest",
    "Daily Screener",
])

# ===== AMBIL DATA HARGA =====
try:
    if fast_period >= slow_period:
        st.error("SMA cepat harus lebih kecil daripada SMA lambat.")
        st.stop()

    data = get_stock_data(ticker, period)

    if data.empty:
        st.error("Data tidak ditemukan. Periksa kembali kode sahamnya.")
        st.stop()

    data["SMA Fast"] = data["Close"].rolling(fast_period).mean()
    data["SMA Slow"] = data["Close"].rolling(slow_period).mean()

    data["Position"] = (data["SMA Fast"] > data["SMA Slow"]).astype(int)
    data["Stock Return"] = data["Close"].pct_change()

    data["Strategy Return"] = (
        data["Position"].shift(1) * data["Stock Return"]
    )

    data["Trade"] = data["Position"].diff().abs().fillna(0)

    data["Strategy Return Net"] = (
        data["Strategy Return"] - (data["Trade"] * commission)
    )

    data["Equity Strategy"] = initial_cash * (
        1 + data["Strategy Return Net"].fillna(0)
    ).cumprod()

    data["Equity Buy Hold"] = initial_cash * (
        1 + data["Stock Return"].fillna(0)
    ).cumprod()

    last_price = data["Close"].iloc[-1]
    daily_change = data["Close"].pct_change().iloc[-1] * 100

    final_value = data["Equity Strategy"].iloc[-1]
    buy_hold_value = data["Equity Buy Hold"].iloc[-1]

    strategy_return = ((final_value / initial_cash) - 1) * 100
    buy_hold_return = ((buy_hold_value / initial_cash) - 1) * 100

    running_max = data["Equity Strategy"].cummax()
    drawdown = (data["Equity Strategy"] / running_max - 1) * 100
    max_drawdown = drawdown.min()

    number_of_trades = int(data["Trade"].sum())

    current_signal = (
        "HOLD / TREN NAIK"
        if data["Position"].iloc[-1] == 1
        else "CASH / TREN TURUN"
    )

    # ===== TAB 1: DASHBOARD HARGA =====
    with tab1:
        col1, col2, col3, col4 = st.columns(4)

        col1.metric("Saham", ticker)
        col2.metric("Harga terakhir", format_rupiah(last_price))
        col3.metric("Perubahan harian", f"{daily_change:.2f}%")
        col4.metric("Sinyal saat ini", current_signal)

        fig_price = go.Figure()

        fig_price.add_trace(go.Candlestick(
            x=data.index,
            open=data["Open"],
            high=data["High"],
            low=data["Low"],
            close=data["Close"],
            name="Harga",
        ))

        fig_price.add_trace(go.Scatter(
            x=data.index,
            y=data["SMA Fast"],
            name=f"SMA {fast_period}",
            line=dict(color="orange"),
        ))

        fig_price.add_trace(go.Scatter(
            x=data.index,
            y=data["SMA Slow"],
            name=f"SMA {slow_period}",
            line=dict(color="blue"),
        ))

        fig_price.update_layout(
            title=f"Grafik {ticker}",
            xaxis_title="Tanggal",
            yaxis_title="Harga (Rp)",
            xaxis_rangeslider_visible=False,
            height=600,
        )

        st.plotly_chart(fig_price, use_container_width=True)

        st.subheader("Data harga terbaru")
        st.dataframe(data.tail(10), use_container_width=True)

    # ===== TAB 2: BACKTEST =====
    with tab2:
        st.subheader(f"Hasil Backtest: {ticker}")

        col1, col2, col3, col4 = st.columns(4)
        col1.metric("Modal awal", format_rupiah(initial_cash))
        col2.metric("Nilai akhir strategi", format_rupiah(final_value))
        col3.metric("Return strategi", f"{strategy_return:.2f}%")
        col4.metric("Return buy & hold", f"{buy_hold_return:.2f}%")

        col5, col6, col7 = st.columns(3)
        col5.metric("Max drawdown", f"{max_drawdown:.2f}%")
        col6.metric("Perubahan posisi", number_of_trades)
        col7.metric("Fee simulasi", f"{commission * 100:.2f}%")

        fig_equity = go.Figure()

        fig_equity.add_trace(go.Scatter(
            x=data.index,
            y=data["Equity Strategy"],
            name="Strategi SMA",
            line=dict(color="green"),
        ))

        fig_equity.add_trace(go.Scatter(
            x=data.index,
            y=data["Equity Buy Hold"],
            name="Buy & Hold",
            line=dict(color="gray", dash="dash"),
        ))

        fig_equity.update_layout(
            title="Perbandingan Nilai Portofolio",
            xaxis_title="Tanggal",
            yaxis_title="Nilai Portofolio (Rp)",
            height=500,
        )

        st.plotly_chart(fig_equity, use_container_width=True)

        st.warning(
            "Backtest ini masih simulasi sederhana. Belum memasukkan lot IDX, "
            "pajak, slippage, antrean order, dan kemungkinan order tidak terisi."
        )

except Exception as error:
    with tab1:
        st.error(f"Terjadi error saat mengambil data harga: {error}")


# ===== TAB 3: DAILY SCREENER =====
with tab3:
    st.subheader("🔎 Daily Stock Screener")
    st.caption(
        "Ranking kandidat dari file hasil_screener.csv. Price–Volume Flow bukan bukti bandar; "
        "Broker dan Foreign Flow hanya dihitung bila data CSV aslinya tersedia."
    )

    try:
        if not SCREENER_FILE.exists():
            raise FileNotFoundError

        modified_time = SCREENER_FILE.stat().st_mtime
        screener_data = load_screener_data(str(SCREENER_FILE), modified_time)
        updated_at = pd.Timestamp.fromtimestamp(modified_time).strftime("%d %b %Y, %H:%M")
        st.caption(f"Data screener terakhir diperbarui: {updated_at} (waktu server)")

        st.sidebar.header("Bobot Screener")

        fundamental_weight = st.sidebar.slider(
            "Fundamental (%)",
            min_value=0,
            max_value=100,
            value=15,
            key="fundamental_weight",
        )

        technical_weight = st.sidebar.slider(
            "Teknikal (%)",
            min_value=0,
            max_value=100,
            value=35,
            key="technical_weight",
        )

        pv_flow_weight = st.sidebar.slider(
            "Price–Volume Flow (%)",
            min_value=0,
            max_value=100,
            value=50,
            key="pv_flow_weight",
        )

        has_broker = "Broker Flow" in screener_data.columns and screener_data["Broker Flow"].notna().any()
        has_foreign = "Foreign Flow" in screener_data.columns and screener_data["Foreign Flow"].notna().any()
        broker_weight = st.sidebar.slider("Broker Flow (%)", 0, 100, 0, key="broker_weight", disabled=not has_broker)
        foreign_weight = st.sidebar.slider("Foreign Flow (%)", 0, 100, 0, key="foreign_weight", disabled=not has_foreign)

        total_weight = (
            fundamental_weight
            + technical_weight
            + pv_flow_weight
            + broker_weight
            + foreign_weight
        )

        if total_weight != 100:
            st.error(
                f"Total bobot harus tepat 100%. "
                f"Sekarang totalnya: {total_weight}%"
            )
            st.stop()

        screener_data["Skor Akhir Baru"] = (
            screener_data["Fundamental"] * fundamental_weight / 100
            + screener_data["Teknikal"] * technical_weight / 100
            + screener_data["Price-Volume Flow"] * pv_flow_weight / 100
            + screener_data["Broker Flow"].fillna(0) * broker_weight / 100
            + screener_data["Foreign Flow"].fillna(0) * foreign_weight / 100
        )

        screener_data = screener_data.sort_values(
            "Skor Akhir Baru",
            ascending=False,
        ).reset_index(drop=True)

        st.info(
            f"Bobot aktif — Fundamental {fundamental_weight}% | "
            f"Teknikal {technical_weight}% | "
            f"Price–Volume Flow {pv_flow_weight}% | Broker Flow {broker_weight}% | Foreign Flow {foreign_weight}%"
        )

        if not has_broker:
            st.info("Broker Flow belum aktif: masukkan broker_summary.csv. Sistem tidak menyimpulkan akumulasi bandar.")
        if not has_foreign:
            st.info("Foreign Flow belum aktif: masukkan foreign_flow.csv.")

        st.subheader("Top 5 Kandidat untuk Dipantau")

        for _, stock in screener_data.head(5).iterrows():
            with st.container(border=True):
                col1, col2, col3, col4, col5 = st.columns(5)

                col1.metric("Saham", stock["Ticker"])
                col2.metric(
                    "Harga terakhir",
                    f"Rp {stock['Harga Terakhir']:,.0f}",
                )
                col3.metric(
                    "Skor akhir",
                    f"{stock['Skor Akhir Baru']:.1f}/100",
                )
                col4.metric("RSI", stock["RSI"])
                col5.metric("Rata-rata transaksi 20H", f"Rp {stock['Rata2 Nilai Transaksi 20H']:,.0f}")

                st.write(f"**Alasan:** {stock['Alasan']}")
                st.caption(
                    f"Fundamental: {stock['Fundamental']:.0f} | "
                    f"Teknikal: {stock['Teknikal']:.0f} | "
                        f"Price–Volume Flow: {stock['Price-Volume Flow']:.0f} | "
                        f"Broker Flow: {stock['Broker Flow'] if pd.notna(stock['Broker Flow']) else 'N/A'} | "
                        f"Foreign Flow: {stock['Foreign Flow'] if pd.notna(stock['Foreign Flow']) else 'N/A'} | "
                    f"Relative volume: {stock['Rel. Volume']:.2f}x"
                )

        st.subheader("Ranking Lengkap")

        display_columns = [
            "Ticker",
            "Harga Terakhir",
            "RSI",
            "Rel. Volume",
            "Fundamental",
            "Teknikal",
                "Rata2 Nilai Transaksi 20H",
                "Price-Volume Flow",
                "Broker Flow",
                "Foreign Flow",
                "Status Broker",
                "Status Foreign",
            "Skor Akhir Baru",
            "Alasan",
        ]

        st.dataframe(
            screener_data[display_columns],
            use_container_width=True,
        )

        csv_download = screener_data.to_csv(index=False).encode("utf-8")

        st.download_button(
            label="⬇️ Download ranking",
            data=csv_download,
            file_name="ranking_screener_idx.csv",
            mime="text/csv",
        )

        st.warning(
            "Screener ini adalah alat seleksi awal, bukan jaminan saham naik "
            "besok. Gunakan bersama level beli, target profit, dan cut loss."
        )

    except FileNotFoundError:
        st.error(
            "File hasil_screener.csv belum ditemukan. "
            "Jalankan `python screener.py` terlebih dahulu."
        )
    except Exception as error:
        st.error(f"Terjadi error saat membaca screener: {error}")
