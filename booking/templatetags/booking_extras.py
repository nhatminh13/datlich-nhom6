from django import template

register = template.Library()


@register.filter
def vnd(value):
    """80000 -> '80.000'"""
    try:
        return f"{int(value):,}".replace(",", ".")
    except (TypeError, ValueError):
        return value
