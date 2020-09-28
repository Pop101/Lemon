from lemon import Lemon, Account

AUTH_KEY = "TOKEN <insert your token>"

if __name__ == "__main__":
    account = Lemon.select_account(AUTH_KEY, name='Demo')
    print('Available funds: {0}'.format(account.get_funds()))
    print('Next market availability: {0}'.format(Lemon.next_market_availability().strftime('%I:%M %p')))
    
    stock = Lemon.search_for_tradeable('Tesla')
    print(stock.isin)