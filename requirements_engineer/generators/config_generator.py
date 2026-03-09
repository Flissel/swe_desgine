"""
Config & Environment Generator - Generates deployment configuration templates.

Produces:
- .env.example with required environment variables
- docker-compose.yml for local development
- Dockerfile template for backend (language-aware)
- Kubernetes manifests (deployment, service, configmap)
- GitHub Actions CI/CD pipeline (language-aware)

Programmatic — adapts to backend_language from TechStack.
Supports: Python, Node.js/TypeScript, Go, Java, Rust, C#.
"""

import json
import re
from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from dataclasses_json import dataclass_json
from pathlib import Path
from datetime import datetime


# ─── Language Lookup Tables ────────────────────────────────────

# Normalize backend_language aliases
LANG_ALIASES = {
    "typescript": "node.js", "javascript": "node.js", "nodejs": "node.js",
    "golang": "go", "csharp": "c#", "dotnet": "c#", ".net": "c#",
    "python3": "python", "py": "python",
}

# Language → Docker base image template
DOCKER_IMAGES = {
    "python":  "python:{version}-slim",
    "node.js": "node:{version}-alpine",
    "go":      "golang:{version}-alpine",
    "java":    "eclipse-temurin:{version}-jdk-alpine",
    "rust":    "rust:{version}-slim",
    "c#":      "mcr.microsoft.com/dotnet/sdk:{version}",
}

# Runtime-only images for multi-stage builds
DOCKER_RUNTIME_IMAGES = {
    "python":  "python:{version}-slim",
    "node.js": "node:{version}-alpine",
    "go":      "alpine:3.19",
    "java":    "eclipse-temurin:{version}-jre-alpine",
    "rust":    "debian:bookworm-slim",
    "c#":      "mcr.microsoft.com/dotnet/aspnet:{version}",
}

# Language → default port
DEFAULT_PORTS = {
    "python": 8000, "node.js": 3000, "go": 8080,
    "java": 8080, "rust": 8080, "c#": 5000,
}

# Framework → specific port override
FRAMEWORK_PORTS = {
    "fastapi": 8000, "django": 8000, "flask": 5000, "litestar": 8000,
    "express": 3000, "nestjs": 3000, "koa": 3000, "hono": 3000, "fastify": 3000,
    "gin": 8080, "fiber": 3000, "echo": 8080, "chi": 8080,
    "spring": 8080, "spring boot": 8080, "quarkus": 8080, "micronaut": 8080,
    "actix": 8080, "axum": 8080, "rocket": 8000,
    "asp.net": 5000,
}

# Default version fallbacks
DEFAULT_VERSIONS = {
    "python": "3.12", "node.js": "22", "go": "1.23",
    "java": "21", "rust": "1.77", "c#": "8.0",
}

# Whether language needs multi-stage build (compiled vs interpreted)
COMPILED_LANGS = {"go", "rust", "java", "c#"}

# Language → install / build / start / test / lint commands
LANG_COMMANDS = {
    "python": {
        "install": "pip install --no-cache-dir -r requirements.txt",
        "build": None,
        "start_cmd": '["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "{port}"]',
        "start_shell": "uvicorn app.main:app --host 0.0.0.0 --port {port}",
        "test": "pytest",
        "test_unit": "pytest tests/unit",
        "test_integration": "pytest tests/integration",
        "lint": "ruff check .",
        "setup_action": "actions/setup-python@v5",
        "setup_key": "python-version",
        "cache": "pip",
        "copy_deps": "requirements.txt",
        "copy_build": ".",
        "workdir": "/app",
        "user": "nobody",
        "env_key": "APP_ENV",
    },
    "node.js": {
        "install": "npm ci",
        "build": "npm run build",
        "start_cmd": '["node", "dist/main.js"]',
        "start_shell": "node dist/main.js",
        "test": "npm run test",
        "test_unit": "npm run test:unit",
        "test_integration": "npm run test:integration",
        "lint": "npm run lint",
        "setup_action": "actions/setup-node@v4",
        "setup_key": "node-version",
        "cache": "npm",
        "copy_deps": "package*.json",
        "copy_build": "dist",
        "workdir": "/app",
        "user": "node",
        "env_key": "NODE_ENV",
    },
    "go": {
        "install": "go mod download",
        "build": "CGO_ENABLED=0 go build -ldflags='-s -w' -o /app/server ./cmd/server",
        "start_cmd": '["/app/server"]',
        "start_shell": "/app/server",
        "test": "go test ./...",
        "test_unit": "go test ./...",
        "test_integration": "go test -tags=integration ./...",
        "lint": "golangci-lint run",
        "setup_action": "actions/setup-go@v5",
        "setup_key": "go-version",
        "cache": None,
        "copy_deps": "go.mod go.sum",
        "copy_build": None,  # binary only
        "workdir": "/app",
        "user": "nonroot",
        "env_key": "APP_ENV",
    },
    "java": {
        "install": None,
        "build": "mvn package -DskipTests",
        "start_cmd": '["java", "-jar", "/app/app.jar"]',
        "start_shell": "java -jar /app/app.jar",
        "test": "mvn test",
        "test_unit": "mvn test",
        "test_integration": "mvn verify -Pfailsafe",
        "lint": "mvn checkstyle:check",
        "setup_action": "actions/setup-java@v4",
        "setup_key": "java-version",
        "cache": "maven",
        "copy_deps": "pom.xml",
        "copy_build": "target/*.jar",
        "workdir": "/app",
        "user": "nobody",
        "env_key": "SPRING_PROFILES_ACTIVE",
    },
    "rust": {
        "install": None,
        "build": "cargo build --release",
        "start_cmd": '["/app/server"]',
        "start_shell": "/app/server",
        "test": "cargo test",
        "test_unit": "cargo test",
        "test_integration": "cargo test --test '*'",
        "lint": "cargo clippy -- -D warnings",
        "setup_action": "dtolnay/rust-toolchain@stable",
        "setup_key": None,
        "cache": None,
        "copy_deps": "Cargo.toml Cargo.lock",
        "copy_build": None,  # binary only
        "workdir": "/app",
        "user": "nonroot",
        "env_key": "APP_ENV",
    },
    "c#": {
        "install": "dotnet restore",
        "build": "dotnet publish -c Release -o /app/publish",
        "start_cmd": '["dotnet", "/app/App.dll"]',
        "start_shell": "dotnet /app/App.dll",
        "test": "dotnet test",
        "test_unit": "dotnet test",
        "test_integration": "dotnet test --filter Category=Integration",
        "lint": "dotnet format --verify-no-changes",
        "setup_action": "actions/setup-dotnet@v4",
        "setup_key": "dotnet-version",
        "cache": None,
        "copy_deps": "*.csproj",
        "copy_build": "publish",
        "workdir": "/app",
        "user": "app",
        "env_key": "ASPNETCORE_ENVIRONMENT",
    },
}


@dataclass_json
@dataclass
class InfraConfig:
    """Complete infrastructure configuration."""
    project_name: str
    env_vars: Dict[str, str] = field(default_factory=dict)
    docker_compose: str = ""
    dockerfile: str = ""
    k8s_deployment: str = ""
    k8s_service: str = ""
    k8s_configmap: str = ""
    ci_pipeline: str = ""


def _to_snake_case(name: str) -> str:
    """Convert PascalCase/camelCase to snake_case."""
    s1 = re.sub(r'(.)([A-Z][a-z]+)', r'\1_\2', name)
    s2 = re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', s1)
    return s2.lower().replace(' ', '_').replace('-', '_')


class ConfigGenerator:
    """Generates infrastructure configuration from tech stack and project data."""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.infra_config: Optional[InfraConfig] = None

    async def initialize(self):
        """No async init needed for programmatic generator."""
        pass

    # ─── Helpers ──────────────────────────────────────────────

    def _detect_lang(self, ts: dict) -> str:
        """Normalize backend language to lookup key.

        Handles version-suffixed values like "Node.js 20.15.1" -> "node.js".
        """
        raw = ts.get("backend_language", "node.js").lower().strip()
        # Strip version number (e.g. "node.js 20.15.1" -> "node.js")
        raw = re.sub(r'\s+[\d][\d.]*$', '', raw)
        return LANG_ALIASES.get(raw, raw)

    def _resolve_port(self, ts: dict) -> int:
        """Get port from framework, then language, then default 3000."""
        fw = re.sub(r'\s+[\d][\d.]*$', '', ts.get("backend_framework", "").lower().strip())
        lang = self._detect_lang(ts)
        return FRAMEWORK_PORTS.get(fw, DEFAULT_PORTS.get(lang, 3000))

    def _get_version(self, ts: dict, lang: str) -> str:
        """Get major version from TechStack versions dict."""
        versions = ts.get("versions", {})
        # Try exact key match first
        for key, val in versions.items():
            k = key.lower()
            if k == lang or k in lang or lang in k:
                return str(val).split(".")[0] if "." in str(val) else str(val)
        return DEFAULT_VERSIONS.get(lang, "latest")

    def _get_cmds(self, lang: str) -> dict:
        """Get command set for language, fallback to node.js."""
        return LANG_COMMANDS.get(lang, LANG_COMMANDS["node.js"])

    # ─── Main entry ──────────────────────────────────────────

    def generate_config(self, tech_stack_dict: dict, api_endpoints: list = None,
                        data_dict_entities: list = None, project_name: str = "") -> InfraConfig:
        """Generate all infrastructure configuration files."""
        slug = _to_snake_case(project_name) if project_name else "app"
        ts = tech_stack_dict or {}

        env_vars = self._generate_env_vars(ts, slug)
        docker_compose = self._generate_docker_compose(ts, slug)
        dockerfile = self._generate_dockerfile(ts, slug)
        port = self._resolve_port(ts)
        k8s_deployment = self._generate_k8s_deployment(ts, slug, port)
        k8s_service = self._generate_k8s_service(slug, port)
        k8s_configmap = self._generate_k8s_configmap(ts, slug, env_vars)
        ci_pipeline = self._generate_ci_pipeline(ts, slug)

        self.infra_config = InfraConfig(
            project_name=project_name,
            env_vars=env_vars,
            docker_compose=docker_compose,
            dockerfile=dockerfile,
            k8s_deployment=k8s_deployment,
            k8s_service=k8s_service,
            k8s_configmap=k8s_configmap,
            ci_pipeline=ci_pipeline,
        )
        return self.infra_config

    # ─── Env vars ──────────────────────────────────────────────

    def _generate_env_vars(self, ts: dict, slug: str) -> Dict[str, str]:
        """Generate environment variables based on tech stack."""
        lang = self._detect_lang(ts)
        cmds = self._get_cmds(lang)
        port = self._resolve_port(ts)

        env = {
            "# Application": "",
            cmds["env_key"]: "development",
            "PORT": str(port),
            "APP_NAME": slug,
            "LOG_LEVEL": "info",
        }

        # Database
        db = ts.get("primary_database", "").lower()
        if "postgres" in db:
            env["# Database"] = ""
            env["DB_HOST"] = "localhost"
            env["DB_PORT"] = "5432"
            env["DB_NAME"] = slug
            env["DB_USER"] = "postgres"
            env["DB_PASSWORD"] = "changeme"
            env["DATABASE_URL"] = f"postgresql://${{DB_USER}}:${{DB_PASSWORD}}@${{DB_HOST}}:${{DB_PORT}}/${{DB_NAME}}"
        elif "mysql" in db or "maria" in db:
            env["# Database"] = ""
            env["DB_HOST"] = "localhost"
            env["DB_PORT"] = "3306"
            env["DB_NAME"] = slug
            env["DB_USER"] = "root"
            env["DB_PASSWORD"] = "changeme"
            env["DATABASE_URL"] = f"mysql://${{DB_USER}}:${{DB_PASSWORD}}@${{DB_HOST}}:${{DB_PORT}}/${{DB_NAME}}"
        elif "mongo" in db:
            env["# Database"] = ""
            env["MONGODB_URI"] = f"mongodb://localhost:27017/{slug}"

        # Cache
        cache = ts.get("cache_layer", "").lower()
        if "redis" in cache:
            env["# Redis"] = ""
            env["REDIS_HOST"] = "localhost"
            env["REDIS_PORT"] = "6379"
            env["REDIS_URL"] = "redis://${REDIS_HOST}:${REDIS_PORT}"

        # Message queue
        mq = ts.get("message_queue", "").lower()
        if "kafka" in mq:
            env["# Kafka"] = ""
            env["KAFKA_BROKERS"] = "localhost:9092"
            env["KAFKA_CLIENT_ID"] = slug
            env["KAFKA_GROUP_ID"] = f"{slug}-consumer"
        elif "rabbit" in mq:
            env["# RabbitMQ"] = ""
            env["RABBITMQ_URL"] = "amqp://guest:guest@localhost:5672"

        # Auth
        env["# Authentication"] = ""
        env["JWT_SECRET"] = "your-secret-key-change-in-production"
        env["JWT_EXPIRY"] = "3600"
        env["JWT_REFRESH_EXPIRY"] = "604800"

        # API gateway
        gw = ts.get("api_gateway", "").lower()
        if "kong" in gw:
            env["# API Gateway"] = ""
            env["KONG_ADMIN_URL"] = "http://localhost:8001"

        # External services
        env["# External Services"] = ""
        env["SMS_PROVIDER_API_KEY"] = ""
        env["SMS_PROVIDER_URL"] = ""
        env["PUSH_NOTIFICATION_KEY"] = ""
        env["STORAGE_BUCKET"] = f"{slug}-uploads"

        return env

    # ─── Docker Compose ───────────────────────────────────────

    def _generate_docker_compose(self, ts: dict, slug: str) -> str:
        """Generate docker-compose.yml for local development."""
        services = {}

        # PostgreSQL
        db = ts.get("primary_database", "").lower()
        db_version = ts.get("versions", {}).get("PostgreSQL", "16")
        if "postgres" in db:
            services["postgres"] = f"""  postgres:
    image: postgres:{db_version}-alpine
    environment:
      POSTGRES_DB: {slug}
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD: changeme
    ports:
      - "5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./data/schema.sql:/docker-entrypoint-initdb.d/01-schema.sql"""
        elif "mysql" in db or "maria" in db:
            mysql_version = ts.get("versions", {}).get("MySQL", "8.0")
            services["mysql"] = f"""  mysql:
    image: mysql:{mysql_version}
    environment:
      MYSQL_DATABASE: {slug}
      MYSQL_ROOT_PASSWORD: changeme
    ports:
      - "3306:3306"
    volumes:
      - mysql_data:/var/lib/mysql"""
        elif "mongo" in db:
            mongo_version = ts.get("versions", {}).get("MongoDB", "7.0")
            services["mongodb"] = f"""  mongodb:
    image: mongo:{mongo_version}
    ports:
      - "27017:27017"
    volumes:
      - mongo_data:/data/db"""

        # Redis
        cache = ts.get("cache_layer", "").lower()
        redis_version = ts.get("versions", {}).get("Redis", "7.2")
        if "redis" in cache:
            services["redis"] = f"""  redis:
    image: redis:{redis_version}-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data"""

        # Kafka + Zookeeper
        mq = ts.get("message_queue", "").lower()
        if "kafka" in mq:
            services["zookeeper"] = """  zookeeper:
    image: confluentinc/cp-zookeeper:7.6.0
    environment:
      ZOOKEEPER_CLIENT_PORT: 2181
    ports:
      - "2181:2181\""""
            services["kafka"] = """  kafka:
    image: confluentinc/cp-kafka:7.6.0
    depends_on:
      - zookeeper
    environment:
      KAFKA_BROKER_ID: 1
      KAFKA_ZOOKEEPER_CONNECT: zookeeper:2181
      KAFKA_ADVERTISED_LISTENERS: PLAINTEXT://localhost:9092
      KAFKA_OFFSETS_TOPIC_REPLICATION_FACTOR: 1
    ports:
      - "9092:9092\""""

        # Kong
        gw = ts.get("api_gateway", "").lower()
        if "kong" in gw:
            services["kong"] = """  kong:
    image: kong:3.7-alpine
    environment:
      KONG_DATABASE: "off"
      KONG_PROXY_ACCESS_LOG: /dev/stdout
      KONG_ADMIN_ACCESS_LOG: /dev/stdout
      KONG_PROXY_ERROR_LOG: /dev/stderr
      KONG_ADMIN_ERROR_LOG: /dev/stderr
      KONG_ADMIN_LISTEN: "0.0.0.0:8001"
    ports:
      - "8000:8000"
      - "8001:8001\""""

        # Build compose file
        lines = [
            f"# Docker Compose for {slug} local development",
            f"# Generated: {datetime.now().isoformat()}",
            "",
            "services:",
        ]
        for svc_yaml in services.values():
            lines.append(svc_yaml)
            lines.append("")

        # Volumes
        volumes = []
        if "postgres" in db:
            volumes.append("  postgres_data:")
        if "mysql" in db or "maria" in db:
            volumes.append("  mysql_data:")
        if "mongo" in db:
            volumes.append("  mongo_data:")
        if "redis" in cache:
            volumes.append("  redis_data:")

        if volumes:
            lines.append("volumes:")
            lines.extend(volumes)
            lines.append("")

        return "\n".join(lines)

    # ─── Dockerfile ───────────────────────────────────────────

    def _generate_dockerfile(self, ts: dict, slug: str) -> str:
        """Generate Dockerfile for the backend service (language-aware)."""
        lang = self._detect_lang(ts)
        version = self._get_version(ts, lang)
        port = self._resolve_port(ts)
        cmds = self._get_cmds(lang)
        framework = ts.get("backend_framework", "").lower()

        build_img = DOCKER_IMAGES.get(lang, "ubuntu:22.04").format(version=version)
        run_img = DOCKER_RUNTIME_IMAGES.get(lang, build_img).format(version=version)

        lines = [
            f"# Dockerfile for {slug} backend ({lang})",
            f"# Generated: {datetime.now().isoformat()}",
            "",
        ]

        if lang in COMPILED_LANGS:
            # Multi-stage build for compiled languages
            lines.append(f"FROM {build_img} AS builder")
            lines.append(f"WORKDIR {cmds['workdir']}")

            # Copy dependency files first (layer caching)
            if cmds.get("copy_deps"):
                for dep_file in cmds["copy_deps"].split():
                    lines.append(f"COPY {dep_file} ./")

            # Install dependencies
            if cmds.get("install"):
                lines.append(f"RUN {cmds['install']}")

            lines.append("COPY . .")

            # Build
            if cmds.get("build"):
                lines.append(f"RUN {cmds['build']}")

            lines.append("")

            # Runtime stage
            lines.append(f"FROM {run_img} AS runner")
            lines.append(f"WORKDIR {cmds['workdir']}")

            if lang == "go":
                lines.append("COPY --from=builder /app/server /app/server")
            elif lang == "rust":
                lines.append("COPY --from=builder /app/target/release/server /app/server")
            elif lang == "java":
                lines.append("COPY --from=builder /app/target/*.jar /app/app.jar")
            elif lang == "c#":
                lines.append("COPY --from=builder /app/publish /app/")

        else:
            # Single-stage for interpreted languages (Python, Node.js)
            lines.append(f"FROM {build_img}")
            lines.append(f"WORKDIR {cmds['workdir']}")

            # Copy dependency files first
            if cmds.get("copy_deps"):
                for dep_file in cmds["copy_deps"].split():
                    lines.append(f"COPY {dep_file} ./")

            # Install dependencies
            if cmds.get("install"):
                lines.append(f"RUN {cmds['install']}")

            lines.append("COPY . .")

            # Build (e.g., npm run build for Node.js)
            if cmds.get("build"):
                lines.append(f"RUN {cmds['build']}")

            # Set production env
            env_key = cmds.get("env_key", "APP_ENV")
            lines.append(f"ENV {env_key}=production")

        lines.append(f"EXPOSE {port}")

        if cmds.get("user"):
            lines.append(f"USER {cmds['user']}")

        # CMD
        start = cmds.get("start_cmd", '["echo", "no start command"]')
        start = start.replace("{port}", str(port))
        lines.append(f"CMD {start}")
        lines.append("")

        return "\n".join(lines)

    # ─── K8s Deployment ───────────────────────────────────────

    def _generate_k8s_deployment(self, ts: dict, slug: str, port: int = 3000) -> str:
        """Generate Kubernetes deployment manifest."""
        return f"""# Kubernetes Deployment for {slug}
# Generated: {datetime.now().isoformat()}
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {slug}
  labels:
    app: {slug}
spec:
  replicas: 2
  selector:
    matchLabels:
      app: {slug}
  template:
    metadata:
      labels:
        app: {slug}
    spec:
      containers:
        - name: {slug}
          image: {slug}:latest
          ports:
            - containerPort: {port}
          envFrom:
            - configMapRef:
                name: {slug}-config
            - secretRef:
                name: {slug}-secrets
          resources:
            requests:
              memory: "256Mi"
              cpu: "250m"
            limits:
              memory: "512Mi"
              cpu: "500m"
          livenessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 30
            periodSeconds: 10
          readinessProbe:
            httpGet:
              path: /health
              port: {port}
            initialDelaySeconds: 5
            periodSeconds: 5
"""

    def _generate_k8s_service(self, slug: str, port: int = 3000) -> str:
        """Generate Kubernetes service manifest."""
        return f"""# Kubernetes Service for {slug}
apiVersion: v1
kind: Service
metadata:
  name: {slug}
spec:
  selector:
    app: {slug}
  ports:
    - protocol: TCP
      port: 80
      targetPort: {port}
  type: ClusterIP
"""

    def _generate_k8s_configmap(self, ts: dict, slug: str, env_vars: dict) -> str:
        """Generate Kubernetes ConfigMap."""
        lines = [
            f"# Kubernetes ConfigMap for {slug}",
            "apiVersion: v1",
            "kind: ConfigMap",
            "metadata:",
            f"  name: {slug}-config",
            "data:",
        ]
        for key, val in env_vars.items():
            if key.startswith("#") or not val or "SECRET" in key or "PASSWORD" in key or "KEY" in key.upper():
                continue
            lines.append(f"  {key}: \"{val}\"")

        return "\n".join(lines) + "\n"

    # ─── CI Pipeline ──────────────────────────────────────────

    def _generate_ci_pipeline(self, ts: dict, slug: str) -> str:
        """Generate GitHub Actions CI pipeline (language-aware)."""
        lang = self._detect_lang(ts)
        version = self._get_version(ts, lang)
        cmds = self._get_cmds(lang)
        port = self._resolve_port(ts)
        db = ts.get("primary_database", "").lower()
        cache = ts.get("cache_layer", "").lower()

        # Build services section
        svc_lines = []
        test_env_lines = []
        if "postgres" in db:
            svc_lines.extend([
                "      postgres:",
                "        image: postgres:16-alpine",
                "        env:",
                f"          POSTGRES_DB: {slug}_test",
                "          POSTGRES_USER: postgres",
                "          POSTGRES_PASSWORD: test",
                "        ports:",
                "          - 5432:5432",
                "        options: >-",
                "          --health-cmd pg_isready",
                "          --health-interval 10s",
                "          --health-timeout 5s",
                "          --health-retries 5",
            ])
            test_env_lines.append(f"          DATABASE_URL: postgresql://postgres:test@localhost:5432/{slug}_test")
        elif "mysql" in db or "maria" in db:
            svc_lines.extend([
                "      mysql:",
                "        image: mysql:8.0",
                "        env:",
                f"          MYSQL_DATABASE: {slug}_test",
                "          MYSQL_ROOT_PASSWORD: test",
                "        ports:",
                "          - 3306:3306",
                "        options: >-",
                "          --health-cmd=\"mysqladmin ping\"",
                "          --health-interval 10s",
                "          --health-timeout 5s",
                "          --health-retries 5",
            ])
            test_env_lines.append(f"          DATABASE_URL: mysql://root:test@localhost:3306/{slug}_test")

        if "redis" in cache:
            svc_lines.extend([
                "      redis:",
                "        image: redis:7-alpine",
                "        ports:",
                "          - 6379:6379",
            ])
            test_env_lines.append("          REDIS_URL: redis://localhost:6379")

        services_block = ""
        if svc_lines:
            services_block = "    services:\n" + "\n".join(svc_lines) + "\n"

        # Setup step
        setup_lines = []
        action = cmds.get("setup_action", "")
        setup_key = cmds.get("setup_key")
        if action:
            setup_lines.append(f"      - name: Setup {lang.title()}")
            setup_lines.append(f"        uses: {action}")
            if setup_key:
                setup_lines.append("        with:")
                setup_lines.append(f"          {setup_key}: '{version}'")
                if cmds.get("cache"):
                    setup_lines.append(f"          cache: '{cmds['cache']}'")
            # Java needs distribution
            if lang == "java":
                setup_lines.append("          distribution: 'temurin'")

        setup_block = "\n".join(setup_lines) if setup_lines else ""

        # Install step
        install_block = ""
        if cmds.get("install"):
            install_block = f"""
      - name: Install dependencies
        run: {cmds['install']}"""

        # Lint step
        lint_block = f"""
      - name: Lint
        run: {cmds['lint']}"""

        # Test env block
        test_env_block = ""
        if test_env_lines:
            test_env_block = "\n        env:\n" + "\n".join(test_env_lines)

        # Test steps
        test_block = f"""
      - name: Unit tests
        run: {cmds.get('test_unit', cmds['test'])}{test_env_block}

      - name: Integration tests
        run: {cmds.get('test_integration', cmds['test'])}{test_env_block}"""

        # Build step
        build_block = ""
        if cmds.get("build"):
            build_block = f"""
      - name: Build
        run: {cmds['build']}"""

        return f"""# GitHub Actions CI/CD for {slug} ({lang})
# Generated: {datetime.now().isoformat()}
name: CI/CD Pipeline

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  test:
    runs-on: ubuntu-latest
{services_block}
    steps:
      - uses: actions/checkout@v4

{setup_block}
{install_block}
{lint_block}
{test_block}
{build_block}

  build-image:
    needs: test
    runs-on: ubuntu-latest
    if: github.ref == 'refs/heads/main'
    steps:
      - uses: actions/checkout@v4

      - name: Build Docker image
        run: docker build -t {slug}:${{{{ github.sha }}}} .

      - name: Push to registry
        run: |
          echo "TODO: Configure container registry push"
"""

    # ─── Markdown ─────────────────────────────────────────────

    def to_markdown(self) -> str:
        """Generate summary markdown."""
        if not self.infra_config:
            return ""
        cfg = self.infra_config
        md = f"# Infrastructure Configuration: {cfg.project_name}\n\n"
        md += f"**Generated:** {datetime.now().isoformat()}\n\n"

        md += "## Files Generated\n\n"
        md += "| File | Description |\n"
        md += "|------|-------------|\n"
        md += "| `.env.example` | Environment variables |\n"
        md += "| `docker-compose.yml` | Local development stack |\n"
        md += "| `Dockerfile` | Backend container image |\n"
        md += "| `kubernetes/deployment.yaml` | K8s deployment |\n"
        md += "| `kubernetes/service.yaml` | K8s service |\n"
        md += "| `kubernetes/configmap.yaml` | K8s config |\n"
        md += "| `.github/workflows/ci.yml` | CI/CD pipeline |\n\n"

        md += "## Environment Variables\n\n"
        md += "| Variable | Default |\n"
        md += "|----------|---------|\n"
        for key, val in cfg.env_vars.items():
            if not key.startswith("#"):
                md += f"| `{key}` | `{val}` |\n"

        return md


def save_config(config: InfraConfig, output_dir) -> None:
    """Save all infrastructure configuration files."""
    infra_dir = Path(output_dir) / "infrastructure"
    infra_dir.mkdir(parents=True, exist_ok=True)

    # .env.example
    env_lines = []
    for key, val in config.env_vars.items():
        if key.startswith("#"):
            env_lines.append(f"\n{key}")
        else:
            env_lines.append(f"{key}={val}")
    with open(infra_dir / ".env.example", "w", encoding="utf-8") as f:
        f.write("\n".join(env_lines) + "\n")

    # docker-compose.yml
    if config.docker_compose:
        with open(infra_dir / "docker-compose.yml", "w", encoding="utf-8") as f:
            f.write(config.docker_compose)

    # Dockerfile
    if config.dockerfile:
        with open(infra_dir / "Dockerfile", "w", encoding="utf-8") as f:
            f.write(config.dockerfile)

    # Kubernetes manifests
    k8s_dir = infra_dir / "kubernetes"
    k8s_dir.mkdir(parents=True, exist_ok=True)
    if config.k8s_deployment:
        with open(k8s_dir / "deployment.yaml", "w", encoding="utf-8") as f:
            f.write(config.k8s_deployment)
    if config.k8s_service:
        with open(k8s_dir / "service.yaml", "w", encoding="utf-8") as f:
            f.write(config.k8s_service)
    if config.k8s_configmap:
        with open(k8s_dir / "configmap.yaml", "w", encoding="utf-8") as f:
            f.write(config.k8s_configmap)

    # CI/CD pipeline
    ci_dir = infra_dir / ".github" / "workflows"
    ci_dir.mkdir(parents=True, exist_ok=True)
    if config.ci_pipeline:
        with open(ci_dir / "ci.yml", "w", encoding="utf-8") as f:
            f.write(config.ci_pipeline)

    # Summary markdown
    gen = ConfigGenerator()
    gen.infra_config = config
    md = gen.to_markdown()
    with open(infra_dir / "infrastructure_overview.md", "w", encoding="utf-8") as f:
        f.write(md)

    # JSON export
    with open(infra_dir / "infrastructure.json", "w", encoding="utf-8") as f:
        json.dump(config.to_dict(), f, indent=2, ensure_ascii=False)
