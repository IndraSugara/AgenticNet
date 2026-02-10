# Agentic AI Network Infrastructure Operator

Sistem AI otonom untuk operasi infrastruktur jaringan menggunakan **LLaMA 3.x** via **Ollama**.

## 🚀 Quick Start

### 1. Install Ollama

Download dan install dari: https://ollama.com/download

### 2. Pull LLaMA 3 Model

```bash
# Untuk model 8B (lebih ringan)
ollama pull llama3:8b

# Atau untuk model 70B (lebih powerful, butuh GPU besar)
ollama pull llama3.3:70b
```

### 3. Setup Environment

```bash
# Copy environment file
cp .env.example .env

# Install dependencies
pip install -r requirements.txt
```

### 4. Jalankan Server

```bash
python main.py
```

Buka browser ke: http://localhost:8000

## 🔁 ODRVA Cycle

Agent mengikuti siklus wajib untuk setiap tugas:

1. **OBSERVE** - Kumpulkan data dan konteks
2. **REASON** - Analisis situasi dan opsi
3. **DECIDE** - Pilih aksi dengan justifikasi transparan
4. **ACT** - Eksekusi dengan hati-hati (dengan risk check)
5. **VERIFY** - Validasi hasil

## 📊 Features

- **Automation & Execution** - Change impact awareness, risk assessment
- **Monitoring & Observability** - Anomaly detection, trend analysis
- **Security & Compliance** - ISO 27001, NIST, CIS Benchmarks
- **Decision Transparency** - Setiap keputusan terdokumentasi

## ⚠️ Prinsip Operasional

- Stabilitas > Kecepatan
- Tidak mengeksekusi perubahan destruktif tanpa validasi
- Menolak aksi jika risiko tinggi dan data tidak cukup

## 🤖 Agentic Workflow API

Sistem mendukung **agentic workflow** untuk eksekusi multi-step tasks secara autonomous.

### Workflow Endpoints

```bash
POST /workflow/create       # Execute workflow
POST /workflow/quick        # Quick mode
GET  /workflow/{id}         # Status
GET  /workflow/list/history # History
WS   /workflow/stream       # Real-time
```

## 🖥️ Infrastructure Monitoring API

Monitor jaringan kantor Anda dengan automated health checks.

### Device Management

```bash
# Tambah device
curl -X POST http://localhost:8000/infra/devices \
  -H "Content-Type: application/json" \
  -d '{"name": "Main Router", "ip": "192.168.1.1", "type": "router"}'

# List semua device
curl http://localhost:8000/infra/devices

# Cek status device
curl http://localhost:8000/infra/devices/dev_0001/status
```

### Monitoring Control

```bash
# Mulai monitoring otomatis
curl -X POST http://localhost:8000/infra/monitor/start

# Stop monitoring
curl -X POST http://localhost:8000/infra/monitor/stop

# Cek semua device sekarang
curl -X POST http://localhost:8000/infra/monitor/check-all
```

### Alerts

```bash
# Lihat alerts aktif
curl http://localhost:8000/infra/alerts

# Summary alerts
curl http://localhost:8000/infra/alerts/summary
```

### Live WebSocket

```javascript
const ws = new WebSocket('ws://localhost:8000/infra/live');
ws.onmessage = (e) => console.parse(e.data));
```

**⚠️ Restart server untuk mengaktifkan fitur baru:**
```bash
python main.py
```
