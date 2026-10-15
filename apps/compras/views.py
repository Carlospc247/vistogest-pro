# apps/compras/views.py
from decimal import Decimal
from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.db import transaction
from django.db.models import Prefetch
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils import timezone
from django.views import View
from django.views.generic import ListView, TemplateView, DetailView
from .forms import CompraForm, ItemCompraFormSet, CompraFiltroForm
from .models import Compra, ItemCompra

class CompraTenantMixin(LoginRequiredMixin):
    def dispatch(self, request,*args,**kwargs):
        tenant=getattr(request,"tenant",None)
        if not tenant or getattr(tenant,"schema_name","public")=="public":
            return HttpResponseForbidden("A área de compras só está disponível dentro de uma empresa.")
        return super().dispatch(request,*args,**kwargs)

def total_compra(compra):
    return sum((item.subtotal for item in compra.itens.all()), Decimal("0.00"))

class CompraDashboardView(CompraTenantMixin, TemplateView):
    template_name="compras/dashboard.html"
    def get_context_data(self, **kwargs):
        c=super().get_context_data(**kwargs)
        compras=list(Compra.objects.prefetch_related("itens").select_related("fornecedor").order_by("-data")[:200])
        hoje=timezone.localdate()
        c.update({"title":"Painel de Compras","total_compras":Compra.objects.count(),"compras_hoje":Compra.objects.filter(data__date=hoje).count(),"valor_compras":sum((total_compra(x) for x in compras),Decimal("0.00")),"compras_recentes":compras[:8]})
        return c

class CompraListView(CompraTenantMixin, ListView):
    model=Compra; template_name="compras/compra_list.html"; context_object_name="compras"; paginate_by=25
    def get_queryset(self):
        qs=Compra.objects.select_related("fornecedor").prefetch_related("itens").order_by("-data")
        self.filtro=CompraFiltroForm(self.request.GET or None)
        if self.filtro.is_valid():
            d=self.filtro.cleaned_data
            if d.get("data_inicio"): qs=qs.filter(data__date__gte=d["data_inicio"])
            if d.get("data_fim"): qs=qs.filter(data__date__lte=d["data_fim"])
            if d.get("fornecedor"): qs=qs.filter(fornecedor=d["fornecedor"])
        return qs
    def get_context_data(self, **kwargs):
        c=super().get_context_data(**kwargs)
        c.update(title="Compras", filtro_form=getattr(self,"filtro",CompraFiltroForm()))
        for compra in c["compras"]:
            compra.total_display=total_compra(compra)
        return c

class CompraDetailView(CompraTenantMixin, DetailView):
    model=Compra; template_name="compras/compra_detail.html"; context_object_name="compra"
    def get_queryset(self): return Compra.objects.select_related("fornecedor").prefetch_related("itens__produto")
    def get_context_data(self, **kwargs):
        c=super().get_context_data(**kwargs); c["title"]=f"Compra #{self.object.pk}"; c["total_compra"]=total_compra(self.object); return c

class CompraFormView(CompraTenantMixin, View):
    template_name="compras/compra_form.html"; success_url=reverse_lazy("compras:listar")
    def get_object(self):
        pk=self.kwargs.get("pk")
        return get_object_or_404(Compra,pk=pk) if pk else Compra()
    def render_page(self, form, formset, status=200):
        obj=getattr(self,"object",None)
        context={"form":form,"item_formset":formset,"object":obj,"title":"Editar Compra" if obj and obj.pk else "Registar Compra"}
        return render(self.request,self.template_name,context,status=status)
    def get(self,request,*args,**kwargs):
        self.object=self.get_object(); form=CompraForm(instance=self.object)
        formset=ItemCompraFormSet(instance=self.object,prefix="itens")
        return self.render_page(form,formset)
    def post(self,request,*args,**kwargs):
        self.object=self.get_object(); form=CompraForm(request.POST,instance=self.object)
        formset=ItemCompraFormSet(request.POST,instance=self.object,prefix="itens")
        if form.is_valid() and formset.is_valid():
            with transaction.atomic():
                compra=form.save()
                formset.instance=compra
                formset.save()
            messages.success(request,"Compra guardada com sucesso.")
            return redirect("compras:detalhe",pk=compra.pk)
        return self.render_page(form,formset,400)

class CompraCreateView(CompraFormView):
    pass

class CompraUpdateView(CompraFormView):
    pass

class CompraDeleteView(CompraTenantMixin, View):
    template_name="compras/compra_confirm_delete.html"
    def get(self,request,pk): return render(request,self.template_name,{"compra":get_object_or_404(Compra,pk=pk)})
    def post(self,request,pk):
        compra=get_object_or_404(Compra,pk=pk)
        compra_id=compra.pk
        compra.delete()
        messages.success(request,f"Compra #{compra_id} eliminada.")
        return redirect("compras:listar")
