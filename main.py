#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Saham Danar v2.0
Telegram Bot untuk monitoring saham Indonesia
Deploy di Railway.app
"""

import os
import sys
import json
import logging
import time
import traceback
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any, Tuple

import yfinance as yf
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')  # Gunakan backend non-interaktif untuk server
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes
from telegram.error import TelegramError
from dotenv import load_dotenv

# ============================================
# KONFIGURASI DENGAN ERROR HANDLING
# ============================================

# Load .env file
load_dotenv()

def get_env_var(var_name: str, default: str = '') -> str:
    """Ambil environment variable dengan error handling"""
    value = os.getenv(var_name)
    if value is None or value == '':
        if default:
            return default
        raise ValueError(f"Environment variable {var_name} tidak ditemukan!")
    return value

# Token - MANDATORY
try:
    TELEGRAM_TOKEN = get_env_var('8523825536:AAFrUBVnWCL90wV-IFvggJ7ZDMLJBpTJl1g')
    print(f"✅ TELEGRAM_TOKEN ditemukan: {TELEGRAM_TOKEN[:15]}...")
except ValueError as e:
    print("=" * 70)
    print("❌ ERROR: TELEGRAM_TOKEN TIDAK DITEMUKAN!")
    print("=" * 70)
    print("\n📌 CARA SETUP DI RAILWAY:")
    print("1. Buka Railway Dashboard")
    print("2. Pilih proyek ini")
    print("3. Klik tab 'Variables'")
    print("4. Tambahkan variable:")
    print("   TELEGRAM_TOKEN = [token_dari_botfather]")
    print("\n📌 CARA DAPATKAN TOKEN:")
    print("1. Buka Telegram")
    print("2. Cari @BotFather")
    print("3. Kirim /newbot")
    print("4. Ikuti instruksi")
    print("5. Copy token yang diberikan")
    print("=" * 70)
    sys.exit(1)

# Optional variables
CHANNEL_ID = os.getenv('CHANNEL_ID', '')
ENVIRONMENT = os.getenv('ENVIRONMENT', 'production')
DEBUG = ENVIRONMENT == 'development'
PORT = int(os.getenv('PORT', 8080))

# Watchlist
try:
    watchlist_str = os.getenv('WATCHLIST', '')
    if watchlist_str:
        WATCHLIST = [s.strip().upper() for s in watchlist_str.split(',') if s.strip()]
    else:
        WATCHLIST = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'UNVR', 'GOTO', 'ANTM', 'INDF']
except:
    WATCHLIST = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'UNVR', 'GOTO', 'ANTM', 'INDF']

# Threshold
VOLUME_THRESHOLD = float(os.getenv('VOLUME_THRESHOLD', '1.5'))
RSI_OVERSOLD = int(os.getenv('RSI_OVERSOLD', '30'))
RSI_OVERBOUGHT = int(os.getenv('RSI_OVERBOUGHT', '70'))

# ============================================
# SETUP LOGGING
# ============================================

# Buat folder logs
os.makedirs('logs', exist_ok=True)

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.DEBUG if DEBUG else logging.INFO,
    handlers=[
        logging.StreamHandler(sys.stdout),
        logging.FileHandler('logs/bot.log', encoding='utf-8')
    ]
)
logger = logging.getLogger(__name__)

# ============================================
# PRINT INFO STARTUP
# ============================================

print("=" * 70)
print("🤖 BOT SAHAM DANAR v2.0")
print("=" * 70)
print(f"📌 Token: {'✓' if TELEGRAM_TOKEN else '✗'}")
print(f"📌 Channel ID: {'✓' if CHANNEL_ID else '✗ (opsional)'}")
print(f"📌 Watchlist: {len(WATCHLIST)} saham")
print(f"📌 Watchlist: {', '.join(WATCHLIST)}")
print(f"📌 Environment: {ENVIRONMENT}")
print(f"📌 Debug: {'Ya' if DEBUG else 'Tidak'}")
print(f"📌 Port: {PORT}")
print("=" * 70)

# ============================================
# NAMA PERUSAHAAN
# ============================================

COMPANY_NAMES = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'TLKM': 'Telkom Indonesia',
    'ASII': 'Astra International',
    'UNVR': 'Unilever Indonesia',
    'GOTO': 'GoTo Gojek Tokopedia',
    'ANTM': 'Aneka Tambang',
    'INDF': 'Indofood',
    'CPIN': 'Charoen Pokphand',
    'ICBP': 'Indofood CBP',
    'PGAS': 'Perusahaan Gas Negara',
    'ADRO': 'Adaro Energy',
    'SMCB': 'Semen Indonesia',
    'TINS': 'Timah Indonesia'
}

# ============================================
# FUNGSI UTILITY
# ============================================

def format_price(price: float) -> str:
    """Format harga ke Rupiah"""
    return f"Rp{price:,.0f}".replace(',', '.')

def format_volume(volume: float) -> str:
    """Format volume dengan satuan"""
    if volume >= 1e9:
        return f"{volume/1e9:.2f}B"
    elif volume >= 1e6:
        return f"{volume/1e6:.2f}M"
    elif volume >= 1e3:
        return f"{volume/1e3:.2f}K"
    else:
        return f"{volume:.0f}"

def is_valid_symbol(symbol: str) -> bool:
    """Validasi kode saham"""
    return len(symbol) >= 3 and symbol.isalpha() and symbol.isupper()

def safe_json_load(filepath: str, default: Any = None) -> Any:
    """Load JSON dengan safe"""
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        logger.warning(f"Error loading {filepath}: {str(e)}")
    return default or {}

def safe_json_save(filepath: str, data: Any) -> bool:
    """Save JSON dengan safe"""
    try:
        os.makedirs(os.path.dirname(filepath), exist_ok=True)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        return True
    except Exception as e:
        logger.error(f"Error saving {filepath}: {str(e)}")
        return False

def get_company_name(symbol: str) -> str:
    """Dapatkan nama perusahaan"""
    return COMPANY_NAMES.get(symbol, symbol)

def get_uptime(start_time: datetime) -> str:
    """Hitung uptime"""
    if not start_time:
        return "Baru mulai"
    delta = datetime.now() - start_time
    days = delta.days
    hours = delta.seconds // 3600
    minutes = (delta.seconds % 3600) // 60
    if days > 0:
        return f"{days}d {hours}h {minutes}m"
    return f"{hours}h {minutes}m"

def get_timestamp() -> str:
    """Dapatkan timestamp sekarang"""
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')

# ============================================
# SCREENER - DATA & ANALISIS
# ============================================

class Screener:
    """Class untuk mengambil dan menganalisis data saham"""
    
    def __init__(self):
        self.cache_dir = 'data'
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'stock_cache.json')
        self.cache = self._load_cache()
        self.watchlist = WATCHLIST.copy()
        self.last_update = None
        
    def _load_cache(self) -> Dict:
        """Load cache dari file"""
        return safe_json_load(self.cache_file, {})

    def _save_cache(self) -> None:
        """Save cache ke file"""
        safe_json_save(self.cache_file, self.cache)
        self.last_update = datetime.now()

    def _get_cache_key(self, symbol: str, period: str) -> str:
        """Buat key untuk cache"""
        return f"{symbol}_{period}"

    def _is_cache_valid(self, cache_key: str, max_age_minutes: int = 5) -> bool:
        """Cek apakah cache masih valid"""
        if cache_key not in self.cache:
            return False
        cache_time = self.cache[cache_key].get('timestamp', '')
        if not cache_time:
            return False
        try:
            cache_date = datetime.fromisoformat(cache_time)
            return (datetime.now() - cache_date) < timedelta(minutes=max_age_minutes)
        except:
            return False

    def get_stock_data(self, symbol: str, period: str = '1mo', force_refresh: bool = False) -> Optional[pd.DataFrame]:
        """
        Mengambil data saham dengan cache
        """
        cache_key = self._get_cache_key(symbol, period)
        
        # Check cache
        if not force_refresh and self._is_cache_valid(cache_key):
            logger.info(f"📦 Menggunakan cache untuk {symbol}")
            try:
                data_dict = self.cache[cache_key]['data']
                df = pd.DataFrame(data_dict)
                if not df.empty:
                    return df
            except Exception as e:
                logger.warning(f"Error load cache {symbol}: {str(e)}")

        try:
            # Ambil dari Yahoo Finance
            ticker_symbol = f"{symbol}.JK"
            ticker = yf.Ticker(ticker_symbol)
            data = ticker.history(period=period)
            
            if data.empty:
                logger.warning(f"⚠️ Data kosong untuk {symbol}")
                return None

            # Simpan ke cache
            self.cache[cache_key] = {
                'timestamp': datetime.now().isoformat(),
                'data': data.to_dict('list')
            }
            self._save_cache()
            
            logger.info(f"✅ Data {symbol} berhasil diambil")
            return data
            
        except Exception as e:
            logger.error(f"❌ Error mengambil data {symbol}: {str(e)}")
            return None

    def calculate_indicators(self, data: pd.DataFrame) -> Optional[Dict]:
        """
        Menghitung indikator teknikal
        """
        if data is None or len(data) < 20:
            return None

        try:
            close = data['Close']
            
            # RSI (14)
            delta = close.diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Moving Averages
            ma20 = close.rolling(window=20).mean()
            ma50 = close.rolling(window=50).mean() if len(data) >= 50 else close.rolling(window=20).mean()
            
            # Volume
            volume = data['Volume']
            avg_volume = volume.rolling(window=20).mean()
            volume_ratio = volume.iloc[-1] / avg_volume.iloc[-1] if avg_volume.iloc[-1] > 0 else 0
            
            # Price change
            change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(data) > 1 else 0

            return {
                'price': close.iloc[-1],
                'change': change,
                'volume': volume.iloc[-1],
                'volume_ratio': volume_ratio,
                'rsi': rsi.iloc[-1] if len(rsi) > 0 else 50,
                'ma20': ma20.iloc[-1] if len(ma20) > 0 else close.iloc[-1],
                'ma50': ma50.iloc[-1] if len(ma50) > 0 else close.iloc[-1],
                'high': data['High'].iloc[-1],
                'low': data['Low'].iloc[-1],
                'open': data['Open'].iloc[-1]
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def screen_all(self) -> List[Dict]:
        """
        Screening semua saham
        """
        results = []
        
        for symbol in self.watchlist:
            try:
                data = self.get_stock_data(symbol)
                if data is None:
                    continue
                    
                ind = self.calculate_indicators(data)
                if ind is None:
                    continue

                # Skoring
                score = 0
                
                # RSI
                if ind['rsi'] < RSI_OVERSOLD:
                    score += 2
                elif ind['rsi'] > RSI_OVERBOUGHT:
                    score -= 1
                    
                # Volume
                if ind['volume_ratio'] > VOLUME_THRESHOLD:
                    score += 2
                    
                # MA
                if ind['price'] > ind['ma20']:
                    score += 1
                if ind['price'] > ind['ma50']:
                    score += 1
                    
                # Price change
                if ind['change'] > 2:
                    score += 1
                elif ind['change'] < -2:
                    score -= 1

                results.append({
                    'symbol': symbol,
                    'company': get_company_name(symbol),
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

    def get_latest_price(self, symbol: str) -> Optional[Dict]:
        """
        Mendapatkan harga terbaru
        """
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

    def get_top_by_volume(self, limit: int = 5) -> List[Dict]:
        """
        Mendapatkan saham dengan volume tertinggi
        """
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
            except Exception:
                continue
        results.sort(key=lambda x: x['volume'], reverse=True)
        return results[:limit]

    def clear_cache(self) -> None:
        """Bersihkan cache"""
        self.cache = {}
        self._save_cache()
        logger.info("🗑️ Cache dibersihkan")

# ============================================
# SIGNAL GENERATOR
# ============================================

class SignalGenerator:
    """Generator sinyal trading"""
    
    def __init__(self):
        self.screener = Screener()

    def generate_signal(self, symbol: str) -> Optional[Dict]:
        """
        Generate sinyal untuk satu saham
        """
        data = self.screener.get_stock_data(symbol)
        if data is None:
            return None

        ind = self.screener.calculate_indicators(data)
        if ind is None:
            return None

        signal = 'HOLD'
        reasons = []
        strength = 0

        # RSI Signal
        if ind['rsi'] < RSI_OVERSOLD:
            signal = 'BUY'
            strength += 2
            reasons.append(f'RSI Oversold ({ind["rsi"]:.1f})')
        elif ind['rsi'] > RSI_OVERBOUGHT:
            signal = 'SELL'
            strength += 2
            reasons.append(f'RSI Overbought ({ind["rsi"]:.1f})')

        # MA Crossover
        if ind['ma20'] > ind['ma50'] and ind['price'] > ind['ma20']:
            if signal == 'HOLD':
                signal = 'BUY'
            strength += 1
            reasons.append('Golden Cross (MA20 > MA50)')
        elif ind['ma20'] < ind['ma50'] and ind['price'] < ind['ma20']:
            if signal == 'HOLD':
                signal = 'SELL'
            strength += 1
            reasons.append('Death Cross (MA20 < MA50)')

        # Volume Signal
        if ind['volume_ratio'] > 2.0:
            if signal == 'HOLD':
                signal = 'BUY' if ind['change'] > 0 else 'SELL'
            strength += 1
            reasons.append(f'Volume Tinggi ({ind["volume_ratio"]:.1f}x)')

        # Price Breakout
        if ind['price'] > ind['high'] * 1.02:
            if signal == 'HOLD':
                signal = 'BUY'
            strength += 1
            reasons.append('Breakout Resistance')
        elif ind['price'] < ind['low'] * 0.98:
            if signal == 'HOLD':
                signal = 'SELL'
            strength += 1
            reasons.append('Breakdown Support')

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

    def check_all_signals(self) -> Dict[str, Dict]:
        """
        Cek sinyal untuk semua saham
        """
        signals = {}
        for symbol in self.screener.watchlist:
            try:
                signal = self.generate_signal(symbol)
                if signal:
                    signals[symbol] = signal
            except Exception as e:
                logger.error(f"Error generating signal for {symbol}: {str(e)}")
        return signals

# ============================================
# CHART GENERATOR
# ============================================

class ChartGenerator:
    """Pembuat chart saham"""
    
    def __init__(self):
        self.chart_dir = 'charts'
        os.makedirs(self.chart_dir, exist_ok=True)

    def create_chart(self, symbol: str, period: str = '1mo') -> Optional[str]:
        """
        Membuat chart untuk saham
        """
        try:
            ticker = yf.Ticker(f"{symbol}.JK")
            data = ticker.history(period=period)
            
            if data.empty:
                logger.warning(f"Data kosong untuk chart {symbol}")
                return None

            # Setup figure
            fig, (ax1, ax2) = plt.subplots(
                2, 1, 
                figsize=(12, 8), 
                gridspec_kw={'height_ratios': [3, 1]},
                facecolor='white'
            )
            
            # ===== Price Chart =====
            # Price line
            ax1.plot(data.index, data['Close'], 
                    label='Close', color='#1f77b4', linewidth=2)
            
            # Moving averages
            ax1.plot(data.index, data['Close'].rolling(window=20).mean(), 
                    label='MA20', color='#ff7f0e', linestyle='--', linewidth=1.5)
            ax1.plot(data.index, data['Close'].rolling(window=50).mean(), 
                    label='MA50', color='#d62728', linestyle='--', linewidth=1.5)
            
            # Volume bars
            ax1.bar(data.index, data['Volume'], 
                   alpha=0.2, color='#7f7f7f', label='Volume')
            
            # Format
            ax1.set_title(f'{symbol} - {get_company_name(symbol)}', 
                         fontsize=14, fontweight='bold', pad=10)
            ax1.set_ylabel('Harga (Rp)', fontsize=11)
            ax1.legend(loc='upper left')
            ax1.grid(True, alpha=0.2)
            
            # X-axis format
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))
            ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            
            # ===== RSI Chart =====
            # Calculate RSI
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Plot RSI
            ax2.plot(data.index, rsi, label='RSI', color='#9467bd', linewidth=2)
            
            # RSI levels
            ax2.axhline(y=70, color='#d62728', linestyle='--', alpha=0.5, label='Overbought')
            ax2.axhline(y=30, color='#2ca02c', linestyle='--', alpha=0.5, label='Oversold')
            ax2.fill_between(data.index, 30, 70, alpha=0.1, color='gray')
            
            # Format
            ax2.set_title('RSI (14)', fontsize=12)
            ax2.set_ylabel('RSI', fontsize=11)
            ax2.set_ylim(0, 100)
            ax2.legend(loc='upper left')
            ax2.grid(True, alpha=0.2)
            
            # X-axis format
            ax2.xaxis.set_major_formatter(mdates.DateFormatter('%d-%m-%Y'))
            ax2.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            
            # Layout
            plt.tight_layout()
            
            # Save chart
            filename = f"{self.chart_dir}/{symbol}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='white')
            plt.close()
            
            # Cleanup old charts
            self._cleanup_old_charts(symbol)
            
            logger.info(f"📊 Chart {symbol} berhasil dibuat")
            return filename
            
        except Exception as e:
            logger.error(f"Error creating chart {symbol}: {str(e)}")
            return None

    def _cleanup_old_charts(self, symbol: str, keep: int = 5) -> None:
        """Hapus chart lama"""
        try:
            files = [f for f in os.listdir(self.chart_dir) if f.startswith(symbol)]
            if len(files) > keep:
                files.sort()
                for f in files[:-keep]:
                    os.remove(os.path.join(self.chart_dir, f))
                    logger.debug(f"🗑️ Hapus chart lama: {f}")
        except Exception as e:
            logger.warning(f"Error cleanup charts: {str(e)}")

# ============================================
# BOT UTAMA
# ============================================

class SahamBot:
    """Bot Telegram utama"""
    
    def __init__(self):
        self.bot = Bot(token=TELEGRAM_TOKEN)
        self.screener = Screener()
        self.signal_gen = SignalGenerator()
        self.chart_gen = ChartGenerator()
        self.watchlist = WATCHLIST.copy()
        self.running = False
        self.job = None
        self.start_time = datetime.now()
        self.stats = {
            'total_commands': 0,
            'last_command': None,
            'signals_sent': 0
        }
        
        logger.info("✅ Bot Saham Danar v2.0 siap digunakan")

    def _update_stats(self, command: str) -> None:
        """Update statistik"""
        self.stats['total_commands'] += 1
        self.stats['last_command'] = {
            'command': command,
            'time': get_timestamp(),
            'user': None
        }

    # ============================================
    # COMMAND HANDLERS
    # ============================================

    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /start"""
        self._update_stats('start')
        
        welcome_msg = f"""
🤖 *Bot Saham Danar v2.0*

📊 Bot monitoring saham Indonesia dengan sinyal trading otomatis.

*📋 Perintah yang tersedia:*
/start - Menampilkan menu utama
/help - Bantuan lengkap
/screener - Screening semua saham
/watchlist - Daftar saham yang dimonitor
/add SYMBOL - Tambah saham ke watchlist
/remove SYMBOL - Hapus saham dari watchlist
/signal SYMBOL - Cek sinyal saham
/chart SYMBOL - Tampilkan chart saham
/top - Top 5 saham berdasarkan volume
/check - Cek semua sinyal
/stats - Statistik bot
/refresh - Refresh data cache
/start_bot - Mulai monitoring otomatis
/stop_bot - Stop monitoring otomatis

*📊 Status:*
🟢 Bot Online
📋 Watchlist: {len(self.watchlist)} saham
🕐 Uptime: {get_uptime(self.start_time)}
        """
        await update.message.reply_text(welcome_msg, parse_mode='Markdown')

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /help"""
        self._update_stats('help')
        
        help_msg = """
📚 *Bantuan Bot Saham Danar*

*🎯 Cara Penggunaan:*
1. Tambahkan saham ke watchlist: `/add BBCA`
2. Cek sinyal: `/signal BBCA`  
3. Aktifkan monitoring: `/start_bot`
4. Bot akan kirim notifikasi saat ada sinyal

*📊 Sumber Data:*
• Yahoo Finance (real-time)
• Cache diperbarui setiap 5 menit

*💡 Tips:*
• Gunakan `/screener` untuk melihat semua saham potensial
• Aktifkan notifikasi di channel untuk update real-time
• Data disimpan di cache untuk performa lebih baik

*⚠️ Disclaimer:*
Bot ini hanya untuk informasi, bukan rekomendasi investasi.
Lakukan riset sendiri sebelum mengambil keputusan trading.
        """
        await update.message.reply_text(help_msg, parse_mode='Markdown')

    async def screener(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /screener"""
        self._update_stats('screener')
        
        msg = await update.message.reply_text("🔍 *Sedang melakukan screening...*", parse_mode='Markdown')
        
        try:
            results = self.screener.screen_all()
            if not results:
                await msg.edit_text("⚠️ Tidak ada saham yang memenuhi kriteria saat ini.")
                return
                
            message = "📊 *Hasil Screener Saham*\n\n"
            for stock in results[:10]:
                score_emoji = "🔴" if stock['score'] < 0 else "🟢" if stock['score'] > 0 else "⚪"
                message += f"{score_emoji} *{stock['symbol']}* - {stock['company']}\n"
                message += f"   💰 {format_price(stock['price'])} ({stock['change']:+.2f}%)\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 RSI: {stock['rsi']:.1f}\n"
                message += f"   ⭐ Score: {stock['score']}\n\n"
                
            await msg.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Screener error: {str(e)}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /watchlist"""
        self._update_stats('watchlist')
        
        if not self.watchlist:
            await update.message.reply_text("📋 Watchlist kosong. Tambahkan dengan /add SYMBOL")
            return
            
        message = "📋 *Watchlist Saham*\n\n"
        for symbol in self.watchlist:
            price_data = self.screener.get_latest_price(symbol)
            if price_data:
                change_emoji = "🟢" if price_data['change'] >= 0 else "🔴"
                message += f"{change_emoji} *{symbol}* ({get_company_name(symbol)})\n"
                message += f"   💰 {format_price(price_data['price'])} ({price_data['change']:+.2f}%)\n"
            else:
                message += f"❌ *{symbol}*: Data tidak tersedia\n"
            message += "\n"
                
        await update.message.reply_text(message, parse_mode='Markdown')

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /add SYMBOL"""
        self._update_stats('add')
        
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /add SYMBOL (contoh: /add BBCA)")
            return
            
        symbol = context.args[0].upper()
        if not is_valid_symbol(symbol):
            await update.message.reply_text("❌ Kode saham tidak valid! Gunakan 3-5 huruf kapital.")
            return
            
        if symbol not in self.watchlist:
            self.watchlist.append(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* ({get_company_name(symbol)}) berhasil ditambahkan ke watchlist!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"ℹ️ *{symbol}* sudah ada di watchlist.", parse_mode='Markdown')

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /remove SYMBOL"""
        self._update_stats('remove')
        
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /remove SYMBOL (contoh: /remove BBCA)")
            return
            
        symbol = context.args[0].upper()
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ *{symbol}* berhasil dihapus dari watchlist!", parse_mode='Markdown')
        else:
            await update.message.reply_text(f"❌ *{symbol}* tidak ditemukan di watchlist.", parse_mode='Markdown')

    async def signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /signal SYMBOL"""
        self._update_stats('signal')
        
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /signal SYMBOL (contoh: /signal BBCA)")
            return
            
        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📈 *Menganalisis {symbol}...*", parse_mode='Markdown')
        
        try:
            signal = self.signal_gen.generate_signal(symbol)
            if not signal:
                await msg.edit_text(f"❌ Data untuk *{symbol}* tidak tersedia.", parse_mode='Markdown')
                return
                
            signal_emoji = "🟢" if signal['signal'] == 'BUY' else "🔴" if signal['signal'] == 'SELL' else "⚪"
            signal_text = "🔴 *JUAL*" if signal['signal'] == 'SELL' else "🟢 *BELI*" if signal['signal'] == 'BUY' else "⚪ *TAHAN*"
                
            message = f"📊 *Analisis {symbol}* - {get_company_name(symbol)}\n\n"
            message += f"💰 Harga: {format_price(signal['price'])}\n"
            message += f"📊 Perubahan: {signal['change']:+.2f}%\n"
            message += f"📈 RSI: {signal['rsi']:.1f}\n"
            message += f"📊 Volume: {format_volume(signal['volume'])}\n"
            message += f"📉 MA20: {format_price(signal['ma20'])}\n"
            message += f"📉 MA50: {format_price(signal['ma50'])}\n\n"
            message += f"🎯 *Rekomendasi:* {signal_text}\n"
            message += f"💡 *Alasan:* {signal['reason']}\n"
            message += f"💪 *Strength:* {signal['strength']}/5"
            
            await msg.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Signal error: {str(e)}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /chart SYMBOL"""
        self._update_stats('chart')
        
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /chart SYMBOL (contoh: /chart BBCA)")
            return
            
        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📊 *Membuat chart untuk {symbol}...*", parse_mode='Markdown')
        
        try:
            chart_path = self.chart_gen.create_chart(symbol)
            if chart_path:
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo, 
                        caption=f"📈 Chart {symbol} - {get_company_name(symbol)}\n🕐 {get_timestamp()}"
                    )
                os.remove(chart_path)
                await msg.delete()
            else:
                await msg.edit_text(f"❌ Gagal membuat chart untuk *{symbol}*.", parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Chart error: {str(e)}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /top"""
        self._update_stats('top')
        
        msg = await update.message.reply_text("📊 *Mencari saham dengan volume tertinggi...*", parse_mode='Markdown')
        
        try:
            top_stocks = self.screener.get_top_by_volume(5)
            if not top_stocks:
                await msg.edit_text("❌ Data tidak tersedia.")
                return
                
            message = "🔥 *Top 5 Saham Berdasarkan Volume*\n\n"
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
        """Handler /check"""
        self._update_stats('check')
        
        msg = await update.message.reply_text("🔍 *Mengecek semua sinyal...*", parse_mode='Markdown')
        
        try:
            signals = self.signal_gen.check_all_signals()
            if not signals:
                await msg.edit_text("✅ Tidak ada sinyal yang terdeteksi saat ini.")
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
                    message += f"• *{s['symbol']}* - {s['reason']} (strength: {s['strength']})\n"
                    
            if sell_signals:
                message += "\n*🔴 Sinyal JUAL:*\n"
                for s in sell_signals[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']} (strength: {s['strength']})\n"
                    
            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /stats"""
        self._update_stats('stats')
        
        watchlist_count = len(self.watchlist)
        
        stats_msg = f"""
📊 *Statistik Bot Saham Danar v2.0*

🕐 Uptime: {get_uptime(self.start_time)}
📋 Watchlist: {watchlist_count} saham
🔄 Monitoring: {'✅ Aktif' if self.running else '⛔ Nonaktif'}

*📊 Penggunaan:*
📝 Total commands: {self.stats['total_commands']}
📬 Signals sent: {self.stats['signals_sent']}
🕐 Last command: {self.stats['last_command']['command'] if self.stats['last_command'] else 'Belum ada'}

*📈 Data:*
🗃️ Cache: {len(self.screener.cache)} items
📊 Total saham: {len(WATCHLIST)}
🔄 Last update: {get_timestamp()}

*🖥️ Server:*
🐍 Python: {sys.version.split()[0]}
📦 Platform: Railway.app
🌍 Environment: {ENVIRONMENT}
        """
        await update.message.reply_text(stats_msg, parse_mode='Markdown')

    async def refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /refresh"""
        self._update_stats('refresh')
        
        msg = await update.message.reply_text("🔄 *Merefresh data cache...*", parse_mode='Markdown')
        
        try:
            self.screener.clear_cache()
            await msg.edit_text("✅ *Data cache berhasil direfresh!*", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /start_bot"""
        self._update_stats('start_bot')
        
        if not self.running:
            self.running = True
            self.job = context.job_queue.run_repeating(
                self._monitor_stocks,
                interval=300,  # 5 menit
                first=10
            )
            await update.message.reply_text(
                "✅ *Monitoring otomatis dimulai!*\n"
                "Bot akan mengecek sinyal setiap 5 menit.\n"
                "Notifikasi akan dikirim ke channel jika ada sinyal.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "⚠️ Monitoring sudah aktif.\n"
                f"Interval: {self.job.interval if self.job else 300} detik",
                parse_mode='Markdown'
            )

    async def stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler /stop_bot"""
        self._update_stats('stop_bot')
        
        if self.running and self.job:
            self.running = False
            self.job.schedule_removal()
            self.job = None
            await update.message.reply_text(
                "⏹️ *Monitoring otomatis dihentikan.*",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text(
                "ℹ️ Monitoring tidak aktif.",
                parse_mode='Markdown'
            )

    # ============================================
    # MONITORING FUNCTION
    # ============================================

    async def _monitor_stocks(self, context: ContextTypes.DEFAULT_TYPE):
        """Fungsi monitoring otomatis"""
        try:
            logger.info("🔄 Running automatic monitoring...")
            signals = self.signal_gen.check_all_signals()
            
            for symbol, signal in signals.items():
                if symbol in self.watchlist and signal['signal'] != 'HOLD':
                    # Cek apakah sinyal cukup kuat
                    if signal['strength'] < 2:
                        continue
                        
                    signal_emoji = "🟢" if signal['signal'] == 'BUY' else "🔴"
                    message = f"{signal_emoji} *SINYAL {signal['signal']} - {symbol}*\n\n"
                    message += f"💰 {format_price(signal['price'])}\n"
                    message += f"📊 {signal['change']:+.2f}%\n"
                    message += f"📈 RSI: {signal['rsi']:.1f}\n"
                    message += f"💪 Strength: {signal['strength']}/5\n"
                    message += f"💡 {signal['reason']}\n"
                    message += f"🕐 {get_timestamp()}"

                    if CHANNEL_ID:
                        try:
                            await self.bot.send_message(
                                chat_id=CHANNEL_ID,
                                text=message,
                                parse_mode='Markdown'
                            )
                            self.stats['signals_sent'] += 1
                            logger.info(f"📬 Signal sent for {symbol}: {signal['signal']}")
                            
                            # Kirim chart untuk sinyal kuat
                            if signal['strength'] >= 3:
                                chart_path = self.chart_gen.create_chart(symbol)
                                if chart_path:
                                    with open(chart_path, 'rb') as photo:
                                        await self.bot.send_photo(
                                            chat_id=CHANNEL_ID,
                                            photo=photo,
                                            caption=f"📈 Chart {symbol}"
                                        )
                                    os.remove(chart_path)
                                    
                        except Exception as e:
                            logger.error(f"Error sending signal for {symbol}: {str(e)}")
                            
        except Exception as e:
            logger.error(f"Error in monitoring: {str(e)}")
            logger.error(traceback.format_exc())

    # ============================================
    # ERROR HANDLER
    # ============================================

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handler untuk error"""
        logger.error(f"Update {update} caused error: {context.error}")
        logger.error(traceback.format_exc())
        
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text(
                    "❌ Terjadi kesalahan. Tim pengembang telah diberitahu.\n"
                    "Silakan coba lagi nanti."
                )
        except:
            pass

    # ============================================
    # RUN BOT
    # ============================================

    def run(self):
        """Menjalankan bot"""
        try:
            # Create directories
            os.makedirs('charts', exist_ok=True)
            os.makedirs('data', exist_ok=True)
            os.makedirs('logs', exist_ok=True)

            # Setup application
            application = Application.builder().token(TELEGRAM_TOKEN).build()

            # Register command handlers
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

            # Error handler
            application.add_error_handler(self._error_handler)

            # Run
            logger.info(f"🚀 Starting bot on port {PORT}...")
            print("=" * 70)
            print("🚀 BOT BERJALAN!")
            print(f"📌 Bot: @{(application.bot.get_me()).username}")
            print(f"📌 Watchlist: {len(self.watchlist)} saham")
            print(f"📌 Port: {PORT}")
            print("=" * 70)
            
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=2.0,
                timeout=30
            )
            
        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            logger.error(traceback.format_exc())
            sys.exit(1)

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    try:
        bot = SahamBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n⏹️ Bot dihentikan oleh user")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        sys.exit(1)
