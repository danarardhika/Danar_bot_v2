#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Saham Danar v2.3 - ALL IN ONE
Semua kode dalam 1 file (tanpa import chart.py)
"""

import os
import sys
import json
import logging
import time
import traceback
import random
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
from dotenv import load_dotenv

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
# DATA REALISTIS
# ============================================

REALISTIC_DATA = {
    'BBCA': {'price': 9750, 'change': 0.5, 'volume': 15000000, 'rsi': 55, 'ma20': 9650, 'ma50': 9500, 'high': 9800, 'low': 9600},
    'BBRI': {'price': 4850, 'change': 0.3, 'volume': 20000000, 'rsi': 52, 'ma20': 4800, 'ma50': 4750, 'high': 4900, 'low': 4780},
    'BMRI': {'price': 6250, 'change': 0.2, 'volume': 12000000, 'rsi': 50, 'ma20': 6200, 'ma50': 6150, 'high': 6300, 'low': 6180},
    'TLKM': {'price': 3850, 'change': -0.1, 'volume': 18000000, 'rsi': 48, 'ma20': 3880, 'ma50': 3900, 'high': 3900, 'low': 3820},
    'ASII': {'price': 7250, 'change': 0.8, 'volume': 8000000, 'rsi': 58, 'ma20': 7150, 'ma50': 7050, 'high': 7300, 'low': 7100},
    'UNVR': {'price': 4250, 'change': -0.5, 'volume': 5000000, 'rsi': 45, 'ma20': 4300, 'ma50': 4350, 'high': 4350, 'low': 4200},
    'GOTO': {'price': 82, 'change': -1.2, 'volume': 50000000, 'rsi': 40, 'ma20': 85, 'ma50': 88, 'high': 86, 'low': 80},
    'ADMR': {'price': 1400, 'change': 1.5, 'volume': 3000000, 'rsi': 62, 'ma20': 1350, 'ma50': 1300, 'high': 1420, 'low': 1380},
    'BRPT': {'price': 980, 'change': 0.7, 'volume': 4000000, 'rsi': 56, 'ma20': 960, 'ma50': 940, 'high': 1000, 'low': 970},
    'PTBA': {'price': 3200, 'change': -0.3, 'volume': 6000000, 'rsi': 49, 'ma20': 3250, 'ma50': 3300, 'high': 3280, 'low': 3180},
    'BSDE': {'price': 1050, 'change': 1.2, 'volume': 8000000, 'rsi': 60, 'ma20': 1020, 'ma50': 1000, 'high': 1080, 'low': 1010},
    'SMGR': {'price': 1545, 'change': 0.5, 'volume': 84000, 'rsi': 60, 'ma20': 1526, 'ma50': 1500, 'high': 1555, 'low': 1525}
}

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
    'PTBA': 'Bukit Asam',
    'BSDE': 'Bumi Serpong Damai',
    'SMGR': 'Semen Indonesia'
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

# ============================================
# SCREENER
# ============================================

class Screener:
    def __init__(self):
        self.cache_dir = 'data'
        os.makedirs(self.cache_dir, exist_ok=True)
        self.cache_file = os.path.join(self.cache_dir, 'stock_cache.json')
        self.cache = safe_json_load(self.cache_file, {})
        self.watchlist = WATCHLIST.copy()
        self.use_fallback = False
        self.last_error = None

    def save_cache(self):
        safe_json_save(self.cache_file, self.cache)

    def get_stock_data(self, symbol, period='1mo', max_retries=2):
        cache_key = f"{symbol}_{period}"
        
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

        for attempt in range(max_retries):
            try:
                logger.info(f"📥 Mengambil data {symbol} (attempt {attempt+1}/{max_retries})")
                ticker = yf.Ticker(f"{symbol}.JK")
                data = ticker.history(period=period, timeout=15)
                
                if not data.empty and len(data) > 5:
                    if data['Close'].iloc[-1] > 0 and data['Close'].iloc[-1] < 1000000:
                        self.cache[cache_key] = {
                            'timestamp': datetime.now().isoformat(),
                            'data': data.to_dict('list')
                        }
                        self.save_cache()
                        self.use_fallback = False
                        return data
                    else:
                        logger.warning(f"Data {symbol} tidak valid")
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {str(e)}")
                time.sleep(2)

        logger.warning(f"⚠️ Menggunakan data realistis untuk {symbol}")
        self.use_fallback = True
        return self._create_realistic_data(symbol, period)

    def _create_realistic_data(self, symbol, period='1mo'):
        try:
            data = REALISTIC_DATA.get(symbol)
            if not data:
                data = {'price': 5000, 'change': 0, 'volume': 10000000, 'rsi': 50, 'ma20': 5000, 'ma50': 5000, 'high': 5100, 'low': 4900}
            
            dates = pd.date_range(end=datetime.now(), periods=30, freq='D')
            base_price = data['price']
            prices = []
            for i in range(30):
                change = random.uniform(-0.02, 0.02)
                if i == 0:
                    prices.append(base_price)
                else:
                    prices.append(prices[-1] * (1 + change))
            
            last_price = prices[-1]
            prices = [p * (data['price'] / last_price) for p in prices]
            volumes = [data['volume'] * random.uniform(0.6, 1.4) for _ in range(30)]
            
            return pd.DataFrame({
                'Open': [p * random.uniform(0.98, 0.99) for p in prices],
                'High': [p * random.uniform(1.01, 1.02) for p in prices],
                'Low': [p * random.uniform(0.98, 0.99) for p in prices],
                'Close': prices,
                'Volume': volumes
            }, index=dates)
        except Exception as e:
            logger.error(f"Error creating realistic data: {str(e)}")
            return None

    def calculate_indicators(self, data):
        if data is None or len(data) < 5:
            return None

        try:
            close = data['Close']
            
            if len(close) >= 14:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
            else:
                rsi_val = 50
            
            if len(close) >= 20:
                ma20_val = close.rolling(window=20).mean().iloc[-1]
            else:
                ma20_val = close.iloc[-1]
                
            if len(close) >= 50:
                ma50_val = close.rolling(window=50).mean().iloc[-1]
            else:
                ma50_val = close.iloc[-1]
            
            if len(data) >= 10:
                avg_volume = data['Volume'].rolling(window=10).mean().iloc[-1]
            else:
                avg_volume = data['Volume'].iloc[-1]
            volume_ratio = data['Volume'].iloc[-1] / avg_volume if avg_volume > 0 else 1
            
            change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0
            
            rsi_val = max(0, min(100, rsi_val))
            
            return {
                'price': float(close.iloc[-1]),
                'change': float(change),
                'volume': float(data['Volume'].iloc[-1]),
                'volume_ratio': float(volume_ratio),
                'rsi': float(rsi_val),
                'ma20': float(ma20_val),
                'ma50': float(ma50_val),
                'high': float(data['High'].iloc[-1]) if 'High' in data else float(close.iloc[-1] * 1.02),
                'low': float(data['Low'].iloc[-1]) if 'Low' in data else float(close.iloc[-1] * 0.98)
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def screen_all(self):
        results = []
        for symbol in self.watchlist:
            try:
                data = self.get_stock_data(symbol)
                if data is None or data.empty:
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
        if data is None or data.empty:
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
                if data is None or data.empty:
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
        self.use_fallback = False

# ============================================
# SIGNAL GENERATOR
# ============================================

class SignalGenerator:
    def __init__(self):
        self.screener = Screener()

    def generate_signal(self, symbol):
        try:
            data = self.screener.get_stock_data(symbol)
            if data is None or data.empty:
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

            if ind['change'] > 3:
                if signal == 'HOLD':
                    signal = 'BUY'
                strength += 1
                reasons.append(f'Naik {ind["change"]:.1f}%')
            elif ind['change'] < -3:
                if signal == 'HOLD':
                    signal = 'SELL'
                strength += 1
                reasons.append(f'Turun {abs(ind["change"]):.1f}%')

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
# CHART GENERATOR (LANGSUNG DI SINI)
# ============================================

class ChartGenerator:
    def __init__(self):
        self.chart_dir = 'charts'
        os.makedirs(self.chart_dir, exist_ok=True)
        plt.style.use('dark_background')
        
    def create_chart(self, symbol: str, period: str = '3mo') -> str:
        """Membuat chart lengkap dengan indikator teknikal"""
        try:
            ticker = yf.Ticker(f"{symbol}.JK")
            data = ticker.history(period=period)
            
            if data.empty or len(data) < 30:
                logger.warning(f"Data tidak cukup untuk {symbol}")
                return None
            
            # Buat figure dengan 4 subplot
            fig = plt.figure(figsize=(16, 12))
            fig.patch.set_facecolor('#0d1117')
            gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.15)
            
            # ===== PLOT 1: Harga =====
            ax1 = fig.add_subplot(gs[0])
            ax1.set_facecolor('#0d1117')
            
            ax1.plot(data.index, data['Close'], color='#00d4ff', linewidth=2, label='Close')
            
            sma20 = data['Close'].rolling(window=20).mean()
            sma50 = data['Close'].rolling(window=50).mean()
            ax1.plot(data.index, sma20, color='#ff6b6b', linewidth=1.5, linestyle='--', label='SMA 20')
            ax1.plot(data.index, sma50, color='#ffd93d', linewidth=1.5, linestyle='--', label='SMA 50')
            
            bb_middle = data['Close'].rolling(window=20).mean()
            bb_std = data['Close'].rolling(window=20).std()
            bb_upper = bb_middle + (bb_std * 2)
            bb_lower = bb_middle - (bb_std * 2)
            
            ax1.fill_between(data.index, bb_upper, bb_lower, alpha=0.15, color='#6c5ce7', label='Bollinger (20,2)')
            ax1.plot(data.index, bb_upper, color='#6c5ce7', linewidth=1, alpha=0.5, linestyle=':')
            ax1.plot(data.index, bb_lower, color='#6c5ce7', linewidth=1, alpha=0.5, linestyle=':')
            
            # Info
            last = data.iloc[-1]
            info_text = f"Op: {last['Open']:.0f}, Hi: {last['High']:.0f}, Lo: {last['Low']:.0f}, Cl: {last['Close']:.0f}"
            ax1.text(0.02, 0.98, info_text, transform=ax1.transAxes, fontsize=10, color='#ffffff', 
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax1.set_title(f'{symbol} Custom Chart', color='#ffffff', fontsize=14, fontweight='bold', pad=20)
            ax1.set_ylabel('Harga', color='#a0aec0', fontsize=10)
            ax1.grid(True, alpha=0.15, color='#2d3748')
            ax1.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            ax1.tick_params(colors='#a0aec0')
            
            # ===== PLOT 2: MACD =====
            ax2 = fig.add_subplot(gs[1])
            ax2.set_facecolor('#0d1117')
            
            exp1 = data['Close'].ewm(span=12, adjust=False).mean()
            exp2 = data['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            macd_signal = macd.ewm(span=9, adjust=False).mean()
            macd_hist = macd - macd_signal
            
            ax2.plot(data.index, macd, color='#00d4ff', linewidth=1.5, label='MACD (26, 12)')
            ax2.plot(data.index, macd_signal, color='#ffd93d', linewidth=1.5, label='EXP (9)')
            colors = ['#00d4ff' if val >= 0 else '#ff6b6b' for val in macd_hist]
            ax2.bar(data.index, macd_hist, color=colors, alpha=0.5, width=0.8)
            ax2.axhline(y=0, color='#4a5568', linewidth=0.5)
            
            macd_text = f"MACD (26, 12): {macd.iloc[-1]:.2f}  EXP (9): {macd_signal.iloc[-1]:.2f}"
            ax2.text(0.02, 0.92, macd_text, transform=ax2.transAxes, fontsize=9, color='#a0aec0',
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax2.set_ylabel('MACD', color='#a0aec0', fontsize=10)
            ax2.grid(True, alpha=0.15, color='#2d3748')
            ax2.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax2.tick_params(colors='#a0aec0')
            
            # ===== PLOT 3: RSI =====
            ax3 = fig.add_subplot(gs[2])
            ax3.set_facecolor('#0d1117')
            
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            ax3.plot(data.index, rsi, color='#ff6b6b', linewidth=1.5, label='RSI (14)')
            ax3.axhline(y=70, color='#ff6b6b', linewidth=0.5, linestyle='--', alpha=0.5)
            ax3.axhline(y=30, color='#00d4ff', linewidth=0.5, linestyle='--', alpha=0.5)
            ax3.fill_between(data.index, 70, 100, alpha=0.1, color='#ff6b6b')
            ax3.fill_between(data.index, 0, 30, alpha=0.1, color='#00d4ff')
            
            rsi_text = f"RSI (14): {rsi.iloc[-1]:.0f}"
            ax3.text(0.02, 0.92, rsi_text, transform=ax3.transAxes, fontsize=9, color='#a0aec0',
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax3.set_ylabel('RSI', color='#a0aec0', fontsize=10)
            ax3.set_ylim(0, 100)
            ax3.grid(True, alpha=0.15, color='#2d3748')
            ax3.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax3.tick_params(colors='#a0aec0')
            
            # ===== PLOT 4: Stochastic =====
            ax4 = fig.add_subplot(gs[3])
            ax4.set_facecolor('#0d1117')
            
            low_14 = data['Low'].rolling(14).min()
            high_14 = data['High'].rolling(14).max()
            stoch_k = 100 * ((data['Close'] - low_14) / (high_14 - low_14))
            stoch_d = stoch_k.rolling(3).mean()
            
            ax4.plot(data.index, stoch_k, color='#00d4ff', linewidth=1.5, label='%K (14)')
            ax4.plot(data.index, stoch_d, color='#ffd93d', linewidth=1.5, label='%D (3)')
            ax4.axhline(y=80, color='#ff6b6b', linewidth=0.5, linestyle='--', alpha=0.5)
            ax4.axhline(y=20, color='#00d4ff', linewidth=0.5, linestyle='--', alpha=0.5)
            ax4.fill_between(data.index, 80, 100, alpha=0.1, color='#ff6b6b')
            ax4.fill_between(data.index, 0, 20, alpha=0.1, color='#00d4ff')
            
            stoch_text = f"Stoch %K (14, 3): {stoch_k.iloc[-1]:.2f}  %D (3): {stoch_d.iloc[-1]:.2f}"
            ax4.text(0.02, 0.92, stoch_text, transform=ax4.transAxes, fontsize=9, color='#a0aec0',
                    verticalalignment='top', bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax4.set_ylabel('Stochastic', color='#a0aec0', fontsize=10)
            ax4.set_ylim(0, 100)
            ax4.grid(True, alpha=0.15, color='#2d3748')
            ax4.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax4.tick_params(colors='#a0aec0')
            
            # Format x-axis
            for ax in [ax1, ax2, ax3, ax4]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
                ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
                ax.tick_params(axis='x', colors='#a0aec0')
            
            # Footer
            footer_text = f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WITA"
            fig.text(0.5, 0.01, footer_text, ha='center', fontsize=8, color='#4a5568')
            
            plt.tight_layout()
            filename = f"{self.chart_dir}/{symbol}_custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#0d1117')
            plt.close()
            
            logger.info(f"✅ Chart custom {symbol} berhasil dibuat")
            return filename
            
        except Exception as e:
            logger.error(f"Error creating custom chart: {str(e)}")
            return None

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
        status = "⚠️ Mode Data Realistis" if self.screener.use_fallback else "✅ Data Real-time"
        await update.message.reply_text(
            f"🤖 *Bot Saham Danar v2.3*\n\n"
            f"📊 Status: {status}\n"
            f"📋 Watchlist: {len(self.watchlist)} saham\n"
            f"🕐 Uptime: {self.get_uptime()}\n\n"
            f"📌 Perintah: /help untuk bantuan",
            parse_mode='Markdown'
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "📚 *Bantuan Bot v2.3*\n\n"
            "*📊 Perintah Dasar:*\n"
            "/start - Menu utama\n"
            "/help - Bantuan ini\n"
            "/screener - Screening saham\n"
            "/watchlist - Daftar saham\n"
            "/add SYMBOL - Tambah saham\n"
            "/remove SYMBOL - Hapus saham\n"
            "/signal SYMBOL - Cek sinyal\n"
            "/top - Top 5 volume\n"
            "/check - Cek semua sinyal\n"
            "/stats - Statistik bot\n"
            "/refresh - Refresh data\n\n"
            "*📈 Chart:*\n"
            "/chart SYMBOL - Chart sederhana\n"
            "/chart_custom SYMBOL - Chart lengkap\n\n"
            "*🤖 Monitoring:*\n"
            "/start_bot - Mulai monitoring\n"
            "/stop_bot - Stop monitoring",
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

            if self.screener.use_fallback:
                message += "\n⚠️ *Data Realistis* (Yahoo Finance tidak tersedia)"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
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
            await update.message.reply_text("❌ Gunakan: /add SYMBOL")
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
            await update.message.reply_text("❌ Gunakan: /signal SYMBOL")
            return

        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📈 *Menganalisis {symbol}...*", parse_mode='Markdown')

        try:
            signal = self.signal_gen.generate_signal(symbol)
            if not signal:
                await msg.edit_text(f"❌ Data *{symbol}* tidak tersedia.", parse_mode='Markdown')
                return

            signal_text = "🔴 *JUAL*" if signal['signal'] == 'SELL' else "🟢 *BELI*" if signal['signal'] == 'BUY' else "⚪ *TAHAN*"
            fallback_note = "\n⚠️ *Data Realistis*" if self.screener.use_fallback else ""

            message = f"📊 *Analisis {symbol}*\n\n"
            message += f"💰 Harga: {format_price(signal['price'])}\n"
            message += f"📊 Perubahan: {signal['change']:+.2f}%\n"
            message += f"📈 RSI: {signal['rsi']:.1f}\n"
            message += f"📊 Volume: {format_volume(signal['volume'])}\n"
            message += f"📉 MA20: {format_price(signal['ma20'])}\n"
            message += f"📉 MA50: {format_price(signal['ma50'])}\n\n"
            message += f"🎯 *Rekomendasi:* {signal_text}\n"
            message += f"💡 *Alasan:* {signal['reason']}\n"
            message += f"💪 *Strength:* {signal['strength']}/5"
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
            data = self.screener.get_stock_data(symbol, period='1mo')
            if data is None or data.empty:
                await msg.edit_text(f"❌ Data *{symbol}* tidak tersedia.", parse_mode='Markdown')
                return

            fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(10, 8), gridspec_kw={'height_ratios': [3, 1]})
            ax1.plot(data.index, data['Close'], label='Close', linewidth=2, color='blue')
            if len(data) >= 20:
                ax1.plot(data.index, data['Close'].rolling(20).mean(), label='MA20', linestyle='--', color='orange')
            ax1.set_title(f'{symbol} - {COMPANY_NAMES.get(symbol, symbol)}')
            ax1.set_ylabel('Price')
            ax1.legend()
            ax1.grid(True, alpha=0.3)
            ax2.bar(data.index, data['Volume'], alpha=0.5, color='gray')
            ax2.set_ylabel('Volume')
            ax2.grid(True, alpha=0.3)
            plt.tight_layout()
            
            filename = f"chart_{symbol}.png"
            plt.savefig(filename, dpi=80, bbox_inches='tight')
            plt.close()

            with open(filename, 'rb') as photo:
                await update.message.reply_photo(photo=photo, caption=f"📈 Chart {symbol}")
            os.remove(filename)
            await msg.delete()

        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def chart_custom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Gunakan: /chart_custom SYMBOL (contoh: /chart_custom BBCA)\n\n"
                "*Indikator:* Bollinger, SMA, MACD, RSI, Stochastic",
                parse_mode='Markdown'
            )
            return
            
        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📊 *Membuat chart custom {symbol}...*", parse_mode='Markdown')
        
        try:
            chart_path = self.chart_gen.create_chart(symbol)
            if chart_path:
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo, 
                        caption=f"📈 *{symbol} - Custom Chart*\n🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
                        parse_mode='Markdown'
                    )
                os.remove(chart_path)
                await msg.delete()
            else:
                await msg.edit_text(f"❌ Gagal membuat chart untuk *{symbol}*.", parse_mode='Markdown')
        except Exception as e:
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
                    message += f"• *{s['symbol']}* - {s['reason']} (Strength: {s['strength']}/5)\n"

            if sell:
                message += "\n*🔴 Sinyal JUAL:*\n"
                for s in sell[:5]:
                    message += f"• *{s['symbol']}* - {s['reason']} (Strength: {s['strength']}/5)\n"

            await msg.edit_text(message, parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        status = "⚠️ Realistis" if self.screener.use_fallback else "✅ Real-time"
        await update.message.reply_text(
            f"📊 *Statistik Bot v2.3*\n\n"
            f"🕐 Uptime: {self.get_uptime()}\n"
            f"📋 Watchlist: {len(self.watchlist)} saham\n"
            f"📊 Data: {status}\n"
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
            await msg.edit_text("✅ *Data cache berhasil direfresh!*", parse_mode='Markdown')
        except Exception as e:
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.running:
            self.running = True
            self.job = context.job_queue.run_repeating(self._monitor_stocks, interval=300, first=10)
            await update.message.reply_text("✅ *Monitoring dimulai!*", parse_mode='Markdown')
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
                        message = f"🟢 *SINYAL {signal['signal']} - {symbol}*\n\n"
                        message += f"💰 {format_price(signal['price'])}\n"
                        message += f"📊 {signal['change']:+.2f}%\n"
                        message += f"💡 {signal['reason']}"
                        await self.bot.send_message(chat_id=CHANNEL_ID, text=message, parse_mode='Markdown')
        except Exception as e:
            logger.error(f"Error monitoring: {str(e)}")
            self.error_count += 1

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        logger.error(f"Error: {context.error}")
        self.error_count += 1
        try:
            if update and update.effective_message:
                await update.effective_message.reply_text("❌ Terjadi kesalahan. Gunakan /refresh")
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
            application.add_handler(CommandHandler("chart_custom", self.chart_custom))
            application.add_handler(CommandHandler("top", self.top))
            application.add_handler(CommandHandler("check", self.check))
            application.add_handler(CommandHandler("stats", self.stats))
            application.add_handler(CommandHandler("refresh", self.refresh))
            application.add_handler(CommandHandler("start_bot", self.start_bot))
            application.add_handler(CommandHandler("stop_bot", self.stop_bot))

            application.add_error_handler(self._error_handler)

            logger.info("🚀 Bot starting...")
            print("=" * 60)
            print("🤖 BOT SAHAM DANAR v2.3 - ALL IN ONE")
            print("=" * 60)
            print(f"📌 Token: ✓")
            print(f"📌 Watchlist: {len(self.watchlist)} saham")
            print(f"📌 Chart Custom: Aktif")
            print("=" * 60)

            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=2.0,
                timeout=30
            )

        except Exception as e:
            logger.error(f"Fatal error: {str(e)}")
            sys.exit(1)

# ============================================
# MAIN
# ============================================

if __name__ == '__main__':
    try:
        bot = SahamBot()
        bot.run()
    except KeyboardInterrupt:
        print("\n⏹️ Bot dihentikan")
        sys.exit(0)
    except Exception as e:
        print(f"\n❌ Fatal: {str(e)}")
        sys.exit(1)
