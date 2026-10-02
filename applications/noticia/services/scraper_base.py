from abc import ABC, abstractmethod
from .engine import fetch_html


class ScraperBase(ABC):
    def get_html(self, session, url, origin, deadline):
        return fetch_html(session, url, origin, deadline)

    @abstractmethod
    def scrape(self):
        raise NotImplementedError
