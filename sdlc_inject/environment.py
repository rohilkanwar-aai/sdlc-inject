"""Environment generation (Docker, monitoring, load testing)."""

from pathlib import Path

import yaml
from jinja2 import Template
from rich.console import Console

from .models import Pattern

console = Console()


def generate_environment(
    pattern: Pattern,
    output_dir: Path,
    include_monitoring: bool = False,
    include_load_generator: bool = False,
) -> None:
    """Generate environment files for a pattern."""
    output_dir.mkdir(parents=True, exist_ok=True)

    # Generate Docker Compose
    if pattern.environment and pattern.environment.docker:
        generate_docker_compose(pattern, output_dir)
    else:
        generate_default_docker(pattern, output_dir)

    # Generate monitoring
    if include_monitoring:
        generate_monitoring(pattern, output_dir)

    # Generate load generator
    if include_load_generator:
        generate_load_generator(pattern, output_dir)

    # Generate README
    generate_readme(pattern, output_dir, include_monitoring, include_load_generator)


def generate_docker_compose(pattern: Pattern, output_dir: Path) -> None:
    """Generate Docker Compose from pattern definition."""
    docker = pattern.environment.docker

    services = {}
    for svc in docker.services:
        service_def = {"container_name": svc.name}

        if svc.image:
            service_def["image"] = svc.image

        if svc.build:
            service_def["build"] = {
                "context": svc.build.context,
                "dockerfile": svc.build.dockerfile,
            }
            if svc.build.args:
                service_def["build"]["args"] = svc.build.args

        if svc.ports:
            service_def["ports"] = svc.ports

        if svc.environment:
            service_def["environment"] = svc.environment

        if svc.volumes:
            service_def["volumes"] = svc.volumes

        if svc.depends_on:
            service_def["depends_on"] = svc.depends_on

        services[svc.name] = service_def

    compose = {
        "version": "3.8",
        "services": services,
        "networks": {
            "default": {
                "name": f"{pattern.id.lower()}-network"
            }
        }
    }

    (output_dir / "docker-compose.yaml").write_text(
        yaml.dump(compose, default_flow_style=False, sort_keys=False)
    )


def generate_default_docker(pattern: Pattern, output_dir: Path) -> None:
    """Generate default Docker setup."""
    compose = f"""version: '3.8'

services:
  app:
    build:
      context: ../target
      dockerfile: Dockerfile
    ports:
      - "8080:8080"
    environment:
      - RUST_LOG=debug
      - PATTERN_ID={pattern.id}
    volumes:
      - ./data:/data

networks:
  default:
    name: {pattern.id.lower()}-network
"""
    (output_dir / "docker-compose.yaml").write_text(compose)

    dockerfile = """FROM rust:1.75 as builder

WORKDIR /app
COPY . .
RUN cargo build --release

FROM debian:bookworm-slim
RUN apt-get update && apt-get install -y ca-certificates && rm -rf /var/lib/apt/lists/*
COPY --from=builder /app/target/release/app /usr/local/bin/
CMD ["app"]
"""
    (output_dir / "Dockerfile").write_text(dockerfile)


def generate_monitoring(pattern: Pattern, output_dir: Path) -> None:
    """Generate monitoring stack configuration."""
    monitoring_dir = output_dir / "monitoring"
    monitoring_dir.mkdir(exist_ok=True)

    # Prometheus config
    prometheus_config = """global:
  scrape_interval: 15s
  evaluation_interval: 15s

scrape_configs:
  - job_name: 'app'
    static_configs:
      - targets: ['app:8080']
"""

    if pattern.environment and pattern.environment.monitoring:
        metrics = pattern.environment.monitoring.prometheus_metrics
        if metrics:
            prometheus_config += "\n# Pattern-specific metrics:\n"
            for m in metrics:
                prometheus_config += f"# - {m}\n"

    (monitoring_dir / "prometheus.yml").write_text(prometheus_config)

    # Grafana datasources
    grafana_dir = monitoring_dir / "grafana"
    grafana_dir.mkdir(exist_ok=True)

    datasources = """apiVersion: 1

datasources:
  - name: Prometheus
    type: prometheus
    access: proxy
    url: http://prometheus:9090
    isDefault: true
"""
    (grafana_dir / "datasources.yml").write_text(datasources)

    # Monitoring compose
    network_name = pattern.id.lower()
    monitoring_compose = f"""version: '3.8'

services:
  prometheus:
    image: prom/prometheus:v2.45.0
    volumes:
      - ./monitoring/prometheus.yml:/etc/prometheus/prometheus.yml
    ports:
      - "9090:9090"
    networks:
      - {network_name}-network

  grafana:
    image: grafana/grafana:10.0.0
    volumes:
      - ./monitoring/grafana:/etc/grafana/provisioning/datasources
    ports:
      - "3000:3000"
    environment:
      - GF_SECURITY_ADMIN_PASSWORD=admin
    depends_on:
      - prometheus
    networks:
      - {network_name}-network

networks:
  {network_name}-network:
    external: true
"""
    (output_dir / "docker-compose.monitoring.yaml").write_text(monitoring_compose)


def generate_load_generator(pattern: Pattern, output_dir: Path) -> None:
    """Generate load testing configuration."""
    loadgen_dir = output_dir / "loadgen"
    loadgen_dir.mkdir(exist_ok=True)

    # Determine tool and config
    tool = "k6"
    config = {}

    if pattern.environment and pattern.environment.load_generator:
        tool = pattern.environment.load_generator.tool
        config = pattern.environment.load_generator.config

    vus = config.get("concurrent_users", 10)
    duration = config.get("duration", "5m")

    if tool == "k6":
        script = f"""import http from 'k6/http';
import {{ check, sleep }} from 'k6';

export const options = {{
  vus: {vus},
  duration: '{duration}',
}};

export default function () {{
  const url = __ENV.TARGET_URL || 'http://localhost:8080';

  const response = http.get(url + '/health');
  check(response, {{
    'status is 200': (r) => r.status === 200,
  }});

  sleep(1);
}}
"""
        (loadgen_dir / "script.js").write_text(script)

        dockerfile = """FROM grafana/k6:0.47.0
COPY script.js /scripts/script.js
CMD ["run", "/scripts/script.js"]
"""
        (loadgen_dir / "Dockerfile").write_text(dockerfile)

    elif tool == "locust":
        script = f"""from locust import HttpUser, task, between

class LoadTestUser(HttpUser):
    wait_time = between(1, 2)

    @task
    def health_check(self):
        self.client.get("/health")
"""
        (loadgen_dir / "locustfile.py").write_text(script)

        dockerfile = """FROM locustio/locust
COPY locustfile.py /home/locust/locustfile.py
"""
        (loadgen_dir / "Dockerfile").write_text(dockerfile)

    # Load generator compose
    network_name = pattern.id.lower()
    loadgen_compose = f"""version: '3.8'

services:
  loadgen:
    build:
      context: ./loadgen
    environment:
      - TARGET_URL=http://app:8080
    networks:
      - {network_name}-network

networks:
  {network_name}-network:
    external: true
"""
    (output_dir / "docker-compose.loadgen.yaml").write_text(loadgen_compose)


def generate_readme(
    pattern: Pattern,
    output_dir: Path,
    include_monitoring: bool,
    include_load_generator: bool,
) -> None:
    """Generate README for environment."""
    trigger_conditions = ""
    if pattern.trigger:
        for cond in pattern.trigger.conditions:
            trigger_conditions += f"- {cond.description}\n"

    readme = f"""# Environment Setup for {pattern.id}

## Pattern: {pattern.name}

{pattern.description[:500]}

## Quick Start

1. Start the application:
   ```bash
   docker-compose up -d
   ```
"""

    if include_monitoring:
        readme += """
2. Start monitoring:
   ```bash
   docker-compose -f docker-compose.monitoring.yaml up -d
   ```
   - Prometheus: http://localhost:9090
   - Grafana: http://localhost:3000 (admin/admin)
"""

    if include_load_generator:
        readme += """
3. Run load test:
   ```bash
   docker-compose -f docker-compose.loadgen.yaml up
   ```
"""

    readme += f"""
## Trigger Conditions

{trigger_conditions or "See pattern documentation"}

## Stopping

```bash
docker-compose down
"""

    if include_monitoring:
        readme += "docker-compose -f docker-compose.monitoring.yaml down\n"

    if include_load_generator:
        readme += "docker-compose -f docker-compose.loadgen.yaml down\n"

    readme += """```

## Files

- `docker-compose.yaml` - Main application services
"""

    if include_monitoring:
        readme += "- `docker-compose.monitoring.yaml` - Prometheus + Grafana\n"
        readme += "- `monitoring/` - Monitoring configuration\n"

    if include_load_generator:
        readme += "- `docker-compose.loadgen.yaml` - Load generator\n"
        readme += "- `loadgen/` - Load test scripts\n"

    (output_dir / "README.md").write_text(readme)
