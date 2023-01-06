# ESPP 2

## Introduction

## Architecture

Plugin based.
Given the previous years holding file and this years transactions file will generate a tax report.

### Importers

- TD Ameritrade API (JSON) download. Downloads annual transactions and store them in JSON files in the data directory.

### Normalizers

These modules read transaction files and normalize them into pandas dataframes for processing.

- TD Ameritrade API (JSON). A module that downloads annual transaction files directly using the TD Ameritrade API
- TD Ameritrade CSV. Processing of manually downloaded CSV transaction files

- TODO: Schwab CSV

-> Importer

### FMV

Downloads stock prices and exchange rates and caches them in per symbol data files in the data directory.

### Reporting


### Holdings file

One file per year of the holdings per 31/12.
Contains a record for each stock held, with price, accumulated tax deduction etc.