__author__ = 'dsyko'

import MtGox
import Secret
import couchdb
import math
import time
import numpy
from pylab import plot, ylim, xlim, show, xlabel, ylabel, grid



class TradeController:
    def __init__(self, api_interface, couch_interface):
        self.api_interface = api_interface
        self.couch_interface = couch_interface
        #TODO: Poll exchange to get current holdings keep track in local var
        #TODO: Poll exchange to get recent price information, enough for window
        #TODO: Log start time to DB, keep a last_active variable up to date

    def movingaverage(self, array, window_size):
        #TODO add different weightings
        weightings = numpy.repeat(1.0, window_size) / window_size
        return numpy.convolve(array, weightings, 'same')

    #TODO: create a method to be called with newest price information
    # This method will compute moving average or whatever is desired and then trade BTC according to info


#Gox = MtGox.GoxRequester(Secret.gox_api_key, Secret.gox_auth_secret)
couch = couchdb.Server(Secret.couch_url)
database = couch['bitcoin-historic-data']

times = []
price = []
view_name = "Prices/time"
start_time = 1364244060000000
end_time = 1364256000000000
times_in_db = database.view(view_name)
for single_time in times_in_db[start_time:end_time]:
    times.append(single_time.key)
    price.append(single_time.value)


plot(times, price)
#y_av = movingaverage(y, 10)
#plot(x, y_av,"r")
#xlim(0,20)
xlabel("Time, microseconds since 1970.")
ylabel("Price of Bitcoin")
grid(True)
show()