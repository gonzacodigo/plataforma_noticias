from abc import ABC, abstractmethod
import requests
from bs4 import BeautifulSoup

class ScraperBase(ABC):
    headers = {'User-Agent': 'Mozilla/5.0'}

    def get_html(self, url):
        response = requests.get(url, headers=self.headers)
        if response.status_code == 200:
            return BeautifulSoup(response.content, 'html.parser')
        return None

    @abstractmethod
    def scrape(self):
        pass
