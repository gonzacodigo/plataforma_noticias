from applications.noticia.services.engine import run_source


def scrape_telefe_show():
    return run_source("telefe_show")
