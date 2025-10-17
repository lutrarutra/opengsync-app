
def main():
    import os
    from opengsync_db.core import DBHandler

    db = DBHandler()
    db.connect(
        user=os.environ["POSTGRES_USER"],
        password=os.environ["POSTGRES_PASSWORD"],
        host=os.environ["POSTGRES_HOST"],
        port=os.environ["POSTGRES_PORT"],
        db=os.environ["POSTGRES_DB"],
    )
    
    db.open_session()
    db.create_tables()
    db.close_session(commit=True)


if __name__ == "__main__":
    main()
    exit(0)
