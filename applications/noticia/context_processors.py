from django.conf import settings


def brand(request):
    return {
        "brand_name": "Desenchufadas",
        "instagram_url": settings.INSTAGRAM_URL,
        "canonical_url": settings.SITE_URL + request.path,
        "social_image": settings.SITE_URL
        + settings.STATIC_URL
        + "img/LOGODESENCHUFADAS2-TRANSPARENTE.png",
    }
