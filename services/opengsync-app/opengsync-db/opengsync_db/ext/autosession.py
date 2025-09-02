from ..core.DBHandler import DBHandler

_db_instance: DBHandler | None = None


def set_db(db: DBHandler):
    global _db_instance
    _db_instance = db


def load_ipython_extension(ipython):
    """
    Called when the extension is loaded with %load_ext
    """
    def pre_run_cell(*args, **kwargs):
        if _db_instance is not None:
            _db_instance.open_session()

    def post_run_cell(result):
        if _db_instance is not None:
            if _db_instance._session is not None:
                _db_instance.close_session()

    ipython.events.register('pre_run_cell', pre_run_cell)
    ipython.events.register('post_run_cell', post_run_cell)


def unload_ipython_extension(ipython):
    """
    Called when the extension is unloaded with %unload_ext
    """
    ipython.events.unregister('pre_run_cell', None)
    ipython.events.unregister('post_run_cell', None)
    print("[DB] Extension unloaded, hooks removed")
