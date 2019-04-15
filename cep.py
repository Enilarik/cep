#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import sys
import os
import regex
import csv
from decimal import Decimal as D
from pprint import pprint
from datetime import datetime
from pathlib import Path


# - will match owner
# prior to march 2019
owner_regex_v1 = r'Identifiant client\s+(?P<owner>\D*)'
# after march 2019
owner_regex_v2 = r'^(?P<title>MR|MME|MLLE)\s+(?P<owner>\D*?)$'

# - will match dates
emission_date_regex = r'\b(?P<date>[\d/]{10})\b'

# - will match debits
# Ex 1.
# 18/10 CB CENTRE LECLERC  FACT 161014      13,40
# Ex 2.
# 27/05 PRLV FREE MOBILE      3,99
# -Réf. donneur d'ordre :
# fmpmt-XXXXXXXX
# -Réf. du mandat : FM-XXXXXXXX-X
# [\S\s].*?
debit_regex = (r'^'
    '(?P<op_dte>\d\d\/\d\d)'                                        # date: dd/dd
    '(?P<op_lbl>.*?)'                                               # label: any single character (.), between 0 and unlimited (*), lazy (?)
    '\s.*?'                                                         # any whitespace and non-whitespace character (i.e. any character) ([\S\s]), any character (.) between 0 and unlimited (+), lazy
    '(?P<op_amt>(?<=\s)\d{1,3}\s{1}\d{1,3}\,\d{2}|\d{1,3}\,\d{2}(?!([\S\s].*?((?<=(?=(^(?!(?1))\s.*(?1))))\s.*(?3)))))$'
                                                                    # amount: alternative between ddd ddd,dd and ddd,dd, until the end of line ($)
                                                                    # the positive lookebehind assures that there is at least one white space before any amount
                                                                    # the positive lookbehind handles the following case where amount to match is 4,45 and not 14,40:
                                                                    # 19/10 INTERETS TAEG 14,40
                                                                    # VALEUR AU 18/10     4,45
    '\s*'                                                           # any whitespace character (\s), between 0 and unlimited (*), greedy
    '(?P<op_lbl_extra>[\S\s]*?(?=^(?1)|^(?3)|\Z))'                  # extra label: 'single line mode' until the positive lookehead is satisfied
                                                                    # positive lookahead --> alternative between:
                                                                    #   -line starting with first named subpatern (date)
                                                                    #   -line starting with third named subpatern (amount)
                                                                    #   -EOL
                                                                    # we use [\s\S]*? to do like the single line mode
                                                                    # basically it's going to match any non-whitespace OR whitespace character. That is, any character, including linebreaks.
                                                                    # we could have used (?s) to activate the real line mode...
                                                                    # ...but Python doesn't support mode-modified groups (meaning that it will change the mode for the whole regex)
)

# - will match credits
# Ex 1.
# 150,0008/11 VIREMENT PAR INTERNET
# Ex 2.
# 11,8011/02VIR SEPA LA MUTUELLE DES ETUDIA
# XXXXX/XX/XX-XXXX/XXXXXXXXX
# -Réf. donneur d'ordre :
# XXXXX/XX/XX-XXXX/XXXXXXXXX
credit_regex = (r'^'
    '(?P<op_amt>\d{1,3}\s{1}\d{1,3}\,\d{2}|\d{1,3}\,\d{2})'     # amount: alternative between ddd ddd,dd and ddd,dd
    '(?P<op_dte>\d\d\/\d\d)'                                    # date: dd/dd
    '(?P<op_lbl>.*)$'
    '\s*'                                                       # any whitespace character (\s), between 0 and unlimited (*), greedy
    '(?P<op_lbl_extra>[\S\s]*?(?=^(?1)|^(?2)|\Z))'              # extra label: 'single line mode' until the positive lookehead is satisfied
                                                                # positive lookahead --> alternative between:
                                                                #   -line starting with first subpatern (amount)
                                                                #   -line starting with second subpatern (date)
                                                                #   -EOL
                                                                # we use [\s\S]*? to do like the single line mode
                                                                # basically it's going to match any non-whitespace OR whitespace character. That is, any character, including linebreaks.
                                                                # we could have used (?s) to activate the real line mode...
                                                                # ...but Python doesn't support mode-modified groups (meaning that it will change the mode for the whole regex)
)

# - will match previous account balances (including date and balance)
#   SOLDE PRECEDENT AU 15/10/14 56,05
#   SOLDE PRECEDENT AU 15/10/14 1 575,00
#   SOLDE PRECEDENT   0,00
previous_balance_regex = r'SOLDE PRECEDENT AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+(?P<bal_amt>[\d, ]+?)$'

# - will match new account balances
#   NOUVEAU SOLDE CREDITEUR AU 15/11/14 (en francs : 1 026,44) 156,48
new_balance_regex = r'NOUVEAU SOLDE CREDITEUR AU (?P<bal_dte>\d\d\/\d\d\/\d\d)\s+\(en francs : (?P<bal_amt_fr>[\d, ]+)\)\s+(?P<bal_amt>[\d, ]+?)$'

one_character_line_regex = r'^( +|.|\n)$'
longer_than_70_regex = r'^(.{70,})$'
smaller_than_2_regex = r'^.{,2}$'
empty_line_regex = r'^(\s*)$'
trailing_spaces_and_tabs_regex = r'[ \t]+$'
line_return_regex = r'(\n)$'


# counters for stats
other_op_count = 0
bank_op_count = 0
deposit_op_count = 0
wire_transfer_op_count = 0
check_op_count = 0
card_debit_op_count = 0
withdrawal_op_count = 0
direct_debit_op_count = 0


def parse_pdf_file(filename):
    # force filename as string
    filename = str(filename)
    if filename.upper().endswith('PDF') == False:
        return (True, None)

    print('Parsing: ' + filename)

    # escape spaces in name
    filename = regex.sub(r'\s', '\\ ', filename)

    # parse pdf
    command = 'pdf2txt.py -M 120 -W 1 -L 0.3 -F 0.5 -o tmp.txt ' + filename
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
    # flag lines with one character or less
    cleaned = regex.sub(one_character_line_regex, 'FLAG_DELETE_THIS_LINE', statement, flags=regex.M)
    # keep only non-flaged lines
    cleaned = '\n'.join([s for s in cleaned.splitlines() if 'FLAG_DELETE_THIS_LINE' not in s])
    return cleaned


def clean_account(account, account_number):
    # split the text by the 'new_balance_regex' line
    cleaned = regex.split(new_balance_regex, account, flags=regex.M)
    # keep the first part (i.e. everything that's before the 'new_balance_regex' line)
    cleaned = cleaned[0]
    # flag lines with specific words
    words_to_remove = [
        account_number,
        'Relevé',
        'vos comptes',
        'Page',
        'Débit Crédit',
        'Détail des opérations',
        'frais bancaires et cotisations',
        'SOLDE PRECEDENT AU',
    ]
    words_to_remove_regex = r'^.*\b(' + '|'.join(words_to_remove) + r')\b.*$'
    # flag lines longer than 70
    cleaned = regex.sub(longer_than_70_regex, 'FLAG_DELETE_THIS_LINE', cleaned, flags=regex.M)
    # flag lines with words to remove
    cleaned = regex.sub(words_to_remove_regex, 'FLAG_DELETE_THIS_LINE', cleaned, flags=regex.M)
    # remove trailing spaces
    cleaned = regex.sub(trailing_spaces_and_tabs_regex, '', cleaned, flags=regex.M)
    # flag empty lines
    cleaned = regex.sub(empty_line_regex, 'FLAG_DELETE_THIS_LINE', cleaned, flags=regex.M)
    # flag lines with less than 2 characters
    cleaned = regex.sub(smaller_than_2_regex, 'FLAG_DELETE_THIS_LINE', cleaned, flags=regex.M)
    # keep only non-flaged lines
    cleaned = '\n'.join([s for s in cleaned.splitlines() if 'FLAG_DELETE_THIS_LINE' not in s])
    return cleaned


def search_account_owner(regex_to_use, statement):
    # search for owner to identify multiple accounts
    account_owner = regex.search(regex_to_use, statement, flags=regex.M)
    if (not account_owner):
        raise ValueError('No account owner was found.')
    # extract and strip
    account_owner = account_owner.group('owner').strip()
    return account_owner


def search_accounts(statement):
    # get owner
    owner = search_account_owner(owner_regex_v1, statement)

    account_regex = r'^((?:MR|MME|MLLE) ' + owner + ' - .* - ([^(\n]*))$'
    accounts = regex.findall(account_regex, statement, flags=regex.M)

    # no accounts found, try to get owner with other regex
    if (len(accounts) == 0):
        owner = search_account_owner(owner_regex_v2, statement)
        account_regex = r'^((?:MR|MME|MLLE) ' + owner + ' - .* - ([^(\n]*))$'
        accounts = regex.findall(account_regex, statement, flags=regex.M)

    print(' * Account owner is ' + owner)
    print(' * There are {0} accounts: '.format(len(accounts)))
    # cleanup account number for each returned account
    # we use a syntax called 'list comprehension'
    cleaned_accounts = [(full, regex.sub(r'\D', '', account_number))
                        for (full, account_number) in accounts]
    return cleaned_accounts


def search_emission_date(statement):
    emission_date = regex.search(emission_date_regex, statement)
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
    previous_balance = regex.search(previous_balance_regex, account, flags=regex.M)

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
    new_balance = regex.search(new_balance_regex, account, flags=regex.M)

    # if the regex matched
    if new_balance:
        new_balance_date = new_balance.group('bal_dte').strip()
        new_balance_amount = new_balance.group('bal_amt').strip()
        new_balance_amount = string_to_decimal(new_balance_amount)

    if not (new_balance_amount and new_balance_date):
        print('⚠️  couldn\'t find a new balance for this account')
    return (new_balance_amount, new_balance_date)


#                              _   _
#    ___  _ __   ___ _ __ __ _| |_(_) ___  _ __
#   / _ \| '_ \ / _ \ '__/ _` | __| |/ _ \| '_ \
#  | (_) | |_) |  __/ | | (_| | |_| | (_) | | | |
#   \___/| .__/ \___|_|  \__,_|\__|_|\___/|_| |_|
#        |_|
#
def set_operation_year(emission, statement_emission_date):
    # fake a leap year
    emission = datetime.strptime(emission + '00', '%d/%m%y')
    if emission.month <= statement_emission_date.month:
        emission = emission.replace(year=statement_emission_date.year)
    else:
        emission = emission.replace(year=statement_emission_date.year - 1)
    return datetime.strftime(emission, '%d/%m/%Y')


def set_operation_amount(amount, debit):
    if debit:
        return ['', decimal_to_string(amount)]
    return [decimal_to_string(amount), '']


def search_operation_type(op_label):
    op_label = op_label.upper()
    # bank fees, international fees, subscription fee to bouquet, etc.
    if ((op_label.startswith('*')) or (op_label.startswith('INTERETS'))):
        type = 'BANK'
        global bank_op_count
        bank_op_count += 1
    # cash deposits on the account
    elif ((op_label.startswith('VERSEMENT'))):
        type = 'DEPOSIT'
        global deposit_op_count
        deposit_op_count += 1
    # incoming / outcoming wire transfers: salary, p2p, etc.
    elif ((op_label.startswith('VIREMENT')) or (op_label.startswith('VIR SEPA'))):
        type = 'WIRETRANSFER'
        global wire_transfer_op_count
        wire_transfer_op_count += 1
    # check deposits / payments
    elif ((op_label.startswith('CHEQUE')) or (op_label.startswith('REMISE CHEQUES')) or (op_label.startswith('REMISE CHQ'))):
        type = 'CHECK'
        global check_op_count
        check_op_count += 1
    # payments made via debit card
    elif ((op_label.startswith('CB'))):
        type = 'CARDDEBIT'
        global card_debit_op_count
        card_debit_op_count += 1
    # withdrawals
    elif ((op_label.startswith('RETRAIT DAB')) or (op_label.startswith('RET DAB'))):
        type = 'WITHDRAWAL'
        global withdrawal_op_count
        withdrawal_op_count += 1
    # direct debits
    elif ((op_label.startswith('PRLV'))):
        type = 'DIRECTDEBIT'
        global direct_debit_op_count
        direct_debit_op_count += 1
    else:
        type = 'OTHER'
        global other_op_count
        other_op_count += 1

    return type


def create_operation_entry(op_date, statement_emission_date, account_number, op_label,
                            op_label_extra, op_amount, debit):
    # search the operation type according to its label
    op_type = search_operation_type(op_label)

    op = [
        set_operation_year(op_date, statement_emission_date),
        account_number,
        op_type,
        op_label.strip(),
        # op_label_extra.strip().replace('\n','\\'),
        op_label_extra.strip(),
        # the star '*' operator is like spread '...' in JS
        *set_operation_amount(op_amount, debit)
    ]
    return op


def string_to_decimal(str):
    # replace french separator by english one (otherwise there is a conversion syntax error)
    str = str.replace(',', '.')
    # remove useless spaces
    str = str.replace(' ', '')
    # convert to decimal
    nb = D(str)
    return nb


def decimal_to_string(dec):
    dec_as_str = str(dec)
    # replace english separator by french one
    dec_as_str = dec_as_str.replace('.', ',')
    return dec_as_str


def main():
    operations = []
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

            # clean account to keep only operations
            account = clean_account(account, full)
            # search all debit operations
            debit_ops = regex.finditer(debit_regex, account, flags=regex.M)
            for debit_op in debit_ops:
                # extract regex groups
                op_date = debit_op.group('op_dte').strip()
                op_label = debit_op.group('op_lbl').strip()
                op_label_extra = debit_op.group('op_lbl_extra').strip()
                op_amount = debit_op.group('op_amt').strip()
                # convert amount to regular Decimal
                op_amount = string_to_decimal(op_amount)
                # update total
                total -= op_amount
                # print('debit {0}'.format(op_amount))
                operations.append(create_operation_entry(op_date, emission_date,
                                                         account_number, op_label, op_label_extra, op_amount, True))

            # search all credit operations
            credit_ops = regex.finditer(credit_regex, account, flags=regex.M)
            for credit_op in credit_ops:
                # extract regex groups
                op_date = credit_op.group('op_dte').strip()
                op_label = credit_op.group('op_lbl').strip()
                op_label_extra = credit_op.group('op_lbl_extra').strip()
                op_amount = credit_op.group('op_amt').strip()
                # convert amount to regular Decimal
                op_amount = string_to_decimal(op_amount)
                # update total
                total += op_amount
                # print('credit {0}'.format(op_amount))
                operations.append(create_operation_entry(op_date, emission_date,
                                                         account_number, op_label, op_label_extra, op_amount, False))

            # check inconsistencies
            if not ((previous_balance + total) == new_balance):
                print(account)
                print(
                    '⚠️  inconsistency detected between imported operations and new balance')
                errors += 1
                print('previous_balance is {0}'.format(previous_balance))
                print('predicted new_balance is {0}'.format(
                    previous_balance + total))
                print('new_balance should be {0}'.format(new_balance))

        current_file.close()
        print('✅ Parse ok')

    # sort everything by date
    operations.sort(key=lambda x: datetime.strptime(x[0], '%d/%m/%Y'))

    # write result in file
    with open('output.csv', 'w', newline='') as f:
        # we use ';' separator to avoid conflicts with amounts' ','
        writer = csv.writer(f, delimiter=';')
        writer.writerows(
            [['date', 'account', 'type', 'label', 'label_extra', 'credit', 'debit'], *operations]
        )
    print('OPERATIONS({0})'.format(len(operations)))
    print(
        'OTHER({0})/BANK({1})/DEPOSIT({2})/WIRETRANSFER({3})/CHECK({4})/CARDDEBIT({5})/WITHDRAWAL({6})/DIRECTDEBIT({7})'
        .format(
            other_op_count,
            bank_op_count,
            deposit_op_count,
            wire_transfer_op_count,
            check_op_count,
            card_debit_op_count,
            withdrawal_op_count,
            direct_debit_op_count
        )
    )
    print('ERRORS({0})'.format(errors))

    # rm tmp file
    os.remove('tmp.txt')


if __name__ == "__main__":
    main()
