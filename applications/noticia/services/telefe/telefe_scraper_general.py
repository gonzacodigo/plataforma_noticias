from applications.noticia.services.engine import run_source


def scrape_telefe_general():
    return run_source("telefe")
