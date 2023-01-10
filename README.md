# ESPP 2

## Introduction
The ESPP2 tool is a command line tool built to help calculate Norwegian taxes on ESPP (Employee Stock Purchase Plan) and RSU (Restricted Stock Unit) shares.

The tool is built as a pipeline of small utilities.


### Transaction History Normalizer
A transaction history normaliser that uses per-broker plugins to normalize a transaction history into a JSON format, following the expected ESPP2 transaction history data model.
Currently the Schwab CSV format is supported. In addition TD Ameritrade CSV is supported for regular stock transactions. A manual JSON format and a Morgan Stanley HTML table scraper is underway.

### Fair Market Value
The FMV module downloads and caches historical fair market values for shares and exchange rates.
It has a manually maintained list of Oracle P&L 6 month sliding window rates used for ESPP.

### Tax calculation
The main espp2 tool takes a normalized transaction history for the current year, a holdings file listing all held positions at the end of the previous year, and a list of "wires" received all in JSON format. Then it calculates the gains/losses and outputs that in a tax-report file and a holdings file for the current year.

### Holdings file generation
As the tax generation tool requires the previous years positions. That may have to be calculated as it's different from the previous version of this tool. There are 3 ways to generate the previous year holding file:

1. Exporting it from the pickle file from last years tax run (previous version)
2. Generated from the complete transaction history from all years
3. Manually created holdings file and as much transaction history as is available.

The tools for these are under construction.

## Installation

```
python3 -m venv venv
source venv/bin/activate
pip install git+https://github.com/otroan/ESPP2.git#egg=espp2
```

## How to run

```
espp2_transnorm --transaction-file <schwab-2022.csv> --format schwab --output-file <schwab-transactions-2022.json>

espp2 --year=2022 --transaction-file <schwab-transactions-2022.json> --inholdings-file=<schwab-holdings-2021.json> --output-file <schwab-tax-report-2022.json --log=debug --wire-file=<schwab-wires-2022.json>

```

## TODO
- [ ] ESPPv1 pickle holdings export
- [ ] Holdings export from complete transaction history
- [ ] Manual JSON transaction history importer
- [ ] TD Ameritrade CSV transaction history importer
- [ ] JSON schema and validation for transaction, holdings, and wire formats
- [ ] Windows, OSX packaging through Github actions
- [ ] Unit tests


