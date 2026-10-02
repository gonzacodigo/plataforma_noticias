from applications.noticia.services.engine import run_source


def scrape_tn_general():
    return run_source("tn")
