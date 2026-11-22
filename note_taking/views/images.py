"""Pages et actions des images : liste, détail, suppression, suggestions de
l'éditeur (#90) et image collée ou déposée (#196)."""

from django.contrib import messages
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect
from django.views.decorators.http import require_GET, require_POST
from django.views.generic import DetailView, ListView

from core.exceptions import AppError
from core.suggestions import rank_by_name
from images.exceptions import ImageError
from images.models import Image
from images.services import delete_image as delete_image_service

from ..captures import import_capture
from ..models import Note


class ImageList(ListView):
    model = Image
    context_object_name = "images"
    template_name = "note_taking/images_list.html"


class ImageDetail(DetailView):
    model = Image
    context_object_name = "image"
    template_name = "note_taking/image_detail.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["notes"] = (
            Note.objects.filter(parts__images=self.object).distinct().order_by("date")
        )
        return context


@require_POST
def delete_image(request, pk):
    """Supprime une image inutilisée ; une image utilisée est refusée."""
    image = get_object_or_404(Image, pk=pk)
    name = image.name
    try:
        delete_image_service(image)
    except AppError as e:
        messages.error(request, str(e))
        return redirect("note_taking:image_detail", pk=pk)
    messages.success(request, f"L'image « {name} » est supprimée.")
    return redirect("note_taking:images_list")


@require_GET
def image_suggestions(request):
    """Les images, pour les suggestions de l'éditeur (#90) : la référence à écrire
    dans la note et l'adresse de la vignette ; `?q=` filtre par nom."""
    images = rank_by_name(
        Image.objects.all(), request.GET.get("q", ""), lambda image: image.name
    )
    return JsonResponse(
        {
            "results": [
                {
                    "name": image.name,
                    "reference": f"images/{image.name}",
                    "url": image.file.url,
                }
                for image in images
            ]
        }
    )


@require_POST
def image_capture(request):
    """Importe une image collée ou déposée (#196) : l'éditeur insère la référence
    renvoyée ; la page des images se recharge ensuite (`notify`) et y affiche le
    message de succès ou de refus."""
    notify = bool(request.POST.get("notify"))

    def refuse(text: str):
        if notify:
            messages.error(request, text)
        return JsonResponse({"error": text}, status=400)

    file = request.FILES.get("image")
    if file is None:
        return refuse("Aucune image reçue.")
    try:
        image = import_capture(file)
    except ImageError as e:
        return refuse(str(e))
    if notify:
        messages.success(request, f"L'image « {image.name} » est importée.")
    return JsonResponse(
        {
            "name": image.name,
            "reference": f"images/{image.name}",
            "url": image.file.url,
        },
        status=201,
    )
