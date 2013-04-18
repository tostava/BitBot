__author__ = 'dsyko'

#import libraries we'll need
import time
import json
import Secret
import couchdb


class HistoricGoxRequester:

    def __init__(self, couch_database, start_time, end_time, usd_balance, btc_balance):
        self.start_time = start_time
        self.start_time = end_time
        self.current_time = start_time
        self.usd_balance = usd_balance
        self.btc_balance = btc_balance
        self.couch_interface = couch_database.view(Secret.bitcoin_historic_data_view_name)
        self.price_list = self.couch_interface[start_time:end_time]
        self.current_price = 0
        self.trade_queue = []

    def execute_trades(self):
        #TODO: Add lag, and slippage simulation ability
        #check self.trade_queue for trades. If the price is right, execute that trade!
        for order in self.trade_queue:
            if order['type'] == 'buy' and (order['usd_price'] is None or self.current_price <= order['usd_price']):
                self.btc_balance += order['num_btc']
                self.usd_balance -= self.current_price * order['num_btc']
                self.trade_queue.remove(order)
            elif order['type'] == 'sell' and (order['usd_price'] is None or self.current_price >= order['usd_price']):
                self.btc_balance -= order['num_btc']
                self.usd_balance += self.current_price * order['num_btc']
                self.trade_queue.remove(order)

    def market_info_emitter(self):
        for price in self.price_list:
            self.current_time = price.key
            self.current_price = price.value
            self.execute_trades()
            yield price.key, price.value
        yield False, False

    def account_info(self):
        return {'login_id': 'historic', 'trade_fee': 0.6, 'btc_balance': self.btc_balance, 'usd_balance': self.usd_balance, 'api_rights': ["get_info", "trade"]}

    def trade_order(self, order_type, num_bitcoins, usd_price = None):
        """

        :param order_type: "buy" or "sell"
        :param num_bitcoins: number of bitcoins
        :param usd_price:  USD price of bitcoins or omit param for market order
        :return: Bool[True if trade order success, otherwise False], String[unique id of trade if successful]
        """
        #Add our trade to the trade queue, the trade queue will be used in execute_trade() to make trades when appropriate
        order_id = int((time.time()) * 1e6)
        self.trade_queue.append({'type': order_type, 'num_btc': num_bitcoins, 'usd_price': usd_price, 'order_id': order_id})
        return True, order_id


    def orders_info(self):
        """


        :return: A list of objects with structure [{"order_id": "unique id of order", "type": "buy or sell",
                                        "num_btc": "number of btc in order", "usd_price": "price per coin"}, ...]
        """
        return self.trade_queue

    def cancel_order_id(self, order_id):
        """


        :param order_id: unique id of order to cancel
        :return: json object returned by MtGox
        """
        for order in self.trade_queue:
            if order['order_id'] == order_id:
                self.trade_queue.remove(order)
        return True


    def cancel_order_by_type(self, order_type):
        """

        :param order_type: 'all', 'buy' or 'sell' specifies which orders to cancel
        :return: json object returned by MtGox
        """
        for order in self.trade_queue:
            if order_type == 'all' or order_type == order['type']:
                self.cancel_order_id(order['order_id'])

        return True

    def market_lag(self):
        return 0

    def market_info(self):
        #grab info from our market info emitter which is using couchDB to get market data
        trade_time, trade_price = next(self.market_info_emitter())
        if trade_time is not False:
            return {"time": trade_time, "volume": 0, "price": trade_price, "lag": self.market_lag()}

        return False

    def historic_data(self, start_time=None):
        """

        :param start_time: unix time stamp to begin getting (up to 24 hours of data) from gox
        """
        pass

#Following code will only be executed if this module is run independently, not when imported. Use it to test the module.
if __name__ == "__main__":



    def pretty(text):
        return json.dumps(text, indent = 4, sort_keys = True)

    #Creating instance of our historic prices from MtGox api interface.
    couch = couchdb.Server(Secret.couch_url)
    database = couch[Secret.bitcoin_historic_data_db_name]
    start_time = 1365292800000000
    end_time = 1365336000000000

    Gox = HistoricGoxRequester(database, start_time, end_time, 100, 0)

    #Get information on our account
    print pretty(Gox.account_info())

    #Get current market info
    print pretty(Gox.market_info())

