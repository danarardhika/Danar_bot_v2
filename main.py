#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Saham Danar v2.2 - FIXED
Dengan fallback data jika Yahoo Finance bermasalah
"""

import os
import sys
import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError, NetworkError
from dotenv import load_dotenv
import requests

# ============================================
# KONFIGURASI
# ============================================

load_dotenv()

TELEGRAM_TOKEN = os.getenv('TELEGRAM_TOKEN', '')
if not TELEGRAM_TOKEN:
    print("❌ ERROR: TELEGRAM_TOKEN tidak ditemukan!")
    sys.exit(1)

CHANNEL_ID = os.getenv('CHANNEL_ID', '')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
PORT = int(os.getenv('PORT', 8080))

# Watchlist
watchlist_str = os.getenv('WATCHLIST', '')
if watchlist_str:
    WATCHLIST = [s.strip().upper() for s in watchlist_str.split(',') if s.strip()]
else:
    WATCHLIST = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'UNVR', 'GOTO']

VOLUME_THRESHOLD = float(os.getenv('VOLUME_THRESHOLD', '1.5'))

# ============================================
# SETUP LOGGING
# ============================================

os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot.log')
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# FALLBACK DATA (Jika Yahoo Finance Gagal)
# ============================================

FALLBACK_DATA = {
    'BBCA': {'price': 9500, 'change': 0.5, 'volume': 15000000, 'rsi': 55},
    'BBRI': {'price': 4800, 'change': 0.3, 'volume': 20000000, 'rsi': 52},
    'BMRI': {'price': 6200, 'change': 0.2, 'volume': 12000000, 'rsi': 50},
    'TLKM': {'price': 3800, 'change': -0.1, 'volume': 18000000, 'rsi': 48},
    'ASII': {'price': 7200, 'change': 0.8, 'volume': 8000000, 'rsi': 58},
    'UNVR': {'price': 4200, 'change': -0.5, 'volume': 5000000, 'rsi': 45},
    'GOTO': {'price': 80, 'change': -1.2, 'volume': 50000000, 'rsi': 40}
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

def safe_json_load(filepath, default=None):
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r') as f:
                return json.load(f)
    except:
        pass
    return default or {}

def safe_json_save(filepath, data):
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w') as f:
            json.dump(data, f, indent=2)
        return True
    except:
        return False

COMPANY_NAMES = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'TLKM': 'Telkom Indonesia',
    'ASII': 'Astra International',
    'UNVR': 'Unilever Indonesia',
    'GOTO': 'GoTo Gojek Tokopedia',
    'ADMR': 'Adaro Minerals',
    'BRPT': 'Barito Pacific',
    'PTBA': 'Bukit Asam'
}

# ============================================
# SCREENER DENGAN FALLBACK
# ============================================

class Screener:
    def __init__(self):
        self.cache_dir = 'data'
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'stock_cache.json')
        self.cache = safe_json_load(self.cache_file, {})
        self.watchlist = WATCHLIST.copy()
        self.use_fallback = False  # Aktif jika Yahoo Finance gagal

    def save_cache(self):
        safe_json_save(self.cache_file, self.cache)

    def get_stock_data(self, symbol, period='1mo', max_retries=2):
        """Ambil data dengan fallback jika gagal"""
        cache_key = f"{symbol}_{period}"
        
        # Cek cache
        if cache_key in self.cache:
            cache_time = self.cache[cache_key].get('timestamp', '')
            if cache_time:
                try:
                    cache_date = datetime.fromisoformat(cache_time)
                    if (datetime.now() - cache_date) < timedelta(minutes=5):
                        logger.info(f"📦 Cache {symbol}")
                        data_dict = self.cache[cache_key]['data']
                        return pd.DataFrame(data_dict)
                except:
                    pass

        # Coba ambil dari Yahoo Finance
        for attempt in range(max_retries):
            try:
                logger.info(f"📥 Mengambil data {symbol} (attempt {attempt+1}/{max_retries})")
                
                # Coba dengan .JK (saham Indonesia)
                ticker = yf.Ticker(f"{symbol}.JK")
                data = ticker.history(period=period, timeout=10)
                
                if not data.empty:
                    self.cache[cache_key] = {
                        'timestamp': datetime.now().isoformat(),
                        'data': data.to_dict('list')
                    }
                    self.save_cache()
                    self.use_fallback = False
                    return data
                    
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed for {symbol}: {str(e)}")
                time.sleep(2)

        # Jika semua gagal, gunakan fallback
        logger.warning(f"⚠️ Menggunakan fallback data untuk {symbol}")
        self.use_fallback = True
        return self._create_fallback_data(symbol, period)

    def _create_fallback_data(self, symbol, period='1mo'):
        """Buat data dummy jika Yahoo Finance gagal"""
        try:
            # Ambil dari FALLBACK_DATA
            fallback = FALLBACK_DATA.get(symbol, {
                'price': 5000,
                'change': 0,
                'volume': 10000000,
                'rsi': 50
            })
            
            # Buat dataframe dummy
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            prices = [fallback['price'] * (1 + np.random.randn() * 0.02) for _ in range(30)]
            prices = np.cumsum(prices) / 30 * fallback['price']
            
            data = pd.DataFrame({
                'Open': prices * 0.99,
                'High': prices * 1.02,
                'Low': prices * 0.98,
                'Close': prices,
                'Volume': [fallback['volume'] * (0.8 + 0.4 * np.random.rand()) for _ in range(30)]
            }, index=dates)
            
            return data
            
        except Exception as e:
            logger.error(f"Error creating fallback data: {str(e)}")
            return None

    def calculate_indicators(self, data):
        if data is None or len(data) < 10:
            return None

        try:
            close = data['Close']
            
            # Sederhanakan perhitungan untuk fallback data
            if len(close) < 14:
                rsi = 50
                ma20 = close.iloc[-1]
                ma50 = close.iloc[-1]
            else:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi = rsi.iloc[-1] if len(rsi) > 0 else 50
                
                ma20 = close.rolling(window=20).mean().iloc[-1] if len(close) >= 20 else close.iloc[-1]
                ma50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else close.iloc[-1]
            
            avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1] if len(data) >= 10 else data['Volume'].iloc[-1]
            volume_ratio = data['Volume'].iloc[-1] / avg_volume if avg_volume > 0 else 1
            change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0

            return {
                'price': close.iloc[-1],
                'change': change,
                'volume': data['Volume'].iloc[-1],
                'volume_ratio': volume_ratio,
                'rsi': rsi if not np.isnan(rsi) else 50,
                'ma20': ma20 if not np.isnan(ma20) else close.iloc[-1],
                'ma50': ma50 if not np.isnan(ma50) else close.iloc[-1],
                'high': data['High'].iloc[-1] if 'High' in data else close.iloc[-1] * 1.02,
                'low': data['Low'].iloc[-1] if 'Low' in data else close.iloc[-1] * 0.98
            }
        except Exception as e:
            logger.error(f"Error indicators: {str(e)}")
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

    def clear_cache(self):
        self.cache = {}
        self.save_cache()

# ============================================
# SIGNAL GENERATOR
# ============================================

class SignalGenerator:
    def __init__(self):
        self.screener = Screener()

    def generate_signal(self, symbol):
        try:
            data = self.screener.get_stock_data(symbol)
            if data is None:
                return None

            ind = self.screener.calculate_indicators(data)
            if ind is None:
                return None

            signal = 'HOLD'
            reasons = []
            strength = 0

            if ind['rsi'] < 30:
                signal = 'BUY'
                strength += 2
                reasons.append(f'RSI Oversold ({ind["rsi"]:.1f})')
            elif ind['rsi'] > 70:
                signal = 'SELL'
                strength += 2
                reasons.append(f'RSI Overbought ({ind["rsi"]:.1f})')

            if ind['ma20'] > ind['ma50'] and ind['price'] > ind['ma20']:
                if signal == 'HOLD':
                    signal = 'BUY'
                strength += 1
                reasons.append('Golden Cross')
            elif ind['ma20'] < ind['ma50'] and ind['price'] < ind['ma20']:
                if signal == 'HOLD':
                    signal = 'SELL'
                strength += 1
                reasons.append('Death Cross')

            if ind['volume_ratio'] > 2.0:
                if signal == 'HOLD':
                    signal = 'BUY' if ind['change'] > 0 else 'SELL'
                strength += 1
                reasons.append(f'Volume Tinggi ({ind["volume_ratio"]:.1f}x)')

            return {
                'symbol': symbol,
                'price': ind['price'],
                'change': ind['change'],
                'rsi': ind['rsi'],
                'volume': ind['volume'],
                'ma20': ind['ma20'],
                'ma50': ind['ma50'],
                'signal': signal,
                'strength': strength,
                'reason': ', '.join(reasons) if reasons else 'Tidak ada sinyal kuat'
            }
        except Exception as e:
            logger.error(f"Error signal {symbol}: {str(e)}")
            return None

    def check_all_signals(self):
        signals = {}
        for symbol in self.screener.watchlist:
            try:
                signal = self.generate_signal(symbol)
                if signal:
                    signals[symbol] = signal
            except Exception as e:
                logger.error(f"Error check signal {symbol}: {str(e)}")
        return signals

# ============================================
# BOT UTAMA
# ============================================

class SahamBot:
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.screener = Screener()
        self.signal_gen = SignalGenerator()
        self.watchlist = WATCHLIST.copy()
        self.running = False
        self.job = None
        self.start_time = datetime.now()
        self.error_count = 0
        self.max_errors = 20

    def get_uptime(self):
        delta = datetime.now() - self.start_time
        days = delta.days
        hours = delta.seconds // 3600
        minutes = (delta.seconds % 3600) // 60
        if days > 0:
            return f"{days}d {hours}h {minutes}m"
        return f"{hours}h {minutes}m"

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        fallback_status = "⚠️ Mode Fallback (Data Simulasi)" if self.screener.use_fallback else "✅ Data Real-time"
        
        await update.message.reply_text(
            f"🤖 *Bot Saham Danar v2.2*\n\n"
            f"📊 Status: {fallback_status}\n"
            f"📋 Watchlist: {len(self.watchlist)} saham\n"
            f"🕐 Uptime: {self.get_uptime()}\n\n"
            f"Perintah: /help untuk bantuan",
            parse_mode='Markdown'
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 *Bantuan Bot*\n\n"
            "/start - Menu utama\n"
            "/screener - Screening saham\n"
            "/watchlist - Daftar saham\n"
            "/add SYMBOL - Tambah saham\n"
            "/remove SYMBOL - Hapus saham\n"
            "/signal SYMBOL - Cek sinyal\n"
            "/chart SYMBOL - Chart saham\n"
            "/top - Top 5 volume\n"
            "/check - Cek semua sinyal\n"
            "/stats - Statistik bot\n"
            "/refresh - Refresh data\n"
            "/start_bot - Mulai monitoring\n"
            "/stop_bot - Stop monitoring\n\n"
            "⚠️ *Jika data tidak tersedia*, bot akan menggunakan data simulasi.",
            parse_mode='Markdown'
        )

    async def screener(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 *Screening...*", parse_mode='Markdown')
        try:
            results = self.screener.screen_all()
            if not results:
                await msg.edit_text("⚠️ Tidak ada hasil. Coba /refresh")
                return

            message = "📊 *Hasil Screener*\n\n"
            for stock in results[:10]:
                emoji = "🟢" if stock['score'] > 0 else "🔴" if stock['score'] < 0 else "⚪"
                message += f"{emoji} *{stock['symbol']}* - {stock['company']}\n"
                message += f"   💰 {format_price(stock['price'])} ({stock['change']:+.2f}%)\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 RSI: {stock['rsi']:.1f} | Score: {stock['score']}\n\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Screener error: {str(e)}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.watchlist:
            await update.message.reply_text("📋 Watchlist kosong.")
            return

        message = "📋 *Watchlist*\n\n"
        for symbol in self.watchlist:
            price = self.screener.get_latest_price(symbol)
            if price:
                emoji = "🟢" if price['change'] >= 0 else "🔴"
                message += f"{emoji} *{symbol}* - {COMPANY_NAMES.get(symbol, symbol)}\n"
                message += f"   💰 {format_price(price['price'])} ({price['change']:+.2f}%)\n"
            else:
                message += f"❌ *{symbol}*: Data tidak tersedia\n"
            message += "\n"

        await update.message.reply_text(message, parse_mode='Markdown')

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /add SYMBOL (contoh: /add BBCA)")
            return

        symbol = context.args[0].upper()
        if symbol not in self.watchlist:
            self.watchlist.append(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* ditambahkan!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ *{symbol}* sudah ada.", parse_mode='Markdown')

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /remove SYMBOL")
            return

        symbol = context.args[0].upper()
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* dihapus!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ *{symbol}* tidak ditemukan.", parse_mode='Markdown')

    async def signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /signal SYMBOL (contoh: /signal BBCA)")
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

            fallback_note = "\n⚠️ *Data Simulasi*" if self.screener.use_fallback else ""

            message = f"📊 *Analisis {symbol}*\n\n"
            message += f"💰 {format_price(signal['price'])}\n"
            message += f"📊 {signal['change']:+.2f}%\n"
            message += f"📈 RSI: {signal['rsi']:.1f}\n"
            message += f"📊 Vol: {format_volume(signal['volume'])}\n"
            message += f"📉 MA20: {format_price(signal['ma20'])}\n"
            message += f"📉 MA50: {format_price(signal['ma50'])}\n\n"
            message += f"🎯 {signal_text}\n"
            message += f"💡 {signal['reason']}"
            message += fallback_note

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
            # Ambil data
            data = self.screener.get_stock_data(symbol, period='1mo')
            if data is None or data.empty:
                await msg.edit_text(f"❌ Data *{symbol}* tidak tersedia.", parse_mode='Markdown')
                return

            # Buat chart sederhana
            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})
            
            # Price chart
            ax1.plot(data.index, data['Close'], label='Close', linewidth=2, color='blue')
            if len(data) >= 20:
                ax1.plot(data.index, data['Close'].rolling(20).mean(), label='MA20', linestyle='--', color='orange')
            ax1.set_title(f'{symbol} - {COMPANY_NAMES.get(symbol, symbol)}')
            ax1.set_ylabel('Price')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            
            # Volume chart
            ax2.bar(data.index, data['Volume'], alpha=0.5, color='gray')
            ax2.set_ylabel('Volume')
            ax2.grid(True, alpha=0.3)
            
            plt.tight_layout()
            
            # Simpan
            filename = f"chart_{symbol}.png"
            plt.savefig(filename, dpi=80, bbox_inches='tight')
            plt.close()

            # Kirim
            with open(filename, 'rb') as photo:
                await update.message.reply_photo(photo=photo, caption=f"📈 Chart {symbol}")
            
            os.remove(filename)
            await msg.delete()

        except Exception as e:
            logger.error(f"Chart error: {str(e)}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("📊 *Mencari volume tertinggi...*", parse_mode='Markdown')

        try:
            top_stocks = self.screener.get_top_by_volume(5)
            if not top_stocks:
                await msg.edit_text("❌ Data tidak tersedia.")
                return

            message = "🔥 *Top 5 Volume*\n\n"
            for i, stock in enumerate(top_stocks, 1):
                emoji = "🟢" if stock['change'] >= 0 else "🔴"
                message += f"{i}. {emoji} *{stock['symbol']}*\n"
                message += f"   💰 {format_price(stock['price'])}\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 {stock['change']:+.2f}%\n\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 *Mengecek sinyal...*", parse_mode='Markdown')

        try:
            signals = self.signal_gen.check_all_signals()
            if not signals:
                await msg.edit_text("✅ Tidak ada sinyal.")
                return

            buy = [s for s in signals.values() if s['signal'] == 'BUY']
            sell = [s for s in signals.values() if s['signal'] == 'SELL']

            message = f"📊 *Hasil Pengecekan*\n\n"
            message += f"🟢 BELI: {len(buy)}\n"
            message += f"🔴 JUAL: {len(sell)}\n"
            message += f"⚪ TAHAN: {len(signals) - len(buy) - len(sell)}\n\n"

            if buy:
                message += "*🟢 Sinyal BELI:*\n"
                for s in buy[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']}\n"

            if sell:
                message += "\n*🔴 Sinyal JUAL:*\n"
                for s in sell[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']}\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        fallback_status = "⚠️ Fallback" if self.screener.use_fallback else "✅ Real-time"
        
        await update.message.reply_text(
            f"📊 *Statistik Bot v2.2*\n\n"
            f"🕐 Uptime: {self.get_uptime()}\n"
            f"📋 Watchlist: {len(self.watchlist)} saham\n"
            f"📊 Data: {fallback_status}\n"
            f"🔄 Monitoring: {'✅ Aktif' if self.running else '⛔ Nonaktif'}\n"
            f"📦 Cache: {len(self.screener.cache)} items\n"
            f"❌ Error: {self.error_count}\n"
            f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            parse_mode='Markdown'
        )

    async def refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔄 *Refresh data...*", parse_mode='Markdown')
        try:
            self.screener.clear_cache()
            self.screener.use_fallback = False
            await msg.edit_text("✅ *Data cache berhasil direfresh!*\nCoba /screener lagi.", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.running:
            self.running = True
            self.job = context.job_queue.run_repeating(
                self._monitor_stocks,
                interval=300,
                first=10
            )
            await update.message.reply_text(
                "✅ *Monitoring dimulai!*\n"
                "Cek sinyal setiap 5 menit.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("⚠️ Monitoring sudah aktif.", parse_mode='Markdown')

    async def stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if self.running and self.job:
            self.running = False
            self.job.schedule_removal()
            self.job = None
            await update.message.reply_text("⏹️ *Monitoring dihentikan.*", parse_mode='Markdown')
        else:
            await update.message.reply_text("ℹ️ Monitoring tidak aktif.", parse_mode='Markdown')

    async def _monitor_stocks(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info("🔄 Running monitoring...")
            signals = self.signal_gen.check_all_signals()

            for symbol, signal in signals.items():
                if symbol in self.watchlist and signal['signal'] != 'HOLD' and signal['strength'] >= 2:
                    if CHANNEL_ID:
                        try:
                            message = f"🟢 *SINYAL {signal['signal']} - {symbol}*\n\n"
                            message += f"💰 {format_price(signal['price'])}\n"
                            message += f"📊 {signal['change']:+.2f}%\n"
                            message += f"💡 {signal['reason']}"

                            await self.bot.send_message(
                                chat_id=CHANNEL_ID,
                                text=message,
                                parse_mode='Markdown'
                            )
                            logger.info(f"📬 Signal sent: {symbol}")
                        except Exception as e:
                            logger.error(f"Error sending signal: {str(e)}")

        except Exception as e:
            logger.error(f"Error monitoring: {str(e)}")
            self.error_count += 1

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error: {context.error}")
        self.error_count += 1
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Terjadi kesalahan. Bot akan mencoba pulih...\n"
                    "Gunakan /refresh jika perlu."
                )
        except:
            pass

        if self.error_count > self.max_errors:
            logger.warning(f"⚠️ Terlalu banyak error ({self.error_count}), restarting...")
            self.error_count = 0
            sys.exit(0)

    def run(self):
        try:
            os.makedirs('data', exist_ok=True)
            os.makedirs('charts', exist_ok=True)
            os.makedirs('logs', exist_ok=True)

            application = Application.builder().token(TELEGRAM_TOKEN).build()

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

            application.add_error_handler(self._error_handler)

            logger.info("🚀 Bot starting...")
            print("=" * 60)
            print("🤖 BOT SAHAM DANAR v2.2 - FIXED")
            print("=" * 60)
            print(f"📌 Token: ✓")
            print(f"📌 Watchlist: {len(self.watchlist)} saham")
            print(f"📌 Fallback Data: Aktif jika Yahoo Finance gagal")
            print("=" * 60)

            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=2.0,
                timeout=30
            )

        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            logger.error(traceback.format_exc())
            time.sleep(5)
            sys.exit(1)

if __name__ == '__main__':
    try:
        bot = SahamBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n⏹️ Bot dihentikan")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal: {str(e)}")
        time.sleep(5)
        sys.exit(1)
