__author__ = 'dsyko'

import MtGox
import Secret
import couchdb
import time
import pandas as pd
import HistoricDataCapture
from pylab import plot, ylim, xlim, show, xlabel, ylabel, grid



class TradeController:
    def __init__(self, api_interface, couch_interface, run_id):
        """

        :param api_interface: MtGox or HistoricTesting API
        :param couch_interface: interface to our couchDB
        :param run_id: unique string, used when logging trade outcomes to couchDB
        """
        self.api_interface = api_interface
        self.couch_interface = couch_interface
        self.run_id = str(run_id)


        #Check if we have a database by this name on couch, if so append time stamp to name
        if self.run_id in self.couch_interface:
            self.run_id += "-" + str(int(time.time() * 1e6))
        print "Logging trade info in %s db on couchDB" % self.run_id
        self.log_database = self.couch_interface.create(self.run_id)

        #Temporary variable to avoid spamming API with requests, del after we use the info
        account_info = self.api_interface.account_info()
        self.btc_balance = account_info['btc_balance']
        self.usd_balance = account_info['usd_balance']
        self.trade_fee = account_info['trade_fee']
        del account_info
        self.btc_price = {}
        self.last_market_info = []
        self.recent_price_info = pd.Series()
        self.last_trade_attempt = 0
        self.seconds_between_trades = 0

    def initialize_price_info(self, trade_start_time, window_size_minutes, update_from_gox):

        #Get historic data from couchDB so we can compute our windowed moving avg, or other stats
        #We will ask for price values ending at the time we want to start trading, going back to fill the window
        """

        :param trade_start_time: microsecond time stamp at which trading will begin
        :param window_size_minutes: how far back to grab data from, starting at trade_start_time
        :param update_from_gox: True or False, if True and there isn't enough data in couchDB grab data from MtGox
        :return: None
        """
        end_time = trade_start_time
        #Going back 4 times the window size, sometimes there are no trades for a few minutes
        start_time = trade_start_time - (2 * window_size_minutes * 60000000)
        historic_data = self.couch_interface[Secret.bitcoin_historic_data_db_name]
        times_in_db = historic_data.view(Secret.bitcoin_historic_data_view_name)
        temp_time_window = times_in_db[start_time:end_time]

        #Not enough values in DB. Fuck it we'll do it live, call historicData to get info from GOX into DB
        if len(temp_time_window) < window_size_minutes:

            if update_from_gox:
                print "Grabbing info from Gox only have %d points need %d" % (len(temp_time_window), window_size_minutes)
                Historic = HistoricDataCapture.HistoricDataCapture(self.api_interface, historic_data)
                Historic.gox_to_couchdb(start_time, end_time, 60 * 1e6)
            else:
                #don't want to update from GOX, just grab more data from couchDB
                print "Grabbing more data from couchDB only have %d points need %d" % (len(temp_time_window), window_size_minutes)
                start_time -= (4 * window_size_minutes * 60000000)

            temp_time_window = times_in_db[start_time:end_time]
            print "now we have %d points" % len(temp_time_window)

        recent_times = [trade_val.key for trade_val in temp_time_window]
        recent_prices = [trade_val.value for trade_val in temp_time_window]
        #self.recent_price_info = pd.Series(recent_prices, [pd.Timestamp(usecond_time *1000) for usecond_time in recent_times ], name="bitcoinprice")
        self.recent_price_info = pd.Series(recent_prices, recent_times, name="bitcoinprice")

        #Convert keys from integers to strings so we can convert to json and save in couchDB
        json_price_info = {str(the_time): the_price for the_time, the_price in self.recent_price_info.to_dict().iteritems()}
        self.log_database[str(int(time.time() * 1e6))] = {'init_time': int(time.time() * 1e6), 'init_price_info': json_price_info}
        return self.recent_price_info

    def log_trade_order(self, result, order_type,  num_btc, price):
        if result:
            self.log_database[str(int(time.time() * 1e6))] = {'trade_added': {'type': order_type, 'num_btc': num_btc, 'usd_price': price}}
        else:
            self.log_database[str(int(time.time() * 1e6))] = {'trade_fail': {'type': order_type,'num_btc': num_btc, 'usd_price': price}}
        print "trading! trying to %s %.2f bitcoin" % (order_type, num_btc)

    #Ohh god it's crashing! Sell! Sell it alllll!
    #Shit we're going to miss out on this huge price jump, buy all the bit coins. The Chickun arises!
    def trade_trade_trade(self, trade_type):
        #grab account holdings from Gox
        account_info = self.api_interface.account_info()
        self.btc_balance = account_info['btc_balance']
        self.usd_balance = account_info['usd_balance']

        if trade_type == 'sell':
            currency_to_dump = self.btc_balance
        else:
            currency_to_dump = self.usd_balance

        #seconds_between_trades = int(self.api_interface.market_lag()) #wait full market lag before trading again
        #check our balance, if we have bitcoin, sell it off, throttle trade attempts using seconds_between_trades
        if currency_to_dump > 0 and (int(time.time() * 1e6) - self.last_trade_attempt) > (self.seconds_between_trades * 1e6):
            if trade_type == 'sell':
                success, trade_id = self.api_interface.trade_order(trade_type, self.btc_balance)
            else:
                success, trade_id = self.api_interface.trade_order(trade_type, (self.usd_balance / self.last_market_info["price"]))

            self.last_trade_attempt = int(time.time() * 1e6)
            self.log_trade_order(success, trade_type, self.btc_balance, "market")

            #update account holdings from Gox
            account_info = self.api_interface.account_info()
            self.btc_balance = account_info['btc_balance']
            self.usd_balance = account_info['usd_balance']

        #TODO: check status of trade orders, try again if they haven't gone through, throttle according to trading lag
        #TODO: log our sell to DB


    #call this function with updates to market info, this is where all the decisions are made
    def market_info_analyzer(self, market_info, averaging_function, averaging_window, **kwargs):
        #Add market_info into our series
        self.recent_price_info.append(pd.Series({market_info['time']: market_info['price']}))
        self.last_market_info = market_info
        #Delete oldest data point in series to keep it small
        self.recent_price_info = self.recent_price_info[1:]
        #Compute averaging function on series
        if averaging_function is "simple_moving":
            averaged_prices = pd.rolling_mean(self.recent_price_info, averaging_window)
        elif averaging_function is "exponential_moving":
            averaged_prices = pd.ewma(self.recent_price_info, span=averaging_window)

        if kwargs.get("recursive") is True:
            recursions_done = 0
            while recursions_done < kwargs.get("num_recursions"):
                if averaging_function is "simple_moving":
                    averaged_prices = pd.rolling_mean(averaged_prices, averaging_window)
                elif averaging_function is "exponential_moving":
                    averaged_prices = pd.ewma(averaged_prices, span=averaging_window)
                recursions_done += 1

        #Compute slope at last 2 points
        slope = averaged_prices[-2:].diff()[-1:].median()

        #Use slope, possibly market Depth info, and decide to sell or buy
        if slope > 0:
            self.trade_trade_trade('buy')
        elif slope < 0:
            self.trade_trade_trade('sell')
        #update historic db with price info?

#Following code will only be executed if this module is run independently, not when imported. Use it to test the module.
if __name__ == "__main__":
    import MtGoxHistoric

    couch = couchdb.Server(Secret.couch_url)
    db_name = Secret.bitcoin_historic_data_db_name
    database = couch[db_name]
    start_time = 1360749874000000
    end_time = 1363551570000000
    initial_usd_balance = 100
    Gox = MtGoxHistoric.HistoricGoxRequester(database, start_time, end_time, initial_usd_balance, 0)

    Trader = TradeController(Gox, couch, "testing-historic")
    window_size =  60 * 8
    init_series = Trader.initialize_price_info(start_time, window_size, False)

    print "Initial account balances %d BTC and $%d USD" % (Trader.btc_balance, Trader.usd_balance)
    market_info = Gox.market_info()
    while market_info is not False:
        Trader.market_info_analyzer(market_info, "simple_moving", window_size, recursive=False, num_recursions=0)
        market_info = Gox.market_info()
    print "Test Complete!"
    print "Final account balances %.2f BTC and $%.2f USD" % (Trader.btc_balance, Trader.usd_balance)
    final_usd_balance = (Trader.btc_balance * Trader.last_market_info["price"])
    print "Final BTC Holdings worth $%.2f USD" % final_usd_balance
    print "Profit: $%.2f" % (final_usd_balance - initial_usd_balance)
    """
    Gox = MtGox.GoxRequester(Secret.gox_api_key, Secret.gox_auth_secret)
    init_series.plot(style='k--')
    moving_average = pd.rolling_mean(init_series, window_size)
    moving_average2 = pd.rolling_mean(moving_average, window_size * 2)
    moving_average2.plot(style='b')
    (moving_average2.diff() * 1e3).plot(style='g-')
    print moving_average2[-2:].diff()[-1:].median()
    #pd.ewma(moving_average2, span=window_size*4).plot(style='g-')
    show()
    """


