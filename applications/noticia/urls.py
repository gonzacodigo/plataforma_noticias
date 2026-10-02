from django.urls import path
from . import views

app_name = "noticia_app"
urlpatterns = [
    path("", views.List_all_noticiasListView.as_view(), name="inicio"),
    path("instagram-views", views.InstagramViews.as_view(), name="instagram"),
    path(
        "buscador-imagenes",
        views.Google_imagenes_Views.as_view(),
        name="buscador_imagenes",
    ),
    path(
        "noticia-categoria/",
        views.ListNoticiaCategoria.as_view(),
        name="noticia_categoria",
    ),
    path("noticia-medio/", views.ListNoticiaMedios.as_view(), name="noticia_medio"),
    path(
        "detail-noticia/<int:pk>/",
        views.NoticiasDetailView.as_view(),
        name="noticia_detail",
    ),
]
for route, source, name in [
    ("infobae/show", "infobae_show", "noticias-infobae-show"),
    ("infobae", "infobae", "noticias-infobae"),
    ("tn", "tn", "noticias-tn"),
    ("tn/show", "tn_show", "noticias-tn-show"),
    ("telefe/show", "telefe_show", "noticias-telefe-show"),
    ("telefe", "telefe", "noticias-telefe"),
    ("clarin", "clarin", "noticias-clarin"),
]:
    urlpatterns.append(
        path(
            f"api/noticias/{route}/",
            views.ScrapeAPIView.as_view(source=source),
            name=name,
        )
    )
