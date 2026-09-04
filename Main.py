import os
import threading
import requests
from flask import Flask
import telebot
from telebot import types

# =========================
# مفاتيح سرية من Render
# =========================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
TWELVE_DATA_KEY = os.getenv("TWELVE_DATA_KEY")

if not TELEGRAM_TOKEN:
    raise RuntimeError("TELEGRAM_TOKEN غير موجود")

if not TWELVE_DATA_KEY:
    raise RuntimeError("TWELVE_DATA_KEY غير موجود")

bot = telebot.TeleBot(TELEGRAM_TOKEN)
app = Flask(__name__)


# =========================
# حساب EMA
# =========================
def ema(values, period):
    if len(values) < period:
        return None

    multiplier = 2 / (period + 1)
    result = sum(values[:period]) / period

    for price in values[period:]:
        result = (price - result) * multiplier + result

    return result


# =========================
# حساب RSI
# =========================
def rsi(values, period=14):
    if len(values) < period + 1:
        return None

    gains = []
    losses = []

    for i in range(1, len(values)):
        change = values[i] - values[i - 1]

        if change > 0:
            gains.append(change)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(change))

    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period

    for i in range(period, len(gains)):
        avg_gain = ((avg_gain * (period - 1)) + gains[i]) / period
        avg_loss = ((avg_loss * (period - 1)) + losses[i]) / period

    if avg_loss == 0:
        return 100

    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


# =========================
# جلب بيانات Twelve Data
# =========================
def get_prices(symbol):
    url = "https://api.twelvedata.com/time_series"

    params = {
        "symbol": symbol,
        "interval": "1min",
        "outputsize": 100,
        "apikey": TWELVE_DATA_KEY
    }

    response = requests.get(url, params=params, timeout=15)
    data = response.json()

    if "values" not in data:
        error = data.get("message", "خطأ غير معروف")
        raise Exception(error)

    # Twelve Data يرجع الأحدث أولًا
    values = list(reversed(data["values"]))

    closes = [float(x["close"]) for x in values]

    return closes


# =========================
# إنشاء التحليل
# =========================
def analyze(symbol):

    prices = get_prices(symbol)

    if len(prices) < 30:
        raise Exception("عدد البيانات غير كافٍ للتحليل")

    current_price = prices[-1]

    ema9 = ema(prices, 9)
    ema21 = ema(prices, 21)
    rsi_value = rsi(prices, 14)

    score = 0

    # EMA
    if ema9 > ema21:
        score += 1
    elif ema9 < ema21:
        score -= 1

    # السعر مقابل EMA21
    if current_price > ema21:
        score += 1
    elif current_price < ema21:
        score -= 1

    # RSI
    if rsi_value > 55:
        score += 1
    elif rsi_value < 45:
        score -= 1

    if score >= 2:
        signal = "📈 صاعد"
        strength = "قوي"
    elif score <= -2:
        signal = "📉 هابط"
        strength = "قوي"
    else:
        signal = "⚪ محايد"
        strength = "ضعيف / غير واضح"

    return (
        f"📊 تحليل {symbol}\n\n"
        f"💰 السعر: {current_price}\n"
        f"📈 EMA 9: {ema9:.5f}\n"
        f"📉 EMA 21: {ema21:.5f}\n"
        f"📊 RSI: {rsi_value:.2f}\n\n"
        f"🔎 الاتجاه: {signal}\n"
        f"💪 القوة: {strength}\n\n"
        f"⏱️ الإطار: 1 دقيقة\n\n"
        f"⚠️ هذا تحليل مؤشرات احتمالي وليس ضمانًا للربح."
    )


# =========================
# /start
# =========================
@bot.message_handler(commands=["start"])
def start(message):

    markup = types.InlineKeyboardMarkup(row_width=2)

    markup.add(
        types.InlineKeyboardButton(
            "🇪🇺 EUR/USD",
            callback_data="EUR/USD"
        ),
        types.InlineKeyboardButton(
            "🇬🇧 GBP/USD",
            callback_data="GBP/USD"
        ),
        types.InlineKeyboardButton(
            "🇯🇵 USD/JPY",
            callback_data="USD/JPY"
        )
    )

    bot.send_message(
        message.chat.id,
        "🤖 أهلاً بك في بوت التحليل.\n\n"
        "اختر زوج العملات للحصول على تحليل:\n\n"
        "📊 EMA\n"
        "📈 RSI\n"
        "⏱️ بيانات 1 دقيقة",
        reply_markup=markup
    )


# =========================
# عند اختيار الزوج
# =========================
@bot.callback_query_handler(func=lambda call: True)
def callback(call):

    symbol = call.data

    bot.answer_callback_query(
        call.id,
        "⏳ جاري تحليل السوق..."
    )

    try:
        result = analyze(symbol)

        bot.send_message(
            call.message.chat.id,
            result
        )

    except Exception as e:

        bot.send_message(
            call.message.chat.id,
            "❌ تعذر الحصول على البيانات.\n\n"
            f"السبب: {str(e)}"
        )


# =========================
# Health Check لـ Render
# =========================
@app.route("/")
def home():
    return "Quotex Analyzer Bot is running."


# =========================
# تشغيل Telegram
# =========================
def run_bot():
    print("Telegram bot started...")
    bot.infinity_polling(
        timeout=30,
        long_polling_timeout=30
    )


# =========================
# التشغيل
# =========================
if __name__ == "__main__":

    thread = threading.Thread(
        target=run_bot,
        daemon=True
    )

    thread.start()

    port = int(os.environ.get("PORT", 10000))

    app.run(
        host="0.0.0.0",
        port=port
  )
