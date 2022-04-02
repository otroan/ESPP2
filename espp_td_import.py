#!/usr/bin/env python3

import json
import argparse
from td.client import TDClient


def auth():
    # Create a new session, credentials path is required.
    TDSession = TDClient(
        client_id='STGADCM1N10JMOG9A5KMAAQQJYVUC6JT',
        redirect_uri='https://127.0.0.1',
        credentials_path='data/td_ameritrade_creds.json'
    )

    # Login to the session
    TDSession.login()
    return TDSession


##account_number = '789650920'

def get_transactions(account, token, startdate, enddate):
    http = urllib3.PoolManager(
        cert_reqs='CERT_REQUIRED',
        ca_certs=certifi.where())
    url = 'https://api.tdameritrade.com/v1/accounts/' + account + \
        '/transactions?startDate=' + startdate + '&endDate=' + enddate
    print(f'Fetching from {url}')
    r = http.request('GET', url, headers={'Authorization': token})
    print(r.status)
    if r.status != 200:
        raise Exception('Reading transactions failed')
    return r.data.decode('utf-8')

#
# Dump transactions for all years
#

def get_arguments():
    parser = argparse.ArgumentParser(description='Tax Calculator.')
    parser.add_argument('year', type=str,
                        help='Which year(s) to calculate tax for')
    parser.add_argument('-t', '--account', help='Per trader transaction file-prefix')
    return parser.parse_args()


def main():
    # Get arguments
    args = get_arguments()
    account_number = args.account
    years = args.year.split('-')
    start = int(years[0])
    if len(years ) == 1:
        end = start
    else:
        end = int(years[1])

    td = auth()

    for year in range(start, end+1):
        startdate = str(year)+'-01-01'
        enddate = str(year) + '-12-31'
        data = td.get_transactions(account=account_number, transaction_type = 'ALL', start_date=startdate, end_date=enddate)
        filename = 'data/tdameritrade-'+str(year)+'.json'
        print(f'Writing to {filename}')
        with open(filename, 'w') as f:
            json.dump(data, f)
    
if __name__ == '__main__':
    main()

