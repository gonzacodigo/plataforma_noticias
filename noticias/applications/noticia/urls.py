"""agenda URL Configuration

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/3.0/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""

app_name = "noticia_app"

from django.urls import path
from .views import NoticiasInfobaeAPIView, NoticiasTnAPIView, NoticiasTelefeAPIView
from . import views 
urlpatterns = [
        path('',
         views.List_all_noticiasListView.as_view(),
         name='inicio'
         ),
        path('instagram-views',
         views.InstagramViews.as_view(),
         name='instagram'
         ),
        path('buscador-imagenes',
         views.Google_imagenes_Views.as_view(),
         name='buscador_imagenes'
         ),
    path('noticia-categoria/', views.ListNoticiaCategoria.as_view(), name='noticia_categoria'),
    path('noticia-medio/', views.ListNoticiaMedios.as_view(), name='noticia_medio'),
    path('api/noticias/infobae/', NoticiasInfobaeAPIView.as_view(), name='noticias-infobae'),
    path('api/noticias/tn/', NoticiasTnAPIView.as_view(), name='noticias-tn'),
    path('api/noticias/telefe/', NoticiasTelefeAPIView.as_view(), name='noticias-telefe'),
]

