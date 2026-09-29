"""Persian text normalisation shared by URL building and redirect matching.

No Odoo imports: used by models, controllers and the migration.
"""
import re

# tashdid, fatha/kasra/damma, tanwin, sukun, hamza above/below, superscript
# alef, tatweel
_MARKS = re.compile('[ً-ٰٟـ]')
_FOLD = str.maketrans({
    'ي': 'ی',  # ي -> ی
    'ى': 'ی',  # ى -> ی
    'ئ': 'ی',  # ئ -> ی
    'ك': 'ک',  # ك -> ک
    'ة': 'ه',  # ة -> ه
    'ۀ': 'ه',  # ۀ -> ه
    'أ': 'ا',  # أ -> ا
    'إ': 'ا',  # إ -> ا
    'ٱ': 'ا',  # ٱ -> ا
    'ؤ': 'و',  # ؤ -> و
    'ء': None,      # ء dropped
})
_NUMBERING = re.compile('^\\s*[0-9۰-۹]+\\s*[-.)–]\\s*')
_SEPARATORS = re.compile('[\\s‌‍\\-_:،,.؛;()«»"\'!?؟/]+')


def fa_slug_text(text):
    """Text that goes into a URL slug: no leading chapter number, no
    diacritics, plain Persian letter forms."""
    text = _NUMBERING.sub('', text or '')
    return _MARKS.sub('', text).translate(_FOLD).strip()


def fa_fold_letters(text):
    """Arabic-keyboard letter forms -> Persian (for tolerant lookups)."""
    return (text or '').replace('ي', 'ی').replace('ك', 'ک')


def fa_match_key(text):
    """Loose comparison key for titles/slugs: folded letters, no marks,
    no numbering, alef-madda as alef, no separators or half-spaces."""
    text = fa_slug_text(text).replace('آ', 'ا')
    return _SEPARATORS.sub('', text).lower()
