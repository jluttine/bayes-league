# Bayes League

## Instructions

To test locally, run the following commands in the project root directory (where
`manage.py` file is located).

Install dependencies (Django) in your preferred way. For instance:

``` shell
pip install django autograd scipy
```


Initialize the local database (run only once):

``` shell
python manage.py makemigrations
python manage.py migrate

```

Run the local server:

``` shell

python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser.
