from django.contrib.auth import views as auth_views
from django.urls import path
from applications.cuentas.forms import IngresoForm
from . import herramientas_ia, views

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
    path(
        "detail-noticia/<int:pk>/ia/<slug:tipo>/",
        herramientas_ia.GenerarIANoticiaView.as_view(),
        name="generar_ia",
    ),
    # Dirección anterior del copy: sigue andando para páginas que quedaron abiertas.
    path(
        "detail-noticia/<int:pk>/generar-copy/",
        herramientas_ia.GenerarIANoticiaView.as_view(),
        name="generar_copy",
    ),
    path("ia/<int:pk>/guardar/", herramientas_ia.GuardarIAView.as_view(), name="guardar_ia"),
    path(
        "ingresar/",
        auth_views.LoginView.as_view(
            template_name="registration/login.html",
            authentication_form=IngresoForm,
            redirect_authenticated_user=True,
        ),
        name="ingresar",
    ),
    path("salir/", auth_views.LogoutView.as_view(), name="salir"),
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
