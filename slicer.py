#!/usr/bin/python
# -*- coding: utf-8 -*-

# Apple Slicer
#
# This script parses iTunes Connect financial reports and splits sales
# by Apple subsidiaries which are legally accountable for them.
# It may be used to help generating Reverse Charge invoices for accounting and
# in order to correctly issue Recapitulative Statements mandatory in the EU.
#
# Copyright (c) 2015 fedoco <fedoco@users.noreply.github.com>
#
# Permission is hereby granted, free of charge, to any person obtaining a copy
# of this software and associated documentation files (the "Software"), to deal
# in the Software without restriction, including without limitation the rights
# to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
# copies of the Software, and to permit persons to whom the Software is
# furnished to do so, subject to the following conditions:
#
# The above copyright notice and this permission notice shall be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
# AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
# LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
# OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN
# THE SOFTWARE.

import sys, os, csv, locale
import apple
from decimal import Decimal
from datetime import datetime

# CONFIGURATION

# ISO code of local currency into which foreign sales amounts should be converted
local_currency = 'EUR'

# desired locale used for formatting dates and prices
locale.setlocale(locale.LC_ALL, 'de_DE')

# name of file in which currency exchange rates are listed - these can be copy-pasted from iTunes Connect's
# "Payments & Financial Reports > Payments" page and need to match the financial reports' date range
currency_data_filename = 'currency_data.txt'

# -------------------------------------------------------------------------------------------------------------------------------------

def format_date(date_str):
    """Formats an US-style date string according to the default format of the current locale."""
    return datetime.strptime(date_str,"%m/%d/%Y").strftime('%x')

def format_currency(number):
    """Format a number according to the currency format of the current locale but without the currency symbol.""" 
    return locale.currency(number, False, True)

def parse_currency_data(filename):
    """Parse exchange rate and withholding tax rate (relevant f. ex. for JPY revenue) for each currency listed in the given file."""

    d = {}

    try:
        f = open(filename, 'r')
    except IOError:
      print 'Exchange rates data file missing: "%s"' % filename + '\n'
      print 'You can create this file by copy-pasting the listing under',
      print '"Earned / Paid on" of iTunes Connect\'s "Payments & Financial Reports > Payments" page'
      sys.exit(1)

    for line in csv.reader(f, delimiter = '\t'):
        if not len(line) > 10:
            continue 
        currency = line[0]
        exchange_rate = line[8]
        withholding_tax_factor = 1.0 - abs(float(line[4].replace(',', '')) / float(line[3].replace(',', '')))

        d[currency] = exchange_rate, withholding_tax_factor

    f.close()

    return d

def parse_financial_reports(workingdir):
    """Parse the sales listed in all iTunes Connect financial reports in the given directory and group them by country and product."""

    countries = {}
    currencies = {}
    date_range = None

    for filename in os.listdir(workingdir):
        # skip files that are not financial reports
        if not filename.endswith('txt') or filename == currency_data_filename:
            continue

        f = open(workingdir + '/' + filename, 'r')
        for line in csv.reader(f, delimiter = '\t'):
            # skip lines that don't start with a date
            if not '/' in line[0]:
                continue

            # consider first occurrence the authoritative date range and assume it is the same for all reports
            if not date_range:
                date_range = format_date(line[0]) + ' - ' + format_date(line[1])

            # all fields of interest of the current line
            quantity = int(line[5])
            amount = Decimal(line[7])
            currency = line[8]
            product = line[12]
            countrycode = line[17]

            # add current line's product quantity and amount to dictionary
            products = countries.get(countrycode, dict())
            quantity_and_amount = products.get(product, (0, Decimal(0)))
            products[product] = tuple(map(lambda x, y: x + y, quantity_and_amount, (quantity, amount)))
            countries[countrycode] = products

            # remember currency of current line's country
            currencies[countrycode] = currency

            # special case affecting countries Apple put in the "Rest of World" group: currency for those is listed as "USD"
            # in the sales reports but the corresponding exchange rate is labelled "USD - RoW" - a pragmatic way of identifying
            # those "RoW" countries is to inspect the filename of the sales report
            if "_WW." in filename:
              currencies[countrycode] = "USD - RoW"

        f.close()

    return countries, currencies, date_range 

def print_sales_by_corporation(sales, currencies):
    """Print sales grouped by Apple subsidiaries, by countries in which the sales have been made and by products sold."""

    corporations = {}

    for country in sales:
        corporations.setdefault(apple.corporation(country), {})[country] = sales[country]

    for corporation in corporations:
        corporation_sum = Decimal(0)
        print '\n\n' + apple.address(corporation)

        for countrycode in corporations[corporation]:
            country_currency = currencies[countrycode]
            products_sold = corporations[corporation][countrycode]

            print '\nSales in {0} ({1})'.format(apple.countryname(countrycode), countrycode)
            print '\tQuantity\tProduct\tAmount\tExchange Rate\tAmount in ' + local_currency

            for product in products_sold:
                exchange_rate = Decimal('1.00000')
                quantity, amount = products_sold[product]
                amount_in_local_currency = amount

                if not country_currency == local_currency:
                    exchange_rate, withholding_tax_factor = currency_data[country_currency]
                    amount_in_local_currency = amount * Decimal(exchange_rate) * Decimal(withholding_tax_factor)

                print '\t{0}\t{1}\t{2} {3}\t{4}\t{5} {6}'.format(quantity, product, country_currency, format_currency(amount),
                exchange_rate, format_currency(amount_in_local_currency), local_currency.replace('EUR', '€'))

                corporation_sum += amount_in_local_currency

        print '\n{0} Total:\t{1} {2}'.format(corporation, format_currency(corporation_sum), local_currency.replace('EUR', '€'))

# -------------------------------------------------------------------------------------------------------------------------------------

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print 'Apple Slicer\n'
        print 'Usage: ' + sys.argv[0] + ' <directory>\n'
        print 'Directory must contain iTunes Connect financial reports (*.txt) and a file named "' + currency_data_filename + '"'
        print 'which contains matching currency data copy-pasted from iTunes Connect\'s "Payments & Financial Reports > Payments" page'
        sys.exit(1)

    workingdir = sys.argv[1]

    currency_data = parse_currency_data(workingdir + '/' + currency_data_filename)

    sales, currencies, date_range = parse_financial_reports(workingdir)

    print 'Sales date: ' + date_range,

    print_sales_by_corporation(sales, currencies)

    sys.exit(0)
