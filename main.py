import os
import sys
import json
import logging
import asyncio
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from dotenv import load_dotenv

# ============================================
# KONFIGURASI
# ============================================
load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN tidak ditemukan!")

CHANNEL_ID = os.getenv('CHANNEL_ID', '')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
PORT = int(os.getenv('PORT', 8080))

# Daftar saham default
DEFAULT_WATCHLIST = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'UNVR', 'GOTO', 'ANTM', 'INDF']
WATCHLIST = [s.strip() for s in os.getenv('WATCHLIST', '').split(',') if s.strip()] or DEFAULT_WATCHLIST

# Threshold
VOLUME_THRESHOLD = float(os.getenv('VOLUME_THRESHOLD', '1.5'))

# Setup logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[logging.StreamHandler(sys.stdout)]
)
logger = logging.getLogger(__name__)

# Nama perusahaan
COMPANY_NAMES = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'TLKM': 'Telkom Indonesia',
    'ASII': 'Astra International',
    'UNVR': 'Unilever Indonesia',
    'GOTO': 'GoTo Gojek Tokopedia',
    'ANTM': 'Aneka Tambang',
    'INDF': 'Indofood'
}

# ============================================
# FUNGSI UTILITY
# ============================================
def format_price(price):
    return f"Rp{price:,.0f}".replace(',', '.')

def format_volume(volume):
    if volume >= 1e9:
        return f"{volume/1e9:.2f}B"
    elif volume >= 1e6:
        return f"{volume/1e6:.2f}M"
    elif volume >= 1e3:
        return f"{volume/1e3:.2f}K"
    else:
        return f"{volume:.0f}"

def is_valid_symbol(symbol):
    return len(symbol) >= 3 and symbol.isalpha() and symbol.isupper()

def safe_json_load(filepath, default=None):
    try:
        with open(filepath, 'r') as f:
            return json.load(f)
    except:
        return default or {}

def safe_json_save(filepath, data):
    try:
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
            return True
    except:
        return False

# ============================================
# SCREENER (Data & Analisis)
# ============================================
class Screener:
    def __init__(self):
        self.cache_dir = 'data'
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'stock_cache.json')
        self.cache = safe_json_load(self.cache_file, {})
        self.watchlist = WATCHLIST

    def save_cache(self):
        safe_json_save(self.cache_file, self.cache)

    def get_stock_data(self, symbol, period='1mo'):
        cache_key = f"{symbol}_{period}"
        
        # Cek cache (5 menit)
        if cache_key in self.cache:
            cache_time = self.cache[cache_key].get('timestamp', '')
            if cache_time:
                cache_date = datetime.fromisoformat(cache_time)
                if (datetime.now() - cache_date) < timedelta(minutes=5):
                    logger.info(f"Using cached data for {symbol}")
                    data_dict = self.cache[cache_key]['data']
                    return pd.DataFrame(data_dict)

        try:
            ticker = yf.Ticker(f"{symbol}.JK")
            data = ticker.history(period=period)
            
            if data.empty:
                logger.warning(f"Data kosong untuk {symbol}")
                return None

            # Simpan cache
            self.cache[cache_key] = {
                'timestamp': datetime.now().isoformat(),
                'data': data.to_dict('list')
            }
            self.save_cache()
            return data
            
        except Exception as e:
            logger.error(f"Error mengambil data {symbol}: {str(e)}")
            return None

    def calculate_indicators(self, data):
        if data is None or len(data) < 20:
            return None

        try:
            # RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))

            # Moving Averages
            ma20 = data['Close'].rolling(window=20).mean()
            ma50 = data['Close'].rolling(window=50).mean() if len(data) >= 50 else data['Close'].rolling(window=20).mean()

            # Volume
            avg_volume = data['Volume'].rolling(window=20).mean()
            volume_ratio = data['Volume'].iloc[-1] / avg_volume.iloc[-1] if avg_volume.iloc[-1] > 0 else 0

            # Price change
            change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100 if len(data) > 1 else 0

            return {
                'price': data['Close'].iloc[-1],
                'change': change,
                'volume': data['Volume'].iloc[-1],
                'volume_ratio': volume_ratio,
                'rsi': rsi.iloc[-1] if len(rsi) > 0 else 50,
                'ma20': ma20.iloc[-1] if len(ma20) > 0 else data['Close'].iloc[-1],
                'ma50': ma50.iloc[-1] if len(ma50) > 0 else data['Close'].iloc[-1],
                'high': data['High'].iloc[-1],
                'low': data['Low'].iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def screen_all(self):
        results = []
        for symbol in self.watchlist:
            try:
                data = self.get_stock_data(symbol)
                if data is None:
                    continue
                    
                ind = self.calculate_indicators(data)
                if ind is None:
                    continue

                score = 0
                if ind['rsi'] < 30:
                    score += 2
                elif ind['rsi'] > 70:
                    score -= 1
                if ind['volume_ratio'] > VOLUME_THRESHOLD:
                    score += 2
                if ind['price'] > ind['ma20']:
                    score += 1
                if ind['price'] > ind['ma50']:
                    score += 1
                if ind['change'] > 2:
                    score += 1
                elif ind['change'] < -2:
                    score -= 1

                results.append({
                    'symbol': symbol,
                    'company': COMPANY_NAMES.get(symbol, symbol),
                    'price': ind['price'],
                    'change': ind['change'],
                    'volume': ind['volume'],
                    'rsi': ind['rsi'],
                    'score': score
                })
            except Exception as e:
                logger.error(f"Error screening {symbol}: {str(e)}")
                continue

        results.sort(key=lambda x: x['score'], reverse=True)
        return results

    def get_latest_price(self, symbol):
        data = self.get_stock_data(symbol, period='5d')
        if data is None:
            return None
        ind = self.calculate_indicators(data)
        if ind is None:
            return None
        return {
            'price': ind['price'],
            'change': ind['change'],
            'volume': ind['volume']
        }

    def get_top_by_volume(self, limit=5):
        results = []
        for symbol in self.watchlist:
            try:
                data = self.get_stock_data(symbol, period='5d')
                if data is None:
                    continue
                ind = self.calculate_indicators(data)
                if ind is None:
                    continue
                results.append({
                    'symbol': symbol,
                    'price': ind['price'],
                    'change': ind['change'],
                    'volume': ind['volume']
                })
            except:
                continue
        results.sort(key=lambda x: x['volume'], reverse=True)
        return results[:limit]

# ============================================
# SIGNAL GENERATOR
# ============================================
class SignalGenerator:
    def __init__(self):
        self.screener = Screener()

    def generate_signal(self, symbol):
        data = self.screener.get_stock_data(symbol)
        if data is None:
            return None

        ind = self.screener.calculate_indicators(data)
        if ind is None:
            return None

        signal = 'HOLD'
        reasons = []

        # RSI
        if ind['rsi'] < 30:
            signal = 'BUY'
            reasons.append(f'RSI oversold ({ind["rsi"]:.1f})')
        elif ind['rsi'] > 70:
            signal = 'SELL'
            reasons.append(f'RSI overbought ({ind["rsi"]:.1f})')

        # MA Crossover
        if ind['ma20'] > ind['ma50'] and ind['price'] > ind['ma20']:
            if signal == 'HOLD':
                signal = 'BUY'
            reasons.append('Golden cross')
        elif ind['ma20'] < ind['ma50'] and ind['price'] < ind['ma20']:
            if signal == 'HOLD':
                signal = 'SELL'
            reasons.append('Death cross')

        # Volume
        if ind['volume_ratio'] > 2:
            if signal == 'HOLD':
                signal = 'BUY' if ind['change'] > 0 else 'SELL'
            reasons.append(f'Volume tinggi ({ind["volume_ratio"]:.1f}x)')

        return {
            'symbol': symbol,
            'price': ind['price'],
            'change': ind['change'],
            'rsi': ind['rsi'],
            'volume': ind['volume'],
            'ma20': ind['ma20'],
            'ma50': ind['ma50'],
            'signal': signal,
            'reason': ', '.join(reasons) if reasons else 'Tidak ada sinyal kuat'
        }

    def check_all_signals(self):
        signals = {}
        for symbol in self.screener.watchlist:
            try:
                signal = self.generate_signal(symbol)
                if signal:
                    signals[symbol] = signal
            except Exception as e:
                logger.error(f"Error signal {symbol}: {str(e)}")
        return signals

# ============================================
# CHART GENERATOR
# ============================================
class ChartGenerator:
    def __init__(self):
        self.chart_dir = 'charts'
        os.makedirs(self.chart_dir, exist_ok=True)

    def create_chart(self, symbol, period='1mo'):
        try:
            ticker = yf.Ticker(f"{symbol}.JK")
            data = ticker.history(period=period)
            
            if data.empty:
                return None

            # Create figure
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(12, 8), gridspec_kw={'height_ratios': [3, 1]})
            
            # Price chart
            ax1.plot(data.index, data['Close'], label='Close', color='blue', linewidth=2)
            ax1.plot(data.index, data['Close'].rolling(window=20).mean(), label='MA20', color='orange', linestyle='--')
            ax1.plot(data.index, data['Close'].rolling(window=50).mean(), label='MA50', color='red', linestyle='--')
            ax1.bar(data.index, data['Volume'], alpha=0.3, color='gray', label='Volume')
            
            ax1.set_title(f'{symbol} - Price Chart', fontsize=14, fontweight='bold')
            ax1.set_ylabel('Price')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax1.xaxis.set_major_locator(mdates.WeekdayLocator())

            # RSI chart
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            ax2.plot(data.index, rsi, label='RSI', color='purple', linewidth=2)
            ax2.axhline(y=70, color='red', linestyle='--', alpha=0.5)
            ax2.axhline(y=30, color='green', linestyle='--', alpha=0.5)
            ax2.fill_between(data.index, 30, 70, alpha=0.1, color='gray')
            
            ax2.set_title('RSI (14)', fontsize=12)
            ax2.set_ylabel('RSI')
            ax2.set_ylim(0, 100)
            ax2.grid(True, alpha=0.3)
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%Y-%m-%d'))
            ax2.xaxis.set_major_locator(mdates.WeekdayLocator())
            
            plt.tight_layout()
            
            # Save chart
            filename = f"{self.chart_dir}/{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(filename, dpi=100, bbox_inches='tight')
            plt.close()
            
            # Cleanup old charts
            self.cleanup_old_charts(symbol)
            
            return filename
            
        except Exception as e:
            logger.error(f"Error creating chart {symbol}: {str(e)}")
            return None

    def cleanup_old_charts(self, symbol, keep=5):
        try:
            files = [f for f in os.listdir(self.chart_dir) if f.startswith(symbol)]
            if len(files) > keep:
                files.sort()
                for f in files[:-keep]:
                    os.remove(os.path.join(self.chart_dir, f))
        except:
            pass

# ============================================
# BOT UTAMA
# ============================================
class SahamBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.screener = Screener()
        self.signal_gen = SignalGenerator()
        self.chart_gen = ChartGenerator()
        self.watchlist = WATCHLIST.copy()
        self.running = False
        self.job = None

    def get_uptime(self):
        try:
            with open('uptime.txt', 'r') as f:
                start_time = datetime.fromisoformat(f.read().strip())
                delta = datetime.now() - start_time
                days = delta.days
                hours = delta.seconds // 3600
                minutes = (delta.seconds % 3600) // 60
                if days > 0:
                    return f"{days}d {hours}h {minutes}m"
                return f"{hours}h {minutes}m"
        except:
            return "Baru mulai"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        welcome_msg = f"""
🤖 *Bot Saham Danar v2*

📊 Bot monitoring saham Indonesia dengan sinyal trading otomatis.

*Perintah:*
/start - Menu utama
/help - Bantuan
/screener - Screening saham
/watchlist - Daftar saham
/add SYMBOL - Tambah saham
/remove SYMBOL - Hapus saham
/signal SYMBOL - Sinyal saham
/chart SYMBOL - Chart saham
/top - Top 5 volume
/check - Cek semua sinyal
/stats - Statistik bot
/refresh - Refresh data
/start_bot - Mulai monitoring
/stop_bot - Stop monitoring

*Status:* 🟢 Online
*Watchlist:* {len(self.watchlist)} saham
        """
        await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_msg = """
📚 *Bantuan Bot Saham Danar*

*Cara Penggunaan:*
1. /add SYMBOL - Tambah saham ke watchlist
2. /signal SYMBOL - Cek sinyal saham
3. /start_bot - Aktifkan monitoring otomatis

*Sumber Data:* Yahoo Finance (real-time)
*Update:* Data cache 5 menit

*Tips:*
• Gunakan /screener untuk lihat semua saham
• Aktifkan notifikasi untuk update real-time
• Data otomatis tersimpan di cache
        """
        await update.message.reply_text(help_msg, parse_mode='Markdown')

    async def screener(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 *Screening saham...*", parse_mode='Markdown')
        
        try:
            results = self.screener.screen_all()
            if not results:
                await msg.edit_text("⚠️ Tidak ada saham yang memenuhi kriteria.")
                return

            message = "📊 *Hasil Screener Saham*\n\n"
            for stock in results[:10]:
                score_emoji = "🔴" if stock['score'] < 0 else "🟢"
                message += f"{score_emoji} *{stock['symbol']}* ({stock['company']})\n"
                message += f"  💰 {format_price(stock['price'])} ({stock['change']:+.2f}%)\n"
                message += f"  📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"  📈 RSI: {stock['rsi']:.1f}\n"
                message += f"  ⭐ Score: {stock['score']}\n\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.watchlist:
            await update.message.reply_text("📋 Watchlist kosong.")
            return

        message = "📋 *Watchlist Saham*\n\n"
        for symbol in self.watchlist:
            price_data = self.screener.get_latest_price(symbol)
            if price_data:
                change_emoji = "🟢" if price_data['change'] >= 0 else "🔴"
                message += f"{change_emoji} *{symbol}*: {format_price(price_data['price'])} ({price_data['change']:+.2f}%)\n"
            else:
                message += f"❌ *{symbol}*: Data tidak tersedia\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /add SYMBOL (contoh: /add BBCA)")
            return

        symbol = context.args[0].upper()
        if not is_valid_symbol(symbol):
            await update.message.reply_text("❌ Kode saham tidak valid!")
            return

        if symbol not in self.watchlist:
            self.watchlist.append(symbol)
            # Update juga di screener
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* ditambahkan ke watchlist!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ *{symbol}* sudah ada di watchlist.", parse_mode='Markdown')

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /remove SYMBOL")
            return

        symbol = context.args[0].upper()
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* dihapus dari watchlist!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ *{symbol}* tidak ditemukan.", parse_mode='Markdown')

    async def signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /signal SYMBOL")
            return

        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📈 *Menganalisis {symbol}...*", parse_mode='Markdown')

        try:
            signal = self.signal_gen.generate_signal(symbol)
            if not signal:
                await msg.edit_text(f"❌ Data *{symbol}* tidak tersedia.", parse_mode='Markdown')
                return

            signal_emoji = "🟢" if signal['signal'] == 'BUY' else "🔴" if signal['signal'] == 'SELL' else "⚪"
            signal_text = "🔴 *JUAL*" if signal['signal'] == 'SELL' else "🟢 *BELI*" if signal['signal'] == 'BUY' else "⚪ *TAHAN*"

            message = f"📊 *Analisis {symbol}*\n\n"
            message += f"💰 Harga: {format_price(signal['price'])}\n"
            message += f"📊 Perubahan: {signal['change']:+.2f}%\n"
            message += f"📈 RSI: {signal['rsi']:.1f}\n"
            message += f"📊 Volume: {format_volume(signal['volume'])}\n"
            message += f"📉 MA20: {format_price(signal['ma20'])}\n"
            message += f"📉 MA50: {format_price(signal['ma50'])}\n\n"
            message += f"🎯 *Rekomendasi:* {signal_text}\n"
            message += f"💡 *Alasan:* {signal['reason']}"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /chart SYMBOL")
            return

        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📊 *Membuat chart {symbol}...*", parse_mode='Markdown')

        try:
            chart_path = self.chart_gen.create_chart(symbol)
            if chart_path:
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(photo=photo, caption=f"📈 Chart {symbol}")
                os.remove(chart_path)
            else:
                await msg.edit_text(f"❌ Gagal membuat chart *{symbol}*.", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("📊 *Mencari volume tertinggi...*", parse_mode='Markdown')

        try:
            top_stocks = self.screener.get_top_by_volume(5)
            if not top_stocks:
                await msg.edit_text("❌ Data tidak tersedia.")
                return

            message = "🔥 *Top 5 Volume Saham*\n\n"
            for i, stock in enumerate(top_stocks, 1):
                change_emoji = "🟢" if stock['change'] >= 0 else "🔴"
                message += f"{i}. {change_emoji} *{stock['symbol']}*\n"
                message += f"   💰 {format_price(stock['price'])}\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 {stock['change']:+.2f}%\n\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 *Mengecek semua sinyal...*", parse_mode='Markdown')

        try:
            signals = self.signal_gen.check_all_signals()
            if not signals:
                await msg.edit_text("✅ Tidak ada sinyal terdeteksi.")
                return

            buy_signals = [s for s in signals.values() if s['signal'] == 'BUY']
            sell_signals = [s for s in signals.values() if s['signal'] == 'SELL']

            message = "📊 *Hasil Pengecekan Sinyal*\n\n"
            message += f"🟢 BELI: {len(buy_signals)}\n"
            message += f"🔴 JUAL: {len(sell_signals)}\n"
            message += f"⚪ TAHAN: {len(signals) - len(buy_signals) - len(sell_signals)}\n\n"

            if buy_signals:
                message += "*🟢 Sinyal BELI:*\n"
                for s in buy_signals[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']}\n"

            if sell_signals:
                message += "\n*🔴 Sinyal JUAL:*\n"
                for s in sell_signals[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']}\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        stats_msg = f"""
📊 *Statistik Bot*

🕐 Uptime: {self.get_uptime()}
📋 Watchlist: {len(self.watchlist)} saham
🔄 Monitoring: {'✅ Aktif' if self.running else '⛔ Nonaktif'}

*Last Update:* {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}
        """
        await update.message.reply_text(stats_msg, parse_mode='Markdown')

    async def refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔄 *Refresh data...*", parse_mode='Markdown')
        try:
            self.screener.cache = {}
            self.screener.save_cache()
            await msg.edit_text("✅ *Data cache berhasil direfresh!*", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.running:
            self.running = True
            self.job = context.job_queue.run_repeating(
                self.monitor_stocks,
                interval=300,  # 5 menit
                first=10
            )
            await update.message.reply_text(
                "✅ *Monitoring otomatis dimulai!*\n"
                "Bot akan mengecek sinyal setiap 5 menit.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "⚠️ Monitoring sudah aktif.",
                parse_mode='Markdown'
            )

    async def stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.running and self.job:
            self.running = False
            self.job.schedule_removal()
            self.job = None
            await update.message.reply_text(
                "⏹️ *Monitoring dihentikan.*",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "ℹ️ Monitoring tidak aktif.",
                parse_mode='Markdown'
            )

    async def monitor_stocks(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info("Running monitoring...")
            signals = self.signal_gen.check_all_signals()

            for symbol, signal in signals.items():
                if symbol in self.watchlist and signal['signal'] != 'HOLD':
                    signal_emoji = "🟢" if signal['signal'] == 'BUY' else "🔴"
                    message = f"{signal_emoji} *SINYAL {signal['signal']} - {symbol}*\n\n"
                    message += f"💰 {format_price(signal['price'])}\n"
                    message += f"📊 {signal['change']:+.2f}%\n"
                    message += f"📈 RSI: {signal['rsi']:.1f}\n"
                    message += f"💡 {signal['reason']}"

                    if CHANNEL_ID:
                        try:
                            await self.bot.send_message(
                                chat_id=CHANNEL_ID,
                                text=message,
                                parse_mode='Markdown'
                            )
                            logger.info(f"Signal sent for {symbol}: {signal['signal']}")
                        except Exception as e:
                            logger.error(f"Error sending signal: {str(e)}")
        except Exception as e:
            logger.error(f"Error monitoring: {str(e)}")

    async def error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error: {context.error}")
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Terjadi kesalahan. Coba lagi nanti."
                )
        except:
            pass

    def run(self):
        # Save uptime
        with open('uptime.txt', 'w') as f:
            f.write(datetime.now().isoformat())

        # Create directories
        os.makedirs('charts', exist_ok=True)
        os.makedirs('data', exist_ok=True)

        # Setup application
        application = Application.builder().token(TELEGRAM_TOKEN).build()

        # Register commands
        application.add_handler(CommandHandler("start", self.start))
        application.add_handler(CommandHandler("help", self.help))
        application.add_handler(CommandHandler("screener", self.screener))
        application.add_handler(CommandHandler("watchlist", self.watchlist))
        application.add_handler(CommandHandler("add", self.add))
        application.add_handler(CommandHandler("remove", self.remove))
        application.add_handler(CommandHandler("signal", self.signal))
        application.add_handler(CommandHandler("chart", self.chart))
        application.add_handler(CommandHandler("top", self.top))
        application.add_handler(CommandHandler("check", self.check))
        application.add_handler(CommandHandler("stats", self.stats))
        application.add_handler(CommandHandler("refresh", self.refresh))
        application.add_handler(CommandHandler("start_bot", self.start_bot))
        application.add_handler(CommandHandler("stop_bot", self.stop_bot))

        application.add_error_handler(self.error_handler)

        # Run
        logger.info(f"Starting bot on port {PORT}...")
        application.run_polling(
            allowed_updates=Update.ALL_TYPES,
            drop_pending_updates=True,
            poll_interval=2.0,
            timeout=30
        )

# ============================================
# MAIN
# ============================================
if __name__ == '__main__':
    try:
        bot = SahamBot()
        bot.run()
    except Exception as e:
        logger.error(f"Fatal error: {str(e)}")
        sys.exit(1)
