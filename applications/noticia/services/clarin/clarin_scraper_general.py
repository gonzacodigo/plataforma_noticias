from applications.noticia.services.engine import run_source


def scrape_clarin_general():
    return run_source("clarin")
