from lemon import Lemon, Account

AUTH_KEY = "TOKEN <insert your token>"

if __name__ == "__main__":
    account = Lemon.select_account(AUTH_KEY, name='Demo')
    print('Available funds: {0}'.format(account.get_funds()))

    # the servers are down right now
    stock = Lemon.search_for_tradeable('Tesla')