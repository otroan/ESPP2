# ESPP 2

[![pytest](https://github.com/otroan/ESPP2/actions/workflows/main.yml/badge.svg)](https://github.com/otroan/ESPP2/actions/workflows/main.yml)

## Overview

The ESPP2 tool serves both as a backend for a web frontend and a command line tool. The tool is built to help calculate Norwegian taxes on ESPP (Employee Stock Purchase Plan) and RSU (Restricted Stock Unit) shares. It also supports other shares held from Schwab.

To calculate taxes, the tool needs to know the whole history of each stock position in your posession or sold during the year. The purchase price and date when it was acquired, as well as any dividends and tax-free deductions accumulated.

The espp2 tool takes a transaction history for the current year, a holdings file listing all held positions at the end of the previous year, and a list of "wires" received, all in JSON format. Then it calculates the gains/losses and outputs that in a tax-report file and a holdings file for the current year.

**Note**: Norwegian tax law requires selling FIFO and this tools assumes this, while some brokers allow the user to sell an arbitrary lot. When selling, you must make sure to sell the oldest stocks first.

The tool runs in multiple phases to collect all the required data. The various use cases are described below. Most support is for Schwab users, Morgan Stanley is experimental. A few advanced but less tested methods are further down in this document.

## Installation

Requires Python3.11 or 3.12

```bash
git clone https://github.com/otroan/ESPP2.git
cd ESPP2
python3 -m venv venv
source venv/bin/activate
pip install git+https://github.com/otroan/ESPP2.git#egg=espp2
```

## Development Setup

### Pre-commit Hooks

This project uses pre-commit hooks to ensure code quality. To set up the development environment:

1. Install the package with development dependencies:

```bash
git clone https://github.com/otroan/ESPP2.git
cd ESPP2
pip install -e ".[dev]"
# Or if using poetry:
poetry install --with dev
```

2. Install the pre-commit hooks:

```bash
pre-commit install
```

The pre-commit hooks will now run automatically on every commit, checking:

- Tests pass (pytest)

To manually run all pre-commit hooks:

```bash
pre-commit run --all-files
```

To run a specific hook:

```bash
pre-commit run pytest
```

## Schwab

### Download transaction history

The transaction history for Schwab can be downloaded from https://client.schwab.com:
* Choose _Equity Awards_
* Choose _Transaction History_
* Make sure the blue drop down box is set to _Equity Award Center_
* Date range _Previous 4 Years_
* Click _Search_
* Using the export link in the upper right corner of the page, export as JSON
* Copy that file into a folder, it is referred to as ```schwab-transactions.json``` later on

This transaction history only covers transactions from the last 4 years. If this file covers all your transactions, then you won't need more.

If your history of transactions reaches further back and you have last year's holdings file ```holdings-2023.json``` at hand, then you will need to add it as a parameter as shown below.

### Add information about wires

If you have made transfers to a Norwegian bank account, run the tool with the ```--outwires``` option to generate a template file for the wires.

```bash
espp2 <schwab-transactions.json> [--inholdings holdings-2023.json] --outwires wires-2024.json
```

Now edit ```wires-2024.json``` and fill in the actual amount you have received in your bank acount in NOK where you see 'NaN'. Save the changes. This is required to be able to calculate transfer gain/loss that must be reported.

### Main run

Now you can perform the main run with all the information to generate the tax report.

```bash
espp2 <schwab-transactions.json> [--inholdings holdings-2023.json] --wires wires-2024.json --outholdings holdings-2024.json --output calc-2024.zip
```

A new holdings file will be generated that you must ***store in a safe place*** for next year. It will also generate a zip file with a spreadsheet that has all the transactions and underlaying calculations neatly documented, mainly in case that the tax office asks you to provide documentation.

## Morgan Stanley

Note: Morgan support is still under construction. Proceed with caution!

Morgan Stanley provides a semi-complete transaction history for all years. The tool can be run with the Morgan Stanley transaction file as input.

```bash
espp2 <morgan-2024.html> --outholdings <morgan-holdings-2024.json> --output calc-2024.zip
```

```espp2 --help``` will show the available options. The --verbose option will show the tax calculations in more detail and it is important to verify that these are correct.

*In particular it is important to verify that the total stock positions match the statements from the stock broker. If these numbers do not match, the resulting tax calculation will be wrong.*


## Less tested options for special cases and advanced users

### Option 1: Schwab - Complete transaction history and no holdigns file

Schwab provides a complete transaction history back to 2009 in 4 year increments. The _holdinator_ tool can be used to generate a holdings file for any year.

```bash
holdinator <schwab-all-transaction-files> --outholdings holdings-2023.json
espp2 <schwab-all-transactions.json> --inholdings holdings-2023.json --output calc-2024.zip
```

## Release notes 2025

- Removed old plugins
  - Removed support for TD Ameritrade (acquired by Schwab)
  - Removed support for Schwab CSV1 and CSV2 formats
  - Removed ESPPv1 pickle
- Split holdings generation into separate CLI tool (holdinator)
- Committed known symbol cache files to repo so key to data broker is no longer needed
- Added validation checks for opening and closing cash balance
- Added more unit tests. Including for aksjonaermodellen
- Handle cash as a FIFO and only apply aggregation principle on sale amount
- Aggregation princpile applied when sale and wire happens within 14 days
- New table from CLI showing ESPP benefits
- morgan fixes. opening/closing values, dates for sales/purchase
- support holdings in zip format (last years run output)
- Added new Amount type that dynamically handles currency exchanges


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
