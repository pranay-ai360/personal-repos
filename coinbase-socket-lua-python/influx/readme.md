docker run -d -p 8086:8086 \
  -v "$PWD/data:/var/lib/influxdb2" \
  -v "$PWD/config:/etc/influxdb2" \
  -e DOCKER_INFLUXDB_INIT_MODE=setup \
  -e DOCKER_INFLUXDB_INIT_USERNAME=un \
  -e DOCKER_INFLUXDB_INIT_PASSWORD=pass \
  -e DOCKER_INFLUXDB_INIT_ORG=demo \
  -e DOCKER_INFLUXDB_INIT_BUCKET=demo \
  influxdb:2
