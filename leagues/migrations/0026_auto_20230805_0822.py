# Generated by Django 4.2.1 on 2023-08-05 08:22

from django.db import migrations


def create_through_relations(apps, schema_editor):
    """Copy existing data to the new through models"""
    Match = apps.get_model('leagues', 'Match')
    HomeTeamPlayer = apps.get_model('leagues', 'HomeTeamPlayer')
    AwayTeamPlayer = apps.get_model('leagues', 'AwayTeamPlayer')
    for match in Match.objects.all():
        for player in match.home_team.all():
            HomeTeamPlayer(
                match=match,
                player=player,
            ).save()
        for player in match.away_team.all():
            AwayTeamPlayer(
                match=match,
                player=player,
            ).save()
    return


class Migration(migrations.Migration):

    dependencies = [
        ('leagues', '0025_hometeamplayer_awayteamplayer'),
    ]

    operations = [
        # See: https://stackoverflow.com/a/51351406
        migrations.RunPython(
            create_through_relations,
            reverse_code=migrations.RunPython.noop,
        ),
    ]