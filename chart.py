#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
Chart Generator dengan Indikator Teknikal Lengkap
Style mirip ChartDirector
"""

import os
import sys
import logging
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from matplotlib.patches import Rectangle
import numpy as np
import pandas as pd
import yfinance as yf
from datetime import datetime, timedelta

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ============================================
# KELAS CHART GENERATOR
# ============================================

class ChartGenerator:
    def __init__(self):
        self.chart_dir = 'charts'
        os.makedirs(self.chart_dir, exist_ok=True)
        
        # Setting style
        plt.style.use('dark_background')
        
    def create_chart(self, symbol: str, period: str = '3mo') -> str:
        """
        Membuat chart lengkap dengan indikator teknikal
        
        Indikator:
        - Candlestick / Line Chart
        - Bollinger Bands (20, 2)
        - SMA 20 & SMA 50
        - Volume
        - MACD (26, 12, 9)
        - Stochastic (14, 3)
        - RSI (14)
        - William %R
        """
        try:
            # Ambil data
            ticker = yf.Ticker(f"{symbol}.JK")
            data = ticker.history(period=period)
            
            if data.empty:
                logger.warning(f"Data kosong untuk {symbol}")
                return None
                
            # Pastikan data cukup
            if len(data) < 50:
                logger.warning(f"Data tidak cukup untuk {symbol} (hanya {len(data)} hari)")
                return None
            
            # Buat figure dengan 4 subplot
            fig = plt.figure(figsize=(16, 12))
            fig.patch.set_facecolor('#0d1117')
            
            # Setup grid
            gs = fig.add_gridspec(4, 1, height_ratios=[3, 1, 1, 1], hspace=0.15)
            
            # ============================================
            # PLOT 1: Harga + Indikator
            # ============================================
            ax1 = fig.add_subplot(gs[0])
            ax1.set_facecolor('#0d1117')
            
            # Garis harga
            ax1.plot(data.index, data['Close'], color='#00d4ff', linewidth=2, label='Close')
            
            # SMA 20 & 50
            sma20 = data['Close'].rolling(window=20).mean()
            sma50 = data['Close'].rolling(window=50).mean()
            
            ax1.plot(data.index, sma20, color='#ff6b6b', linewidth=1.5, linestyle='--', label='SMA 20')
            ax1.plot(data.index, sma50, color='#ffd93d', linewidth=1.5, linestyle='--', label='SMA 50')
            
            # Bollinger Bands (20, 2)
            bb_middle = data['Close'].rolling(window=20).mean()
            bb_std = data['Close'].rolling(window=20).std()
            bb_upper = bb_middle + (bb_std * 2)
            bb_lower = bb_middle - (bb_std * 2)
            
            ax1.fill_between(data.index, bb_upper, bb_lower, alpha=0.15, color='#6c5ce7', label='Bollinger (20,2)')
            ax1.plot(data.index, bb_upper, color='#6c5ce7', linewidth=1, alpha=0.5, linestyle=':')
            ax1.plot(data.index, bb_lower, color='#6c5ce7', linewidth=1, alpha=0.5, linestyle=':')
            
            # Info harga terakhir
            last_price = data['Close'].iloc[-1]
            last_high = data['High'].iloc[-1]
            last_low = data['Low'].iloc[-1]
            last_open = data['Open'].iloc[-1]
            last_volume = data['Volume'].iloc[-1]
            
            # Tambahkan info di sudut kiri atas
            info_text = f"Op: {last_open:.0f}, Hi: {last_high:.0f}, Lo: {last_low:.0f}, Cl: {last_price:.0f}"
            ax1.text(0.02, 0.98, info_text, transform=ax1.transAxes, 
                    fontsize=10, color='#ffffff', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # Info Bollinger
            bb_text = f"Bollinger (20, 2): {bb_lower.iloc[-1]:.0f} - {bb_upper.iloc[-1]:.0f}"
            ax1.text(0.02, 0.92, bb_text, transform=ax1.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # SMA info
            sma_text = f"SMA (20): {sma20.iloc[-1]:.0f}  SMA (5): {data['Close'].rolling(5).mean().iloc[-1]:.0f}"
            ax1.text(0.02, 0.86, sma_text, transform=ax1.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # Setting axis
            ax1.set_title(f'{symbol} Custom Chart', color='#ffffff', fontsize=14, fontweight='bold', pad=20)
            ax1.set_ylabel('Harga', color='#a0aec0', fontsize=10)
            ax1.grid(True, alpha=0.15, color='#2d3748')
            ax1.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            
            # Format x-axis
            ax1.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
            ax1.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
            ax1.tick_params(colors='#a0aec0')
            
            # ============================================
            # PLOT 2: MACD
            # ============================================
            ax2 = fig.add_subplot(gs[1])
            ax2.set_facecolor('#0d1117')
            
            # Hitung MACD
            exp1 = data['Close'].ewm(span=12, adjust=False).mean()
            exp2 = data['Close'].ewm(span=26, adjust=False).mean()
            macd = exp1 - exp2
            macd_signal = macd.ewm(span=9, adjust=False).mean()
            macd_histogram = macd - macd_signal
            
            # Plot MACD
            ax2.plot(data.index, macd, color='#00d4ff', linewidth=1.5, label='MACD (26, 12)')
            ax2.plot(data.index, macd_signal, color='#ffd93d', linewidth=1.5, label='EXP (9)')
            
            # Histogram
            colors = ['#00d4ff' if val >= 0 else '#ff6b6b' for val in macd_histogram]
            ax2.bar(data.index, macd_histogram, color=colors, alpha=0.5, width=0.8)
            
            # Garis nol
            ax2.axhline(y=0, color='#4a5568', linewidth=0.5, linestyle='-')
            
            # Info MACD
            macd_text = f"MACD (26, 12): {macd.iloc[-1]:.2f}  EXP (9): {macd_signal.iloc[-1]:.2f}"
            ax2.text(0.02, 0.92, macd_text, transform=ax2.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # Divergence
            divergence = macd.iloc[-1] - macd_signal.iloc[-1]
            div_text = f"Divergence: {divergence:.3f}"
            ax2.text(0.02, 0.82, div_text, transform=ax2.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax2.set_ylabel('MACD', color='#a0aec0', fontsize=10)
            ax2.grid(True, alpha=0.15, color='#2d3748')
            ax2.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax2.tick_params(colors='#a0aec0')
            
            # ============================================
            # PLOT 3: RSI + Stochastic
            # ============================================
            ax3 = fig.add_subplot(gs[2])
            ax3.set_facecolor('#0d1117')
            
            # RSI (14)
            delta = data['Close'].diff()
            gain = (delta.where(delta > 0, 0)).rolling(window=14).mean()
            loss = (-delta.where(delta < 0, 0)).rolling(window=14).mean()
            rs = gain / loss
            rsi = 100 - (100 / (1 + rs))
            
            # Plot RSI
            ax3.plot(data.index, rsi, color='#ff6b6b', linewidth=1.5, label='RSI (14)')
            
            # Level RSI
            ax3.axhline(y=70, color='#ff6b6b', linewidth=0.5, linestyle='--', alpha=0.5)
            ax3.axhline(y=30, color='#00d4ff', linewidth=0.5, linestyle='--', alpha=0.5)
            ax3.fill_between(data.index, 70, 100, alpha=0.1, color='#ff6b6b')
            ax3.fill_between(data.index, 0, 30, alpha=0.1, color='#00d4ff')
            
            # Info RSI
            rsi_text = f"RSI (14): {rsi.iloc[-1]:.0f}"
            ax3.text(0.02, 0.92, rsi_text, transform=ax3.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # William %R
            high_14 = data['High'].rolling(14).max()
            low_14 = data['Low'].rolling(14).min()
            williams_r = -100 * (high_14 - data['Close']) / (high_14 - low_14)
            
            # Plot Williams %R (di axis lain)
            ax3_2 = ax3.twinx()
            ax3_2.plot(data.index, williams_r, color='#ffd93d', linewidth=1, linestyle=':', label='William %R')
            ax3_2.axhline(y=-20, color='#ff6b6b', linewidth=0.5, linestyle='--', alpha=0.3)
            ax3_2.axhline(y=-80, color='#00d4ff', linewidth=0.5, linestyle='--', alpha=0.3)
            
            williams_text = f"William %R: {williams_r.iloc[-1]:.2f}"
            ax3.text(0.02, 0.82, williams_text, transform=ax3.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax3.set_ylabel('RSI', color='#a0aec0', fontsize=10)
            ax3.set_ylim(0, 100)
            ax3.grid(True, alpha=0.15, color='#2d3748')
            ax3.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax3.tick_params(colors='#a0aec0')
            ax3_2.tick_params(colors='#a0aec0')
            
            # ============================================
            # PLOT 4: Stochastic + Volume
            # ============================================
            ax4 = fig.add_subplot(gs[3])
            ax4.set_facecolor('#0d1117')
            
            # Stochastic (14, 3)
            low_14 = data['Low'].rolling(14).min()
            high_14 = data['High'].rolling(14).max()
            stoch_k = 100 * ((data['Close'] - low_14) / (high_14 - low_14))
            stoch_d = stoch_k.rolling(3).mean()
            
            # Plot Stochastic
            ax4.plot(data.index, stoch_k, color='#00d4ff', linewidth=1.5, label='%K (14)')
            ax4.plot(data.index, stoch_d, color='#ffd93d', linewidth=1.5, label='%D (3)')
            
            # Level Stochastic
            ax4.axhline(y=80, color='#ff6b6b', linewidth=0.5, linestyle='--', alpha=0.5)
            ax4.axhline(y=20, color='#00d4ff', linewidth=0.5, linestyle='--', alpha=0.5)
            ax4.fill_between(data.index, 80, 100, alpha=0.1, color='#ff6b6b')
            ax4.fill_between(data.index, 0, 20, alpha=0.1, color='#00d4ff')
            
            # Info Stochastic
            stoch_text = f"Stoch %K (14, 3): {stoch_k.iloc[-1]:.2f}  %D (3): {stoch_d.iloc[-1]:.2f}"
            ax4.text(0.02, 0.92, stoch_text, transform=ax4.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            # Info level
            level_text = "80: 80  20: 20"
            ax4.text(0.02, 0.82, level_text, transform=ax4.transAxes,
                    fontsize=9, color='#a0aec0', verticalalignment='top',
                    bbox=dict(boxstyle='round', facecolor='#1f2937', alpha=0.8))
            
            ax4.set_ylabel('Stochastic', color='#a0aec0', fontsize=10)
            ax4.set_ylim(0, 100)
            ax4.grid(True, alpha=0.15, color='#2d3748')
            ax4.legend(loc='upper left', facecolor='#1f2937', edgecolor='#2d3748', labelcolor='#ffffff')
            ax4.tick_params(colors='#a0aec0')
            
            # Format x-axis untuk semua plot
            for ax in [ax1, ax2, ax3, ax4]:
                ax.xaxis.set_major_formatter(mdates.DateFormatter('%b %d'))
                ax.xaxis.set_major_locator(mdates.WeekdayLocator(interval=2))
                ax.tick_params(axis='x', colors='#a0aec0')
            
            # Footer
            footer_text = f"Generated at {datetime.now().strftime('%Y-%m-%d %H:%M:%S')} WITA using Python/Matplotlib"
            fig.text(0.5, 0.01, footer_text, ha='center', fontsize=8, color='#4a5568')
            
            # Simpan chart
            plt.tight_layout()
            filename = f"{self.chart_dir}/{symbol}_custom_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
            plt.savefig(filename, dpi=100, bbox_inches='tight', facecolor='#0d1117')
            plt.close()
            
            logger.info(f"✅ Chart custom {symbol} berhasil dibuat")
            return filename
            
        except Exception as e:
            logger.error(f"Error creating custom chart: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
            return None
