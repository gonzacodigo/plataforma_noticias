from django.core.management.base import BaseCommand
from applications.noticia.services.infobae_scraper import infobaeScraper

class Command(BaseCommand):
    help = 'Ejecuta todos los scrapers de noticias'

    def handle(self, *args, **kwargs):
        infobaeScraper().scrape()
        self.stdout.write(self.style.SUCCESS('Scraping completado con éxito'))
