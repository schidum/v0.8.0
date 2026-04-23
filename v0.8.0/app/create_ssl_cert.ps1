# create_ssl.ps1 - Create clean SSL certificates (cert.pem + key.pem)

Write-Host "=== Creating SSL certificates for localhost ===" -ForegroundColor Cyan

# Create certs folder
New-Item -ItemType Directory -Path certs -Force | Out-Null

Write-Host "Generating certificate..." -ForegroundColor Yellow

# Create self-signed certificate
$cert = New-SelfSignedCertificate `
    -DnsName "localhost" `
    -CertStoreLocation "cert:\CurrentUser\My" `
    -KeyExportPolicy Exportable `
    -Provider "Microsoft Enhanced RSA and AES Cryptographic Provider"

# Temporary password
$password = ConvertTo-SecureString -String "123456" -Force -AsPlainText

# Export to temporary pfx
Export-PfxCertificate -Cert $cert -FilePath "certs\temp.pfx" -Password $password | Out-Null

# Extract cert.pem (certificate only)
openssl pkcs12 -in certs\temp.pfx -out certs\cert.pem -clcerts -nokeys -passin pass:123456

# Extract key.pem (private key only)
openssl pkcs12 -in certs\temp.pfx -out certs\key.pem -nocerts -nodes -passin pass:123456

# Remove temporary file
Remove-Item "certs\temp.pfx" -Force

Write-Host "SUCCESS!" -ForegroundColor Green
Write-Host "Certificates created in folder: certs" -ForegroundColor Green
Write-Host ""
Write-Host "Files:" -ForegroundColor Yellow
Write-Host "   - certs\cert.pem" -ForegroundColor Yellow
Write-Host "   - certs\key.pem" -ForegroundColor Yellow
Write-Host ""
Write-Host "Run the server with:" -ForegroundColor Cyan
Write-Host "uvicorn app.main:app --host 127.0.0.1 --port 8443 --ssl-keyfile certs\key.pem --ssl-certfile certs\cert.pem" -ForegroundColor White