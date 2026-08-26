#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Bot Saham Danar v2.4 - Dengan Candlestick Chart (mplfinance) & Screener V3
FIX: Semua chart pakai screener.get_stock_data(), fallback realistic data
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
import mplfinance as mpf
from telegram import Bot, Update
from telegram.ext import Application, CommandHandler, ContextTypes, MessageHandler, filters
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
ENVIRONMENT = os.getenv('ENVIRONMENT', 'development')
PORT = int(os.getenv('PORT', 8080))

# Watchlist
watchlist_str = os.getenv('WATCHLIST', '')
if watchlist_str:
    WATCHLIST = [s.strip().upper() for s in watchlist_str.split(',') if s.strip()]
else:
    WATCHLIST = ['BBCA', 'BBRI', 'BMRI', 'TLKM', 'ASII', 'UNVR', 'GOTO', 'BUMI', 'ADRO', 'ANTM', 'INCO', 'HRUM', 'ADMR']

VOLUME_THRESHOLD = float(os.getenv('VOLUME_THRESHOLD', '1.5'))

# Cache duration
CACHE_DURATION_MINUTES = int(os.getenv('CACHE_DURATION_MINUTES', '5'))

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
# DATA REALISTIS (FALLBACK)
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
    'SMGR': {'price': 1545, 'change': 0.5, 'volume': 84000, 'rsi': 60, 'ma20': 1526, 'ma50': 1500, 'high': 1555, 'low': 1525},
    'BUMI': {'price': 150, 'change': 2.5, 'volume': 100000000, 'rsi': 65, 'ma20': 145, 'ma50': 140, 'high': 155, 'low': 148},
    'ADRO': {'price': 2500, 'change': 1.2, 'volume': 25000000, 'rsi': 58, 'ma20': 2450, 'ma50': 2400, 'high': 2550, 'low': 2480},
    'ANTM': {'price': 2000, 'change': 0.8, 'volume': 30000000, 'rsi': 55, 'ma20': 1950, 'ma50': 1900, 'high': 2050, 'low': 1980},
    'INCO': {'price': 4500, 'change': -0.5, 'volume': 15000000, 'rsi': 48, 'ma20': 4550, 'ma50': 4600, 'high': 4600, 'low': 4450},
    'HRUM': {'price': 1800, 'change': 1.5, 'volume': 10000000, 'rsi': 62, 'ma20': 1750, 'ma50': 1700, 'high': 1850, 'low': 1780},
}

COMPANY_NAMES = {
    'BBCA': 'Bank Central Asia',
    'BBRI': 'Bank Rakyat Indonesia',
    'BMRI': 'Bank Mandiri',
    'TLKM': 'Telkom Indonesia',
    'ASII': 'Astra International',
    'UNVR': 'Unilever Indonesia',
    'GOTO': 'GoTo Gojek Tokopedia',
    'ADMR': 'Adaro Minerals Indonesia',
    'BRPT': 'Barito Pacific',
    'PTBA': 'Bukit Asam',
    'BSDE': 'Bumi Serpong Damai',
    'SMGR': 'Semen Indonesia',
    'BUMI': 'Bumi Resources',
    'ADRO': 'Adaro Energy',
    'ANTM': 'Aneka Tambang',
    'INCO': 'Vale Indonesia',
    'HRUM': 'Harum Energy',
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

def format_value(value):
    if value >= 1e12:
        return f"Rp{value/1e12:.2f}T"
    elif value >= 1e9:
        return f"Rp{value/1e9:.2f}M"
    elif value >= 1e6:
        return f"Rp{value/1e6:.2f}M"
    else:
        return f"Rp{value:,.0f}".replace(',', '.')

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

    def get_stock_data(self, symbol, period='1mo', max_retries=2, force_refresh=False):
        """Ambil data saham dengan cache, retry, dan fallback ke realistic data"""
        cache_key = f"{symbol}_{period}"
        
        # Cek cache
        if not force_refresh and cache_key in self.cache:
            cache_time = self.cache[cache_key].get('timestamp', '')
            if cache_time:
                try:
                    cache_date = datetime.fromisoformat(cache_time)
                    if (datetime.now() - cache_date) < timedelta(minutes=CACHE_DURATION_MINUTES):
                        logger.info(f"📦 Cache {symbol} (umur: {(datetime.now() - cache_date).seconds//60}m)")
                        data_dict = self.cache[cache_key]['data']
                        return pd.DataFrame(data_dict)
                except:
                    pass

        # Coba ambil dari Yahoo Finance
        for attempt in range(max_retries):
            try:
                logger.info(f"📥 Mengambil data {symbol} (attempt {attempt+1}/{max_retries})")
                ticker = yf.Ticker(f"{symbol}.JK")
                data = ticker.history(period=period, timeout=20)
                
                if not data.empty and len(data) > 3:
                    if data['Close'].iloc[-1] > 0 and data['Close'].iloc[-1] < 1000000:
                        self.cache[cache_key] = {
                            'timestamp': datetime.now().isoformat(),
                            'data': data.to_dict('list')
                        }
                        self.save_cache()
                        self.use_fallback = False
                        logger.info(f"✅ Data {symbol} berhasil diambil ({len(data)} hari)")
                        return data
                    else:
                        logger.warning(f"Data {symbol} tidak valid (harga: {data['Close'].iloc[-1]})")
            except Exception as e:
                logger.warning(f"Attempt {attempt+1} failed: {str(e)}")
                time.sleep(2)

        # Jika semua attempt gagal, gunakan realistic data
        logger.warning(f"⚠️ Menggunakan data realistis untuk {symbol}")
        self.use_fallback = True
        return self._create_realistic_data(symbol, period)

    def _create_realistic_data(self, symbol, period='1mo', days=60):
        """Buat data realistis sebagai fallback"""
        try:
            data = REALISTIC_DATA.get(symbol)
            if not data:
                data = {'price': 5000, 'change': 0, 'volume': 10000000, 'rsi': 50, 'ma20': 5000, 'ma50': 5000, 'high': 5100, 'low': 4900}
            
            n_days = max(days, 30)
            dates = pd.date_range(end=datetime.now(), periods=n_days, freq='D')
            base_price = data['price']
            prices = []
            opens = []
            highs = []
            lows = []
            
            for i in range(n_days):
                change = random.uniform(-0.02, 0.02)
                if i == 0:
                    price = base_price
                else:
                    price = prices[-1] * (1 + change)
                prices.append(price)
                
                open_price = price * random.uniform(0.98, 1.02)
                high_price = max(open_price, price) * random.uniform(1.01, 1.02)
                low_price = min(open_price, price) * random.uniform(0.98, 0.99)
                opens.append(open_price)
                highs.append(high_price)
                lows.append(low_price)
            
            last_price = prices[-1]
            factor = data['price'] / last_price
            prices = [p * factor for p in prices]
            opens = [o * factor for o in opens]
            highs = [h * factor for h in highs]
            lows = [l * factor for l in lows]
            volumes = [data['volume'] * random.uniform(0.6, 1.4) for _ in range(n_days)]
            
            return pd.DataFrame({
                'Open': opens,
                'High': highs,
                'Low': lows,
                'Close': prices,
                'Volume': volumes
            }, index=dates)
        except Exception as e:
            logger.error(f"Error creating realistic data: {str(e)}")
            return None

    def calculate_indicators(self, data):
        if data is None or len(data) < 3:
            return None

        try:
            close = data['Close']
            high = data['High']
            low = data['Low']
            volume = data['Volume']
            
            if len(close) >= 14:
                delta = close.diff()
                gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
                loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
                rs = gain / loss
                rsi = 100 - (100 / (1 + rs))
                rsi_val = rsi.iloc[-1] if len(rsi) > 0 else 50
            else:
                rsi_val = 50
            
            ma5 = close.rolling(window=5).mean().iloc[-1] if len(close) >= 5 else close.iloc[-1]
            ma10 = close.rolling(window=10).mean().iloc[-1] if len(close) >= 10 else close.iloc[-1]
            ma20 = close.rolling(window=20).mean().iloc[-1] if len(close) >= 20 else close.iloc[-1]
            ma50 = close.rolling(window=50).mean().iloc[-1] if len(close) >= 50 else close.iloc[-1]
            ma20_volume = volume.rolling(window=20).mean().iloc[-1] if len(volume) >= 20 else volume.iloc[-1]
            
            if len(close) >= 10:
                momentum = ((close.iloc[-1] - close.iloc[-10]) / close.iloc[-10]) * 100
            else:
                momentum = 0
            
            adx = self._calculate_adx(data, period=14)
            adx_val = adx.iloc[-1] if len(adx) > 0 else 20
            
            avg_volume = volume.rolling(window=10).mean().iloc[-1] if len(volume) >= 10 else volume.iloc[-1]
            volume_ratio = volume.iloc[-1] / avg_volume if avg_volume > 0 else 1
            
            change = ((close.iloc[-1] - close.iloc[-2]) / close.iloc[-2]) * 100 if len(close) > 1 else 0
            
            value = close.iloc[-1] * volume.iloc[-1]
            
            rsi_val = max(0, min(100, rsi_val))
            
            return {
                'price': float(close.iloc[-1]),
                'change': float(change),
                'volume': float(volume.iloc[-1]),
                'volume_ratio': float(volume_ratio),
                'rsi': float(rsi_val),
                'ma5': float(ma5),
                'ma10': float(ma10),
                'ma20': float(ma20),
                'ma50': float(ma50),
                'ma20_volume': float(ma20_volume),
                'momentum': float(momentum),
                'adx': float(adx_val),
                'value': float(value),
                'high': float(high.iloc[-1]) if 'High' in data else float(close.iloc[-1] * 1.02),
                'low': float(low.iloc[-1]) if 'Low' in data else float(close.iloc[-1] * 0.98)
            }
        except Exception as e:
            logger.error(f"Error calculating indicators: {str(e)}")
            return None

    def _calculate_adx(self, data, period=14):
        try:
            high = data['High']
            low = data['Low']
            close = data['Close']
            
            high_low = high - low
            high_close = (high - close.shift()).abs()
            low_close = (low - close.shift()).abs()
            ranges = pd.concat([high_low, high_close, low_close], axis=1)
            true_range = ranges.max(axis=1)
            
            up_move = high - high.shift()
            down_move = low.shift() - low
            
            plus_dm = np.where((up_move > down_move) & (up_move > 0), up_move, 0)
            minus_dm = np.where((down_move > up_move) & (down_move > 0), down_move, 0)
            
            atr = true_range.rolling(period).mean()
            plus_di = 100 * (pd.Series(plus_dm).rolling(period).mean() / atr)
            minus_di = 100 * (pd.Series(minus_dm).rolling(period).mean() / atr)
            
            dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
            adx = dx.rolling(period).mean()
            
            return adx
        except Exception as e:
            logger.error(f"Error calculating ADX: {str(e)}")
            return pd.Series([20] * len(data))

    def screen_v3(self, symbols=None):
        if symbols is None:
            symbols = self.watchlist
            
        results = []
        total_checked = 0
        total_passed = 0
        
        for symbol in symbols:
            try:
                total_checked += 1
                data = self.get_stock_data(symbol, period='2mo')
                if data is None or data.empty or len(data) < 10:
                    continue
                    
                ind = self.calculate_indicators(data)
                if ind is None:
                    continue
                
                criteria = {
                    'Harga > MA10': ind['price'] > ind['ma10'],
                    'MA5 > MA10': ind['ma5'] > ind['ma10'],
                    'MA10 > MA20': ind['ma10'] > ind['ma20'],
                    'RSI 50-75': 50 < ind['rsi'] < 75,
                    'Momentum > 0': ind['momentum'] > 0,
                    'ADX > 20': ind['adx'] > 20,
                    'Volume > MA20 Vol': ind['volume'] > ind['ma20_volume'],
                    'Value > 50M': ind['value'] > 50000000000
                }
                
                passed = sum(criteria.values())
                total_criteria = len(criteria)
                all_passed = all(criteria.values())
                
                if all_passed:
                    total_passed += 1
                    results.append({
                        'symbol': symbol,
                        'company': COMPANY_NAMES.get(symbol, symbol),
                        'price': ind['price'],
                        'change': ind['change'],
                        'volume': ind['volume'],
                        'rsi': ind['rsi'],
                        'ma5': ind['ma5'],
                        'ma10': ind['ma10'],
                        'ma20': ind['ma20'],
                        'ma20_volume': ind['ma20_volume'],
                        'momentum': ind['momentum'],
                        'adx': ind['adx'],
                        'value': ind['value'],
                        'criteria': criteria,
                        'passed': passed,
                        'total_criteria': total_criteria
                    })
                    
            except Exception as e:
                logger.error(f"Error screening V3 {symbol}: {str(e)}")
                continue
        
        results.sort(key=lambda x: x['value'], reverse=True)
        
        return {
            'results': results,
            'total_checked': total_checked,
            'total_passed': total_passed
        }

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

    def get_latest_price(self, symbol, force_refresh=False):
        data = self.get_stock_data(symbol, period='5d', force_refresh=force_refresh)
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

    def generate_signal(self, symbol, force_refresh=False):
        try:
            data = self.screener.get_stock_data(symbol, force_refresh=force_refresh)
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
# CHART GENERATOR - MENGGUNAKAN MPLFINANCE
# ============================================

class ChartGenerator:
    def __init__(self):
        self.chart_dir = 'charts'
        os.makedirs(self.chart_dir, exist_ok=True)
        
    def _get_data(self, symbol, period='3mo'):
        """Ambil data menggunakan screener (dengan cache & fallback)"""
        screener = Screener()
        data = screener.get_stock_data(symbol, period=period)
        
        if data is None or data.empty:
            logger.error(f"❌ No data for {symbol}")
            return None, True
        
        # Cek apakah data dari fallback
        is_fallback = screener.use_fallback
        
        return data, is_fallback
        
    def create_candlestick_chart(self, symbol: str, period: str = '3mo') -> str:
        """
        Membuat candlestick chart menggunakan mplfinance
        """
        try:
            logger.info(f"📊 Creating candlestick chart for {symbol}")
            
            # Ambil data pakai screener (sama seperti /chart)
            data, is_fallback = self._get_data(symbol, period)
            
            if data is None or data.empty:
                logger.error(f"❌ No data for {symbol}")
                return None
            
            # Siapkan data untuk mplfinance
            # Pastikan kolom yang dibutuhkan ada
            required_cols = ['Open', 'High', 'Low', 'Close', 'Volume']
            for col in required_cols:
                if col not in data.columns:
                    logger.error(f"❌ Missing column: {col}")
                    return None
            
            # Index harus datetime
            if not isinstance(data.index, pd.DatetimeIndex):
                data.index = pd.to_datetime(data.index)
            
            # Buat chart dengan mplfinance
            fig, axes = mpf.plot(
                data,
                type='candle',
                style='charles',
                volume=True,
                mav=(5, 10, 20, 50),
                figsize=(14, 10),
                returnfig=True,
                xrotation=0,
                tight_layout=True,
                ylabel='Harga',
                ylabel_lower='Volume',
                title=f'{symbol} - {COMPANY_NAMES.get(symbol, symbol)}',
                warn_too_much_data=1000
            )
            
            # Tambahkan informasi harga terakhir
            last = data.iloc[-1]
            change = ((data['Close'].iloc[-1] - data['Close'].iloc[-2]) / data['Close'].iloc[-2]) * 100 if len(data) > 1 else 0
            change_text = f"+{change:.2f}%" if change >= 0 else f"{change:.2f}%"
            
            # Add info text
            info_text = f"O: {last['Open']:.0f} | H: {last['High']:.0f} | L: {last['Low']:.0f} | C: {last['Close']:.0f} | {change_text}"
            axes[0].text(
                0.02, 0.98, info_text, 
                transform=axes[0].transAxes, 
                fontsize=11, 
                color='white',
                verticalalignment='top',
                bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8)
            )
            
            # Tambahkan footer
            data_source = 'Realistis' if is_fallback else 'Real-time'
            footer_text = f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} | Data: {data_source} | {len(data)} hari"
            fig.text(0.5, 0.01, footer_text, ha='center', fontsize=8, color='#4a5568')
            
            # Simpan chart
            filename = f"{self.chart_dir}/{symbol}_candle_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(filename, dpi=120, bbox_inches='tight', facecolor='#0d1117')
            plt.close()
            
            logger.info(f"✅ Candlestick chart {symbol} berhasil dibuat: {filename}")
            return filename
            
        except Exception as e:
            logger.error(f"Error creating candlestick chart: {str(e)}\n{traceback.format_exc()}")
            return None

    def create_chart(self, symbol: str, period: str = '3mo') -> str:
        """Alias untuk create_candlestick_chart"""
        return self.create_candlestick_chart(symbol, period)

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
            f"🤖 Bot Saham Danar v2.4\n\n"
            f"Status: {status}\n"
            f"Watchlist: {len(self.watchlist)} saham\n"
            f"Uptime: {self.get_uptime()}\n"
            f"Cache: {CACHE_DURATION_MINUTES} menit\n\n"
            f"Perintah: /help untuk bantuan"
        )

    async def help(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        help_text = (
            "📚 *DAFTAR PERINTAH BOT v2.4*\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📊 *PERINTAH DASAR*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "/start - Menu utama\n"
            "/help - Bantuan ini\n"
            "/screener - Screening saham standar\n"
            "/screener_v3 - Screening V3 (Advanced) ⭐\n"
            "/watchlist - Daftar saham\n"
            "/add SYMBOL - Tambah saham ke watchlist\n"
            "/remove SYMBOL - Hapus saham dari watchlist\n"
            "/signal SYMBOL - Cek sinyal\n"
            "/top - Top 5 volume\n"
            "/check - Cek semua sinyal\n"
            "/stats - Statistik bot\n"
            "/refresh - Refresh data cache\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🔄 *HARGA REAL-TIME*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "/rp SYMBOL - Refresh harga terbaru ⭐\n"
            "/refresh_price SYMBOL - Sama seperti di atas\n"
            "/force_refresh - Refresh semua data\n"
            "/fr - Alias force_refresh\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📈 *CHART*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "/chart SYMBOL - Chart sederhana (line)\n"
            "/cc SYMBOL - Candlestick chart lengkap ⭐\n"
            "/chart_custom SYMBOL - Candlestick chart\n"
            "/chartcustom SYMBOL - Candlestick chart\n"
            "/customchart SYMBOL - Candlestick chart\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🎯 *SCREENER V3 KRITERIA*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "1. Harga > MA10\n"
            "2. MA5 > MA10 > MA20\n"
            "3. RSI 50-75\n"
            "4. Momentum > 0\n"
            "5. ADX > 20\n"
            "6. Volume > MA20 Volume\n"
            "7. Value > 50 Milyar\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "🤖 *MONITORING*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "/start_bot - Mulai monitoring\n"
            "/stop_bot - Stop monitoring\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "📌 *CONTOH PENGGUNAAN*\n"
            "━━━━━━━━━━━━━━━━━━━━━━\n"
            "/rp BBCA - Refresh harga BBCA\n"
            "/screener_v3 - Screening V3\n"
            "/cc BUMI - Candlestick chart BUMI\n"
            "/add ADRO - Tambah ADRO ke watchlist\n\n"
            "⚠️ *Catatan:*\n"
            "• Yahoo Finance delay 15-20 menit\n"
            "• Gunakan /rp untuk refresh manual\n"
            "• Bisa chart SEMUA saham termasuk ADMR!"
        )
        await update.message.reply_text(help_text, parse_mode='Markdown')

    async def unknown(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "❌ Perintah tidak dikenal.\n\n"
            "Gunakan /help untuk melihat daftar perintah yang tersedia.\n\n"
            "Tips:\n"
            "/rp BBCA - Refresh harga terbaru\n"
            "/screener_v3 - Screening V3 (Advanced)\n"
            "/cc BBCA - Candlestick chart"
        )

    async def screener_v3(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text(
            "🔍 Screening V3...\n"
            "⏳ Mohon tunggu..."
        )
        
        try:
            result = self.screener.screen_v3()
            
            if not result['results']:
                await msg.edit_text(
                    f"📊 Hasil Screener V3\n\n"
                    f"Tidak ada saham yang memenuhi semua kriteria.\n"
                    f"Total diperiksa: {result['total_checked']} saham\n\n"
                    f"💡 Coba tambahkan lebih banyak saham ke watchlist."
                )
                return
            
            message = "🎯 *HASIL SCREENER V3*\n\n"
            message += f"📊 Total diperiksa: {result['total_checked']} saham\n"
            message += f"✅ Total lolos: {result['total_passed']} saham\n\n"
            message += "━━━━━━━━━━━━━━━━━━━━━━\n\n"
            
            for i, stock in enumerate(result['results'][:10], 1):
                message += f"{i}. *{stock['symbol']}* - {stock['company']}\n"
                message += f"   💰 Harga: {format_price(stock['price'])} ({stock['change']:+.2f}%)\n"
                message += f"   📊 Volume: {format_volume(stock['volume'])}\n"
                message += f"   💰 Value: {format_value(stock['value'])}\n"
                message += f"   📈 RSI: {stock['rsi']:.1f}\n"
                message += f"   📊 MA5: {format_price(stock['ma5'])}\n"
                message += f"   📊 MA10: {format_price(stock['ma10'])}\n"
                message += f"   📊 MA20: {format_price(stock['ma20'])}\n"
                message += f"   📈 Momentum: {stock['momentum']:+.2f}%\n"
                message += f"   📊 ADX: {stock['adx']:.1f}\n"
                message += f"   ✅ Lolos: {stock['passed']}/{stock['total_criteria']} kriteria\n"
                message += "\n"
            
            if len(result['results']) > 10:
                message += f"... dan {len(result['results']) - 10} saham lainnya.\n\n"
            
            message += "⚠️ Gunakan /rp SYMBOL untuk refresh harga terbaru."
            
            await msg.edit_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Screener V3 error: {e}\n{traceback.format_exc()}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def refresh_price(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text(
                "❌ Gunakan: /rp SYMBOL\n\n"
                "Contoh: /rp BBCA\n"
                "Untuk refresh harga terbaru dari pasar.\n\n"
                "⚠️ Catatan: Yahoo Finance delay 15-20 menit."
            )
            return
        
        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"🔄 Refresh harga {symbol}... (skip cache)")
        
        try:
            data = self.screener.get_stock_data(symbol, force_refresh=True)
            if data is None or data.empty:
                await msg.edit_text(f"❌ Gagal mengambil data {symbol}")
                return
            
            ind = self.screener.calculate_indicators(data)
            if ind is None:
                await msg.edit_text(f"❌ Gagal menghitung indikator {symbol}")
                return
            
            company = COMPANY_NAMES.get(symbol, symbol)
            fallback_note = " ⚠️ (Data Realistis)" if self.screener.use_fallback else ""
            
            message = f"📊 Harga Terbaru {symbol} - {company}{fallback_note}\n\n"
            message += f"💰 Harga: {format_price(ind['price'])}\n"
            message += f"📊 Perubahan: {ind['change']:+.2f}%\n"
            message += f"📊 Volume: {format_volume(ind['volume'])}\n"
            message += f"📈 RSI: {ind['rsi']:.1f}\n"
            message += f"📉 MA5: {format_price(ind['ma5'])}\n"
            message += f"📉 MA10: {format_price(ind['ma10'])}\n"
            message += f"📉 MA20: {format_price(ind['ma20'])}\n"
            message += f"📉 MA50: {format_price(ind['ma50'])}\n"
            message += f"📈 Momentum: {ind['momentum']:+.2f}%\n"
            message += f"📊 ADX: {ind['adx']:.1f}\n"
            message += f"💰 Value: {format_value(ind['value'])}\n\n"
            message += f"🕐 Update: {datetime.now().strftime('%H:%M:%S')}\n"
            message += f"📦 Cache: {CACHE_DURATION_MINUTES} menit"
            
            await msg.edit_text(message)
            
        except Exception as e:
            logger.error(f"Refresh price error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def force_refresh_all(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔄 Force refresh semua data...")
        
        try:
            self.screener.clear_cache()
            self.screener.use_fallback = False
            
            success_count = 0
            fail_count = 0
            
            for symbol in self.watchlist:
                try:
                    data = self.screener.get_stock_data(symbol, max_retries=3, force_refresh=True)
                    if data is not None and not data.empty:
                        success_count += 1
                        logger.info(f"✅ Refreshed {symbol}")
                    else:
                        fail_count += 1
                except Exception as e:
                    fail_count += 1
                    logger.error(f"Failed to refresh {symbol}: {e}")
                time.sleep(0.5)
            
            await msg.edit_text(
                f"✅ Force refresh selesai!\n\n"
                f"📊 Berhasil: {success_count} saham\n"
                f"❌ Gagal: {fail_count} saham\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"⚠️ Catatan: Yahoo Finance delay 15-20 menit.\n"
                f"Gunakan /rp SYMBOL untuk refresh per saham."
            )
            
        except Exception as e:
            logger.error(f"Force refresh error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def watchlist(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.watchlist:
            await update.message.reply_text("📋 Watchlist kosong.")
            return

        try:
            message = "📋 *WATCHLIST*\n\n"
            message += "━━━━━━━━━━━━━━━━━━━━━━\n"
            
            for symbol in self.watchlist:
                price = self.screener.get_latest_price(symbol)
                company = COMPANY_NAMES.get(symbol, symbol)
                
                if price:
                    emoji = "🟢" if price['change'] >= 0 else "🔴"
                    message += f"{emoji} *{symbol}* - {company}\n"
                    message += f"   💰 {format_price(price['price'])}\n"
                    message += f"   📊 {price['change']:+.2f}%\n"
                    message += f"   📊 Vol: {format_volume(price['volume'])}\n"
                else:
                    message += f"❌ *{symbol}* - {company}\n"
                    message += f"   ⚠️ Data tidak tersedia\n"
                message += "\n"
            
            message += "━━━━━━━━━━━━━━━━━━━━━━\n"
            message += f"Total: {len(self.watchlist)} saham\n\n"
            message += "💡 Gunakan /rp SYMBOL untuk refresh harga"
            
            await update.message.reply_text(message, parse_mode='Markdown')
            
        except Exception as e:
            logger.error(f"Watchlist error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def screener(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 Screening...")
        try:
            results = self.screener.screen_all()
            if not results:
                await msg.edit_text("⚠️ Tidak ada hasil. Coba /refresh")
                return

            message = "📊 Hasil Screener\n\n"
            for stock in results[:10]:
                emoji = "🟢" if stock['score'] > 0 else "🔴" if stock['score'] < 0 else "⚪"
                message += f"{emoji} {stock['symbol']} - {stock['company']}\n"
                message += f"   💰 {format_price(stock['price'])} ({stock['change']:+.2f}%)\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 RSI: {stock['rsi']:.1f} | Score: {stock['score']}\n\n"

            if self.screener.use_fallback:
                message += "\n⚠️ Data Realistis (Yahoo Finance tidak tersedia)"

            await msg.edit_text(message)
        except Exception as e:
            logger.error(f"Screener error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def add(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /add SYMBOL")
            return

        symbol = context.args[0].upper()
        if symbol not in self.watchlist:
            self.watchlist.append(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ {symbol} ditambahkan ke watchlist!")
        else:
            await update.message.reply_text(f"ℹ️ {symbol} sudah ada di watchlist.")

    async def remove(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /remove SYMBOL")
            return

        symbol = context.args[0].upper()
        if symbol in self.watchlist:
            self.watchlist.remove(symbol)
            self.screener.watchlist = self.watchlist
            await update.message.reply_text(f"✅ {symbol} dihapus dari watchlist!")
        else:
            await update.message.reply_text(f"❌ {symbol} tidak ditemukan di watchlist.")

    async def signal(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /signal SYMBOL")
            return

        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📈 Menganalisis {symbol}...")

        try:
            signal = self.signal_gen.generate_signal(symbol)
            if not signal:
                await msg.edit_text(f"❌ Data {symbol} tidak tersedia.")
                return

            signal_text = "🔴 JUAL" if signal['signal'] == 'SELL' else "🟢 BELI" if signal['signal'] == 'BUY' else "⚪ TAHAN"
            fallback_note = "\n⚠️ Data Realistis" if self.screener.use_fallback else ""

            message = f"📊 Analisis {symbol}\n\n"
            message += f"💰 Harga: {format_price(signal['price'])}\n"
            message += f"📊 Perubahan: {signal['change']:+.2f}%\n"
            message += f"📈 RSI: {signal['rsi']:.1f}\n"
            message += f"📊 Volume: {format_volume(signal['volume'])}\n"
            message += f"📉 MA20: {format_price(signal['ma20'])}\n"
            message += f"📉 MA50: {format_price(signal['ma50'])}\n\n"
            message += f"🎯 Rekomendasi: {signal_text}\n"
            message += f"💡 Alasan: {signal['reason']}\n"
            message += f"💪 Strength: {signal['strength']}/5"
            message += fallback_note

            await msg.edit_text(message)
        except Exception as e:
            logger.error(f"Signal error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def chart(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Chart sederhana dengan line (tetap pakai screener)"""
        if not context.args:
            await update.message.reply_text("❌ Gunakan: /chart SYMBOL")
            return

        symbol = context.args[0].upper()
        msg = await update.message.reply_text(f"📊 Membuat chart {symbol}...")

        try:
            data = self.screener.get_stock_data(symbol, period='1mo')
            if data is None or data.empty:
                await msg.edit_text(f"❌ Data {symbol} tidak tersedia.")
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
                await update.message.reply_photo(photo=photo, caption=f"📈 Chart {symbol} (Line)")
            os.remove(filename)
            await msg.delete()

        except Exception as e:
            logger.error(f"Chart error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def chart_custom(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """
        Chart custom dengan CANDLESTICK menggunakan mplfinance
        """
        if not context.args:
            await update.message.reply_text(
                "❌ Gunakan: /cc SYMBOL\n\n"
                "Contoh:\n"
                "/cc BBCA - Candlestick chart BBCA\n"
                "/cc BUMI - Candlestick chart BUMI\n"
                "/cc ADMR - Candlestick chart ADMR ⭐\n\n"
                "📊 *Indikator:*\n"
                "• Candlestick OHLC\n"
                "• MA5, MA10, MA20, MA50\n"
                "• Volume\n\n"
                "📌 Bisa chart SEMUA saham!",
                parse_mode='Markdown'
            )
            return
            
        symbol = context.args[0].upper()
        
        msg = await update.message.reply_text(
            f"📊 Membuat candlestick chart {symbol}...\n"
            f"⏳ Mohon tunggu (10-15 detik)..."
        )
        
        try:
            logger.info(f"📊 Generating candlestick chart for {symbol}")
            chart_path = self.chart_gen.create_candlestick_chart(symbol, period='3mo')
            
            if chart_path and os.path.exists(chart_path):
                logger.info(f"✅ Chart created: {chart_path}")
                with open(chart_path, 'rb') as photo:
                    await update.message.reply_photo(
                        photo=photo, 
                        caption=f"📈 *{symbol} - Candlestick Chart*\n"
                               f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                               f"*Indikator:* MA5, MA10, MA20, MA50\n"
                               f"*Data:* {'Real-time' if not self.screener.use_fallback else 'Realistis'}\n\n"
                               f"💡 *Warna:* 🟢 Hijau = Naik | 🔴 Merah = Turun",
                        parse_mode='Markdown'
                    )
                time.sleep(0.5)
                if os.path.exists(chart_path):
                    os.remove(chart_path)
                    logger.info(f"🗑️ Chart file deleted: {chart_path}")
                await msg.delete()
            else:
                logger.error(f"❌ Failed to create chart for {symbol}")
                await msg.edit_text(
                    f"❌ Gagal membuat candlestick chart untuk {symbol}.\n\n"
                    f"*Kemungkinan penyebab:*\n"
                    f"• Yahoo Finance sedang bermasalah\n"
                    f"• Data saham sangat baru (kurang dari 10 hari)\n"
                    f"• Simbol tidak valid\n\n"
                    f"*Solusi:*\n"
                    f"• Tunggu 5 menit dan coba /cc {symbol} lagi\n"
                    f"• Gunakan /refresh untuk reset cache\n"
                    f"• Coba /chart {symbol} (chart line)\n"
                    f"• Cek di Yahoo Finance: https://finance.yahoo.com/quote/{symbol}.JK",
                    parse_mode='Markdown'
                )
        except Exception as e:
            logger.error(f"Chart custom error: {str(e)}\n{traceback.format_exc()}")
            await msg.edit_text(
                f"❌ Error: {str(e)[:200]}\n\n"
                f"💡 Gunakan /refresh jika perlu.\n"
                f"📊 Atau coba /chart {symbol} untuk chart sederhana."
            )

    async def top(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("📊 Mencari volume tertinggi...")
        try:
            top_stocks = self.screener.get_top_by_volume(5)
            if not top_stocks:
                await msg.edit_text("❌ Data tidak tersedia.")
                return

            message = "🔥 Top 5 Volume\n\n"
            for i, stock in enumerate(top_stocks, 1):
                emoji = "🟢" if stock['change'] >= 0 else "🔴"
                message += f"{i}. {emoji} {stock['symbol']}\n"
                message += f"   💰 {format_price(stock['price'])}\n"
                message += f"   📊 Vol: {format_volume(stock['volume'])}\n"
                message += f"   📈 {stock['change']:+.2f}%\n\n"

            await msg.edit_text(message)
        except Exception as e:
            logger.error(f"Top error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def check(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔍 Mengecek sinyal...")
        try:
            signals = self.signal_gen.check_all_signals()
            if not signals:
                await msg.edit_text("✅ Tidak ada sinyal.")
                return

            buy = [s for s in signals.values() if s['signal'] == 'BUY']
            sell = [s for s in signals.values() if s['signal'] == 'SELL']

            message = f"📊 Hasil Pengecekan\n\n"
            message += f"🟢 BELI: {len(buy)}\n"
            message += f"🔴 JUAL: {len(sell)}\n"
            message += f"⚪ TAHAN: {len(signals) - len(buy) - len(sell)}\n\n"

            if buy:
                message += "🟢 Sinyal BELI:\n"
                for s in buy[:5]:
                    message += f"- {s['symbol']} - {s['reason']} (Strength: {s['strength']}/5)\n"

            if sell:
                message += "\n🔴 Sinyal JUAL:\n"
                for s in sell[:5]:
                    message += f"- {s['symbol']} - {s['reason']} (Strength: {s['strength']}/5)\n"

            await msg.edit_text(message)
        except Exception as e:
            logger.error(f"Check error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def stats(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            status = "⚠️ Realistis" if self.screener.use_fallback else "✅ Real-time"
            await update.message.reply_text(
                f"📊 Statistik Bot v2.4\n\n"
                f"Uptime: {self.get_uptime()}\n"
                f"Watchlist: {len(self.watchlist)} saham\n"
                f"Data: {status}\n"
                f"Monitoring: {'✅ Aktif' if self.running else '⛔ Nonaktif'}\n"
                f"Cache: {len(self.screener.cache)} items\n"
                f"Cache Duration: {CACHE_DURATION_MINUTES} menit\n"
                f"Error: {self.error_count}\n"
                f"{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            )
        except Exception as e:
            logger.error(f"Stats error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def refresh(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        msg = await update.message.reply_text("🔄 Refresh data cache...")
        try:
            self.screener.clear_cache()
            self.screener.use_fallback = False
            await msg.edit_text(
                f"✅ Data cache berhasil direfresh!\n"
                f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n"
                f"💡 Gunakan /rp SYMBOL untuk refresh harga terbaru."
            )
        except Exception as e:
            logger.error(f"Refresh error: {e}")
            await msg.edit_text(f"❌ Error: {str(e)}")

    async def start_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if not self.running:
                self.running = True
                self.job = context.job_queue.run_repeating(self._monitor_stocks, interval=300, first=10)
                await update.message.reply_text("✅ Monitoring dimulai!")
            else:
                await update.message.reply_text("⚠️ Monitoring sudah aktif.")
        except Exception as e:
            logger.error(f"Start bot error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def stop_bot(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            if self.running and self.job:
                self.running = False
                self.job.schedule_removal()
                self.job = None
                await update.message.reply_text("⏹️ Monitoring dihentikan.")
            else:
                await update.message.reply_text("ℹ️ Monitoring tidak aktif.")
        except Exception as e:
            logger.error(f"Stop bot error: {e}")
            await update.message.reply_text(f"❌ Error: {str(e)}")

    async def _monitor_stocks(self, context: ContextTypes.DEFAULT_TYPE):
        try:
            logger.info("🔄 Running monitoring...")
            signals = self.signal_gen.check_all_signals()
            for symbol, signal in signals.items():
                if symbol in self.watchlist and signal['signal'] != 'HOLD' and signal['strength'] >= 2:
                    if CHANNEL_ID:
                        message = f"🟢 SINYAL {signal['signal']} - {symbol}\n\n"
                        message += f"💰 {format_price(signal['price'])}\n"
                        message += f"📊 {signal['change']:+.2f}%\n"
                        message += f"💡 {signal['reason']}"
                        await self.bot.send_message(chat_id=CHANNEL_ID, text=message)
        except Exception as e:
            logger.error(f"Error monitoring: {str(e)}")
            self.error_count += 1

    async def _error_handler(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        error_msg = str(context.error)
        logger.error(f"❌ Error: {error_msg}\n{traceback.format_exc()}")
        self.error_count += 1
        
        try:
            if update and update.effective_message:
                if len(error_msg) > 200:
                    error_msg = error_msg[:200] + "..."
                
                await update.effective_message.reply_text(
                    f"❌ Terjadi kesalahan:\n{error_msg}\n\n"
                    f"💡 Gunakan /refresh atau /help untuk bantuan."
                )
        except Exception as e:
            logger.error(f"Error in error handler: {e}")
        
        if self.error_count > self.max_errors:
            logger.warning(f"⚠️ Terlalu banyak error ({self.error_count}), restarting...")
            self.error_count = 0
            sys.exit(0)

    def run(self):
        try:
            logger.info("=" * 60)
            logger.info("🚀 BOT SAHAM DANAR v2.4 STARTING")
            logger.info("=" * 60)
            logger.info(f"📌 Token: {'✓' if TELEGRAM_TOKEN else '✗'}")
            logger.info(f"📌 Watchlist: {len(self.watchlist)} saham")
            logger.info(f"📌 Cache Duration: {CACHE_DURATION_MINUTES} menit")
            logger.info(f"📌 Chart: mplfinance (candlestick + MA + Volume)")
            logger.info(f"📌 Environment: {ENVIRONMENT}")
            logger.info(f"📌 Port: {PORT}")
            logger.info("=" * 60)

            os.makedirs('data', exist_ok=True)
            os.makedirs('charts', exist_ok=True)
            os.makedirs('logs', exist_ok=True)

            application = Application.builder().token(TELEGRAM_TOKEN).build()

            # Command handlers
            application.add_handler(CommandHandler("start", self.start))
            application.add_handler(CommandHandler("help", self.help))
            application.add_handler(CommandHandler("screener", self.screener))
            application.add_handler(CommandHandler("screener_v3", self.screener_v3))
            application.add_handler(CommandHandler("watchlist", self.watchlist))
            application.add_handler(CommandHandler("add", self.add))
            application.add_handler(CommandHandler("remove", self.remove))
            application.add_handler(CommandHandler("signal", self.signal))
            application.add_handler(CommandHandler("chart", self.chart))
            
            # Chart custom dengan candlestick (mplfinance)
            application.add_handler(CommandHandler("chart_custom", self.chart_custom))
            application.add_handler(CommandHandler("chartcustom", self.chart_custom))
            application.add_handler(CommandHandler("customchart", self.chart_custom))
            application.add_handler(CommandHandler("cc", self.chart_custom))
            
            # Refresh harga
            application.add_handler(CommandHandler("refresh_price", self.refresh_price))
            application.add_handler(CommandHandler("rp", self.refresh_price))
            application.add_handler(CommandHandler("force_refresh", self.force_refresh_all))
            application.add_handler(CommandHandler("fr", self.force_refresh_all))
            
            # Lainnya
            application.add_handler(CommandHandler("top", self.top))
            application.add_handler(CommandHandler("check", self.check))
            application.add_handler(CommandHandler("stats", self.stats))
            application.add_handler(CommandHandler("refresh", self.refresh))
            application.add_handler(CommandHandler("start_bot", self.start_bot))
            application.add_handler(CommandHandler("stop_bot", self.stop_bot))

            # Unknown command
            application.add_handler(MessageHandler(filters.COMMAND, self.unknown))
            application.add_error_handler(self._error_handler)

            print("=" * 60)
            print("🤖 BOT SAHAM DANAR v2.4 - CANDLESTICK CHART (mplfinance)")
            print("=" * 60)
            print(f"📌 Token: ✓")
            print(f"📌 Watchlist: {len(self.watchlist)} saham")
            print(f"📌 Cache Duration: {CACHE_DURATION_MINUTES} menit")
            print(f"📌 Screener V3: Aktif")
            print(f"📌 Chart: mplfinance (candlestick + MA5,10,20,50 + Volume)")
            print(f"📌 Fallback: Data realistis jika Yahoo gagal")
            print(f"📌 Environment: {ENVIRONMENT}")
            print("=" * 60)
            print("📊 Bot siap menerima perintah!")
            print("💡 Contoh: /screener_v3, /rp BBCA, /cc ADMR, /watchlist")
            print("=" * 60)

            # Gunakan polling (lebih stabil di Railway)
            application.run_polling(
                allowed_updates=Update.ALL_TYPES,
                drop_pending_updates=True,
                poll_interval=2.0,
                timeout=30
            )

        except Exception as e:
            logger.error(f"Fatal error: {str(e)}\n{traceback.format_exc()}")
            print(f"\n❌ Fatal: {str(e)}")
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
