import requests
import datetime
from pytz import timezone

from bs4 import BeautifulSoup
from django.utils.text import slugify

from leagues import models


def plusminus_to_result(x):
    h = 21 + min(0, x)
    a = 21 + min(0, -x)
    return (h, a)


def table_to_results(table):
    rows = table.find_all("tr")
    xs = []
    for row in rows[1:]:
        cells = row.find_all("td")
        name = cells[0].contents[0][3:]
        plusminus = int(cells[1].contents[0])
        xs.append((name, plusminus))

    # a&b vs c&d = x
    # a&c vs b&d = y
    # a&d vs b&c = z
    #
    # a =  x + y + z
    # b =  x - y - z
    # c = -x + y - z
    # d = -x - y + z
    #
    # x = (a + b) / 2
    # y = (a + c) / 2
    # z = (a + d) / 2

    if len(xs) != 4:
        # Ignore groups with "extra" players that were ignored from results.
        # This happens often in the bottom group.
        return []

    return [
        (
            [xs[0][0], xs[1][0]],
            [xs[2][0], xs[3][0]],
            plusminus_to_result((xs[0][1] + xs[1][1]) // 2),
        ),
        (
            [xs[0][0], xs[2][0]],
            [xs[1][0], xs[3][0]],
            plusminus_to_result((xs[0][1] + xs[2][1]) // 2),
        ),
        (
            [xs[0][0], xs[3][0]],
            [xs[1][0], xs[2][0]],
            plusminus_to_result((xs[0][1] + xs[3][1]) // 2),
        ),
    ]


def import_bvt(league, year, name, start_gdid):
    stop = False
    gdid = start_gdid
    previous_stages = []

    fail = "\033[91m"
    ok = "\033[92m"
    end = "\033[0m"

    while not stop:
        url = f"https://bvt.fi/viikkokisat/gd_info.php?gdid={gdid}"
        gdid += 1
        response = requests.get(url)
        print(f"Parsing {url} ...")
        soup = BeautifulSoup(response.text, features="html.parser")
        if soup.h1.contents == []:
            # Empty page
            print(f"{fail} x No results available{end}")
            break
        title = soup.h1.contents[0]
        try:
            (n, date) = title.lower().split(", ")
        except ValueError:
            print(f"{fail} x Incorrect title format: {title}{end}")
            continue
        if n != name:
            # Wrong league
            print(f"{fail} x Wrong league: {n} != {name}{end}")
            continue
        tz = timezone("Europe/Helsinki")
        try:
            dt = tz.localize(
                datetime.datetime.strptime(
                    date + " 18:00",
                    "%d.%m.%Y %H:%M",
                )
            )
        except ValueError:
            print(f"{fail} x Not a date: {date}{end}")
            continue
        if dt.year < year:
            print(f"{fail} x Results too old{end}")
            continue
        if dt.year > year:
            print("{fail} x Results too new{end}")
            break
        (stage, created) = models.Stage.objects.get_or_create(
            league=league,
            name=date,
            defaults=dict(
                slug=slugify(date),
            )
        )
        stage.included.set(previous_stages)
        previous_stages.append(stage)
        stage.bottom()
        if not created:
            # Matches already imported
            print(f"{ok} o Results already imported{end}")
            continue
        tables = soup.find_all("table")
        results = []
        for table in tables:
            results = results + table_to_results(table)
        for result in results:
            home_team = [
                models.Player.objects.get_or_create(league=league, name=name)[0]
                for name in result[0]
            ]
            away_team = [
                models.Player.objects.get_or_create(league=league, name=name)[0]
                for name in result[1]
            ]
            m = models.Match.objects.create(
                league=league,
                stage=stage,
            )
            m.home_team.set(home_team)
            m.away_team.set(away_team)
            home_points = result[2][0]
            away_points = result[2][1]
            models.Period.objects.create(
                match=m,
                home_points=home_points,
                away_points=away_points,
                datetime=dt,
            )

        print(f"{ok} o Results from '{soup.h1}' imported{end}")

    from leagues.views import update_ranking
    update_ranking(league, *previous_stages)

    return
