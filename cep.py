#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import sys
import os
import re
from decimal import Decimal as D
from pprint import pprint
from datetime import datetime
from pathlib import Path


# - will match owner
# we use named regex group (?P<owner>...) to ease the extraction
owner_regex = r'Identifiant client\s+(?P<owner>\D*)'

# - will match dates
#
emission_date_regex = r'\b(?P<date>[\d/]{10})\b'

# - will match debits
#                                           __
#                                             |
#
# 18/10 CB CENTRE LECLERC  FACT 161014      13,40
debit_regex = r'^(?P<op_dte>\d\d\/\d\d)(?P<op_dsc>.*)\s+(?P<op_amt>(\d+\,\d{2}))$'

# - will match credits
#    __
#   |
# 150,0008/11 VIREMENT PAR INTERNET
credit_regex = r'^(?P<op_amt>(\d+\,\d{2}))(?P<op_dte>\d\d\/\d\d)(?P<op_dsc>.*)$'

# - will match previous account balances (including date and balance)
#                              __
#                                    |
#                               __
#                                 |
#   SOLDE PRECEDENT AU 15/10/14 56,05
#   SOLDE PRECEDENT AU 15/10/14 1 575,00
#   SOLDE PRECEDENT   0,00
# we use named regex group (?P<exc_date>...) to ease the extraction
previous_balance_regex = r'SOLDE PRECEDENT AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+(?P<bal_amt>[\d, ]+?)$'

# - will match new account balances
#                                                               __
#                                                                 |
#   NOUVEAU SOLDE CREDITEUR AU 15/11/14 (en francs : 1 026,44) 156,48
new_balance_regex = r'NOUVEAU SOLDE CREDITEUR AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+\(en francs : (?P<bal_amt_fr>[\d, ]+)\)\s+(?P<bal_amt>[\d, ]+?)$'

# stats
no_section_count = 0
section_count = 0
total_count = 0

# sections
sections = [
    ('DEPOT', 'Opérations de dépôt', False),
    ('TRANSFERT', 'Virements reçus', False),
    ('CHECK', 'Paiements chèques', True),
    ('BANK', 'Frais bancaires et cotisations', True),
    ('DEBIT', 'Paiements carte bancaire', True),
    ('WITHDRAWAL', 'Retraits carte bancaire', True),
    ('DIRECTDEBIT', 'Prélèvements', True)
]


def parse_pdf_file(filename):
    # force filename as string
    filename = str(filename)
    if filename.endswith('pdf') == False:
        return (True, None)

    print('Parsing: ' + filename)

    # escape spaces in name
    filename = re.sub(r'\s', '\\ ', filename)

    # parse pdf
    command = 'pdf2txt.py -M 200 -o tmp.txt ' + filename
    os.system(command)

    # open resulting file
    parsed_file = open('tmp.txt', 'r')

    # save reference to interact with the file outside of this function
    global current_file
    current_file = parsed_file

    # read file content and return it
    file_content = parsed_file.read()
    return (False, file_content)


def clean_statement(statement):
    # remove lines with one character or less
    re.sub(r'(\n.| +)$', '', statement, flags=re.M)
    return statement


def search_account_owner(statement):
    # search for owner to identify multiple accounts
    account_owner = re.search(owner_regex, statement)
    # extract and strip
    account_owner = account_owner.group('owner').strip()
    print(' * Account owner is ' + account_owner)
    return account_owner


def search_accounts(statement):
    # get owner
    owner = search_account_owner(statement)

    account_regex = r'^((?:MR|MME|MLLE) ' + owner + ' - .* - ([^(\n]*))$'
    accounts = re.findall(account_regex, statement, flags=re.M)
    print(' * There are {0} accounts:'.format(len(accounts)))
    return accounts


def search_emission_date(statement):
    emission_date = re.search(emission_date_regex, statement)
    # extract and strip
    emission_date = emission_date.group('date').strip()
    # parse date
    emission_date = datetime.strptime(
        emission_date, '%d/%m/%Y')
    print(' * Emission date is ' + emission_date.strftime('%d/%m/%Y'))
    return emission_date


def search_previous_amount(account):
    previous_amount = 0.0
    previous_amount_date = None
    # in the case of a new account (with no history) or a first statement...
    # ...this regex won't match
    previous_amount = re.search(previous_amount_regex, account, flags=re.M)

    # if the regex matched
    if previous_amount:
        previous_amount_date = previous_amount.group('exc_date').strip()
        previous_amount = previous_amount.group('exc_amt').strip()
        print(previous_amount_date)
        print(previous_amount)

    if not (previous_amount and previous_amount_date):
        print('⚠️  couldn\'t find an history for this account')
    return (previous_amount, previous_amount_date)


def set_year(emission, statement):
    # fake a leap year
    emission = datetime.strptime(emission + '00', '%d/%m%y')
    if emission.month <= statement.month:
        emission = emission.replace(year=statement.year)
    else:
        emission = emission.replace(year=statement.year - 1)
    return datetime.strftime(emission, '%d/%m/%Y')


def set_amount(amount, debit):
    # if debit, put amount AFTER the last ';' so it belongs in the right column
    if debit:
        return ';' + amount
    # if credit, put amount BEFORE the last ';' so it belongs in the right column
    return amount + ';'


def set_entry(emission, statement_emission, account_number, index, statement,
              amount, debit):
    res = set_year(emission, statement_emission) + ';'
    res += account_number + ';'
    res += index + ';'
    res += statement.strip() + ';'
    res += set_amount(amount, debit)
    res += '\n'
    return res

# TODO:
# ligne avec * --> frais
# verifier solde de départ (montant et date) matche avec solde fin fichier précédent
# verifier coherence solde depart solde fin --> faire le calcul de toutes les operations (permet de voir si operations non parsees)

def string_to_decimal(str):
    # replace french separator by american one
    str = str.replace(',', '.')
    # remove useless spaces
    str = str.replace(' ', '')
    # convert to decimal
    nb = D(str)
    return nb

def main():
    csv = 'date;account;type;statement;credit;debit\n'

    # go through each file of directory
    p = Path(sys.argv[1])
    for filename in sorted(p.iterdir()):
        # 1. parse statement file
        (file_is_not_pdf, parsed_statement) = parse_pdf_file(filename)
        if file_is_not_pdf == True:
            # skip the current iteration
            continue

        # 2. clean statement content
        statement = clean_statement(parsed_statement)

        # 3. search for date of emission of the statement
        emission_date = search_emission_date(statement)

        # 4. search all accounts
        accounts = search_accounts(statement)

        for (full, account_number) in reversed(accounts):
            (statement, _, account) = statement.partition(full)
            account_number = re.sub(r'\D', '', account_number)
            print('   * ' + account_number)

            # search for last amount
            (previous_amount, previous_amount_date) = search_previous_amount(account)

            # create a working copy
            account_copy = account

            # isolate and parse each section
            no_section = True
            for (index, section, debit) in reversed(sections):
                (account, _, result) = account.partition(section)

                res = re.findall(debit_regex, result, flags=re.M)
                for (op_date, op_description, op_amount) in res:
                    no_section = False
                    csv += set_entry(op_date, emission_date,
                                     account_number, index, op_description, op_amount, debit)

            # nothing has been found above: test others things
            if no_section:
                # this should alaways match debit
                res = re.findall(debit_regex, account_copy, flags=re.M)
                for (op_date, op_description, op_amount) in res:
                    csv += set_entry(op_date, emission_date,
                                     account_number, 'OTHER', op_description, op_amount, True)

                # this should alaways match credit
                res = re.findall(credit_regex, account_copy, flags=re.M)
                for (op_amount, op_date, op_description) in res:
                    csv += set_entry(op_date, emission_date,
                                     account_number, 'OTHER', op_description, op_amount, False)

        current_file.close()
        print('✅ Parse ok')

    # move bank lines with REMISE as credit
    csv = re.sub(r'(.*BANK;\* REMISE.*;);([\d, ]+)', r'\1\2;', csv)

    # remove not useful information for debit
    csv = re.sub(r'(.*)CB (.*\w) +FACT \d{6}(.*)', r'\1\2\3', csv)

    # write result in file
    file_result = open('./compte.csv', 'w')
    file_result.write(csv)
    file_result.close()

    # rm tmp file
    os.remove('tmp.txt')


if __name__ == "__main__":
    main()

# alerte en cas de prélèvement habituel mais d'un montant inhabituel (17,89 --> 27,89)
