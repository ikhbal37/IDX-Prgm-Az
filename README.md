# IDX Trading Bot

Web dashboard Streamlit untuk melihat harga IDX, simulasi strategi SMA, dan ranking hasil screener.

## Menjalankan di komputer sendiri

```bash
pip install -r requirements.txt
streamlit run app.py
```

Lalu buka alamat yang muncul, biasanya `http://localhost:8501`.

## Memperbarui hasil screener

```bash
python screener.py
```

Perintah tersebut memperbarui `hasil_screener.csv`. Refresh halaman dashboard setelah proses selesai.

## Deploy sebagai web publik

1. Upload seluruh isi folder ini ke sebuah repository GitHub baru.
2. Buka [Streamlit Community Cloud](https://share.streamlit.io/), login dengan GitHub, lalu pilih **Create app**.
3. Pilih repository tersebut, branch `main`, dan isi **Main file path** dengan `app.py`.
4. Klik **Deploy**. Setelah selesai, Streamlit memberi URL yang dapat dibuka dari laptop atau HP.

## Batasan penting

- Halaman publik berarti file `hasil_screener.csv` dan kode dapat diakses oleh pengunjung repository publik. Jangan simpan API key atau data pribadi di repository.
- Screener tidak otomatis berjalan setiap hari di Streamlit Community Cloud. Jalankan `python screener.py` di komputer, lalu upload hasil CSV terbaru ke GitHub; atau nanti kita tambahkan penjadwalan dan database.
- Backtest adalah simulasi sederhana dan bukan rekomendasi investasi.
