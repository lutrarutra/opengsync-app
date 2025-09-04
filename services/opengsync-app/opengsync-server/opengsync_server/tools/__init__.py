import os

from .utils import connect_similar_strings, make_filenameable, parse_float, parse_int, titlecase_with_acronyms, tab_10_colors, check_indices, mapstr, make_alpha_numeric, get_barcode_table  # noqa
from . import io  # noqa
from .classproperty import classproperty  # noqa
from .RedisMSFFileCache import RedisMSFFileCache  # noqa
from .StaticSpreadSheet import StaticSpreadSheet  # noqa
from .MailHandler import MailHandler  # noqa

if os.getenv("GEMINI_API_KEY"):
    from .TextGen import TextGen  # noqa
    textgen = TextGen()
else:
    textgen = None