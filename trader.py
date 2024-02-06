import threading
import MetaTrader5 as mt5
from datetime import datetime, timedelta
import pandas as pd
import pytz
import schedule
import time
import strategy
import constants
import sys
import keys

# lock = threading.Lock()

def connect():
    # lock.acquire()
    account = keys.demoAccountNum
    password = keys.demoPassword
    server = keys.demoServer

    # initialize and login to metatrader
    if not mt5.initialize(login=account, password=password, server=server):
        print("initialize() failed, error code =",mt5.last_error())
        quit()
        
    authorized=mt5.login(account, password=password, server=server)

    if authorized:
        print("connected: connecting to mt5 client")
    else:
        print(f'failed to connect to account {account}, error code: {mt5.last_error()}')
        

def disconnect():
    mt5.shutdown()
    # lock.release()
    print("Disconnecting from MT5 Client")
 
 
def get_sample_data(pair="EURUSD", time_frame=mt5.TIMEFRAME_H4):
    # define range of data to pull
    utc_from = datetime(2021, 1, 1)
    utc_to = datetime(2021, 1, 10)
    # pull data, choosing timeframe (4 hours per piece), and stock
    rates = mt5.copy_rates_range(pair, time_frame, utc_from, utc_to)

    # print the rates of the stock
    for rate in rates:
        print(rate)
    
        
def open_position(pair, order_type, size, tp_distance=None, stop_distance=None):
    # open a position on a pair - check that it exists first
    symbol_info = mt5.symbol_info(pair)
    if symbol_info is None:
        print(pair, "not found")
        return

    if not symbol_info.visible:
        print(pair, "is not visible, trying to switch on")
        if not mt5.symbol_select(pair, True):
            print("symbol_select({}}) failed, exit",pair)
            return
    print(pair, "found!")
    
    # point is the smallest price increment change that can happen on the instrument
    point = symbol_info.point
    
    # calculate stop loss and take profit prices (essentially prices to cash out)
    if(order_type == "BUY"):
        order = mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(pair).ask
        if(stop_distance):
            sl = price - (stop_distance * point)
        if(tp_distance):
            tp = price + (tp_distance * point)
    
    if(order_type == "SELL"):
        order = mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(pair).bid
        if(stop_distance):
            sl = price + (stop_distance * point)
        if(tp_distance):
            tp = price - (tp_distance * point)
            
    # build and send request to api to submit order
    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": pair,
        "volume": float(size),
        "type": order,
        "price": price,
        "sl": sl,
        "tp": tp,
        "magic": 234000,
        "comment": "My first trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    
    result = mt5.order_send(request)
    
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Failed to send order :(")
    else:
        print ("Order successfully placed!")
      
        
def positions_get(symbol=None):
    # get and return currently open positions
    if(symbol is None):
        res = mt5.positions_get()
    else:
        res = mt5.positions_get(symbol=symbol)
    
    if res is not None and res != ():
        df = pd.DataFrame(list(res), columns=res[0]._asdict().keys())
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    return pd.DataFrame()


def close_position(deal_id):
    # get the position to close from the list of open positions
    open_positions = positions_get()
    open_positions = open_positions[open_positions['ticket'] == deal_id]
    # extract following parameters after extracting row
    order_type  = open_positions["type"][0]
    symbol = open_positions['symbol'][0]
    volume = open_positions['volume'][0]
    # sell or buy depending on whether it is a buy or sell position
    if(order_type == mt5.ORDER_TYPE_BUY):
        order_type = mt5.ORDER_TYPE_SELL
        price = mt5.symbol_info_tick(symbol).bid
    else:
        order_type = mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(symbol).ask

    # build and send request to mt5 api
    close_request={
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": float(volume),
        "type": order_type,
        "position": deal_id,
        "price": price,
        "magic": 234000,
        "comment": "Close trade",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }
    result = mt5.order_send(close_request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        print("Failed to close order :(")
    else:
        print ("Order successfully closed!")


def close_position_by_symbol(symbol):
    # close positions on a certain stock
    open_positions = positions_get(symbol)
    if not open_positions.empty:
        open_positions['ticket'].apply(lambda x: close_position(x))
    
    
def calc_position_size(symbol, strategy):
    # calculate lot size based on percentage risk of funds
    print("Calculating position size for: ", symbol)
    account = mt5.account_info()
    balance = float(account.balance)
    pip_value = constants.get_pip_value(symbol, strategy['account_currency'])
    lot_size = (float(balance) * (float(strategy["risk"])/100)) / (pip_value * strategy["stopLoss"])
    lot_size = round(lot_size, 2)
    return lot_size
    
    
def get_order_history(date_from, date_to):
    res = mt5.history_deals_get(date_from, date_to)
    
    if(res is not None and res != ()):
        df = pd.DataFrame(list(res),columns=res[0]._asdict().keys())
        df['time'] = pd.to_datetime(df['time'], unit='s')
        return df
    
    return pd.DataFrame()


def calc_daily_lost_trades():
    now = datetime.now().astimezone(pytz.timezone('GMT'))
    now = datetime(now.year, now.month, now.day, hour=now.hour, minute=now.minute)
    midnight = now.replace(hour=0, minute=0, second=0, microsecond=0)
    res = get_order_history(midnight, now)

    if(res.empty):
        return 0
    else:
        lost_trade_count = 0
        for i, row in res.iterrows():
            profit = float(row['profit'])
            if(profit < 0):
                lost_trade_count += 1
        return lost_trade_count   
    
    
def check_max_drawdown(strategy):
    print("Checking maximum drawdown...")
    inital_balance = strategy['initialBalance']
    max_drawdown = strategy['maximumDrawdown']
    account_info = mt5.account_info()
    current_balance = account_info['balance']   
    
    # close all positions if max drawdown has been reached
    if(current_balance < (inital_balance * max_drawdown)):
        print("Maximum drawdown has been reached! Trading halted.")
        open_positions = positions_get()
        for index, position in open_positions.iterrows():
            deal_id = position['ticket']
            close_position(deal_id)
        exit()    
    
    
def check_trades(time_frame, pair_data, strategy):
    # allocate strategy dynamically
    for pair, data in pair_data.items():
        
        # calculate the averages specified in the strategy, and add them to the data
        moving_averages = strategy['movingAverages']
        for m in moving_averages: 
            ma_func = constants.movingAveragesFunctions[m]
            val = moving_averages[m]['val']
            data[m] = ma_func(data['close'], val)
        
        # close any deal that has been open for longer than 2 hours
        open_positions = positions_get()
        current_dt = datetime.now().astimezone(pytz.timezone('GMT'))
        for index, position in open_positions.iterrows():
            trade_open_dt = position['time'].replace(tzinfo = pytz.timezone('GMT'))
            deal_id = position['ticket']
            if(current_dt - trade_open_dt >= timedelta(hours = strategy['maxTime'])):
                close_position(deal_id)
        
        # actual execution of strategy - currently only works on ema and sma values
        last_row = data.tail(1).iloc[0] # get the most recent data point/ tick
        
        # exit strategy - exit if value is below EMA and above SMA - indication of bearish
        if(last_row['close'] < last_row['EMA'] and last_row['close'] > last_row['SMA']):
            close_position_by_symbol(pair)
            
        # exit if daily losses exceeds strategy
        lost_trade_count = calc_daily_lost_trades()
        if(lost_trade_count > strategy['maxLosses']):
            print("Daily losses have been exceeded. Not executing any more trades today")
            continue
        # entry strategy - enter if value is above EMA and below SMA - indication of it about to go up
        if(last_row['close'] > last_row['EMA'] and last_row['close'] < last_row['SMA']):
            lot_size = calc_position_size(pair, strategy)
            open_position(pair, "BUY", lot_size, float(strategy['takeProfit']), float(strategy['stopLoss']))
        

def get_data(time_frame, strategy, max_data_points):
    # get the data on the pairs within a certain given time
    pairs = strategy['pairs']
    pair_data = dict()
    for pair in pairs:
        # for each pair get the data from the 1st jan 2024 till now in tick steps of time_frame length
        # we use the max_data_points as calculated from the max number of points required for the averages as defined in the strategy
        utc_from = datetime.now() - timedelta(minutes=max_data_points * time_frame)
        utc_from = utc_from.astimezone(pytz.timezone('GMT'))
        
        date_to = datetime.now().astimezone(pytz.timezone('GMT'))
        date_to = datetime(date_to.year, date_to.month, date_to.day, hour=date_to.hour, minute=date_to.minute)
        
        rates = mt5.copy_rates_range(pair, time_frame, utc_from, date_to)
        
        rates_frame = pd.DataFrame(rates)
        rates_frame['time'] = pd.to_datetime(rates_frame['time'], unit='s')
        rates_frame.drop(rates_frame.tail(1).index, inplace = True) # drop latest one as to not get like half a tick's worth of data
        pair_data[pair] = rates_frame
    return pair_data


def run_trader(time_frame, strategy, max_data_points):
    print("Running trader at", datetime.now())
    connect()
    pair_data = get_data(time_frame, strategy, max_data_points) # will return a dict of stockname:[all ticks from tick{now-max_data_points} till now]
    check_trades(time_frame, pair_data, strategy)
    disconnect()


def live_trading(strategy):
    max_data_points = max([ma['val'] for ma in strategy['movingAverages'].values()]) + 5
    
    # execute algorithm every 15 mins
    schedule.every().hour.at(":00").do(run_trader, mt5.TIMEFRAME_M15, strategy, max_data_points)
    schedule.every().hour.at(":15").do(run_trader, mt5.TIMEFRAME_M15, strategy, max_data_points)
    schedule.every().hour.at(":30").do(run_trader, mt5.TIMEFRAME_M15, strategy, max_data_points)
    schedule.every().hour.at(":45").do(run_trader, mt5.TIMEFRAME_M15, strategy, max_data_points)
    schedule.every(15).minutes.do(check_max_drawdown, strategy)
    
    while True:
        schedule.run_pending()
        time.sleep(1)

if __name__ == '__main__':
    for arg in sys.argv[1:]:
        current_strategy = arg
        print("Trading bot started with strategy:", current_strategy)
        current_strategy = strategy.load_strategy(current_strategy)
        live_trading(current_strategy)
        # trading = threading.Thread(target=live_trading, args=(current_strategy,))
        # trading.start()
