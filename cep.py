#!/usr/bin/env python3
# -*- encoding: utf-8 -*-
import sys
import os
import re
from pprint import pprint
from datetime import datetime
from pathlib import Path


def set_year(emission, reference):
    # fake a leap year
    emission = datetime.strptime(emission + '00', '%d/%m%y')
    if emission.month <= reference.month:
        emission = emission.replace(year=reference.year)
    else:
        emission = emission.replace(year=reference.year - 1)
    return datetime.strftime(emission, '%d/%m/%Y')


def set_amount(amount, debit):
    if debit:
        return ';' + amount
    return amount + ';'


def set_entry(emission, reference_emission, account_number, index, statement,
              amount, debit):
    res = set_year(emission, reference_emission) + ';'
    res += account_number + ';'
    res += index + ';'
    res += statement.strip() + ';'
    res += set_amount(amount, debit)
    res += '\n'
    return res


def main():
    csv = 'date;account;type;statement;credit;debit\n'

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

    # stats
    no_section_count = 0
    section_count = 0
    total_count = 0

    # regex
    reg1 = r'^(\d\d\/\d\d)(.*)\s+([\d, ]+?)$'
    reg2 = r'^([\d, ]+?)(\d\d\/\d\d)(.*)$'
    date_regex = r'\b([\d/]{10})\b'

    # go through each file
    p = Path(sys.argv[1])
    for filename in sorted(p.iterdir()):
        filename = str(filename)
        if filename.endswith('pdf') == False:
            continue

        print('Parsing: ' + filename)

        # escape spaces in name
        filename = re.sub(r'\s', '\\ ', filename)

        # parse pdf
        command = 'pdf2txt.py -M 200 -o tmp.txt ' + filename
        os.system(command)

        # open parsed
        file_parsed = open('tmp.txt', 'r')
        parsed = file_parsed.read()

        # remove lines with one character or less
        parsed = re.sub(r'(\n.| +)$', '', parsed, flags=re.M)

        # search for date of emission of the pdf
        reference_emission = re.findall(date_regex, parsed)[0]
        reference_emission = datetime.strptime(reference_emission, '%d/%m/%Y')
        print(' * Emission date is ' + reference_emission.strftime("%Y-%m-%d"))

        # search for owner to identify multiple accounts
        owner = re.findall(r'Identifiant client\s+(\D*)', parsed)[0].strip()
        print(' * Account owner is ' + owner)
        account_regex = r'^((?:MR|MME|MLLE) ' + owner + ' - .* - ([^(\n]*))$'
        accounts = re.findall(account_regex, parsed, flags=re.M)
        print(' * There are {0} accounts:'.format(len(accounts)))

        for (full, account_number) in reversed(accounts):
            (parsed, _, account) = parsed.partition(full)
            account_number = re.sub(r'\D', '', account_number)
            print('   * ' + account_number)

            account_copy = account

            # isolate and parse each section
            no_section = True
            for (index, section, debit) in reversed(sections):
                (account, _, result) = account.partition(section)

                res = re.findall(reg1, result, flags=re.M)
                for (emission, statement, amount) in res:
                    no_section = False
                    csv += set_entry(emission, reference_emission,
                                     account_number, index, statement, amount, debit)

            # nothing has been found above: test others things
            if no_section:
                # this should alaways match debit
                res = re.findall(reg1, account_copy, flags=re.M)
                for (emission, statement, amount) in res:
                    csv += set_entry(emission, reference_emission,
                                     account_number, 'OTHER', statement, amount, True)

                # this should alaways match credit
                res = re.findall(reg2, account_copy, flags=re.M)
                for (amount, emission, statement) in res:
                    csv += set_entry(emission, reference_emission,
                                     account_number, 'OTHER', statement, amount, False)

        file_parsed.close()
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
