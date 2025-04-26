from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from .services.infobae_scraper import scrape_infobae

class NoticiasInfobaeAPIView(APIView):
    def get(self, request):
        data = scrape_infobae()

        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)

