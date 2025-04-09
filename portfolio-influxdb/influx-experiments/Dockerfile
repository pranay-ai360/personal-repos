# Dockerfile
FROM influxdb:2.6
# Expose the default InfluxDB port
EXPOSE 8086
# Optionally, you can copy custom configuration files here.
# COPY influxdb.conf /etc/influxdb/influxdb.conf

WORKDIR /app

COPY . .

CMD ["influxd"]