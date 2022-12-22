#!/usr/bin/env python3

import csv

def SchwabCSVImport(logger, csv_file):
    data = []

    with open(csv_file) as csv_fd:
        reader = csv.reader(csv_fd)

        next(reader)
        header = next(reader)
        assert header == ['Date', 'Action', 'Symbol', 'Description', 'Quantity', 'Fees & Commissions', 'Disbursement Election', 'Amount']
        field = lambda x: header.index(x)
        data = []
        try:
            while True:
                row = next(reader)
                if len(row) == 1:
                    continue
                subheader = None

                while row[field('Date')] == '':
                    if not subheader:
                        subheader = row
                        row = next(reader)
                    if 'subdata' not in data[-1]:
                        data[-1]['subdata'] = []
                    data[-1]['subdata'].append({subheader[v].upper(): k for v, k in enumerate(row) if v != 0})
                    row = next(reader)
                data.append({header[v].upper(): k for v, k in enumerate(row)})
        except StopIteration:
            pass

        logger.debug("CSV data successfully read:")
        for d in data:
            logger.debug(d)

        return data

if __name__ == '__main__':
    import logging
    xxx = csvImport(logging, 'data/schwab-2021.csv')
    print('XXX', str(xxx))
