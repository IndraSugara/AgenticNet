FROM ubuntu:22.04

RUN apt-get update && apt-get install -y \
    snmptrapd \
    snmp \
    snmp-mibs-downloader \
    netcat-openbsd \
    && rm -rf /var/lib/apt/lists/*

# Copy config & handler
COPY snmptrapd.conf /etc/snmp/snmptrapd.conf
COPY handler.sh /usr/local/bin/handler.sh
RUN chmod +x /usr/local/bin/handler.sh

# Run snmptrapd in foreground, all communities, log to stdout
CMD ["snmptrapd", "-f", "-Lo", "-c", "/etc/snmp/snmptrapd.conf", "udp:162"]
