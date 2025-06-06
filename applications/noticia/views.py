from django.urls import reverse_lazy
from django.db.models import Case, When, IntegerField
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.generic import TemplateView, ListView, DetailView
from .services.infobae.infobae_scraper_show import scrape_infobae_show
from .services.infobae.infobae_scraper_general import scrape_infobae_general
from .services.tn.tn_scraper_general import scrape_tn_general
from .services.tn.tn_scraper_show import scrape_tn_show
from .services.telefe.telefe_scraper_show import scrape_telefe_show
from .services.telefe.telefe_scraper_general import scrape_telefe_general
from .services.clarin.clarin_scraper_general import scrape_clarin_general
from .models import Noticia
from .forms import CategoriaForm
from applications.medio.forms import MedioForm


# Vista que muestra los detalles de un empleado específico
class NoticiasDetailView(DetailView):
    model = Noticia  # Se usa el modelo Empleado
    template_name = 'noticia/noticia_detail.html'  # Plantilla a renderizar
    # No devuelve una lista, sino un objeto individual, no se necesita un bucle en el template

# Vista que muestra una plantilla estática de presentación
class InstagramViews(TemplateView):
    template_name = 'instagram/instagram.html'

# Vista que muestra una plantilla estática de presentación
class Google_imagenes_Views(TemplateView):
    template_name = 'google/buscador_imagenes.html'
    
class NoticiasInfobaeShowAPIView(APIView):
    def get(self, request):
        data = scrape_infobae_show()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)
    
class NoticiasInfobaeAPIView(APIView):
    def get(self, request):
        data = scrape_infobae_general()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)
    
class NoticiasTnAPIView(APIView):
    def get(self, request):
        data = scrape_tn_general()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)
    
class NoticiasclarinAPIView(APIView):
    def get(self, request):
        data = scrape_clarin_general()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)
    

class NoticiasTnShowAPIView(APIView):
    def get(self, request):
        data = scrape_tn_show()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)
        
    
class NoticiasTelefeShowAPIView(APIView):
    def get(self, request):
        data = scrape_telefe_show()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)


class NoticiasTelefeAPIView(APIView):
    def get(self, request):
        data = scrape_telefe_general()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)


class List_all_noticiasListView(ListView):
    model = Noticia
    context_object_name = 'noticias'
    template_name = 'noticia/noticia_list.html'
    paginate_by = 300

    def get_queryset(self):
        palabra_clave = self.request.GET.get('kword', '').strip()
        f1 = self.request.GET.get('fecha1', '').strip()
        f2 = self.request.GET.get('fecha2', '').strip()

        # Usamos el manager según los filtros
        if f1 and f2:
            queryset = Noticia.objects.buscar_noticia(f1, f2)
        elif palabra_clave:
            queryset = Noticia.objects.buscar_noticia_titulo(palabra_clave)
        else:
            queryset = Noticia.objects.buscar_noticia()

        # Anotamos la prioridad
        queryset = queryset.annotate(
            prioridad=Case(
                When(categoria__nombre__iexact='ESPECTACULOS', then=0),
                When(categoria__nombre__iexact='DEPORTES', then=1),
                When(categoria__nombre__iexact='POLITICA', then=2),
                default=3,
                output_field=IntegerField(),
            )
        )

        # Ordenar por prioridad y fecha (ya ordenado por fecha ascendente/descendente según el manager)
        return queryset.order_by('prioridad', 'fecha' if f1 and f2 else '-fecha')

            
                       

class ListNoticiaCategoria(ListView):
    model = Noticia
    context_object_name = 'noticias'
    template_name = 'noticia/lista_noticia_categoria.html'
    #paginate_by = 30  # Se establece la paginación en 5 noticias por página


    def get_queryset(self):
        categorias = self.request.GET.getlist('categorias')
        if categorias:
            return Noticia.objects.filter(categoria__id__in=categorias).order_by('-fecha')
        return Noticia.objects.all().order_by('-fecha')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CategoriaForm(self.request.GET)
        return context

class ListNoticiaMedios(ListView):
    model = Noticia
    context_object_name = 'noticias'
    template_name = 'noticia/lista_noticia_medio.html'
    #paginate_by = 30

    def get_queryset(self):
        medio_id = self.request.GET.get('medio')
        queryset = Noticia.objects.all()
        if medio_id:
            queryset = queryset.filter(medio__id=medio_id)
        return queryset.order_by('-fecha')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = MedioForm(self.request.GET)
        return context