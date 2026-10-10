from django import template
from reportlab.pdfbase.pdfmetrics import stringWidth

register = template.Library()


@register.filter
def pdf_font_size(value, column):
    """Fit common long values to the A4 column, retaining a readable minimum.

    Widths are usable points after padding for the invoice's 36/8/22/17/17
    percent columns on an A4 page with 14 mm side margins.
    Exceptionally long names can still wrap without clipping or losing text.
    """
    widths = {'name': 175, 'quantity': 104, 'money': 78}
    font = 'Helvetica-Bold' if column == 'name' else 'Helvetica'
    width = stringWidth(str(value), font, 1)
    size = min(7.875, widths[column] / width) if width else 7.875
    return f'{max(6, size):.3f}'


@register.filter
def pdf_name_wrap(value):
    """Wrap at word boundaries unless one token exceeds the entire column."""
    if any(stringWidth(word, 'Helvetica-Bold', 6) > 175 for word in str(value).split()):
        return 'CJK'
    return 'LTR'
