from applications.noticia.services.engine import run_source


def scrape_infobae_general():
    return run_source("infobae")
