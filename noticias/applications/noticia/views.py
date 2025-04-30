from django.urls import reverse_lazy
from rest_framework.views import APIView
from rest_framework.response import Response
from rest_framework import status
from django.views.generic import TemplateView, ListView
from .services.infobae_scraper import scrape_infobae
from .models import Noticia
from .forms import CategoriaForm

# Vista que muestra una plantilla estática de presentación
class indexViews(TemplateView):
    template_name = 'inicio.html'
    
class NoticiasInfobaeAPIView(APIView):
    def get(self, request):
        data = scrape_infobae()
            # Redirección tras la creación exitosa
        if isinstance(data, tuple):  # Error handling (data, status_code)
            return Response(data[0], status=data[1])

        return Response(data, status=status.HTTP_200_OK)

# Vista que lista todos los empleados con paginación de 5 empleados por página
class List_all_noticiasListView(ListView):
        model = Noticia
        context_object_name = 'noticias'
        template_name = 'noticia/noticia_list.html'
        paginate_by = 8  # Se establece la paginación en 5 empleados por página

        def get_queryset(self):
            palabra_clave = self.request.GET.get('kword', '').strip()
            f1 = self.request.GET.get('fecha1', '').strip()
            f2 = self.request.GET.get('fecha2', '').strip()

            if f1 and f2:
                # Buscar por rango de fechas, incluyendo opcionalmente la palabra clave
                return Noticia.objects.buscar_noticia(f1, f2)
            elif palabra_clave:
                # Buscar por palabra clave
                return Noticia.objects.buscar_noticia_titulo(palabra_clave)
            else:
                # Buscar todas las noticias hasta hoy (usando el método que programaste)
                return Noticia.objects.buscar_noticia()
            

class ListNoticiaCategoria(ListView):
    model = Noticia
    context_object_name = 'noticias'
    template_name = 'noticia/lista_noticia_categoria.html'
    paginate_by = 8  # Se establece la paginación en 5 empleados por página


    def get_queryset(self):
        categorias = self.request.GET.getlist('categorias')
        if categorias:
            return Noticia.objects.filter(categoria__id__in=categorias).order_by('-fecha')
        return Noticia.objects.all().order_by('-fecha')

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context['form'] = CategoriaForm(self.request.GET)
        return context

