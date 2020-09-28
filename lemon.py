import requests
from Levenshtein import distance
from datetime import timedelta, datetime, time
from pytz import timezone
from threading import Timer


def _get_closest_string(string, iterable, preprocess=lambda s: s):
    string = preprocess(string)
    distances = sorted({s : distance(string, preprocess(s))/max(len(preprocess(s)),0.01) for s in iterable}.items(), key=lambda i: i[1], reverse=True)
    if len(distances) > 0: return distances[0][0]
    return string

class Lemon:
    @staticmethod
    def select_account(auth, name=''):
        """
        Selects an account beloning to the holder of the authentication provided. \n
        If no name is provided, it selects the first accound. Otherwise, it searches available accounts for the closest match.
        """
        assert Lemon.validate_key(auth), 'Endpoint not reachable. Check your credentials and connection.'
        
        accounts = requests.get('https://api.lemon.markets/rest/v1/accounts/', headers={'Authorization': auth}).json()['results']
        
        if name:
            names = [a['name'] for a in accounts]
            index = names.index(_get_closest_string(name, names))
            return Account(accounts[index]['uuid'], auth)
        return Account(accounts[0]['uuid'], auth)
    
    @staticmethod
    def is_market_open(timestamp:datetime=datetime.now()): # von https://www.ls-tc.de/de/handelszeiten
        """
        Returns if the market is open. Does not take holidays into account.
        """
        timestamp = timestamp.astimezone(timezone('Europe/Berlin')) # The market is in the MEZ/MESZ timezone. So is Berlin.
        time_calc = lambda h, m: time(hour=h,minute=m,tzinfo=timezone('Europe/Berlin'))
        
        if timestamp.weekday() == 5:
            return time_calc(10,00) <= timestamp.time() <= time_calc(13,00)
        elif timestamp.weekday() == 6:
            return time_calc(17,00) <= timestamp.time() <= time_calc(19,00)
        else:
            return time_calc(7,30) <= timestamp.time() <= time_calc(23,00)

    @staticmethod
    def next_market_availability(timestamp:datetime=datetime.now()):
        """
        Returns the next market availability to the given `datetime` object,\n
        or the given `datetime` object if it is currently available.
        """
        if Lemon.is_market_open(timestamp): return timestamp
        return Lemon.next_market_opening(timestamp=timestamp)

    @staticmethod
    def next_market_opening(timestamp:datetime=datetime.now()):
        """
        Returns the next market opening time ahead of the given `datetime`, or `datetime.now()` by default.
        """
        given_timezone = timestamp.astimezone().tzinfo # save now so we can convert back
        timestamp = timestamp.astimezone(timezone('Europe/Berlin'))

        time_calc = lambda h, m: time(hour=h,minute=m,tzinfo=timezone('Europe/Berlin'))
        market_openings = [time_calc(7,30)] * 5 + [time_calc(10,00), time_calc(17,00)]

        if timestamp.time() <= market_openings[timestamp.weekday()]:
            next_opening = market_openings[timestamp.weekday()]
        else:
            next_opening = market_openings[(timestamp.weekday() + 1) % 7]
        return timestamp.replace(hour=next_opening.hour, minute=next_opening.minute).astimezone(given_timezone)
    
    @staticmethod
    def next_market_closing(timestamp=datetime.now()):
        """
        Returns the next market closing time ahead of the given `datetime`, or `datetime.now()` by default.
        """
        given_timezone = timestamp.astimezone().tzinfo # save now so we can convert back
        timestamp = timestamp.astimezone(timezone('Europe/Berlin'))

        time_calc = lambda h, m: time(hour=h,minute=m,tzinfo=timezone('Europe/Berlin'))
        market_closings = [time_calc(23,00)] * 5 + [time_calc(13,00), time_calc(19,00)]

        if timestamp.time() <= market_closings[timestamp.weekday]:
            next_closing = market_closings[timestamp.weekday]
        else:
            next_closing = market_closings[(timestamp.weekday + 1) % 7]
        return timestamp.replace(hour=next_closing.hour, minute=next_closing.minute).astimezone(given_timezone)

    @staticmethod
    def search_for_tradeable(query):
        """
        Searches for a `Tradeable` by query. \n
        Only searches by title, wkin, and isin, not symbol. \n
        Returns `None` if tradeable is not found
        """

        search = requests.get('https://api.lemon.markets/rest/v1/data/instruments/', params={'search': str(query)})
        search.raise_for_status(); search = search.json()
        if search['count'] >= 1: return Tradeable(search['results'][0]['isin'])
        return None

    @staticmethod
    def get_tradeable_cost(tradeable, timeout_limit=0.25):
        """
        Returns the last recorded price of a `Tradeable`
        """

        assert isinstance(tradeable, Tradeable), "Tradeable provided is not a Tradeable"
        if timeout_limit > 0: # TODO: add check if market is open 
            try:
                ticker = requests.get('https://api.lemon.markets/rest/v1/data/instruments/{0}/ticks/latest/'.format(tradeable.isin),timeout=timeout_limit)
                ticker.raise_for_status(); ticker = ticker.json()
                return ticker['price']
            except (requests.exceptions.ReadTimeout, TimeoutError):
                pass
        ticker = requests.get('https://api.lemon.markets/rest/v1/data/instruments/{0}/candle/m1/'.format(tradeable.isin), params={'ordering': '-date', 'limit': 1})
        ticker.raise_for_status(); ticker = ticker.json()
        return ticker['results'][0]['close']
    
    @staticmethod
    def validate_key(auth):
        """Checks if the authentication given is valid. Wastes an API call."""
        
        try:
            req = requests.get('https://api.lemon.markets/rest/v1/accounts/', headers={'Authorization': auth})
            req.raise_for_status(); req = req.json()
            return 'results' in str(req)
        except (TimeoutError, ValueError): return False
class Tradeable:
    def __init__(self, isin):
        self.isin = isin
    
    def get_cost(self):
        """
        Returns the last recorded cost for this `Tradeable`. \n
        An alias for `Lemon.get_tradeable_cost`.
        """
        return Lemon.get_tradeable_cost(self.isin)


class Account:
    def __init__(self, uuid, auth_key):
        self.uuid = uuid
        self.auth = auth_key
    
    def get_funds(self):
        """
        Gets the available, investible funds of this account.
        """
        assert Lemon.validate_key(self.auth), 'Authorization invalid. Check your credentials and connection.'
        
        req = requests.get('https://api.lemon.markets/rest/v1/accounts/{0}/state/'.format(self.uuid), headers={'Authorization': self.auth})
        req.raise_for_status(); req = req.json()
        return req['cash_to_invest']

    def get_held_tradeables(self):
        """
        Returns a list of all Tradeables currently held.
        """
        assert Lemon.validate_key(self.auth), 'Authorization invalid. Check your credentials and connection.'
        
        held = requests.get('https://api.lemon.markets/rest/v1/accounts/{0}/portfolio/aggregated'.format(self.uuid), headers={'Authorization': self.auth})
        held.raise_for_status(); held = held.json()
        return [HeldTradeable(x['instrument']['isin'], self) for x in held]
    
    def get_orders(self, ignore_executed:bool= True):
        """
        Returns a list of `Orders`. \n
        If `ignore_executed` is `True`, it returns a list of `Orders` that have not been executed yet
        """
        assert Lemon.validate_key(self.auth), 'Authorization invalid. Check your credentials and connection.'

        orders = list()
        page = 'https://api.lemon.markets/rest/v1/accounts/{0}/orders/'.format(self.uuid)
        while page:
            response = requests.get(page, headers={'Authorization': self.auth})
            response.raise_for_status(); response = response.json()
            page = response['next']
            
            filtered_orders = filter(lambda x: 'executed' not in str(x['status']).lower() or not ignore_executed, response['results'])
            orders.extend(list(map(lambda x: Order(x['uuid'], self), filtered_orders)))
        return orders
    
    def create_order(self, tradeable:Tradeable, quantity:int=1, buy:bool=False, slippage:float=0.01, limits:tuple=(False, False), length=timedelta(hours=16)):
        """
        Creates an order on the stock market. \n
        `tradeable`: the Tradeable to order \n
        `quantity`: the quantity to buy or sell. `1` by default. Must be an integer. \n
        `buy`: If it should create a buy or sell order. `False` by default. \n
        `slippage`: Automatically calculates the limit based on price change. 1% by default. Set to below 0 to disable.
        `limits`: A tuple representing the (`stop limit`, `limit`) of the order. `(None, None)` by default. Set either to `None` to disable it. Overrides `slippage`. \n
        `length`: A `timedelta` or `int` representing how long the order should remain valid. `16 hours` by default
        """
        
        request_args = {'instrument': tradeable, 'quantity': quantity}

        if isinstance(length, timedelta):
            request_args['valid_until'] = ((datetime.now() + length) - datetime(1970,1,1)).total_seconds()
        else:
             request_args['valid_until'] = ((datetime.now() + timedelta(seconds=length)) - datetime(1970,1,1)).total_seconds()
        
        # Set side and calculate limit based on slippage
        if buy:
            request_args['side'] = 'buy'
            slippage_price = (1+slippage) * Lemon.get_tradeable_cost(tradeable)
        else:
            request_args['side'] = 'sell'
            slippage_price = (1-slippage) * Lemon.get_tradeable_cost(tradeable)
            
        if slippage > 0: request_args['limit_price'] = slippage_price
        
        # override for manually-set limits
        if limits:
            limits = sorted(limits)
            if limits[0]:
                request_args['stop_limit'] = limits[0]
            if limits[1]:
                request_args['limit_price'] = limits[1]
        
        if buy: assert quantity * request_args['limit_price'] <= self.get_funds(), 'Price limit is greater than investable funds!'
        order = requests.post('https://api.lemon.markets/rest/v1/accounts/{0}/orders/'.format(self.uuid), data=request_args, headers={'Authorization': self.auth})
        order.raise_for_status(); order = order.json()
        return Order(order['uuid'], self)
    
    def create_buy_order(self, tradeable:Tradeable, quantity:int=1, slippage:float=0.01, limits:tuple=(False, False), length=timedelta(hours=16)):
        """
        Creates a buy order on the stock market. Alias for `Account.create_order` \n
        `tradeable`: the Tradeable to order \n
        `quantity`: the quantity to buy or sell. `1` by default. Must be an integer. \n
        `slippage`: Automatically calculates the limit based on price change. 1% by default. Set to below 0 to disable.
        `limits`: A tuple representing the (`stop limit`, `limit`) of the order. `(None, None)` by default. Set either to `None` to disable it. Overrides `slippage`. \n
        `length`: A `timedelta` or `int` representing how long the order should remain valid. `16 hours` by default
        """
        return self.create_order(tradeable, quantity=quantity, buy=True, slippage=slippage, limits=limits, length=length)
    
    def create_sell_order(self, tradeable:Tradeable, quantity:int=1, slippage:float=0.01, limits:tuple=(False, False), length=timedelta(hours=16)):
        """
        Creates a sell order on the stock market. Alias for `Account.create_order` \n
        `tradeable`: the Tradeable to order \n
        `quantity`: the quantity to buy or sell. `1` by default. Must be an integer. \n
        `slippage`: Automatically calculates the limit based on price change. 1% by default. Set to below 0 to disable.
        `limits`: A tuple representing the (`stop limit`, `limit`) of the order. `(None, None)` by default. Set either to `None` to disable it. Overrides `slippage`. \n
        `length`: A `timedelta` or `int` representing how long the order should remain valid. `16 hours` by default
        """
        return self.create_order(tradeable, quantity=quantity, buy=False, slippage=slippage, limits=limits, length=length)


class Order:
    def __init__(self, uuid, account):
        assert isinstance(account, Account), "Accout provided is not a valid accout"
        self.uuid = uuid
        self.account = account
    
    def delete(self):
        """
        Deletes this order. Returns `True` if successful, `False` otherwise.
        """
        assert Lemon.validate_key(self.account.auth), 'Authorization invalid. Check your credentials and connection.'
        deleted = requests.delete('https://api.lemon.markets/rest/v1/accounts/{0}/orders/{1}/'.format(self.account.uuid,self.uuid), headers={'Authorization': self.account.auth})
        deleted.raise_for_status()
        return deleted.status_code == 204
    
    def get_status(self):
        """
        Gets a `tuple` representing the status of the order. \n
        The first value is the status as a string, the second is the amount it executed with, or `-1` if still pending.
        """
        
        assert Lemon.validate_key(self.account.auth), 'Authorization invalid. Check your credentials and connection.'
        order = requests.get('https://api.lemon.markets/rest/v1/accounts/{0}/orders/{1}/'.format(self.account.uuid,self.uuid), headers={'Authorization': self.account.auth})
        order.raise_for_status(); order = order.json()

        if 'open' in order['status']: return (order['status'], -1)
        return order['status'], order['average_price']


class HeldTradeable(Tradeable):
    def __init__(self, isin, account):
        assert isinstance(account, Account), "Account provided is not a valid accout"
        self.isin = isin
        self.account = account
    
    def get_amount(self):
        """
        Returns how many of this `Tradeable` you hold.
        """
        held_tradeable = requests.get('https://api.lemon.markets/rest/v1/accounts/{0}/portfolio/{1}/aggregated/'.format(self.account.uuid, self.isin), headers={'Authorization': self.account.auth})
        held_tradeable.raise_for_status(); held_tradeable = held_tradeable.json()

        if len(held_tradeable) <= 0: return 0
        return held_tradeable['quantity']

    def get_cost(self):
        """
        Returns the average cost of acquiring this `Tradeable`, or `-1` if you do not hold any.
        """
        held_tradeable = requests.get('https://api.lemon.markets/rest/v1/accounts/{0}/portfolio/{1}/aggregated/'.format(self.account.uuid, self.isin), headers={'Authorization': self.account.auth})
        held_tradeable.raise_for_status(); held_tradeable = held_tradeable.json()
        
        if len(held_tradeable) <= 0: return -1
        return held_tradeable['average_price']