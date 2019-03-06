# CEP
(CEP stands for *Caisse d'Epargne Parser*)

**CEP aims at parsing PDF statements from the Caisse d'Épargne (a french banking group) and gathering extracted operations into a CSV file.**

What you'll get at the end is a 6 columns CSV file:
- date of the operation
- account number concerned by the operation
- operation type:
    - `BANK`: bank fees, international operation fees, etc.
    - `DEPOSIT`: cash deposits on the account
    - `WIRETRANSFER`: incoming / outcoming wiretransfers
    - `CHECK`: check deposits / payments
    - `CARDDEBIT`: payments made via debit card
    - `WITHDRAWAL`: withdrawals
    - `DIRECTDEBIT`: direct debits
    - `OTHER`: other kind op operation
- operation description
- credit amount (if credit)
- debit amount (if debit)

As a fork from Adrien's original work ([here](https://github.com/zarov/cep)), my version brings some improvements and evolutions:
- better operation parsing (originally, CEP was sometimes detecting operations that were not operations!)
- operation type detection (the in place detection wasn't working at all 🤷‍♂️)
- inconsistency checks (hence, CEP verifies that all operations are correctly parsed)
- capacity to handle operations with amount up to 999,999.99€
- proper CSV writing


### How to install CEP?
Prior to using CEP, you'll need `pdfminer` installed in your virtualenv:
```bash
cd cep
virtualenv -p /usr/bin/python2 .
source bin/activate
pip install pdfminer
```

### How to use CEP?
From your virtualenv:
```bash
python3 cep.py folder_containing_your_statements/
```

You'll notice that we create a virtualenv sourced from a **Python2** interpreter, whereas we run CEP using a **Python3** runner.
The explanation is that `pdfminer` can only be installed using Python2, whereas CEP uses some Python3 features (such as [PEP3102](https://www.python.org/dev/peps/pep-3102/)).


### Compatibility
As far as I tested, CEP works on PDF statements officially emitted by the Caisse d'Épargne, between years 2014 and 2019.
Feel free to fill an issue in if CEP doesn't work as intended!

### Warning
The operation amounts are saved as they are found in the statement. Thus, a decimal comma is used as a separator, instead of the dot decimal separator used in US, UK, etc.
