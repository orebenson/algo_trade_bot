from matplotlib.dates import DateFormatter
import pandas as pd
import matplotlib.pyplot as plt
from datetime import datetime
import MetaTrader5 as mt5
import constants
import keys
import strategy
import numpy as np
import random
import sys

class MT5Connection:
    def __init__(self, account, password, server):
        self.account = account
        self.password = password
        self.server = server

    def connect(self):
        if not mt5.initialize(login=self.account, password=self.password, server=self.server):
            print("initialize() failed, error code =", mt5.last_error())
            sys.exit()

        authorized = mt5.login(self.account, password=self.password, server=self.server)

        if authorized:
            print("connected: connecting to mt5 client")
        else:
            print(f'failed to connect to account {self.account}, error code: {mt5.last_error()}')

    def disconnect(self):
        mt5.shutdown()
        print("Disconnecting from MT5 Client")

    def get_historical_data(self, pair, time_frame, start_date, end_date):
        utc_from = start_date
        utc_to = end_date
        rates = mt5.copy_rates_range(pair, time_frame, utc_from, utc_to)
        rates_frame = pd.DataFrame(rates)
        rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
        return rates_frame


class Backtester:
    @staticmethod
    def calc_position_size(symbol, strategy):
        account = mt5.account_info()
        balance = float(account.balance)
        pip_value = constants.get_pip_value(symbol, strategy['account_currency'])
        lot_size = (float(balance) * (float(strategy["risk"]) / 100)) / (pip_value * strategy["stopLoss"])
        lot_size = round(lot_size, 2)
        return lot_size

    @staticmethod
    def simulate_trades(pair, data, strategy):
        positions = []
        balance = strategy['initialBalance']
        equity_curve = []
        equity_curve_timestamps = []
        actual_price = []

        for i, row in data.iterrows():
            close_price = row['close']
            open_time = row['time']
            
            trading_start_time = datetime.strptime("00:01:00", "%H:%M:%S").time()
            trading_end_time = datetime.strptime("23:59:00", "%H:%M:%S").time()

            if open_time.time() < trading_start_time or open_time.time() > trading_end_time:
                continue  # Skip if outside trading hours
            
            # calculate the averages for ema and sma
            moving_averages = strategy['movingAverages']
            
            ema_func = constants.movingAveragesFunctions['EMA']
            ema_val = ema_func(data[:i+1]['close'], moving_averages['EMA']['val']).iloc[-1]
            
            sma_func = constants.movingAveragesFunctions['SMA']
            sma_val = sma_func(data[:i+1]['close'], moving_averages['SMA']['val']).iloc[-1]
            
            # If condition met, simulate opening a position
            
            if (close_price > ema_val) and (close_price < sma_val):
                lot_size = Backtester.calc_position_size(pair, strategy)
                order_type = "BUY"
                price = close_price
                take_profit_distance = float(strategy['takeProfit'])
                stop_loss_distance = float(strategy['stopLoss'])
                
                # Introduce slippage
                slippage_enabled = strategy.get('slippage_enabled', False)
                slippage_probability = strategy.get('slippage_probability', 0.1)
                slippage_ticks = random.randint(1, 3)

                if slippage_enabled and random.random() < slippage_probability:
                    print(f"{open_time} - Slippage occurred on opening. Skipping {slippage_ticks} ticks.")
                    continue

                # Simulate opening position
                positions.append({
                    'open_time': open_time,
                    'symbol': pair,
                    'order_type': order_type,
                    'size': lot_size,
                    'entry_price': price,
                    'take_profit_distance': take_profit_distance,
                    'stop_loss_distance': stop_loss_distance,
                })

                print(f"{open_time} - BUY - {lot_size} lots at {price}")

            # Simulate closing positions and update equity
            new_positions = []
            for position in positions:
                
                slippage_enabled = strategy.get('slippage_enabled', False)
                slippage_probability = strategy.get('slippage_probability', 0.1)
                slippage_ticks = random.randint(1, 3)

                if slippage_enabled and random.random() < slippage_probability:
                    print(f"{open_time} - Slippage occurred on closing. Skipping {slippage_ticks} ticks.")
                    continue
                
                if (close_price < ema_val and close_price > sma_val) or (close_price <= position['entry_price'] - position['stop_loss_distance']) or (close_price >= position['entry_price'] + position['take_profit_distance']):
                    equity_change = (close_price - position['entry_price']) * position['size']
                    balance += equity_change
                    print(f"{open_time} - SELL - {position['size']} lots at {close_price}. P/L: {equity_change}")
                else:
                    new_positions.append(position)
            positions = new_positions

            # Update equity for open positions
            for position in positions:
                equity_change = (close_price - position['entry_price']) * position['size']
                balance += equity_change

            # Append the updated equity to the equity curve
            equity_curve.append(balance)
            equity_curve_timestamps.append(open_time)
            actual_price.append(close_price)

        # Convert lists to NumPy arrays
        equity_curve = np.array(equity_curve)
        equity_curve_timestamps = np.array(equity_curve_timestamps)
        actual_price = np.array(actual_price)

        return equity_curve_timestamps, equity_curve, actual_price

    @staticmethod
    def plot_backtest_equity_curves(pairs, equity_data):
        fig, ax1 = plt.subplots(figsize=(10, 6))

        for pair, equity_curve_data in zip(pairs, equity_data):
            timestamps = equity_curve_data['timestamps']
            equity_curve = equity_curve_data['equity']
            actual_price = equity_curve_data['actual_price']

            # Ensure lengths are consistent
            if len(timestamps) != len(equity_curve):
                print(f"Error: Length mismatch for {pair}. Skipping...")
                continue
            
            # Plot equity curve on the primary y-axis (left)
            ax1.plot(timestamps, equity_curve, label=f'Equity Curve - {pair}', color='blue')

        ax1.set_xlabel('Time')
        ax1.set_ylabel('Equity (in Account Currency)', color='blue')  # Primary y-axis label
        ax1.tick_params('y', colors='blue')  # Color of tick labels on primary y-axis

        # Formatting timestamp labels
        date_format = DateFormatter('%d %b %H:%M')
        ax1.xaxis.set_major_formatter(date_format)

        # Create a secondary y-axis (right) for actual price
        ax2 = ax1.twinx()
        ax2.plot(timestamps, actual_price, label=f'Actual Price - {pair}', color='green')
        ax2.set_ylabel('Actual Price', color='green')  # Secondary y-axis label
        ax2.tick_params('y', colors='green')  # Color of tick labels on secondary y-axis

        ax1.legend(loc='upper left')
        ax2.legend(loc='upper right')

        # Customize grid for more detail
        ax1.grid(True, linestyle='--', alpha=0.5)
        ax1.minorticks_on()
        ax1.grid(which='minor', linestyle=':', linewidth='0.5', alpha=0.5)

        plt.title('Backtest Equity Curves')
        plt.tight_layout()
        plot_time = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        plt.savefig(f'graphs\\backtest_equity_curve_{plot_time}.png')
        plt.show()

    @staticmethod
    def backtest(strategy, time_frame, start_date, end_date, pairs, mt5_connection):
        equity_data = []

        for pair in pairs:
            historical_data = mt5_connection.get_historical_data(pair, time_frame, start_date, end_date)
            equity_curve_timestamps, equity_curve, actual_price = Backtester.simulate_trades(pair, historical_data, strategy)
            equity_data.append({'pair': pair, 'timestamps': equity_curve_timestamps, 'equity': equity_curve, 'actual_price':actual_price})

        Backtester.plot_backtest_equity_curves(pairs, equity_data)

def main():
    mt5_connection = MT5Connection(keys.demoAccountNum, keys.demoPassword, keys.demoServer)
    mt5_connection.connect()

    current_strategy = strategy.load_strategy("strategy1")
    time_frame = mt5.TIMEFRAME_M15
    start_date = datetime(2023, 1, 2)
    end_date = datetime(2023, 12, 29)
    pairs = ["GBPUSD"]

    Backtester.backtest(current_strategy, time_frame, start_date, end_date, pairs, mt5_connection)

if __name__ == '__main__':
    main()
