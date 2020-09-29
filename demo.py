from lemon import Lemon, Account

AUTH_KEY = "TOKEN <insert your token>"

if __name__ == "__main__":
    account = Lemon.select_account(AUTH_KEY, name='Demo')
    print('Available funds: {0}'.format(account.get_funds()))
    print('Next market availability: {0}'.format(Lemon.next_market_availability().strftime('%I:%M %p')))
    
    tesla = Lemon.search_for_tradeable('Tesla')
    print('Tesla\'s isin: {0}. Tesla\'s symbol: {1}.'.format(tesla.isin, tesla.symbol))

    buy = input('Would you like to proceed into buying stocks?')
    if not buy.lower().startswith('y'): exit(0)

    # buy a tesla stock
    account.create_buy_order(tesla)

    # sell all our stocks
    for held_stock in account:
        held_stock.sell(quantity=held_stock.get_amount())