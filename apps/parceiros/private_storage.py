"""Storage proxy that intentionally refuses public URLs for partner evidence files.

Define STORAGES['partner_private'] to a private S3-compatible/bucket storage in the
project settings. Never point it to a public-read bucket or the ordinary public media
storage. Downloads must go through PartnerMessageAttachmentView after authorization.
"""
from django.conf import settings
from django.core.files.storage import Storage, storages
from django.utils.deconstruct import deconstructible


@deconstructible
class PartnerPrivateStorage(Storage):
    def _backend(self):
        alias = getattr(settings, "PARTNER_PRIVATE_STORAGE_ALIAS", "partner_private")
        return storages[alias]

    def _open(self, name, mode="rb"):
        return self._backend().open(name, mode)

    def _save(self, name, content):
        return self._backend().save(name, content)

    def exists(self, name):
        return self._backend().exists(name)

    def delete(self, name):
        return self._backend().delete(name)

    def size(self, name):
        return self._backend().size(name)

    def path(self, name):
        return self._backend().path(name)

    def url(self, name):
        raise ValueError("Ficheiros de parceiros não têm URL público; use a rota autenticada de download.")
