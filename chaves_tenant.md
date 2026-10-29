python -c "from cryptography.hazmat.primitives.asymmetric import rsa; from cryptography.hazmat.primitives import serialization as s; k=rsa.generate_private_key(public_exponent=65537,key_size=2048); open('chave_privada.pem','wb').write(k.private_bytes(s.Encoding.PEM,s.PrivateFormat.PKCS8,s.NoEncryption())); open('chave_publica.pem','wb').write(k.public_key().public_bytes(s.Encoding.PEM,s.PublicFormat.SubjectPublicKeyInfo)); print('Ok. chave_privada.pem e chave_publica.pem salvas na raíz do projeto.')"

# apagaras chaves da raiz para não ficarem expostas
Remove-Item .\chave_privada.pem, .\chave_publica.pem

# confirmar a existencia de chaves:
psql -U postgres -d sotarq_vendor -c "SELECT nif_contribuinte, left(chave_contribuinte_privada, 20) AS inicio_cifrado, length(chave_contribuinte_privada) AS tamanho FROM mundoemaquinas.fiscal_assinaturadigital;"