import pandas as pd
import numpy as np
import alpaca_trade_api as tradeapi
import matplotlib.pyplot as plt
import matplotlib.ticker as mtick  
from matplotlib.animation import FuncAnimation
from matplotlib.widgets import Slider
import matplotlib.dates as mdates
import tkinter as tk
from tkinter import simpledialog, messagebox
import winsound, requests, warnings, sys
import yfinance as yf 

warnings.filterwarnings("ignore")

# --- Initialize Tkinter for Startup Prompts Only ---
root = tk.Tk()
root.withdraw()

ALPACA_KEY = simpledialog.askstring("Authentication", "Enter your Alpaca API Key ID:", parent=root)
ALPACA_SECRET = simpledialog.askstring("Authentication", "Enter your Alpaca Secret Key:", parent=root)

if not ALPACA_KEY or not ALPACA_SECRET:
    messagebox.showerror("Error", "Alpaca API keys are required to stream data.")
    sys.exit()

root.destroy()

# --- 1. CLOUD ENDPOINT CONFIGURATION ---
FIREBASE_URL = "https://trading-bot-1c9f5-default-rtdb.firebaseio.com/.json"

# --- 2. ALPACA PAPER TRADING CLIENT ---
api = tradeapi.REST(
    key_id=ALPACA_KEY, 
    secret_key=ALPACA_SECRET, 
    base_url="https://paper-api.alpaca.markets", 
    api_version='v2'
)

try: 
    api.get_account()
except Exception as e:
    print(f"Authentication Failed: Alpaca Error: {e}")
    sys.exit()

ticker_symbol_yf = 'BTC-USD' 
ticker_symbol_alpaca = 'BTCUSD'

bb_window, rsi_period, bb_std, RSI_BUY_LIMIT = 20, 14, 1.4, 45 
TRAILING_FLOOR_PCT = 0.0005

# --- 3. MATPLOTLIB CANVAS DESIGN ---
plt.style.use('dark_background')
fig, ax = plt.subplots(figsize=(14, 7))
fig.canvas.manager.set_window_title(f"🚀 {ticker_symbol_alpaca} Live Real-Time Dashboard")

# Chart bounds adjusted to give the text layers plenty of vertical breathing room
fig.subplots_adjust(left=0.08, right=0.82, top=0.88, bottom=0.32) 

# Sidebar pinned to the far right edge of your application glass screen
sidebar_ax = fig.add_axes([0.86, 0.05, 0.13, 0.90]) 
sidebar_ax.axis('off')

# Stacked Interactive Risk Management Sliders
slider1_ax = fig.add_axes([0.18, 0.18, 0.55, 0.03])
cash_slider = Slider(ax=slider1_ax, label='Risk Allocation % ', valmin=1.0, valmax=20.0, valinit=2.0, valfmt='%1.1f%%', color='#00ffcc')

slider2_ax = fig.add_axes([0.18, 0.12, 0.55, 0.03])
sl_slider = Slider(ax=slider2_ax, label='Stop Loss % ', valmin=0.5, valmax=5.0, valinit=1.5, valfmt='%1.1f%%', color='#ff3399')

slider3_ax = fig.add_axes([0.18, 0.06, 0.55, 0.03])
tp_slider = Slider(ax=slider3_ax, label='Take Profit % ', valmin=0.5, valmax=5.0, valinit=1.5, valfmt='%1.1f%%', color='#ffff33')

print(f"🚀 Starting Real-Time Multi-Strategy Loop for {ticker_symbol_alpaca}...")

def play_chime(t):
    try: 
        winsound.Beep(600, 150)
        if t == "buy": winsound.Beep(900, 200) 
        else: winsound.Beep(850, 150); winsound.Beep(550, 250)
    except: pass 

def update_bot(frame):
    try:
        # Dynamically sample slider selections every clock iteration
        current_sl_pct = sl_slider.val / 100.0
        current_tp_pct = tp_slider.val / 100.0

        # --- START OF NEW CODE ---
        df = yf.download(
            tickers=ticker_symbol_yf, 
            period="3d", 
            interval="1m", 
            progress=False, 
            auto_adjust=True
        )
        
        if df.empty:
            print(f"Warning: No market data payload found for {ticker_symbol_yf}")
            return
            
        df = df.reset_index()
        
        # Handle MultiIndex column layouts often returned by yf.download
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
            
        df['datetime'] = df['Datetime']
        df['close_val'] = df['Close']
        # --- END OF NEW CODE (It stops right here) ---

        if len(df) < bb_window: return

        # Leave everything below this line alone!
        df['MA20'] = df['close_val'].rolling(window=bb_window).mean()
        df['STD20'] = df['close_val'].rolling(window=bb_window).std()
        df['Upper_BB'] = df['MA20'] + (df['STD20'] * bb_std)
        df['Lower_BB'] = df['MA20'] - (df['STD20'] * bb_std)
        df['Donchian_High'] = df['close_val'].rolling(window=20).max()
        df['EMA50'] = df['close_val'].ewm(span=50, adjust=False).mean()

        delta = df['close_val'].diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=rsi_period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=rsi_period).mean()
        loss = loss.replace(0, 0.00001)
        df['RSI'] = 100 - (100 / (1 + (gain / loss)))

        c_price = df['close_val'].iloc[-1]
        lower_bb = df['Lower_BB'].iloc[-1]
        upper_bb = df['Upper_BB'].iloc[-1]
        mid_ma = df['MA20'].iloc[-1]
        donchian_h = df['Donchian_High'].iloc[-2]
        ema50 = df['EMA50'].iloc[-1]
        l_rsi = df['RSI'].iloc[-1]
        b_width = (upper_bb - lower_bb) / mid_ma
        
        if c_price < ema50 and l_rsi < 30:
            mode, buy_signal = "CRASH SHIELD 🛡️", (c_price < lower_bb and l_rsi < 25)
        elif b_width > 0.04 and c_price > ema50:
            mode, buy_signal = "TREND BREAKOUT 📈", (c_price >= donchian_h and l_rsi < 65)
        else:
            mode, buy_signal = "MEAN REVERSION 🔄", (c_price < lower_bb and l_rsi < RSI_BUY_LIMIT)

        acc = api.get_account()
        cash_bal, equity = float(acc.cash), float(acc.equity)
        pos = api.list_positions()
        btc_pos = next((p for p in pos if p.symbol == ticker_symbol_alpaca), None)
        has_pos = bool(btc_pos)
        qty = float(btc_pos.qty) if has_pos else 0.0
        
        action, sl, tp, unreal, ret, entry, p_color = "SCANNING", 0.0, 0.0, 0.0, 0.0, 0.0, '#00ffcc'

        if has_pos:
            unreal, ret, entry = float(btc_pos.unrealized_pl), float(btc_pos.unrealized_plpc) * 100, float(btc_pos.avg_entry_price)
            p_color = '#00ffcc' if unreal >= 0 else '#ff3399'
            
            sl, tp = entry * (1.0 - current_sl_pct), entry * (1.0 + current_tp_pct)

            # --- CHECK CONDITIONS FOR TRADING EXECUTION ---
            if (ret >= (TRAILING_FLOOR_PCT * 100) and c_price < df['close_val'].iloc[-2]) or \
               (c_price <= sl) or \
               (c_price >= tp) or \
               (c_price >= mid_ma and mode == "MEAN REVERSION 🔄"):
                
                # Determine specific string flag tag for telemetry updates
                if c_price <= sl: action = "STOP LOSS 🔴"
                elif c_price >= tp: action = "TAKE PROFIT 🟢"
                elif ret >= (TRAILING_FLOOR_PCT * 100): action = "TRAILING LOCK 🟢"
                else: action = "REVERTED 🔴"
                
                # FIXED: Cancel pending working fills and WAIT for the exchange to process it
                try:
                    api.cancel_all_orders()
                    import time
                    time.sleep(1) # crucial 1-second breather block for the API backend
                except:
                    pass

                # Force precision layout trimming to clear exchange asset fee margins
                safe_sell_qty = round(qty * 0.999, 4) 
                
                if safe_sell_qty > 0:
                    try:
                        api.submit_order(symbol=ticker_symbol_alpaca, qty=safe_sell_qty, side='sell', type='market', time_in_force='gtc')
                        play_chime("sell")
                    except Exception as order_err:
                        print(f"Order submission rejected by exchange engine: {order_err}")
            else: 
                action = "HOLDING ⚪"
        else:
            if buy_signal:
                t_qty = round((cash_bal * (cash_slider.val / 100.0)) / c_price, 4)
                if t_qty > 0:
                    try:
                        api.submit_order(symbol=ticker_symbol_alpaca, qty=t_qty, side='buy', type='market', time_in_force='gtc')
                        action = f"BUY SENT 🟢"
                        play_chime("buy")
                    except Exception as buy_err:
                        print(f"Buy Order Rejected: {buy_err}")
            else: 
                action = "WAIT SETUP ⚪"


                # --- 1. CALCULATE ORDER & POSITION METRICS ---
        holding_usd_value = qty * c_price
        
        try:
            open_orders_list = api.list_orders(status='open')
            working_count = len(open_orders_list)
        except:
            working_count = 0
            
        try:
            closed_orders_list = api.list_orders(status='closed', limit=50)
            filled_today_count = sum(1 for o in closed_orders_list if o.status == 'filled')
        except:
            filled_today_count = 0

        # --- 2. EXHAUSTIVE REAL-TIME PAYLOAD SYNC TO FIREBASE ROOT ---
        try:
            firebase_payload = {
                # Live Market Metrics
                "state": f"{mode} | {action}",
                "market_mode": f"{mode}",
                "action_status": f"{action}",
                "rsi": round(float(l_rsi), 1),
                "price": round(float(c_price), 2),
                
                # Capital & Account Metrics
                "cash": round(float(cash_bal), 2),
                "equity": round(float(equity), 2),
                "acct_pnl": round(float(equity - 100000.0), 2),
                
                # Positions & Active Order Metrics
                "held": round(float(qty), 5),
                "holding_usd_value": round(float(holding_usd_value), 2),
                "entry_price": round(float(entry), 2) if has_pos else 0.0,
                "trade_pnl": round(float(unreal), 2) if has_pos else 0.0,
                "trade_pct": round(float(ret), 2) if has_pos else 0.0,
                "working_orders_count": int(working_count),
                "fills_today_count": int(filled_today_count),
                
                # Target Metrics (Slider Positions)
                "stop_loss_trigger": round(float(sl), 2) if has_pos else f"-{sl_slider.val:.1f}%",
                "take_profit_trigger": round(float(tp), 2) if has_pos else f"+{tp_slider.val:.1f}%"
            }
            
            # This completely replaces your root node with the full sync state
            requests.put(FIREBASE_URL, json=firebase_payload, timeout=3)
        except Exception as firebase_err: 
            print(f"Cloud update sync skipped: {firebase_err}")


        # --- Redraw Plot Canvas ---
        ax.clear()
        plot_df = df.tail(40)
        ax.plot(plot_df['datetime'], plot_df['close_val'], color='#00ffcc', linewidth=2, label=f'Price (${c_price:,.2f})')
        ax.plot(plot_df['datetime'], plot_df['MA20'], color='#666666', linestyle=':', label='Mid MA')
        ax.plot(plot_df['datetime'], plot_df['Upper_BB'], color='#ff3399', alpha=0.4, label='Upper Band')
        ax.plot(plot_df['datetime'], plot_df['Lower_BB'], color='#ffff33', alpha=0.4, label='Lower Band')
        ax.fill_between(plot_df['datetime'], plot_df['Lower_BB'], plot_df['Upper_BB'], color='#222222', alpha=0.3)
        
        if has_pos:
            ax.axhline(sl, color='#ff3399', linestyle='--', alpha=0.7, label=f'Stop Loss (${sl:,.2f})')
            ax.axhline(tp, color='#ffff33', linestyle='--', alpha=0.7, label=f'Take Profit (${tp:,.2f})')
            ax.axhline(entry, color='#ffffff', linestyle=':', alpha=0.5, label=f'Entry (${entry:,.2f})')

                # --- FIXED: Pinned price indicator badge to the left edge to prevent sidebar overlap ---
        ax.axhline(c_price, color='#00ffcc', linestyle=':', alpha=0.4)
        ax.text(
            plot_df['datetime'].iloc[2], # Left side anchor position coordinate
            c_price, 
            f" Current Price: ${c_price:,.2f} ", 
            color='black', 
            weight='bold', 
            fontsize=9, 
            bbox=dict(facecolor='#00ffcc', edgecolor='none', boxstyle='round,pad=0.3')
        )

        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        ax.yaxis.set_major_formatter(mtick.StrMethodFormatter('${x:,.0f}'))
        ax.tick_params(axis='x', rotation=30)
        ax.grid(True, color='#333333', linestyle='--', alpha=0.5)
        
        # Limit Horizontal Axis
        ax.set_xlim(plot_df['datetime'].min(), plot_df['datetime'].max())
        
        # --- PASTE THE NEW Y-AXIS SCALE FIX HERE ---
        visible_data = plot_df[['close_val', 'Lower_BB', 'Upper_BB']]
        y_min = visible_data.min().min() * 0.999
        y_max = visible_data.max().max() * 1.001
        ax.set_ylim(y_min, y_max)
        
        ax.legend(loc='upper left', framealpha=0.6)


                # --- NEW DATA AGGREGATION: Exhaustive Alpaca Order Mapping ---
        open_orders_list = api.list_orders(status='open')
        working_count = len(open_orders_list)
        
        # Query filled historical orders from today's window to track execution totals
        closed_orders_list = api.list_orders(status='closed', limit=50)
        filled_today_count = sum(1 for o in closed_orders_list if o.status == 'filled')
        
        # Calculate active inventory metrics in USD value terms
        holding_usd_value = qty * c_price

        # --- Redraw Sidebar Panel Metrics ---
        sidebar_ax.clear()
        sidebar_ax.axis('off')
        
        # Category 1: Live Market Trends
        sidebar_ax.text(0.01, 1.00, "📊 LIVE MARKET", color='#00ffcc', fontsize=10, weight='bold')
        sidebar_ax.text(0.01, 0.94, f"Mode: {mode.split()[0]}", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.89, f"Action: {action}", color=p_color, fontsize=9, weight='bold')
        sidebar_ax.text(0.01, 0.84, f"RSI Index: {l_rsi:.1f}", color='yellow' if l_rsi > 70 or l_rsi < 30 else 'white', fontsize=9)
        sidebar_ax.text(0.01, 0.79, f"BTC Spot: ${c_price:,.2f}", color='white', fontsize=9)
        
        # Category 2: Core Account & Capital Metrics
        sidebar_ax.text(0.01, 0.71, "💰 ACCOUNT METRICS", color='#ff3399', fontsize=10, weight='bold')
        sidebar_ax.text(0.01, 0.65, f"Available Cash:\n${cash_bal:,.2f}", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.57, f"Total Equity:\n${equity:,.2f}", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.49, f"Session PnL:\n${(equity - 100000.0):+,.2f}", color='#00ffcc' if equity >= 100000.0 else '#ff3399', fontsize=9, weight='bold')
        
        # Category 3: Exhaustive Positions & Active Order Metrics
        sidebar_ax.text(0.01, 0.39, "⚡ ORDER & POSITIONS", color='#ffff33', fontsize=10, weight='bold')
        sidebar_ax.text(0.01, 0.33, f"Size: {qty:.5f} BTC", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.28, f"Value: ${holding_usd_value:,.2f}", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.23, f"Entry: ${entry:,.2f}" if has_pos else "Entry: $0.00", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.18, f"Trade PnL: ${unreal:+,.2f}" if has_pos else "Trade PnL: $0.00", color=p_color, fontsize=9, weight='bold')
        sidebar_ax.text(0.01, 0.13, f"Working Orders: {working_count}", color='orange' if working_count > 0 else 'white', fontsize=9)
        sidebar_ax.text(0.01, 0.08, f"Fills Today: {filled_today_count}", color='white', fontsize=9)
        sidebar_ax.text(0.01, 0.03, f"Stop Loss: ${sl:,.2f}" if has_pos else f"SL Target: -{sl_slider.val:.1f}%", color='white' if not has_pos else '#ff3399', fontsize=9)
        sidebar_ax.text(0.01, -0.02, f"Take Profit: ${tp:,.2f}" if has_pos else f"TP Target: +{tp_slider.val:.1f}%", color='white' if not has_pos else '#00ffcc', fontsize=9)

    except Exception as main_err:
        print(f"Loop runtime execution error encountered: {main_err}")

# --- 4. ENGINE ACTIVATION ---
ani = FuncAnimation(fig, update_bot, interval=15000, cache_frame_data=False)
plt.show()
