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
owner_regex = r'Identifiant client\s+(?P<owner>\D*)'

# - will match dates
emission_date_regex = r'\b(?P<date>[\d/]{10})\b'

# - will match debits
# 18/10 CB CENTRE LECLERC  FACT 161014      13,40
debit_regex = r'^(?P<op_dte>\d\d\/\d\d)(?P<op_dsc>.*?)\s+(?P<op_amt>\d{1,3}\s{1}\d{1,3}\,\d{2}|\d{1,3}\,\d{2})$'

# - will match credits
# 150,0008/11 VIREMENT PAR INTERNET
credit_regex = r'^(?P<op_amt>\d{1,3}\s{1}\d{1,3}\,\d{2}|\d{1,3}\,\d{2})(?P<op_dte>\d\d\/\d\d)(?P<op_dsc>.*)$'

# - will match previous account balances (including date and balance)
#   SOLDE PRECEDENT AU 15/10/14 56,05
#   SOLDE PRECEDENT AU 15/10/14 1 575,00
#   SOLDE PRECEDENT   0,00
previous_balance_regex = r'SOLDE PRECEDENT AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+(?P<bal_amt>[\d, ]+?)$'

# - will match new account balances
#   NOUVEAU SOLDE CREDITEUR AU 15/11/14 (en francs : 1 026,44) 156,48
new_balance_regex = r'NOUVEAU SOLDE CREDITEUR AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+\(en francs : (?P<bal_amt_fr>[\d, ]+)\)\s+(?P<bal_amt>[\d, ]+?)$'


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

    # cleanup account number for each returned account
    # we use a syntax called 'list comprehension'
    cleaned_accounts = [(full, re.sub(r'\D', '', account_number))
                        for (full, account_number) in accounts]
    return cleaned_accounts


def search_emission_date(statement):
    emission_date = re.search(emission_date_regex, statement)
    # extract and strip
    emission_date = emission_date.group('date').strip()
    # parse date
    emission_date = datetime.strptime(
        emission_date, '%d/%m/%Y')
    print(' * Emission date is ' + emission_date.strftime('%d/%m/%Y'))
    return emission_date


def search_previous_balance(account):
    previous_balance_amount = D(0.0)
    previous_balance_date = None
    # in the case of a new account (with no history) or a first statement...
    # ...this regex won't match
    previous_balance = re.search(previous_balance_regex, account, flags=re.M)

    # if the regex matched
    if previous_balance:
        previous_balance_date = previous_balance.group('bal_dte').strip()
        previous_balance_amount = previous_balance.group('bal_amt').strip()
        previous_balance_amount = string_to_decimal(previous_balance_amount)

    if not (previous_balance_amount and previous_balance_date):
        print('⚠️  couldn\'t find a previous balance for this account')
    return (previous_balance_amount, previous_balance_date)


def search_new_balance(account):
    new_balance_amount = D(0.0)
    new_balance_date = None
    new_balance = re.search(new_balance_regex, account, flags=re.M)

    # if the regex matched
    if new_balance:
        new_balance_date = new_balance.group('bal_dte').strip()
        new_balance_amount = new_balance.group('bal_amt').strip()
        new_balance_amount = string_to_decimal(new_balance_amount)

    if not (new_balance_amount and new_balance_date):
        print('⚠️  couldn\'t find a new balance for this account')
    return (new_balance_amount, new_balance_date)


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
        return ';' + str(amount)
    # if credit, put amount BEFORE the last ';' so it belongs in the right column
    return str(amount) + ';'


def set_entry(emission, statement_emission, account_number, index, statement,
              amount, debit):
    res = set_year(emission, statement_emission) + ';'
    res += account_number + ';'
    res += index + ';'
    res += statement.strip() + ';'
    res += set_amount(amount, debit)
    res += '\n'
    return res


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

    errors = 0

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

        # 5 loop over each account
        for (full, account_number) in reversed(accounts):
            print('   * ' + account_number)

            (statement, _, account) = statement.partition(full)

            # search for last/new balances
            (previous_balance, previous_balance_date) = search_previous_balance(account)
            (new_balance, new_balance_date) = search_new_balance(account)
            # create total for inconsistency check
            total = D(0.0)

            # search all debit operations
            debit_ops = re.finditer(debit_regex, account, flags=re.M)
            for debit_op in debit_ops:
                # extract regex groups
                op_date = debit_op.group('op_dte').strip()
                op_description = debit_op.group('op_dsc').strip()
                op_amount = debit_op.group('op_amt').strip()
                # convert amount to regular Decimal
                op_amount = string_to_decimal(op_amount)
                # update total
                total -= op_amount
                print('removing {0}'.format(op_amount))
                csv += set_entry(op_date, emission_date,
                                 account_number, 'OTHER', op_description, op_amount, True)

            # search all credit operations
            credit_ops = re.finditer(credit_regex, account, flags=re.M)
            for credit_op in credit_ops:
                # extract regex groups
                op_date = credit_op.group('op_dte').strip()
                op_description = credit_op.group('op_dsc').strip()
                op_amount = credit_op.group('op_amt').strip()
                # convert amount to regular Decimal
                op_amount = string_to_decimal(op_amount)
                # update total
                total += op_amount
                print('adding {0}'.format(op_amount))
                csv += set_entry(op_date, emission_date,
                                 account_number, 'OTHER', op_description, op_amount, False)

            # check that all operations were added
            if not ((previous_balance + total) == new_balance):
                print(
                    '⚠️  inconsistency detected between imported operations and new balance')
                errors += 1
                print('previous_balance is {0}'.format(previous_balance))
                print('predicted new_balance is {0}'.format(
                    previous_balance + total))
                print('new_balance should be {0}'.format(new_balance))
                print(account)

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
    print('There were {0} errors'.format(errors))


if __name__ == "__main__":
    main()

# TODO:
# ligne avec * --> frais
#
# alerte en cas de prélèvement habituel mais d'un montant inhabituel (17,89 --> 27,89)
