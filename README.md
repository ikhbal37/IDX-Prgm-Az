# IDX Trading Bot

Web dashboard Streamlit untuk melihat harga IDX, simulasi strategi SMA, dan ranking hasil screener.

## Menjalankan di komputer sendiri

```bash
pip install -r requirements.txt
streamlit run app.py
```

Lalu buka alamat yang muncul, biasanya `http://localhost:8501`.

## Memperbarui hasil screener

Di halaman **Daily Screener**, tekan tombol **Refresh data screener**. Server
akan mengambil harga terbaru dan menghitung ulang ranking; tidak perlu
menjalankan `python screener.py` atau mengunggah CSV secara manual.

## Deploy sebagai web publik

1. Upload seluruh isi folder ini ke sebuah repository GitHub baru.
2. Buka [Streamlit Community Cloud](https://share.streamlit.io/), login dengan GitHub, lalu pilih **Create app**.
3. Pilih repository tersebut, branch `main`, dan isi **Main file path** dengan `app.py`.
4. Klik **Deploy**. Setelah selesai, Streamlit memberi URL yang dapat dibuka dari laptop atau HP.

## Batasan penting

- Halaman publik berarti file `hasil_screener.csv` dan kode dapat diakses oleh pengunjung repository publik. Jangan simpan API key atau data pribadi di repository.
- Tombol refresh dijalankan manual oleh pengunjung. Untuk pembaruan otomatis
  setiap hari, tahap berikutnya adalah menambahkan scheduler/server khusus.
- Backtest adalah simulasi sederhana dan bukan rekomendasi investasi.
