# Case billing

Deploy this API version before using Case in the updated Windows app. Apply the
included migration using the API's normal environment:

```powershell
python manage.py migrate
```

The migration adds the Case unit and a case-size snapshot to invoice items.
It preserves existing invoices. The snapshot ensures deleting or replacing an
invoice restores the number of pieces originally sold, even if inventory's
cents-per-case value later changes.

One case is the product's `cent_in_per_cs` times 10 pieces. A Case selection
requires a positive case size representing a whole number of pieces. The rate
is cents per case times the cent rate, or pieces per case times the piece rate,
depending on the inventory entry mode. Quantity means number of cases.

Checks:

```powershell
python manage.py test billing products --settings=billing.test_settings --noinput
python manage.py makemigrations --check --dry-run --settings=billing.test_settings
```

These tests use an isolated in-memory SQLite database.
