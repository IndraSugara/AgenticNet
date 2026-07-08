# open-firewall-snmp.ps1
# Jalankan sebagai Administrator!
# Klik kanan file ini -> Run with PowerShell (as Administrator)

Write-Host "Membuka port UDP 162 (SNMP Trap) di Windows Firewall..." -ForegroundColor Cyan

# Hapus rule lama kalau ada
netsh advfirewall firewall delete rule name="SNMP Trap In" | Out-Null

# Buat rule baru - izinkan UDP 162 dari semua IP
netsh advfirewall firewall add rule `
    name="SNMP Trap In" `
    dir=in `
    action=allow `
    protocol=UDP `
    localport=162 `
    description="Allow SNMP Trap from network devices to Docker container"

Write-Host ""
Write-Host "✅ Firewall rule berhasil dibuat!" -ForegroundColor Green
Write-Host "   Port UDP 162 sekarang terbuka untuk menerima SNMP trap." -ForegroundColor Green
Write-Host ""
Write-Host "Verifikasi rule:" -ForegroundColor Yellow
netsh advfirewall firewall show rule name="SNMP Trap In"
