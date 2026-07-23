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

## Mengaktifkan pesan Telegram test di dashboard

1. Di Streamlit Community Cloud buka aplikasi → **Settings** → **Secrets**.
2. Tempel konfigurasi berikut dan ganti token dengan token asli dari BotFather:

```toml
[telegram]
bot_token = "TOKEN_BOTFATHER"
chat_id = "5382030486"
```

3. Simpan lalu reboot aplikasi.
4. Buka tab **Notifikasi Telegram** dan tekan **Kirim test Telegram**.

Token tidak boleh dimasukkan ke `app.py`, GitHub, atau chat.

## Mengaktifkan alert otomatis tiap 30 menit

Tombol dashboard hanya bisa mengirim saat dashboard dibuka. Agar robot tetap
berjalan saat web ditutup, proyek ini memakai GitHub Actions.

1. Upload `alert_engine.py` dan folder `.github/workflows` ke repo GitHub yang sama.
2. Buka repo GitHub → **Settings → Secrets and variables → Actions**.
3. Tambahkan dua **repository secrets** (jangan gunakan Secrets Streamlit):

```text
TELEGRAM_BOT_TOKEN = token asli dari BotFather
TELEGRAM_CHAT_ID = chat ID dari chat pribadi dengan bot
```

4. Buka tab **Actions**, pilih workflow **IDX intraday Telegram alert**, lalu
   tekan **Run workflow** sebagai uji pertama.

Workflow mencoba cek setiap 30 menit pada 09:00–15:30 WIB, Senin–Jumat. Ia
hanya mengirim alert bila candle selesai memenuhi aturan, lalu menyimpan status
agar ticker yang sama tidak mengirim alert dengan arah sama lebih dari sekali
per hari.

Yahoo Finance dapat terlambat atau tidak menyediakan candle pada sebagian
saham. Karena itu alert adalah indikator riset, bukan data real-time bursa atau
rekomendasi transaksi.

## Batasan penting

- Halaman publik berarti file `hasil_screener.csv` dan kode dapat diakses oleh pengunjung repository publik. Jangan simpan API key atau data pribadi di repository.
- Tombol refresh dijalankan manual oleh pengunjung. Untuk pembaruan otomatis
  setiap hari, tahap berikutnya adalah menambahkan scheduler/server khusus.
- Backtest adalah simulasi sederhana dan bukan rekomendasi investasi.
