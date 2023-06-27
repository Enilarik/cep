# CEP
(CEP stands for *Caisse d'Epargne Parser*)

**CEP aims at parsing PDF statements from the Caisse d'Épargne (a french banking group) and gathering extracted operations into a CSV file.**

**This repository has been forked from Eliott's work ([here]https://github.com/eliottvincent/cep) itself forked from Adrien's original work ([here](https://github.com/zarov/cep))**
**My version mostly brings changements i needed to make things work with my PDF at this date (Mid-2023).**
**I don't own anything related to this parser, only a few bits of code here and there.**

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

### How to install CEP?
Prior to using CEP, you'll need some librairies (`pdfminer.six` and `regex`) installed in your virtualenv:
```bash
cd cep
virtualenv -p /usr/bin/python .
source bin/activate
pip3 install -r requirements.txt
```

### How to use CEP?
From your virtualenv:
```bash
python3 cep.py folder_containing_your_statements/
```

### Compatibility
As far as I tested, CEP works on PDF statements officially emitted by the Caisse d'Épargne, between years 2014 and 2019.
Feel free to fill an issue in if CEP doesn't work as intended!

### Warning
The operation amounts are saved as they are found in the statement. Thus, a decimal comma is used as a separator, instead of the dot decimal separator used in US, UK, etc.
