# System Architecture

## High-Level Architecture

```mermaid
graph TB
    User[Telegram User] --> Bot[passport-telegram]
    Bot --> Platform[passport-platform]
    Platform --> Core[passport-core]
    Core --> LLM[Requesty AI Router]
    Core --> Storage[Binary Storage]
    Platform --> DB[(SQLite Database)]
    
    subgraph "Transport Layer"
        Bot
    end
    
    subgraph "Application Layer"
        Platform
        DB
    end
    
    subgraph "Processing Layer"
        Core
        Storage
        LLM
    end
```

## Package Dependencies

```mermaid
graph LR
    Telegram[passport-telegram] --> Platform[passport-platform]
    Platform --> Core[passport-core]
    Telegram -.-> Core
    
    style Telegram fill:#e1f5ff
    style Platform fill:#fff4e1
    style Core fill:#ffe1e1
```

## Processing Workflow

```mermaid
sequenceDiagram
    participant User
    participant Bot as Telegram Bot
    participant Platform as Platform Service
    participant Core as Core Workflow
    participant LLM as Requesty AI
    
    User->>Bot: Send passport image
    Bot->>Bot: Download image bytes
    Bot->>Platform: process_bytes()
    Platform->>Platform: Get/create user
    Platform->>Platform: Check quota
    Platform->>Platform: Register upload
    Platform->>Core: process_bytes()
    Core->>Core: Validate passport (SIFT)
    Core->>Core: Detect face (YuNet)
    Core->>Core: Crop face
    Core->>LLM: Extract fields
    LLM-->>Core: Passport data
    Core-->>Platform: WorkflowResult
    Platform->>Platform: Record result
    Platform->>Platform: Update usage
    Platform-->>Bot: TrackedProcessingResult
    Bot->>Bot: Format response
    Bot-->>User: Media group + data
```

## Deployment Architecture

```mermaid
graph TB
    GitHub[GitHub Repository] -->|Push to main| Actions[GitHub Actions]
    Actions -->|Build| Docker[Docker Image]
    Actions -->|Push| Registry[Container Registry]
    Actions -->|Deploy| K8s[MicroK8s Cluster]
    
    K8s --> Pod[passport-telegram Pod]
    Pod --> PVC[Persistent Volume]
    Pod --> ConfigMap[ConfigMap]
    Pod --> Secret[Secret]
    
    subgraph "Kubernetes Resources"
        Pod
        PVC
        ConfigMap
        Secret
    end
```

## Data Flow Architecture

```mermaid
flowchart LR
    Input[Image Upload] --> Validate{Valid Passport?}
    Validate -->|No| Error1[Validation Error]
    Validate -->|Yes| Detect{Face Detected?}
    Detect -->|No| Error2[Detection Error]
    Detect -->|Yes| Crop[Crop Face]
    Crop --> Extract[LLM Extraction]
    Extract --> Store[Store Artifacts]
    Store --> Record[Record Result]
    Record --> Response[Success Response]
    
    Error1 --> Partial[Partial Result]
    Error2 --> Partial
```

## Storage Architecture

### Binary Storage (passport-core)

```mermaid
graph TB
    Upload[Image Upload] --> Store{Storage Backend}
    Store -->|local| Local[Local Filesystem]
    Store -->|s3| S3[AWS S3]
    
    Local --> Originals[data/originals/YYYYMMDD/]
    Local --> Faces[data/faces/YYYYMMDD/]
    
    S3 --> S3Originals[s3://bucket/originals/]
    S3 --> S3Faces[s3://bucket/faces/]
```

### Result Storage (passport-core)

```mermaid
graph TB
    Result[Processing Result] --> Backend{Data Store Backend}
    Backend -->|sqlite| SQLite[(SQLite DB)]
    Backend -->|json| JSON[JSON Files]
    Backend -->|csv| CSV[CSV File]
    
    SQLite --> ResultsDB[data/results.sqlite3]
    JSON --> ResultsJSON[data/results/*.json]
    CSV --> ResultsCSV[data/results.csv]
```

### Application Database (passport-platform)

```mermaid
erDiagram
    users ||--o{ uploads : creates
    users ||--o{ usage_ledger : generates
    uploads ||--o| processing_results : has
    
    users {
        int id PK
        string external_provider
        string external_identity
        string status
        string plan
        datetime created_at
        datetime updated_at
    }
    
    uploads {
        int id PK
        int user_id FK
        string source_ref
        string channel
        string status
        datetime created_at
        datetime updated_at
    }
    
    processing_results {
        int id PK
        int upload_id FK
        bool success
        json data
        json error_details
        datetime created_at
    }
    
    usage_ledger {
        int id PK
        int user_id FK
        string event_type
        int units
        datetime created_at
    }
```

## Security Architecture

```mermaid
graph TB
    Request[Incoming Request] --> Auth{Authorized Chat?}
    Auth -->|No| Reject[Reject Request]
    Auth -->|Yes| User{User Status}
    User -->|blocked| Block[User Blocked Error]
    User -->|active| Quota{Quota Check}
    Quota -->|exceeded| Limit[Quota Exceeded Error]
    Quota -->|ok| Process[Process Request]
    
    Process --> NonRoot[Non-root Container User]
    Process --> Caps[Dropped Capabilities]
    Process --> ReadOnly[Read-only Filesystem]
```

## Configuration Architecture

```mermaid
graph TB
    subgraph "Development"
        DevEnv[.env files]
    end
    
    subgraph "Production"
        K8sConfig[Kubernetes ConfigMap]
        K8sSecret[Kubernetes Secret]
    end
    
    subgraph "Application"
        Settings[Pydantic Settings]
    end
    
    DevEnv --> Settings
    K8sConfig --> Settings
    K8sSecret --> Settings
    
    Settings --> Core[passport-core]
    Settings --> Platform[passport-platform]
    Settings --> Telegram[passport-telegram]
```

## Error Handling Architecture

```mermaid
flowchart TB
    Start[Process Request] --> Try{Try Processing}
    Try -->|Success| Complete[Complete Result]
    Try -->|Validation Fails| Partial1[Partial Result + Error]
    Try -->|Detection Fails| Partial2[Partial Result + Error]
    Try -->|Extraction Fails| Partial3[Partial Result + Error]
    Try -->|Unexpected Error| Exception[Raise Exception]
    
    Complete --> Response[Success Response]
    Partial1 --> Response
    Partial2 --> Response
    Partial3 --> Response
    Exception --> ErrorHandler[Error Handler]
    ErrorHandler --> ErrorResponse[Error Response]
```

## Scaling Considerations

### Current Architecture (Single Replica)
- Telegram bot uses long polling (no webhook)
- Single pod deployment with Recreate strategy
- Persistent volume for data storage
- Suitable for low-to-medium traffic

### Future Scaling Options
1. **Horizontal Scaling**
   - Switch to webhook mode for Telegram
   - Multiple replicas with load balancing
   - Shared storage (S3 or NFS)
   - Distributed database (PostgreSQL)

2. **Vertical Scaling**
   - Increase pod resources (CPU/memory)
   - Optimize image processing pipeline
   - Cache LLM responses

3. **Service Separation**
   - Separate processing workers
   - Queue-based architecture (Redis/RabbitMQ)
   - Async processing with status callbacks

## Design Patterns

### Adapter Pattern
- `passport-telegram` and future `passport-api` adapt different transports
- Both use `passport-platform` services
- Core processing logic remains transport-agnostic

### Service Layer Pattern
- Clear separation between transport, application, and processing layers
- Services encapsulate business logic
- Repositories handle data access

### Workflow Pattern
- `PassportWorkflow` provides stage-by-stage processing
- Each stage can be called independently
- Partial results returned on failure

### Repository Pattern
- Data access abstracted through repositories
- Services depend on repositories, not direct database access
- Easier testing with fake implementations

### Settings Pattern
- Pydantic-based configuration
- Environment variable loading
- Type-safe settings with validation
