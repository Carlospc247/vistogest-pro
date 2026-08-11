# development.py
from .base import *

DEBUG = True
SECRET_KEY = "-----BEGIN PRIVATE KEY-----\nMIIEvwIBADANBgkqhkiG9w0BAQEFAASCBKkwggSlAgEAAoIBAQCoPEfdIEbUmtv+\nzDjhc4t6hP0i6vskHvMH6Ye3iRpflCFJXvyk7jxCErZ76KFL8R7wHcnKmot9oHYf\nOQ5x1/tNVld3DC2NPho0LkkhFoiN4+Ary9GY1eBKf9+t8CFc7vlZBphnMHqQgyDJ\nq4SXJdm4PecipzMqX1TUu7dmS05tM0WsWSd+sx0BEgLwDQwpLN/74ReylgI7ygWA\ndQC55Q7iLGmNuJeohBFWtUFcoDR2732WYi7008HvN8+d1fBQNfSqEwr8FLUKGtte\nEMzERBjLvCOoW423VoVCgtyLjiJXqvNTMkzA6J0SzJ1Icktr5+HPBdtjt+tqZtV/\nW5Ho+7ezAgMBAAECggEABx9KMY/Yv85withtfgnsuTqhFtXY3P4cbtTRpJD+11YH\nlLobOwZE8c0mAZfnIDZsh2DTdqrVRfPBnG/Hb0VkA7GokUcoNIcRB+1/thFkpZEk\nn+YIkQ5Y6P6B4zS7zNnnH4A6en/gaHbMsAz9V4LINVcVjm+CqIQRrNHnoUKF5vSH\nkJg7quHIVNarNsqrYKhkVTDO68wMconTPJAgu4ti6xgGAIMQa/iBfDOCooLYfJXI\nclO5DuuIenmgt6bKAihLWVB7XWNNt6LvfYqHVaOP1eByRT1O6X0Ujh6JboMijGoA\nRcyjCVtSa/yrlLoO+mn6kXNBVuC1dq5tZ21194OBJQKBgQDlq5fenGs89Dx49Yzu\nFx/YGVw6E5ZwkwqY/3itcTOxTVtK7PTx3t0Ly8g3cAxx391PatHs1m3DlytUYXSh\nqIcbm51LuGfkMidkTQXhqdyap3On7hsROT/8XBZ5lzFEaVc2NIH2Z7LViTZaD9/i\n9vOFpREUF2SlQC1rHvMe0c3ufwKBgQC7ha/eKhIQEJ38/s09FrtT3FLwHHyd7ENv\na68dea03hbCtpDfdyqyP1aoFQzgu91/1yKK4/ncGySkc9RoPmBuWDyrmiWowHeBy\nLbC8rSrf3DH0xGTrJEPVsg1kGnayVFNmCVZAezll+xG2Si6xTkBv9k1IpZdKdy/D\n+6mxg0ZEzQKBgQCYB4xSaYx7Htlg4HpXqKsFq1PnhcvR3SPov0Os3ABx31kNMem6\nqeH8yvpP6DX0s1GWHomzkwW5sTmXc6N2104IMmxfEUSEQ8bbmDjKdlx3a10dznnQ\nXutCK9scxb5xIKIAWaWl7GLvAxMdbuCvJvVwhCHYANw4n1DxVd1ti0gcFQKBgQCt\n6HbIuAWWZoLOvdPDgtBqHpvAWPrtTs7fh2OZF14gbtkCwJibFbphjosmZEe3ru2M\nuOzIWh4y6d46H8lyiuOSkDB+KxSS2TJtUZhl8scfY0vlLzpUpIZQqdcnbi+EhRXv\nPFuEY4NA485yW2vgPa0e6LKV3BRqGAzxWfTvTsqdRQKBgQDb8RgOMu6Sh1IdYFlP\nk+sZ0+uuHPbbFxtfwQi9+NV//TpJyb/2nIgMjcR0/EoTDe4zSr7kVrdiThj2yvBY\nA7HjbeEuGS8r2NbwV79l5g1ql7N8+8B5rjADbdL13OvkjiagasHVRKB3E/Vb3nCd\ngQ5bxINCvmaAQsQlXY3si0PxKg==\n-----END PRIVATE KEY-----\n"
ALLOWED_HOSTS = ['localhost', '127.0.0.1', '.sotarq.local', '.localhost']

DATABASES = {
    "default": {
        "ENGINE": "django_tenants.postgresql_backend",
        "NAME": "sotarq_vendor",
        "USER": "postgres",
        "PASSWORD": "postgres",
        "HOST": "localhost",
        "PORT": "5432",
    }
}

STATICFILES_STORAGE = "whitenoise.storage.CompressedManifestStaticFilesStorage"

# Em desenvolvimento, o email vai para o console
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'
# Em settings.py
CACHES = {
    'default': {
        'BACKEND': 'django.core.cache.backends.locmem.LocMemCache',
    }
}