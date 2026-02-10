// Test script to verify API endpoint
fetch('http://localhost:8000/monitoring/metrics/detailed')
  .then(r => r.json())
  .then(data => {
    console.log('API Response:', data);
    if (data.metrics && data.metrics.interfaces) {
      console.log('Interfaces found:', data.metrics.interfaces.length);
      data.metrics.interfaces.forEach(iface => {
        console.log(`- ${iface.name}: ${iface.is_up ? 'UP' : 'DOWN'}, sent: ${iface.bytes_sent_mb}MB, recv: ${iface.bytes_recv_mb}MB`);
      });
    }
  })
  .catch(e => console.error('API Error:', e));
