import os

from .utils import connect_similar_strings, make_filenameable, parse_float, parse_int, titlecase_with_acronyms, tab_10_colors, check_indices, mapstr, make_alpha_numeric, get_barcode_table
from . import io
from .classproperty import classproperty
from .RedisMSFFileCache import RedisMSFFileCache
from .StaticSpreadSheet import StaticSpreadSheet
from .MailHandler import MailHandler
from .ExcelWriter import ExcelWriter
from .FileBrowser import FileBrowser
from .SharedFileBrowser import SharedFileBrowser

if os.getenv("GEMINI_API_KEY"):
    from .TextGen import TextGen
    textgen = TextGen()
else:
    textgen = None