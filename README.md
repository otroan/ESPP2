# ESPP 2

[![pytest](https://github.com/otroan/ESPP2/actions/workflows/main.yml/badge.svg)](https://github.com/otroan/ESPP2/actions/workflows/main.yml)

## Overview
The ESPP2 tool serves both as a backend for a web frontend and a command line tool. The tool is built to help calculate Norwegian taxes on ESPP (Employee Stock Purchase Plan) and RSU (Restricted Stock Unit) shares. It also supports other shares held from TD Ameritrade.

To calculate taxes, the tool needs to know the whole history of each stock position in your posession or sold during the year. The purchase price and date when it was acquired, as well as any dividends and tax-free deductions accumulated.

The espp2 tool takes a transaction history for the current year, a holdings file listing all held positions at the end of the previous year, and a list of "wires" received, all in JSON format. Then it calculates the gains/losses and outputs that in a tax-report file and a holdings file for the current year.

**Note**: Norwegian tax law requires selling FIFO and this tools assumes this, while some brokers allow the user to sell an arbitrary lot. When selling, you must make sure to sell the oldest stocks first. 

The tool runs in multiple phases to collect all the required data. The various use cases are described below. Most support is for Schwab users, Morgan Stanley is experimental. A few advanced but less tested methods are further down in this document.

## Installation

Requires Python3.11 or 3.12

```
git clone https://github.com/otroan/ESPP2.git
cd ESPP2
python3 -m venv venv
source venv/bin/activate
pip install git+https://github.com/otroan/ESPP2.git#egg=espp2
```

## Schwab

### Download transaction history

The transaction history for Schwab can be downloaded from https://eac.schwab.com:
* Go to _History_
* From the blue drop down box choose _Equity Award Center_ 
* Date range _Previous 4 Years_
* Click _Search_
* Using the export link in the upper right corner of the page, export as JSON
* Copy that file into the ESPP2 folder, it is referred to as ```schwab-transactions.json``` later on

This transaction history only covers transactions from the last 4 years. If this file covers all your transactions, then you won't need more.

If your history of transactions reaches further back and you have last year's holdings file ```holdings-2022.json``` at hand, then you will need to add it as a parameter as shown below.

### Add information about wires

If you have made transfers to a Norwegian bank account, run the tool with the ```--outwires``` option to generate a template file for the wires.

```
espp2 <schwab-transactions.json> [--inholdings holdings-2022.json] --outwires wires-2023.json
```

Now edit ```wires-2023.json``` and fill in the actual amount you have received in your bank acount in NOK where you see 'NaN'. Save the changes. This is required to be able to calculate transfer gain/loss that must be reported.

### Main run

Now you can perform the main run with all the information to generate the tax report.

```
espp2 <schwab-transactions.json> [--inholdings holdings-2022.json] --wires wires-2023.json --outholdings holdings-2023.json --output calc-2023.zip
```

A new holdings file will be generated that you should ***store in a safe place*** for next year. It will also generate a zip file with a spreadsheet that has all the transactions and underlaying calculations neatly documented, mainly in case that the tax office asks you to provide documentation.

## Morgan Stanley

Note: Morgan support is still under construction. Proceed with caution!

Morgan Stanley provides a complete transaction history for all years. The tool can be run with the Morgan Stanley transaction file as input.

```
espp2 <morgan-2023.html> --outholdings <morgan-holdings-2023.json> --output calc-2023.zip
```

``` espp2 --help``` will show the available options. The --verbose option will show the tax calculations in more detail and it is important to verify that these are correct.

*In particular it is important to verify that the total stock positions match the statements from the stock broker. If these numbers do not match, the resulting tax calculation will be wrong.*



## Less tested options for special cases and advanced users

### Option 3: Schwab - Incomplete transaction history and not holding shares acquired prior to the transaction history in current tax year

If all the shares held prior to the transaction history (4 years), have been sold prior to the tax year, then the tool does not need to deal with those stocks.

Given an expected balance for the end of the previous tax year (2022-12-31 in this case), the tool walks the ledger backwards and inserts an artifical buy record at the beginning.

```
espp2 <schwab-all-transactions.json> --expected-balance '{"symbol": "CSCO", "qty": 936.5268 }' --outholdings holdings-2022.json
espp2 <schwab-all-transactions.json> --inholdings holdings-2022.json --output calc-2023.zip
```

### Option 4: Schwab - Incomplete transaction history and no JSON file

This applies to a user who has so far done their foreign shares taxes manually.
We can calculate the balance for the previous year by using the My_ESPP_Purchases.xls file and the My_Stock_Transactions.xls file from the Cisco stocks website. Combined with a manual record of the numbers of shares held at the end of the previous year.

**NOTE:** This will not work if one has reinvested dividends in shares.

To generate the holdings file:
```
espp2 My_ESPP_Purchases.xlsx My_Stock_Transactions.xlsx --outholdings holdings-2022.json --expected-balance "CSCO: 936.527"
```

To generate taxes:
```
espp2 <schwab-2023.json> --wires wires-2023.json --holdings holdings-2022.json> --output calc-2023.zip
```

### Option 5: Schwab - None of the above works
If none of the above works, then your best may be to run option 3 above, that generates a holdings file for 2022, and gives an artifical buy entry with purchase price 0 for the missing shares. You then need to go back and try to find the purchase prices for the stock buys that make up this lot. That information may be available in Schwab statements.

Another alternative is to try to manually create a Schwab CSV or JSON with all historical trades. Again from Schwab statements.


## Release notes 2023
- Upgraded to Python 3.11/3.12
- Upgraded to Pydantic v2
- Added support for Schwab JSON format
- Added support for Schwab CSV2 format
- New tax calculation module (portfolio) that generates an excel sheet for added tracability
- Relay error and warning messages to the web frontend
- Split positions with sales to correctly calculate tax-free deduction for part positions held at end of year
- Updated tax-free deduction rates and ESPP rates for 2023.
- Updated morgan importer for 2023
