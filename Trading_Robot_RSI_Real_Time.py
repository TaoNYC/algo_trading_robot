""" Input Application for Auto-Trader """

# Import required libraries
import fire
import questionary
import time
from datetime import datetime, timedelta
from pathlib import Path
import pandas as pd
import ast
import json
from sympy import capture
import websocket
from alpaca_trade_api import TimeFrame
import plotly.graph_objects as go
import plotly.express as px
import talib as ta
import numpy as np
import alpaca_trade_api as tradeapi
from alpaca_trade_api import REST, TimeFrame


from utils.helper import get_alpacas_info

alpaca_api_key = get_alpacas_info()[2]
alpaca_secret_key = get_alpacas_info()[3]

# Function to input tickers to track as well as the buy and sell prices
def input_ticker_info():
    # Import csv
    sectors_and_tickers = pd.read_csv(
        Path("./Resources/sectors_and_tickers.csv")
    )

    # Set the sectors available for selection based on columns in CSV
    sector_list = sectors_and_tickers.columns

    # Select the sector for the stock you would like to trade
    sector = questionary.select("From which sector would you like to select your stock?",choices=sector_list).ask()

    # Assign the list of avaible tickers based on the sector selected
    ticker_list = sectors_and_tickers[f"{sector}"]

    # Select the ticker you would like to trade
    ticker = questionary.select("Please select the ticker you would like to trade.",choices=ticker_list).ask()

    # Get current buying power
    buying_power = get_alpacas_info()[0].buying_power
    buying_power = float(buying_power)

    print(f"You have {buying_power} to trade.")

    # Input percentage of portfolio to allocate to this stock
    allocation = questionary.text(f"What percentage of your cash on hand would you like to allocate to trading {ticker} ?").ask()
    allocation = float(allocation)

    # Check that the percentage is positive and not above 100%
    if allocation < 0:
        allocation = questionary.text("Please enter a non-negative number").ask()
    elif allocation > 100:
        allocation = questionary.text("Please enter a number less than 100").ask()

    allocation = float(allocation)
    
    # Ensure inputs are formatted to be consumed by auto-trader
    if allocation > 0 and allocation < 1: 
        allocation = allocation
    else:
        allocation = allocation/100

    # Assign amount to allocate to stock
    trade_allocation = allocation * buying_power

    # Input buy signal percentages
    process_buy = True
    while process_buy:
        buy_signal = questionary.text("What percentage would you like to use as your buy signal").ask()
        buy_signal = float(buy_signal)

        # Handle zero value entries    
        if buy_signal == 0:
            buy_opt_out = questionary.confirm("Are you sure you do not want to buy any of these shares today?").ask()
            if buy_opt_out:
                break
            else:
                continue
        break

    # Ensure inputs are formatted to be consumed by auto-trader
    if buy_signal > 0 and buy_signal < 1: 
        buy_signal = buy_signal
    else:
        buy_signal = buy_signal/100

    # Input sell signal percentages
    process_sell = True
    while process_sell:
        sell_signal = questionary.text("what percentage would you like to use as your sell signal").ask()
        sell_signal = float(sell_signal)

        # Check that the percentage is positive
        if sell_signal < 0:
            sell_signal = questionary.text("Please enter a non-negative number").ask()
        # Handle zero value entries 
        elif sell_signal == 0:
            sell_opt_out = questionary.confirm("Are you sure you do not want to buy any of these shares today?").ask()
            if sell_opt_out:
                break
            else:
                continue
        break
    
    # Ensure unputs are formatted to be consumed by auto-trader
    if sell_signal > 0 and sell_signal < 1:
        sell_signal = sell_signal
    else:
        sell_signal = sell_signal/100
    
    # Return variables
    print(ticker, buy_signal, sell_signal, trade_allocation)
    return ticker, buy_signal, sell_signal, trade_allocation

# Function to initialize the trading bot
def run_robo_trader(ticker, buy_signal, sell_signal, trade_allocation):
    # Set date offset to 11 days prior 
    days_to_subtract = 7

    # Set today as a variable
    today = (datetime.today()).strftime('%Y-%m-%d')
    print(f'today is {today}')

    # Determine the date of 11 days prior
    earlier_date_to_compare = (datetime.today()-timedelta(days=days_to_subtract)).strftime('%Y-%m-%d')
    print(f'earlier_date_to_compare is {earlier_date_to_compare}')

    # Extract price of earlier date from Alpaca API
    bars_from_earlier_date = get_alpacas_info()[1].get_bars(
        ticker,
        TimeFrame.Day,
        earlier_date_to_compare,
        earlier_date_to_compare
    ).df
    print(f'bars_from_earlier_date {bars_from_earlier_date}')

    # Set the close price from earlier date
    price_from_earlier_date = bars_from_earlier_date.iloc[0]['close']
    print(f'The price_from_earlier_date is {price_from_earlier_date}')
    
    # Calculating price to start trading bot
    price_to_start_trading_bot = price_from_earlier_date * (1+buy_signal)
    print(f'price_to_start_trading_bot is {price_to_start_trading_bot}')
    
    api = tradeapi.REST(alpaca_api_key, alpaca_secret_key, "https://paper-api.alpaca.markets", "v2")
    # Set alpaca socket URL
    socket = "wss://stream.data.alpaca.markets/v2/iex"


    days_to_subtract = 7
    today = (datetime.today()).strftime('%Y-%m-%d')
    print(f'today is {today}')
    earlier_date_to_compare = (datetime.today()-timedelta(days=days_to_subtract)).strftime('%Y-%m-%d')
    print(f'earlier_date_to_compare is {earlier_date_to_compare}')
    rest_client = REST(alpaca_api_key, alpaca_secret_key)
    bars_from_earlier_date = rest_client.get_bars(ticker, TimeFrame.Day, earlier_date_to_compare, earlier_date_to_compare).df
    price_from_earlier_date = bars_from_earlier_date.iloc[0]['close']
    print(f'The price_from_earlier_date is {price_from_earlier_date}')

    rsi_timeframe = 3
    oversold_threshold = 49
    overbought_threshold = 51
    #company = "TSLA"
    # Set the number of shares (rounded) that could be bought, given the input amount to trade and last close price
    shares_to_trade = trade_allocation//price_from_earlier_date
    print(f'we will ask trading robot to trade {shares_to_trade} shares of {ticker}')
    data = []
    data_close = []

    # Define function for websockett
    def on_open(ws):
        print("opened")
        # Authenticate into Alpacas
        auth_data = {"action":"auth","key":alpaca_api_key,"secret":alpaca_secret_key}
        ws.send(json.dumps(auth_data))
        listen_message = {"action":"subscribe","bars":[ticker]}
        ws.send(json.dumps(listen_message))

    # Define function to display the previous close time and close price minute by minute
    def on_message(ws, message):
        print("received a message")
        print(message)
        formatted_message = ast.literal_eval(message)

        # Define the time and the close price from when the last message was received
        last_time = formatted_message[0].get("t")
        last_open = formatted_message[0].get("o")
        last_high = formatted_message[0].get("h")
        last_low = formatted_message[0].get("l")
        last_close = formatted_message[0].get("c")
        last_volumne = formatted_message[0].get("v")
        print(f'infor from preivous minitue: time is {last_time}; open is {last_open};high is {last_high};low is {last_low};close is {last_close};volumne is {last_volumne}')
    #    print("Last price after minute closed: {}$".format(last_close))

        last_info=[]
        last_info.append(last_time)
        last_info.append(last_open)
        last_info.append(last_high)
        last_info.append(last_low)
        last_info.append(last_close)
        last_info.append(last_volumne)

        print(f'last_info is {last_info}')
        
        data.append(last_info)
        print(f'Data is {data}')
        
        data_df = pd.DataFrame(data,columns=['time','open','high','low','close','volumue'])
        #data_df = pd.DataFrame(data_df,index='time')
        data_df.set_index(data_df['time'])
        print(f'data_df is {data_df}')
        
        data_close = data_df['close']
        print(f'data_close is {data_close}')
        print(f'len of data_close is {len(data_close)} ')
        
        candlestick_fig = go.Figure(data=[go.Candlestick(x=data_df.index,
                                                        open=data_df['open'],
                                                        high=data_df['high'],
                                                        low=data_df['low'],
                                                        close=data_df['close'])])



        # adding both plots onto one chart
        fig = go.Figure(data=candlestick_fig.data)

        # displaying our chart
        fig.show()




        try:
            # "-3" is added here to take into account first 3 lines without prices
            if len(data_close) > rsi_timeframe:
                np_data = np.array(data_close)
                rsis = ta.RSI(np_data, rsi_timeframe)
                rsi_now = rsis[-1]
                
                print("The list of last 5 RSIs:", rsis[-5:])
                print("Last RSI: ", rsi_now)

                
                rsi_fig = px.line(rsis)
                fig = go.Figure(data=rsi_fig)
                fig.show()
                
                
                if rsi_now < oversold_threshold:
                    try:
                        api.get_position(ticker)
                        print("We hit the threshold to buy, but we already have some shares, so we won't buy more.")
                    except:
                        api.submit_order(symbol=ticker, qty=shares_to_trade, side = "buy", type='market', time_in_force='gtc')
                        print(f'RSI just dropped below oversold_threshold {oversold_threshold}')
                        print('We submitted the order to buy {} {} shares.'.format(shares_to_trade, ticker))
                
                elif rsi_now > overbought_threshold:
                    try:
                        api.get_position(ticker)
                        api.submit_order(symbol=ticker,qty=shares_to_trade,side='sell',type='market',time_in_force='gtc')
                        print(f'RSI just rose above overbought_threshold {overbought_threshold}')
                        print('We submitted an order to sell {} {} shares.'.format(shares_to_trade, ticker))
                    except:
                        print(f"We hit the threshold {overbought_threshold} to sell, but we don't have anything to sell. Next time maybe.")
                
                else:
                    print("The RSI is {} and it's between the given thresholds: {} and {}, so we wait.".format(rsi_now, oversold_threshold, overbought_threshold))
            else:
                print("Not enough prices to calculate RSI and start trading:")
                #print("Not enough prices to calculate RSI and start trading:", len(data)-3, "<=", rsi_timeframe)
        except:
            print("I tried my best, buy I think something went wrong. I'll try again in a moment.")
        


    # Once the realtime price exceeds the signal price, start the trading bot
       
    def on_close(ws):
        print("closed connection")

    # Create the websocket variable to stream realtime data
    ws = websocket.WebSocketApp(
        socket,
        on_open=on_open,
        on_message=on_message,
        on_close=on_close
    )
    ws.run_forever()

# Main function for running the script
def run():
    ticker, buy_signal, sell_signal, trade_allocation = input_ticker_info()
    run_robo_trader(ticker, buy_signal, sell_signal, trade_allocation)

if __name__ == "__main__":
    fire.Fire(run)
