# Microservice Codebase Evaluation for Cascading Failure Pattern Injection

**Date:** 2026-02-07
**Purpose:** Identify optimal open-source microservice architectures for AI agent debugging training environments

## Evaluation Criteria Summary

Target infrastructure requirements for cascade patterns:
- **CASCADE-001**: Payment + Redis + order service + fraud detection
- **CASCADE-007**: Service discovery/DNS + inventory + database replication
- **CASCADE-008**: PostgreSQL with WAL + logrotate (Linux infra)
- **CASCADE-009**: Feature flags + HTTP client thread pools + Redis sessions
- **CASCADE-010**: Cron-based ETL + PostgreSQL materialized views
- **CASCADE-011**: gRPC streaming + protobuf schemas

Ideal codebase characteristics:
- Multiple services with gRPC AND HTTP communication
- Redis for caching/sessions
- PostgreSQL for persistence
- Message queues (RabbitMQ/Kafka)
- 2K-10K lines per service
- Permissive license (MIT/Apache 2.0)
- Active maintenance

---

## TOP RANKED CANDIDATES

### 🥇 RANK 1: OpenTelemetry Astronomy Shop Demo

**GitHub URL:** https://github.com/open-telemetry/opentelemetry-demo

**Overall Score:** 95/100

#### Service Architecture
- **Number of Services:** 21 microservices (15 core business services + 6 infrastructure/support services)
- **Languages:** 11+ languages (.NET, Java, Go, C++, Ruby, Kotlin, TypeScript, Python, JavaScript, PHP, Rust, Elixir)
- **Polyglot:** Excellent diversity for testing cross-language cascading failures

#### Complete Service List
1. **Accounting Service** (.NET) - Order processing and financial records
2. **Ad Service** (Java) - Contextual advertisement generation
3. **Cart Service** (.NET) - Shopping cart management
4. **Checkout Service** (Go) - Order orchestration and payment processing
5. **Currency Service** (C++) - Multi-currency conversion
6. **Email Service** (Ruby) - Order confirmation emails
7. **Flagd** (Go) - Feature flag backend
8. **Flagd-UI** (Elixir) - Feature flag management interface
9. **Fraud Detection Service** (Kotlin) - Payment fraud analysis
10. **Frontend** (TypeScript) - User-facing web application
11. **Frontend Proxy** (C++/Envoy) - HTTP routing and load balancing
12. **Image Provider** (C++/nginx) - Static asset serving
13. **LLM Service** (Python) - AI-powered product recommendations
14. **Load Generator** (Python/Locust) - Traffic simulation
15. **Payment Service** (JavaScript/Node.js) - Payment processing
16. **Product Catalog** (Go) - Product listings and search
17. **Product Reviews** (Python) - User review management
18. **Quote Service** (PHP) - Shipping cost estimation
19. **Recommendation Service** (Python) - Product recommendations
20. **Shipping Service** (Rust) - Shipping logistics
21. **React Native App** (TypeScript) - Mobile client

#### Infrastructure Components
- **Caching:** Redis/Valkey (Cart Service)
- **Database:** PostgreSQL (Accounting Service, Product Reviews)
- **Message Queue:** Kafka (Checkout → Accounting, Fraud Detection)
- **Service Mesh:** Envoy proxy for HTTP routing
- **Communication:** gRPC (primary) + HTTP (secondary)
- **Feature Flags:** Flagd (supports CASCADE-009)
- **Monitoring:** Full OpenTelemetry instrumentation (tracing, metrics, logs)

#### Cascade Pattern Coverage
| Pattern | Coverage | Components Available |
|---------|----------|---------------------|
| CASCADE-001 | ✅ EXCELLENT | Payment + Fraud Detection + Checkout + Kafka queue |
| CASCADE-007 | ✅ GOOD | Envoy service discovery + Product Catalog + PostgreSQL |
| CASCADE-008 | ✅ EXCELLENT | PostgreSQL with WAL replication capabilities |
| CASCADE-009 | ✅ EXCELLENT | Flagd feature flags + HTTP clients + Redis sessions (Cart) |
| CASCADE-010 | ✅ GOOD | PostgreSQL + can add cron ETL to Accounting service |
| CASCADE-011 | ✅ EXCELLENT | gRPC streaming throughout + protobuf schemas |

#### Codebase Metrics
- **License:** Apache-2.0 (permissive, commercial-friendly)
- **Repository Size:** Medium-large (TypeScript 40.8%, Python 18.3%, Elixir 10.9%, Go 6.7%)
- **Service Size:** Estimated 1K-5K lines per service (ideal range)
- **Total Commits:** 1,566
- **Contributors:** 177 (very active community)
- **Latest Release:** v2.2.0 (January 8, 2026)
- **Maintenance:** Actively maintained by maintainers from Datadog, Dynatrace, Honeycomb, Elastic
- **Governance:** Biweekly SIG meetings, part of CNCF OpenTelemetry project

#### Strengths for Cascading Failure Injection
1. **Excellent observability built-in** - Makes it easier to demonstrate cascading failures to AI agents
2. **Real-world e-commerce workflow** - Payment → Checkout → Fraud Detection → Accounting creates natural cascade paths
3. **Message queue integration** - Kafka enables asynchronous failure propagation (CASCADE-001)
4. **Polyglot architecture** - Tests AI agent's ability to debug across language boundaries
5. **Feature flag infrastructure** - Native Flagd support perfect for CASCADE-009 (gradual rollout failures)
6. **Active maintenance** - Regular updates, bug fixes, community support
7. **Docker Compose ready** - Easy to deploy and modify for training environments
8. **Comprehensive documentation** - Well-documented architecture aids task creation

#### Weaknesses
- No built-in inventory/stock service (CASCADE-007 needs augmentation)
- No native cron/ETL service (CASCADE-010 requires addition)
- Larger than minimal examples (complexity could be both benefit and challenge)

#### Recommended Modifications for SDLC Training
1. Add **Inventory Service** (Go) to enable CASCADE-007 (service discovery failures)
2. Add **ETL Service** (Python) with cron scheduler for CASCADE-010 (scheduled job failures)
3. Configure PostgreSQL WAL replication between Accounting and Product Reviews for CASCADE-008
4. Add session management to Cart Service for CASCADE-009 (session store failures)

---

### 🥈 RANK 2: Google Online Boutique (microservices-demo)

**GitHub URL:** https://github.com/GoogleCloudPlatform/microservices-demo

**Overall Score:** 88/100

#### Service Architecture
- **Number of Services:** 11 microservices
- **Languages:** 6 languages (Go, C#, Node.js, Python, Java, C++)
- **Cloud-Native:** Designed for Kubernetes/GKE

#### Complete Service List
1. **Frontend** (Go) - HTTP server for e-commerce website
2. **Cart Service** (C#) - Shopping cart storage in Redis
3. **Product Catalog** (Go) - Product listings and search
4. **Currency Service** (Node.js) - Real-time currency conversion
5. **Payment Service** (Node.js) - Payment processing (mock)
6. **Shipping Service** (Go) - Shipping cost calculation
7. **Email Service** (Python) - Order confirmation emails
8. **Checkout Service** (Go) - Order orchestration
9. **Recommendation Service** (Python) - ML-based product recommendations
10. **Ad Service** (Java) - Contextual advertisements
11. **Load Generator** (Python/Locust) - Traffic simulation

#### Infrastructure Components
- **Caching:** Redis (Cart Service)
- **Database:** None built-in (uses in-memory stores or could add PostgreSQL)
- **Message Queue:** None (synchronous gRPC only)
- **Communication:** gRPC (primary inter-service protocol)
- **Cloud Integration:** GKE, Cloud Spanner, Memorystore, AlloyDB options

#### Cascade Pattern Coverage
| Pattern | Coverage | Components Available |
|---------|----------|---------------------|
| CASCADE-001 | ✅ GOOD | Payment + Cart (Redis) + Checkout (needs fraud service added) |
| CASCADE-007 | ⚠️ PARTIAL | Kubernetes DNS + no inventory service + no database replication |
| CASCADE-008 | ❌ MISSING | No PostgreSQL (could add) |
| CASCADE-009 | ⚠️ PARTIAL | Redis (Cart) + HTTP clients (needs feature flags) |
| CASCADE-010 | ❌ MISSING | No PostgreSQL, no ETL service |
| CASCADE-011 | ✅ EXCELLENT | gRPC throughout with protobuf schemas |

#### Codebase Metrics
- **License:** Apache-2.0
- **Language Distribution:** Go 28.4%, Python 28.3%, C# 8.2%, HTML 10.2%
- **Service Size:** Estimated 1K-4K lines per service
- **Total Commits:** 2,569
- **Contributors:** 139
- **Community:** 19.8k stars, 9.5k forks (largest community)
- **Latest Release:** v0.10.4 (November 26, 2025)
- **Maintenance:** Actively maintained by Google Cloud Platform team

#### Strengths
1. **Simplest architecture** - Easiest to understand and modify
2. **Strong gRPC implementation** - Excellent for CASCADE-011
3. **Largest community** - Most popular microservices reference architecture
4. **Production-quality code** - Google-grade engineering standards
5. **Comprehensive documentation** - Extensive guides and tutorials
6. **Cloud-agnostic** - Runs on any Kubernetes cluster

#### Weaknesses
1. **No message queue** - Missing Kafka/RabbitMQ for async cascade patterns (CASCADE-001)
2. **No PostgreSQL** - Missing database for CASCADE-008, CASCADE-010
3. **No feature flags** - Needs addition for CASCADE-009
4. **No fraud detection service** - Needs augmentation for CASCADE-001
5. **Synchronous-only** - Limited async failure propagation scenarios

#### Recommended Modifications for SDLC Training
1. Add **Fraud Detection Service** for CASCADE-001
2. Add **PostgreSQL database** for Product Catalog and Checkout services (CASCADE-008)
3. Add **Kafka** for async event streaming (Checkout → Fraud Detection)
4. Add **Feature Flag Service** (can use Flagd or simple config service)
5. Add **ETL/Analytics Service** for CASCADE-010

---

### 🥉 RANK 3: Instana Robot Shop

**GitHub URL:** https://github.com/instana/robot-shop

**Overall Score:** 82/100

#### Service Architecture
- **Number of Services:** 8 core microservices + infrastructure
- **Languages:** 7 languages (Java, PHP, Python, Golang, JavaScript, AngularJS)
- **E-commerce:** Robot toy store simulation

#### Complete Service List
1. **Web** (JavaScript/AngularJS 1.x + Nginx) - Single-page application frontend
2. **Cart** (Java/Spring Boot) - Shopping cart management
3. **Catalogue** (PHP/Apache) - Product catalog and search
4. **Payment** (Java/Spring Boot) - Payment processing
5. **User** (Python/Flask) - User authentication and management
6. **Ratings** (Golang) - Product ratings and reviews
7. **Shipping** (Java/Spring Boot) - Shipping logistics
8. **Dispatch** (Node.js/Express) - Order dispatch coordination

#### Infrastructure Components
- **Caching:** Redis (shopping cart storage)
- **Databases:**
  - MongoDB (product catalog, user repository)
  - MySQL (shipping information lookup with Maxmind geographic data)
- **Message Queue:** RabbitMQ (order pipeline processing)
- **Web Servers:** Nginx (reverse proxy), Apache (PHP runtime)
- **Communication:** HTTP/REST (no gRPC)

#### Cascade Pattern Coverage
| Pattern | Coverage | Components Available |
|---------|----------|---------------------|
| CASCADE-001 | ✅ EXCELLENT | Payment + Redis + Cart + RabbitMQ (can add fraud detection) |
| CASCADE-007 | ⚠️ PARTIAL | No service discovery mechanism + no inventory service + MySQL replication possible |
| CASCADE-008 | ❌ MISSING | MySQL instead of PostgreSQL (could migrate) |
| CASCADE-009 | ⚠️ PARTIAL | Redis sessions + HTTP clients (needs feature flags) |
| CASCADE-010 | ❌ MISSING | MySQL instead of PostgreSQL (could migrate or add) |
| CASCADE-011 | ❌ MISSING | HTTP/REST only, no gRPC |

#### Codebase Metrics
- **License:** Apache-2.0
- **Language Distribution:** JavaScript 42.0%, PHP 12.3%, Java 12.3%, Python 7.6%
- **Service Size:** Small to medium per service (~1K-3K lines estimated)
- **Total Commits:** 377
- **Contributors:** 16
- **Community:** 980 stars, 6,000+ forks
- **Maintenance:** Active but smaller community than top 2
- **Purpose:** Explicitly designed for testing monitoring and observability tools

#### Strengths
1. **RabbitMQ integration** - Good for async cascade patterns (CASCADE-001)
2. **Multiple databases** - MongoDB + MySQL provides diverse failure scenarios
3. **Simple architecture** - Easy to understand, good for beginners
4. **Monitoring-focused** - Designed for observability testing
5. **Docker Compose ready** - Simple local deployment
6. **Intentionally imperfect** - Authors note "error handling is patchy" (realistic for debugging training)

#### Weaknesses
1. **No gRPC** - Only HTTP/REST communication (CASCADE-011 not possible)
2. **No PostgreSQL** - Uses MongoDB + MySQL instead (CASCADE-008, CASCADE-010)
3. **No feature flags** - Needs addition for CASCADE-009
4. **Smaller community** - Less active development than top candidates
5. **Older JavaScript stack** - AngularJS 1.x is deprecated
6. **No fraud detection** - Would need to add for CASCADE-001

#### Recommended Modifications for SDLC Training
1. Add **gRPC communication layer** between services (major refactor for CASCADE-011)
2. Add **PostgreSQL** alongside or replacing MySQL for CASCADE-008, CASCADE-010
3. Add **Fraud Detection Service** (Python) for CASCADE-001
4. Add **Feature Flag Service** for CASCADE-009
5. Add **ETL Service** for CASCADE-010

---

### 🏅 RANK 4: Go-CQRS-Kafka-gRPC-Microservices

**GitHub URL:** https://github.com/AleksK1NG/Go-CQRS-Kafka-gRPC-Microservices

**Overall Score:** 75/100

#### Service Architecture
- **Number of Services:** 3 core services (Writer, Reader, API Gateway)
- **Languages:** Go (97.2%)
- **Pattern:** CQRS (Command Query Responsibility Segregation)

#### Service List
1. **Writer Service** (Go) - Command operations (write/create/update/delete)
2. **Reader Service** (Go) - Query operations (read/search)
3. **API Gateway** (Go/Echo) - HTTP → gRPC request routing

#### Infrastructure Components
- **Message Queue:** Kafka (event-driven architecture)
- **Databases:**
  - PostgreSQL (writer/command store)
  - MongoDB (reader/query store)
- **Caching:** Redis
- **Communication:** gRPC (inter-service) + HTTP (API Gateway)
- **Observability:**
  - Jaeger (distributed tracing)
  - Prometheus (metrics)
  - Grafana (dashboards)

#### Cascade Pattern Coverage
| Pattern | Coverage | Components Available |
|---------|----------|---------------------|
| CASCADE-001 | ⚠️ PARTIAL | Kafka + Redis (needs payment/fraud services) |
| CASCADE-007 | ⚠️ PARTIAL | PostgreSQL replication possible (needs inventory service) |
| CASCADE-008 | ✅ EXCELLENT | PostgreSQL with WAL replication ready |
| CASCADE-009 | ⚠️ PARTIAL | Redis + HTTP clients (needs feature flags) |
| CASCADE-010 | ✅ GOOD | PostgreSQL + can add ETL to Writer service |
| CASCADE-011 | ✅ EXCELLENT | gRPC streaming + protobuf schemas |

#### Codebase Metrics
- **License:** Not explicitly stated (check repository)
- **Language Distribution:** Go 97.2%, Makefile 2.3%
- **Service Size:** Medium per service (~2K-4K lines estimated)
- **Total Commits:** 41
- **Contributors:** Small team
- **Community:** 237 stars, 65 forks
- **Maintenance:** Moderately active

#### Strengths
1. **Excellent infrastructure coverage** - PostgreSQL + MongoDB + Redis + Kafka
2. **Strong CQRS pattern** - Great for teaching event-driven debugging
3. **gRPC implementation** - Good for CASCADE-011
4. **PostgreSQL ready** - Perfect for CASCADE-008, CASCADE-010
5. **Comprehensive observability** - Jaeger, Prometheus, Grafana built-in
6. **Single language** - Simpler to reason about, but less realistic

#### Weaknesses
1. **Only 3 services** - Too few for complex cascade scenarios
2. **No business domain** - Abstract CQRS pattern, not e-commerce/realistic workflow
3. **No payment/fraud services** - Needs significant additions for CASCADE-001
4. **No feature flags** - Needs addition for CASCADE-009
5. **Small community** - Limited external validation and support
6. **Not a reference architecture** - More of a pattern demonstration

#### Recommended Modifications for SDLC Training
1. Add **business domain services** (Product, Order, Payment, Inventory) to create realistic workflows
2. Add **Fraud Detection Service** for CASCADE-001
3. Add **Feature Flag Service** for CASCADE-009
4. Add **ETL/Analytics Service** for CASCADE-010
5. **Scale out to 8-10 services** to create realistic complexity

---

### ❌ EXCLUDED: Weaveworks Sock Shop

**GitHub URL:** https://github.com/microservices-demo/microservices-demo

**Status:** ARCHIVED (December 29, 2023) - Read-only

#### Why Excluded
- **Repository archived** - No active maintenance
- **Deprecated technology** - No longer receiving updates or security patches
- **Community inactive** - 94 open issues, 18 open PRs, no resolution
- **Risk factor** - Using archived projects in production training environments is problematic

#### Historical Context
- **Number of Services:** 10 microservices (frontend, catalogue, cart, payment, shipping, user, orders, queue-master + databases)
- **Languages:** Spring Boot, Go, Node.js
- **Infrastructure:** Redis, MySQL, MongoDB, RabbitMQ
- **License:** Apache-2.0
- **Community:** 3.8k stars, 2.9k forks, 53 contributors, 1,705 commits

#### Would Have Been Ranked
If active, would rank #3 (Score: 80/100) due to:
- Good infrastructure coverage (Redis, MySQL, MongoDB, RabbitMQ)
- Realistic e-commerce workflow
- Polyglot architecture
- But missing gRPC (CASCADE-011) and PostgreSQL (CASCADE-008, CASCADE-010)

---

### 🔍 RANK 5: eShop (.NET Reference Architecture)

**GitHub URL:** https://github.com/dotnet/eShop

**Overall Score:** 72/100

#### Service Architecture
- **Number of Services:** 8+ microservices
- **Languages:** C# (.NET 9)
- **Framework:** .NET Aspire (modern cloud-native stack)

#### Infrastructure Components
- **Database:** SQL Server (Azure SQL, not PostgreSQL)
- **Communication:** gRPC + HTTP
- **Orchestration:** .NET Aspire (Docker-based)
- **Cloud:** Azure-optimized (Azure OpenAI, Azure deployment)

#### Cascade Pattern Coverage
| Pattern | Coverage | Components Available |
|---------|----------|---------------------|
| CASCADE-001 | ⚠️ PARTIAL | Payment services + needs Redis + needs fraud detection |
| CASCADE-007 | ⚠️ PARTIAL | .NET Aspire service discovery (needs inventory) |
| CASCADE-008 | ❌ MISSING | SQL Server instead of PostgreSQL |
| CASCADE-009 | ⚠️ PARTIAL | Needs Redis + needs feature flags |
| CASCADE-010 | ❌ MISSING | SQL Server instead of PostgreSQL |
| CASCADE-011 | ✅ GOOD | gRPC support in .NET services |

#### Codebase Metrics
- **License:** MIT
- **Language Distribution:** C# 84.2%, HTML 7.7%, CSS 7.0%
- **Total Commits:** 340
- **Contributors:** 57
- **Maintenance:** Active (Microsoft-backed)

#### Strengths
1. **Modern .NET stack** - .NET 9 + Aspire is cutting-edge
2. **Microsoft backing** - Strong support and documentation
3. **Production-ready code** - Enterprise-grade quality
4. **Azure integration** - Good for cloud-native scenarios
5. **gRPC support** - Good for CASCADE-011

#### Weaknesses
1. **Single language** - Only C#/.NET (less realistic polyglot scenarios)
2. **SQL Server not PostgreSQL** - Incompatible with CASCADE-008, CASCADE-010
3. **No Redis** - Needs addition for CASCADE-001, CASCADE-009
4. **No message queue** - Needs Kafka/RabbitMQ addition
5. **Azure-centric** - May have cloud platform lock-in
6. **Newer project** - Less battle-tested than alternatives

---

## FINAL RECOMMENDATION

### Top 3 Candidates for SDLC Debugging Training

#### 1. OpenTelemetry Astronomy Shop (STRONGLY RECOMMENDED)
**Best for:** Comprehensive debugging training covering all cascade patterns

**Rationale:**
- 21 services provide rich, realistic complexity
- Built-in Kafka, PostgreSQL, Redis, gRPC match all infrastructure requirements
- Feature flags (Flagd) natively support CASCADE-009
- Polyglot architecture (11+ languages) creates realistic cross-language debugging scenarios
- Actively maintained by CNCF with enterprise backing (Datadog, Dynatrace, Honeycomb, Elastic)
- Apache-2.0 license allows commercial use
- Observability-first design makes it easier to demonstrate cascading failures to AI agents

**Effort to Deploy:** Low (Docker Compose ready, comprehensive documentation)

**Modifications Needed:** Minor (add Inventory + ETL services for full coverage)

---

#### 2. Google Online Boutique (RECOMMENDED WITH MODIFICATIONS)
**Best for:** Simpler debugging scenarios with largest community support

**Rationale:**
- 11 services provide good complexity without overwhelming agents
- Largest community (19.8k stars) means extensive examples and support
- Google-grade code quality provides production-realistic scenarios
- Excellent gRPC implementation for CASCADE-011
- Simple to understand architecture
- Apache-2.0 license

**Effort to Deploy:** Low (designed for easy deployment)

**Modifications Needed:** Moderate (add PostgreSQL, Kafka, feature flags, fraud detection service)

---

#### 3. Instana Robot Shop (FALLBACK OPTION)
**Best for:** RabbitMQ-based async debugging patterns with intentional imperfections

**Rationale:**
- Good infrastructure coverage (Redis, MongoDB, MySQL, RabbitMQ)
- Authors explicitly note "error handling is patchy" - realistic for debugging training
- Simpler architecture for beginner AI agent scenarios
- Apache-2.0 license

**Effort to Deploy:** Low (Docker Compose ready)

**Modifications Needed:** Major (add gRPC layer, migrate to PostgreSQL, add feature flags)

---

## IMPLEMENTATION STRATEGY

### Phase 1: Rapid Prototyping (Week 1)
Deploy **OpenTelemetry Astronomy Shop** and inject CASCADE-001, CASCADE-009, CASCADE-011 patterns (these require minimal modifications).

### Phase 2: Infrastructure Augmentation (Week 2)
Add Inventory Service (Go) and ETL Service (Python) to enable CASCADE-007 and CASCADE-010.

### Phase 3: Cascade Pattern Development (Week 3-4)
Develop all 11 cascade patterns with OpenTelemetry as primary codebase.

### Phase 4: Diversification (Week 5)
Deploy **Google Online Boutique** with modifications to test AI agents on different architecture patterns.

### Phase 5: Validation (Week 6)
Test all environments with baseline AI agents (Claude, GPT-4), measure pass rates (<50% target), refine difficulty.

---

## APPENDIX: Infrastructure Mapping

### CASCADE-001: Payment + Redis + Order + Fraud Detection
- **OpenTelemetry:** Payment + Cart (Redis) + Checkout + Fraud Detection + Kafka ✅
- **Online Boutique:** Payment + Cart (Redis) + Checkout (needs fraud detection added) ⚠️
- **Robot Shop:** Payment + Redis + Cart + RabbitMQ (needs fraud detection) ⚠️

### CASCADE-007: Service Discovery + Inventory + DB Replication
- **OpenTelemetry:** Envoy discovery + (add Inventory) + PostgreSQL replication ⚠️
- **Online Boutique:** Kubernetes DNS + (add Inventory) + (add PostgreSQL) ⚠️
- **Robot Shop:** (needs service discovery) + (add Inventory) + MySQL replication ⚠️

### CASCADE-008: PostgreSQL + WAL + logrotate
- **OpenTelemetry:** PostgreSQL (Accounting, Product Reviews) ✅
- **Online Boutique:** (add PostgreSQL) ❌
- **Robot Shop:** (migrate MySQL → PostgreSQL) ❌

### CASCADE-009: Feature Flags + Thread Pools + Redis Sessions
- **OpenTelemetry:** Flagd + HTTP clients + Cart (Redis) ✅
- **Online Boutique:** (add feature flags) + HTTP clients + Cart (Redis) ⚠️
- **Robot Shop:** (add feature flags) + HTTP clients + Redis ⚠️

### CASCADE-010: Cron ETL + PostgreSQL Materialized Views
- **OpenTelemetry:** (add ETL service) + PostgreSQL ⚠️
- **Online Boutique:** (add ETL service) + (add PostgreSQL) ❌
- **Robot Shop:** (add ETL service) + (migrate to PostgreSQL) ❌

### CASCADE-011: gRPC Streaming + Protobuf
- **OpenTelemetry:** gRPC throughout + protobuf schemas ✅
- **Online Boutique:** gRPC throughout + protobuf schemas ✅
- **Robot Shop:** (add gRPC layer, major refactor) ❌

---

## REFERENCES

- [Google Online Boutique](https://github.com/GoogleCloudPlatform/microservices-demo)
- [Weaveworks Sock Shop (Archived)](https://github.com/microservices-demo/microservices-demo)
- [Instana Robot Shop](https://github.com/instana/robot-shop)
- [OpenTelemetry Astronomy Shop](https://github.com/open-telemetry/opentelemetry-demo)
- [OpenTelemetry Demo Architecture](https://opentelemetry.io/docs/demo/architecture/)
- [Go-CQRS-Kafka-gRPC Microservices](https://github.com/AleksK1NG/Go-CQRS-Kafka-gRPC-Microservices)
- [eShop .NET Reference](https://github.com/dotnet/eShop)
- [Awesome Microservices List](https://github.com/mfornos/awesome-microservices)
