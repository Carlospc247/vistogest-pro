"""Helpers to migrate the existing ClienteSite SHA-256 passwords safely.

Integrate these helpers in the current portal register/login/password-reset views.
Never use a single static password shared by all customers.
"""
import hashlib
import hmac
import secrets

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.core.mail import send_mail
from django.core.signing import TimestampSigner
from django.urls import reverse


def definir_senha_portal(cliente_site, senha_em_texto):
    if len(senha_em_texto or "") < 10:
        raise ValueError("A palavra-passe deve ter pelo menos 10 caracteres.")
    cliente_site.senha_hash = make_password(senha_em_texto)
    cliente_site.save(update_fields=["senha_hash", "updated_at"])


def verificar_senha_portal(cliente_site, senha_em_texto):
    """Accept Django hashes; upgrade matching legacy 64-character SHA-256 hashes."""
    armazenada = cliente_site.senha_hash or ""
    if not armazenada or not senha_em_texto:
        return False
    if armazenada.startswith(("pbkdf2_", "argon2$", "bcrypt", "scrypt$")):
        return check_password(senha_em_texto, armazenada)
    legado = hashlib.sha256(senha_em_texto.encode("utf-8")).hexdigest()
    if len(armazenada) == 64 and hmac.compare_digest(legado, armazenada):
        definir_senha_portal(cliente_site, senha_em_texto)
        return True
    return False


def gerar_senha_temporaria():
    """Unique random one-time password; deliver only over an approved private channel."""
    return secrets.token_urlsafe(18)


def enviar_convite_acesso_portal(cliente_interno, request):
    """Create/link a ClienteSite account and email a unique, signed password-setup link.

    Existing users with a password keep their current credentials; this helper never
    silently resets an established customer's password.
    """
    from apps.site.models import ClienteSite

    email = (getattr(cliente_interno, "email", "") or "").strip().lower()
    if not email:
        raise ValueError("O cliente precisa de email para activar o acesso ao portal.")
    nome = (getattr(cliente_interno, "nome_exibicao", None)
            or getattr(cliente_interno, "nome_completo", str(cliente_interno)))
    telefone = getattr(cliente_interno, "telefone", "") or ""
    pessoa_juridica = getattr(cliente_interno, "tipo_cliente", "") == "pessoa_juridica"
    portal, criado = ClienteSite.objects.get_or_create(
        email=email,
        defaults={"nome": nome, "telefone": telefone,
                  "pessoa_juridica": pessoa_juridica, "senha_hash": "", "ativo": True},
    )
    if not criado and portal.senha_hash:
        return {"criado": False, "convite_enviado": False, "motivo": "conta_ja_tem_senha", "cliente_site_id": portal.pk}
    if not portal.ativo:
        portal.ativo = True
        portal.save(update_fields=["ativo", "updated_at"])
    signer = TimestampSigner(salt="site-cliente-recuperacao-senha")
    token = signer.sign(f"{portal.pk}:{portal.senha_hash}")
    url = request.build_absolute_uri(reverse("site:cliente_redefinir_senha", kwargs={"token": token}))
    assunto = "Activar o acesso ao portal do cliente"
    corpo = (
        f"Olá, {portal.nome}.\n\n"
        "A empresa criou um acesso ao seu portal. Defina uma senha individual através do link abaixo.\n\n"
        f"{url}\n\nEste link expira em 1 hora e só pode ser usado uma vez.\n"
        "Se não estava à espera desta mensagem, contacte a empresa."
    )
    send_mail(
        assunto, corpo, getattr(settings, "DEFAULT_FROM_EMAIL", None),
        [portal.email], fail_silently=False,
    )
    return {"criado": criado, "convite_enviado": True, "cliente_site_id": portal.pk}
