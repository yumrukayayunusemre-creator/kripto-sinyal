# 📈 Kripto Sinyal Botu

Binance'teki **bütün USDT paritelerini** (24s hacmi 3 milyon $ üstü olanlar) 15 dakikalık mumlarla, 15 dakikada bir tarar, 7 teknik stratejiyi çalıştırır ve en az birkaç strateji aynı yönü gösterdiğinde **Telegram'a AL/SAT bildirimi** gönderir. GitHub Actions üzerinde **ücretsiz** çalışır, yani bilgisayarının açık olması gerekmez.

## Stratejiler

| Strateji | AL sinyali | SAT sinyali |
|---|---|---|
| RSI dönüşü | RSI 30'un altından yukarı çıkar | RSI 70'in üstünden aşağı iner |
| EMA kesişimi | EMA9, EMA21'i yukarı keser | EMA9, EMA21'i aşağı keser |
| Bollinger + hacim | Üst bant **hacimle** kırılır | Alt bant **hacimle** kırılır |
| MACD kesişimi | MACD sinyal çizgisini yukarı keser | MACD sinyal çizgisini aşağı keser |
| Supertrend | Trend yukarı döner | Trend aşağı döner |
| Stochastic RSI | %K, %D'yi 20'nin altında yukarı keser | %K, %D'yi 80'in üstünde aşağı keser |
| Donchian kırılımı | 20 mumun zirvesi kırılır | 20 mumun dibi kırılır |

**Puanlama:** Her strateji +1 ya da −1 oy verir. Son 2 mumdaki oyların toplamı **≥ +3** olursa AL, **≤ −3** olursa SAT bildirimi gelir. Bunun üstüne bir trend filtresi uygulanır: fiyat EMA200'ün altındayken AL sinyali, üstündeyken SAT sinyali gönderilmez. Bir taramada 5'ten fazla sinyal çıkarsa hepsi **tek bir özet mesajda** gelir. Bütün ayarlar `config.yaml` dosyasında: sadece belirli coinleri taramak için `symbols: [BTCUSDT, ETHUSDT]` yazabilir, hacim filtresini `universe.min_quote_volume` ile değiştirebilirsin.

---

## Kurulum (yaklaşık 15 dakika)

### 1) Telegram botunu oluştur
1. Telegram'da **@BotFather** hesabına `/newbot` yaz, bota bir isim ver. Sana bir **token** verecek (`123456:ABC...` gibi).
2. Yeni botuna Telegram'dan herhangi bir mesaj gönder (ör. "merhaba").
3. Tarayıcıda şu adresi aç: `https://api.telegram.org/bot<TOKEN>/getUpdates`
   Açılan sayfada `"chat":{"id": 123456789` kısmındaki sayı senin **chat id**'n.

### 2) GitHub'a yükle
1. github.com'da yeni bir **private** repo aç (ör. `kripto-sinyal`).
2. Bu klasördeki bütün dosyaları repoya yükle. Gizli bir klasör olan `.github/workflows/scan.yml` de buna dahil.
   *Web'den yüklerken:* "Add file → Upload files" ile klasörü sürükleyip bırak.
3. Repoda **Settings → Secrets and variables → Actions → New repository secret** yoluna gidip iki secret ekle:
   - `TELEGRAM_TOKEN` → BotFather'ın verdiği token
   - `TELEGRAM_CHAT_ID` → chat id'n
4. **Settings → Actions → General → Workflow permissions** altında **Read and write permissions** seçeneğini işaretle.

### 3) Çalıştır
**Actions** sekmesine git, "Kripto sinyal taraması" iş akışını seç ve **Run workflow** butonuna bas. Loglarda her coinin puanını görürsün. Bundan sonra bot 15 dakikada bir kendiliğinden çalışır.

> GitHub zamanlanmış işleri yoğun saatlerde 5–15 dakika gecikmeyle başlatabilir. Bot sadece kapanmış mumlara baktığı için gecikme sinyali bozmaz, sadece biraz geç gelmesine yol açar.
> Repoda 60 gün boyunca hiç değişiklik olmazsa GitHub zamanlanmış işleri durdurur. Bot `state.json` dosyasını güncellediği için bu genelde olmaz.

---

## Stratejileri karşılaştır (backtest)

Kendi bilgisayarında çalıştır:

```bash
pip install -r requirements.txt
python backtest.py                  # 1h, son 2000 mum
python backtest.py --tf 4h --candles 3000
```

Her coin için her stratejinin **işlem sayısı, kazanma oranı, toplam getiri, maksimum düşüş ve kâr faktörü** hesaplanır. Sonuçlar "Al ve tut" ile de karşılaştırılır ve `backtest_rapor.html` dosyasına yazılır.
Sonuçlara göre `config.yaml` içinde kötü giden stratejileri kapatabilir (`enabled: false`), iyi gidenlerin `weight` değerini artırabilirsin.

Kendi bilgisayarında Telegram'ı test etmek için:
```bash
export TELEGRAM_TOKEN=...  TELEGRAM_CHAT_ID=...     # Windows: set TELEGRAM_TOKEN=...
python main.py --test
```

## Sinyal kayıtları
Her taramadaki bütün sinyaller `kayitlar/` klasörüne aylık CSV olarak yazılır (Excel ile açılabilir):
- `sinyaller_YYYY-AA.csv` — puan eşiğini geçen **bütün** sinyaller: coin, yön, puan, fiyat, RSI, ATR, örnek stop/hedef, tetikleyen stratejiler ve Telegram'a bildirilip bildirilmediği (bekleme süresi yüzünden gönderilmeyenler de kaydedilir).
- `strateji_sinyalleri_YYYY-AA.csv` — puan eşiğine bakmadan, **her stratejinin tek tek** verdiği her sinyal.

## Dosyalar
- `config.yaml` — coinler, periyot, strateji ayarları, puan eşiği
- `strategies.py` / `indicators.py` — stratejiler ve göstergeler (yeni strateji eklemek kolay)
- `data.py` — Binance ve OKX herkese açık fiyat verisi (API anahtarı gerekmez)
- `main.py` — canlı tarama ve bildirim
- `backtest.py` — strateji karşılaştırması
- `.github/workflows/scan.yml` — 15 dakikalık otomatik çalışma

## ⚠️ Önemli
Bu bot sadece teknik göstergelere bakarak **otomatik sinyal** üretir. Yatırım tavsiyesi değildir ve kâr garantisi vermez. Kripto piyasası çok oynaktır. Gerçek parayla işlem açmadan önce backtest sonuçlarına bak ve sinyalleri bir süre sadece izle.
