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
                if ind['price
