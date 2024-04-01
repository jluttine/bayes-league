from django.template import Library

register = Library()

@register.filter
def repeat(string, times):
    return (
        "" if times is None or times == 0 or times == "" else
        string * times
    )
