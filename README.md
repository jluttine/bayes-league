# Bayes League


## Instructions

To test locally, run the following commands in the project root directory (where
`manage.py` file is located).

Install dependencies (Django) in your preferred way. For instance:

``` shell
pip install django autograd scipy
```

Initialize the local database (run this whenever you update the code too):

``` shell
python manage.py migrate
```

Run the local development server:

``` shell
python manage.py runserver
```

Open http://127.0.0.1:8000/ in your browser.


## Copyright

Copyright (C) 2023 Jaakko Luttinen <jaakko.luttinen@iki.fi>

This program is free software: you can redistribute it and/or modify it under
the terms of the GNU Affero General Public License version 3 as published by the
Free Software Foundation.

This program is distributed in the hope that it will be useful, but WITHOUT ANY
WARRANTY; without even the implied warranty of MERCHANTABILITY or FITNESS FOR A
PARTICULAR PURPOSE. See the GNU Affero General Public License for more details.

You should have received a copy of the GNU Affero General Public License along
with this program. If not, see <https://www.gnu.org/licenses/>.
