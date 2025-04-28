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
from .views import NoticiasInfobaeAPIView
from . import views 
urlpatterns = [
        path('',
         views.List_all_noticiasListView.as_view(),
         name='inicio'
         ),
    path('noticia-categoria/', views.ListNoticiaCategoria.as_view(), name='noticia_categoria'),
    path('api/noticias/infobae/', NoticiasInfobaeAPIView.as_view(), name='noticias-infobae'),
]

