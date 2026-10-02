from urllib.parse import urlencode
from django.conf import settings
from django.db.models import F
from django.views.generic import TemplateView, ListView, DetailView
from rest_framework.views import APIView
from rest_framework.permissions import IsAdminUser
from rest_framework.throttling import UserRateThrottle
from rest_framework.response import Response
from .forms import BusquedaForm
from .models import Noticia, ScrapeRun
from .services.engine import run_source, ScrapeError, ScrapeBusy


class ScrapeThrottle(UserRateThrottle):
    scope = "scrape"


class ScrapeAPIView(APIView):
    permission_classes = [IsAdminUser]
    throttle_classes = [ScrapeThrottle]
    source = None

    def post(self, request):
        try:
            return Response(run_source(self.source))
        except ScrapeBusy:
            return Response({"error": "La fuente ya se está actualizando."}, status=409)
        except ScrapeError:
            return Response(
                {
                    "error": "No se pudo actualizar la fuente. Consulta el registro de ejecuciones."
                },
                status=502,
            )


class List_all_noticiasListView(ListView):
    model = Noticia
    context_object_name = "noticias"
    template_name = "noticia/noticia_list.html"
    paginate_by = 24

    def get_queryset(self):
        self.form = BusquedaForm(self.request.GET)
        if not self.form.is_valid():
            return Noticia.objects.none()
        data = self.form.cleaned_data
        queryset = Noticia.objects.buscar_noticia(
            data.get("fecha1"), data.get("fecha2")
        )
        if data.get("kword"):
            queryset = queryset.filter(titulo__icontains=data["kword"])
        if data.get("categoria"):
            queryset = queryset.filter(categoria=data["categoria"])
        if data.get("categorias"):
            queryset = queryset.filter(categoria__in=data["categorias"])
        if data.get("medio"):
            queryset = queryset.filter(medio=data["medio"])
        return (
            queryset.select_related("medio", "categoria")
            .defer("contenido")
            .order_by("-fecha", "-id")
        )

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        context.update(
            form=self.form,
            filter_query=params.urlencode(),
            last_run=ScrapeRun.objects.filter(estado__in=["success", "partial"])
            .only("fin")
            .first(),
        )
        return context


class ListNoticiaCategoria(List_all_noticiasListView):
    pass


class ListNoticiaMedios(List_all_noticiasListView):
    pass


class NoticiasDetailView(DetailView):
    model = Noticia
    template_name = "noticia/noticia_detail.html"

    def get_queryset(self):
        return Noticia.objects.select_related("medio", "categoria").prefetch_related(
            "imagenes"
        )

    def get(self, request, *args, **kwargs):
        response = super().get(request, *args, **kwargs)
        seen = list(request.session.get("seen_news", []))
        if self.object.pk not in seen:
            Noticia.objects.filter(pk=self.object.pk).update(visitas=F("visitas") + 1)
            self.object.visitas += 1
            request.session["seen_news"] = (seen + [self.object.pk])[-100:]
        return response

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        url = settings.SITE_URL + self.object.get_absolute_url()
        context.update(
            whatsapp_url="https://wa.me/?"
            + urlencode({"text": self.object.titulo + "\n" + url}),
            facebook_url="https://www.facebook.com/sharer/sharer.php?"
            + urlencode({"u": url}),
        )
        return context


class InstagramViews(TemplateView):
    template_name = "instagram/instagram.html"


class Google_imagenes_Views(TemplateView):
    template_name = "google/buscador_imagenes.html"
