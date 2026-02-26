# apps/fiscal/services/audit_service.py


class AuditLogService:
    @staticmethod
    def registrar(user, acao, empresa_id, ip):
        from apps.fiscal.models import AuditLog
        AuditLog.objects.create(
            user=user,
            acao=acao,
            empresa_id=empresa_id,
            ip_address=ip
        )
