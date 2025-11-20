from ..core.DBHandler import DBHandler

_db_instance: DBHandler | None = None


def set_db(db: DBHandler):
    global _db_instance
    _db_instance = db


def _merge_orm_objects_in_namespace(ip):
    """
    Finds all detached ORM objects in the user's namespace and merges them
    into the current session.
    """
    if not _db_instance or not _db_instance.session:
        return

    session = _db_instance.session
    user_ns = ip.user_ns

    for name, obj in list(user_ns.items()):
        if hasattr(obj, '_sa_instance_state'):
            state = obj._sa_instance_state
            if state.session is None and state.key is not None:
                try:
                    merged_obj = session.merge(obj, load=False)
                    user_ns[name] = merged_obj
                except Exception as e:
                    print(f"[DB] Warning: Could not merge variable '{name}': {e}")


def load_ipython_extension(ipython):
    """
    Called when the extension is loaded with %load_ext
    """
    def pre_run_cell(*args, **kwargs):
        if _db_instance is not None:
            _db_instance.open_session()
            _merge_orm_objects_in_namespace(ipython)

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
