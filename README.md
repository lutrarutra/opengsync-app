# limbless
Web app for NGS sample/library/project tracking

## Installation
    - `pip install -r requirements.txt`
    - `mkdir -p data && cd data`
    - `wget https://github.com/twbs/bootstrap/archive/v5.3.2.zip`
    - `unzip v5.3.2.zip`
    - `rm v5.3.2.zip`
    - `mkdir -p ../limbless/static/style/bootstrap`
    - `mv bootstrap-5.3.2/scss ../limbless/static/style/bootstrap`

## Run flask debug server
    - `docker compose up`
    - `flask run`