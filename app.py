import pandas as pd
import streamlit as st
import yfinance as yf
import plotly.graph_objects as go
from pathlib import Path
from threading import Lock
import screener as screener_engine

st.set_page_config(page_title="IDX Trading Bot", layout="wide")

BASE_DIR = Path(__file__).resolve().parent
SCREENER_FILE = BASE_DIR / "hasil_screener.csv"
SCREENER_REFRESH_LOCK = Lock()

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


@st.cache_data(ttl=3600, show_spinner=False)
def get_liquidity_history(tickers):
    """Ambil harga dan volume harian untuk menghitung likuiditas historis."""
    data = yf.download(
        list(tickers),
        period="2y",
        auto_adjust=True,
        progress=False,
        group_by="column",
        threads=True,
    )
    if data.empty:
        return pd.DataFrame(), pd.DataFrame()

    # Hasil yfinance multi-ticker berbentuk kolom bertingkat: harga lalu ticker.
    if getattr(data.columns, "nlevels", 1) > 1:
        close = data["Close"].copy()
        volume = data["Volume"].copy()
    else:
        ticker_name = str(tickers[0]).replace(".JK", "")
        close = data[["Close"]].rename(columns={"Close": ticker_name})
        volume = data[["Volume"]].rename(columns={"Volume": ticker_name})

    close.columns = [str(column).replace(".JK", "") for column in close.columns]
    volume.columns = [str(column).replace(".JK", "") for column in volume.columns]
    return close.dropna(axis=1, how="all"), volume.dropna(axis=1, how="all")


def calculate_liquidity_table(close, volume, selected_date, window_days):
    """Hitung likuiditas hingga tanggal pilihan tanpa memakai data sesudahnya."""
    end_timestamp = pd.Timestamp(selected_date)
    close = close.loc[:end_timestamp]
    volume = volume.loc[:end_timestamp]
    rows = []

    for stock_ticker in close.columns:
        prices = close[stock_ticker].dropna().tail(window_days)
        traded_volume = volume[stock_ticker].reindex(prices.index).fillna(0)
        if len(prices) < window_days:
            continue

        transaction_value = prices * traded_volume
        active_days = int((traded_volume > 0).sum())
        rows.append({
            "Ticker": stock_ticker,
            "Harga pada tanggal pilihan": prices.iloc[-1],
            "Nilai transaksi hari terakhir": transaction_value.iloc[-1],
            "Rata-rata nilai transaksi": transaction_value.mean(),
            "Rata-rata volume": traded_volume.mean(),
            "Hari aktif": active_days,
            "Aktivitas perdagangan": active_days / window_days,
        })

    return pd.DataFrame(rows).sort_values("Rata-rata nilai transaksi", ascending=False)


# ===== TAB UTAMA =====
tab1, tab2, tab3, tab4 = st.tabs([
    "Dashboard Harga",
    "Backtest",
    "Daily Screener",
    "Likuiditas Saham",
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
        "Tekan tombol untuk mengambil data terbaru dan menghitung ranking. Price–Volume Flow bukan bukti bandar; "
        "Broker dan Foreign Flow hanya dihitung bila data CSV aslinya tersedia."
    )

    refresh_column, status_column = st.columns([1, 3])
    with refresh_column:
        refresh_requested = st.button(
            "🔄 Refresh data screener",
            type="primary",
            help="Mengambil harga terbaru lalu menghitung ulang seluruh ranking.",
        )

    if refresh_requested:
        if not SCREENER_REFRESH_LOCK.acquire(blocking=False):
            st.warning("Refresh sedang dijalankan oleh pengguna lain. Tunggu sebentar lalu buka ulang halaman ini.")
        else:
            try:
                with st.spinner("Mengambil data harga dan menghitung ranking. Proses ini dapat memerlukan 1–3 menit..."):
                    refreshed_data = screener_engine.run_screener()
                st.cache_data.clear()
                st.session_state["screener_refreshed_at"] = pd.Timestamp.now()
                if refreshed_data.empty:
                    st.warning("Refresh selesai, tetapi belum ada saham yang lolos filter hari ini.")
                else:
                    st.success(f"Refresh selesai: {len(refreshed_data)} saham lolos filter.")
            except Exception as error:
                st.error(f"Refresh gagal. Hasil terakhir tetap dipertahankan. Detail: {error}")
            finally:
                SCREENER_REFRESH_LOCK.release()

    try:
        if not SCREENER_FILE.exists():
            raise FileNotFoundError

        modified_time = SCREENER_FILE.stat().st_mtime
        screener_data = load_screener_data(str(SCREENER_FILE), modified_time)
        updated_at = pd.Timestamp.fromtimestamp(modified_time).strftime("%d %b %Y, %H:%M")
        status_column.caption(f"Data terakhir diperbarui: {updated_at} (waktu server)")

        if screener_data.empty:
            st.warning("Data berhasil diperbarui, tetapi tidak ada saham yang lolos filter saat ini.")
            st.stop()

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
            "Tekan tombol **Refresh data screener** di atas."
        )
    except Exception as error:
        st.error(f"Terjadi error saat membaca screener: {error}")


# ===== TAB 4: LIKUIDITAS SAHAM =====
with tab4:
    st.subheader("💧 Dashboard Likuiditas Saham IDX")
    st.caption(
        "Likuiditas diukur dari nilai transaksi (harga penutupan × volume), volume, "
        "dan jumlah hari aktif. Semua angka dihitung hanya sampai tanggal yang kamu pilih."
    )
    st.info(
        "Catatan: data harga harian belum mempunyai jumlah transaksi/order sebenarnya. "
        "Jadi ‘hari aktif’ berarti hari dengan volume perdagangan, bukan jumlah frekuensi transaksi intraday."
    )

    period_choice = st.selectbox(
        "Periode rata-rata",
        ["1 hari", "1 minggu (5 hari bursa)", "1 bulan (20 hari bursa)"],
        index=2,
        key="liquidity_period",
    )
    window_map = {
        "1 hari": 1,
        "1 minggu (5 hari bursa)": 5,
        "1 bulan (20 hari bursa)": 20,
    }
    window_days = window_map[period_choice]

    minimum_value = st.number_input(
        "Minimal rata-rata nilai transaksi (Rp)",
        min_value=0,
        value=3_000_000_000,
        step=500_000_000,
        help="Contoh Rp3 miliar untuk menampilkan saham yang cukup mudah masuk dan keluar.",
        key="liquidity_minimum_value",
    )

    liquidity_button = st.button(
        "🔄 Ambil / refresh data likuiditas",
        type="primary",
        key="refresh_liquidity",
    )

    # Data disimpan di session agar perubahan tanggal/periode tidak mengunduh ulang.
    if liquidity_button or "liquidity_close" not in st.session_state:
        try:
            liquidity_universe = tuple(screener_engine.load_universe())
            with st.spinner("Mengambil harga dan volume historis saham IDX. Pertama kali dapat memerlukan 1–3 menit..."):
                close_prices, trading_volumes = get_liquidity_history(liquidity_universe)
            if close_prices.empty:
                st.error("Data likuiditas tidak berhasil diambil. Coba tekan tombol refresh lagi.")
            else:
                st.session_state["liquidity_close"] = close_prices
                st.session_state["liquidity_volume"] = trading_volumes
                st.success(f"Data siap: {len(close_prices.columns)} saham dengan riwayat harga tersedia.")
        except Exception as error:
            st.error(f"Gagal mengambil data likuiditas: {error}")

    if "liquidity_close" in st.session_state:
        close_prices = st.session_state["liquidity_close"]
        trading_volumes = st.session_state["liquidity_volume"]
        available_dates = close_prices.dropna(how="all").index

        if len(available_dates) == 0:
            st.warning("Belum ada tanggal perdagangan yang tersedia.")
        else:
            selected_date = st.select_slider(
                "Tanggal analisis",
                options=list(available_dates),
                value=available_dates[-1],
                format_func=lambda value: pd.Timestamp(value).strftime("%d %b %Y"),
                key="liquidity_date",
            )
            liquidity_table = calculate_liquidity_table(
                close_prices, trading_volumes, selected_date, window_days
            )
            liquid_stocks = liquidity_table[
                liquidity_table["Rata-rata nilai transaksi"] >= minimum_value
            ].copy()

            selected_label = pd.Timestamp(selected_date).strftime("%d %b %Y")
            metric_1, metric_2, metric_3 = st.columns(3)
            metric_1.metric("Saham yang lolos", len(liquid_stocks))
            metric_2.metric("Periode", period_choice)
            metric_3.metric("Tanggal analisis", selected_label)

            if liquid_stocks.empty:
                st.warning("Tidak ada saham yang lolos batas nilai transaksi pada pilihan ini. Turunkan nilai minimalnya.")
            else:
                st.subheader("Daftar saham likuid")
                display_liquidity = liquid_stocks.copy()
                display_liquidity["Harga pada tanggal pilihan"] = display_liquidity["Harga pada tanggal pilihan"].map(format_rupiah)
                display_liquidity["Nilai transaksi hari terakhir"] = display_liquidity["Nilai transaksi hari terakhir"].map(format_rupiah)
                display_liquidity["Rata-rata nilai transaksi"] = display_liquidity["Rata-rata nilai transaksi"].map(format_rupiah)
                display_liquidity["Rata-rata volume"] = display_liquidity["Rata-rata volume"].map(lambda value: f"{value:,.0f}")
                display_liquidity["Aktivitas perdagangan"] = display_liquidity["Aktivitas perdagangan"].map(lambda value: f"{value:.0%}")
                st.dataframe(display_liquidity, use_container_width=True, hide_index=True)

                top_liquid = liquid_stocks.head(15).sort_values("Rata-rata nilai transaksi")
                figure = go.Figure(go.Bar(
                    x=top_liquid["Rata-rata nilai transaksi"] / 1_000_000_000,
                    y=top_liquid["Ticker"],
                    orientation="h",
                    marker_color="#16a085",
                ))
                figure.update_layout(
                    title=f"Top 15 berdasarkan rata-rata nilai transaksi — {period_choice}",
                    xaxis_title="Rata-rata nilai transaksi (Rp miliar)",
                    yaxis_title="Ticker",
                    height=520,
                )
                st.plotly_chart(figure, use_container_width=True)

                st.download_button(
                    "⬇️ Download daftar likuiditas",
                    data=liquid_stocks.to_csv(index=False).encode("utf-8"),
                    file_name=f"likuiditas_idx_{pd.Timestamp(selected_date).strftime('%Y%m%d')}_{window_days}h.csv",
                    mime="text/csv",
                )
