# Workflows

## End-to-End Processing Workflow

```mermaid
sequenceDiagram
    participant User
    participant Telegram as Telegram Bot
    participant Platform as Platform Service
    participant Core as Core Workflow
    participant LLM as Requesty AI
    participant DB as Database
    participant Storage as Binary Storage
    
    User->>Telegram: Send passport image
    Telegram->>Telegram: Check authorization
    Telegram->>Telegram: Download image bytes
    
    alt Media Group
        Telegram->>Telegram: Collect images (2s window)
        Telegram->>Telegram: Batch processing
    end
    
    Telegram->>Platform: process_bytes(command)
    
    Platform->>DB: Get/create user
    DB-->>Platform: User record
    
    Platform->>DB: Check quota
    DB-->>Platform: Usage summary
    
    alt Quota Exceeded
        Platform-->>Telegram: QuotaExceededError
        Telegram-->>User: Quota limit message
    end
    
    alt User Blocked
        Platform-->>Telegram: UserBlockedError
        Telegram-->>User: Account blocked message
    end
    
    Platform->>DB: Register upload
    DB-->>Platform: Upload record
    
    Platform->>Core: process_bytes()
    
    Core->>Core: Load image
    Core->>Core: Validate passport (SIFT)
    
    alt Not Passport
        Core-->>Platform: Partial result
        Platform->>DB: Record failure
        Platform-->>Telegram: Result (not passport)
        Telegram-->>User: Not passport message
    end
    
    Core->>Core: Detect face (YuNet)
    
    alt No Face
        Core-->>Platform: Partial result
        Platform->>DB: Record failure
        Platform-->>Telegram: Result (no face)
        Telegram-->>User: No face message
    end
    
    Core->>Core: Crop face
    Core->>Storage: Store original image
    Storage-->>Core: Original URI
    Core->>Storage: Store face crop
    Storage-->>Core: Face URI
    
    Core->>LLM: Extract fields (with image)
    LLM-->>Core: PassportData + tokens
    
    Core-->>Platform: WorkflowResult (complete)
    
    Platform->>DB: Record success
    Platform->>DB: Update usage (upload + success + tokens)
    
    Platform-->>Telegram: TrackedProcessingResult
    
    Telegram->>Telegram: Format Arabic response
    Telegram->>User: Send media group
    Telegram->>User: Original image
    Telegram->>User: Face crop
    Telegram-->>User: Extracted data caption
```

## User Registration Workflow

```mermaid
flowchart TB
    Start[Incoming Request] --> Extract[Extract External Identity]
    Extract --> Query{User Exists?}
    
    Query -->|Yes| Return[Return User]
    Query -->|No| Create[Create User]
    
    Create --> SetDefaults[Set Defaults]
    SetDefaults --> Insert[Insert to DB]
    Insert --> Return
    
    Return --> End[User Record]
    
    SetDefaults -.-> Status[status = active]
    SetDefaults -.-> Plan[plan = free]
```

## Quota Evaluation Workflow

```mermaid
flowchart TB
    Start[Check Quota] --> GetPolicy[Get Plan Policy]
    GetPolicy --> GetUsage[Query Usage Ledger]
    
    GetUsage --> CheckUploads{Upload Limit?}
    CheckUploads -->|Unlimited| CheckSuccess{Success Limit?}
    CheckUploads -->|Limited| CompareUploads{Usage < Limit?}
    
    CompareUploads -->|No| Deny[Deny: Upload Limit]
    CompareUploads -->|Yes| CheckSuccess
    
    CheckSuccess -->|Unlimited| Allow[Allow Upload]
    CheckSuccess -->|Limited| CompareSuccess{Successes < Limit?}
    
    CompareSuccess -->|No| Deny2[Deny: Success Limit]
    CompareSuccess -->|Yes| Allow
    
    Allow --> Decision[QuotaDecision: can_upload=true]
    Deny --> Decision2[QuotaDecision: can_upload=false]
    Deny2 --> Decision2
```

## Upload Processing Workflow

```mermaid
flowchart TB
    Start[Upload Request] --> Register[Register Upload]
    Register --> MarkProcessing[Mark as Processing]
    
    MarkProcessing --> Process[Execute Workflow]
    
    Process --> Success{Success?}
    
    Success -->|Yes| RecordSuccess[Record Success Result]
    Success -->|No| RecordFailure[Record Failure Result]
    
    RecordSuccess --> UpdateUpload1[Update Upload Status: complete]
    RecordFailure --> UpdateUpload2[Update Upload Status: failed]
    
    UpdateUpload1 --> LogUsage1[Log Usage: upload + success + tokens]
    UpdateUpload2 --> LogUsage2[Log Usage: upload only]
    
    LogUsage1 --> End[Return Result]
    LogUsage2 --> End
```

## Passport Validation Workflow

```mermaid
flowchart TB
    Start[Input Image] --> LoadTemplate[Load Template]
    LoadTemplate --> MaskTemplate[Apply Mask]
    
    MaskTemplate --> DetectKP1[Detect Template Keypoints]
    Start --> DetectKP2[Detect Input Keypoints]
    
    DetectKP1 --> ComputeDesc1[Compute Descriptors]
    DetectKP2 --> ComputeDesc2[Compute Descriptors]
    
    ComputeDesc1 --> Match[Match Features]
    ComputeDesc2 --> Match
    
    Match --> Filter[Filter Good Matches]
    Filter --> Count{Match Count >= Min?}
    
    Count -->|No| Invalid[is_passport = False]
    Count -->|Yes| Homography[Compute Homography]
    
    Homography --> Transform[Transform Page Quad]
    Transform --> Valid[is_passport = True]
    
    Valid --> Result[ValidationResult]
    Invalid --> Result
```

## Face Detection Workflow

```mermaid
flowchart TB
    Start[Validated Image] --> Quad{Page Quad Available?}
    
    Quad -->|No| FullImage[Use Full Image]
    Quad -->|Yes| CropPage[Crop to Page Quad]
    
    FullImage --> Detect[Run YuNet Detector]
    CropPage --> Detect
    
    Detect --> Faces{Faces Found?}
    
    Faces -->|No| NoFace[Return None]
    Faces -->|Yes| SelectBest[Select Highest Confidence]
    
    SelectBest --> MapCoords[Map to Original Coordinates]
    MapCoords --> Result[FaceDetectionResult]
```

## Face Cropping Workflow

```mermaid
flowchart TB
    Start[Face BBox] --> AddPadding[Add Padding]
    AddPadding --> ClipBounds[Clip to Image Bounds]
    
    ClipBounds --> Crop[Crop Region]
    Crop --> Encode[Encode as JPEG]
    
    Encode --> Result[FaceCropResult]
```

## LLM Extraction Workflow

```mermaid
flowchart TB
    Start[Loaded Image] --> Encode[Encode Image as Base64]
    Encode --> BuildPrompt[Build Extraction Prompt]
    
    BuildPrompt --> AddRules[Add Extraction Rules]
    AddRules --> AddSchema[Add PassportData Schema]
    
    AddSchema --> CallLLM[Call Requesty API]
    
    CallLLM --> Success{Success?}
    
    Success -->|No| Error[Raise ExtractionError]
    Success -->|Yes| Parse[Parse JSON Response]
    
    Parse --> Normalize[Normalize Dates & Sex]
    Normalize --> Validate[Validate with Pydantic]
    
    Validate --> Result[PassportData]
```

## Media Group Collection Workflow

```mermaid
sequenceDiagram
    participant User
    participant Bot
    participant Collector
    participant Scheduler
    
    User->>Bot: Send image 1 (media_group_id: ABC)
    Bot->>Collector: add(ABC, upload1)
    Collector->>Scheduler: Schedule flush (2s)
    
    User->>Bot: Send image 2 (media_group_id: ABC)
    Bot->>Collector: add(ABC, upload2)
    Collector->>Scheduler: Reschedule flush (2s)
    
    User->>Bot: Send image 3 (media_group_id: ABC)
    Bot->>Collector: add(ABC, upload3)
    Collector->>Scheduler: Reschedule flush (2s)
    
    Note over Scheduler: Wait 2 seconds...
    
    Scheduler->>Collector: flush_media_group(ABC)
    Collector->>Bot: Process batch [upload1, upload2, upload3]
    Bot->>User: Batch started message
    
    loop For each upload
        Bot->>Bot: Process upload
        Bot->>User: Send result
    end
```

## Deployment Workflow

```mermaid
flowchart TB
    Start[Push to main] --> Trigger[GitHub Actions Triggered]
    
    Trigger --> Checkout[Checkout Code]
    Checkout --> BuildImage[Build Docker Image]
    
    BuildImage --> TagImage[Tag with commit SHA]
    TagImage --> PushRegistry[Push to Registry]
    
    PushRegistry --> ConfigKubectl[Configure kubectl]
    ConfigKubectl --> ApplyManifests[Apply K8s Manifests]
    
    ApplyManifests --> Namespace[Create/Update Namespace]
    Namespace --> ConfigMap[Apply ConfigMap]
    ConfigMap --> Secret[Apply Secret]
    Secret --> PVC[Create PVC]
    PVC --> Deployment[Apply Deployment]
    
    Deployment --> Rollout[Rollout Restart]
    Rollout --> Wait[Wait for Rollout]
    
    Wait --> Success{Rollout Success?}
    
    Success -->|Yes| Verify[Verify Pod Status]
    Success -->|No| Fail[Deployment Failed]
    
    Verify --> Logs[Check Logs]
    Logs --> Complete[Deployment Complete]
```

## Local Development Workflow

```mermaid
flowchart TB
    Start[Clone Repository] --> Setup1[Setup passport-core]
    
    Setup1 --> InstallCore[uv sync --extra dev]
    InstallCore --> EnvCore[cp .env.example .env]
    EnvCore --> ConfigCore[Set PASSPORT_REQUESTY_API_KEY]
    
    ConfigCore --> Setup2[Setup passport-platform]
    Setup2 --> InstallPlatform[uv sync --extra dev]
    InstallPlatform --> EnvPlatform[cp .env.example .env]
    
    EnvPlatform --> Setup3[Setup passport-telegram]
    Setup3 --> InstallTelegram[uv sync --extra dev]
    InstallTelegram --> EnvTelegram[cp .env.example .env]
    EnvTelegram --> ConfigTelegram[Set BOT_TOKEN, ENV_FILES]
    
    ConfigTelegram --> Test[Run Tests]
    Test --> Lint[Run Linters]
    Lint --> Run[Run Bot]
    
    Run --> Dev[Development Ready]
```

## Testing Workflow

```mermaid
flowchart TB
    Start[Code Changes] --> Unit[Run Unit Tests]
    
    Unit --> UnitPass{Pass?}
    UnitPass -->|No| Fix1[Fix Issues]
    UnitPass -->|Yes| Contract[Run Contract Tests]
    
    Contract --> ContractPass{Pass?}
    ContractPass -->|No| Fix2[Fix Issues]
    ContractPass -->|Yes| Integration[Run Integration Tests]
    
    Integration --> IntPass{Pass?}
    IntPass -->|No| Fix3[Fix Issues]
    IntPass -->|Yes| Lint[Run Linters]
    
    Lint --> LintPass{Pass?}
    LintPass -->|No| Fix4[Fix Issues]
    LintPass -->|Yes| TypeCheck[Run Type Checker]
    
    TypeCheck --> TypePass{Pass?}
    TypePass -->|No| Fix5[Fix Issues]
    TypePass -->|Yes| Complete[All Checks Pass]
    
    Fix1 --> Unit
    Fix2 --> Contract
    Fix3 --> Integration
    Fix4 --> Lint
    Fix5 --> TypeCheck
```

## Error Handling Workflow

```mermaid
flowchart TB
    Start[Process Request] --> Try{Try Processing}
    
    Try -->|InputLoadError| Partial1[Return Partial Result]
    Try -->|ValidationError| Partial2[Return Partial Result]
    Try -->|FaceDetectionError| Partial3[Return Partial Result]
    Try -->|ExtractionError| Partial4[Return Partial Result]
    Try -->|StorageError| Exception1[Raise Exception]
    Try -->|Unexpected| Exception2[Raise Exception]
    Try -->|Success| Complete[Return Complete Result]
    
    Partial1 --> Record1[Record Error Details]
    Partial2 --> Record2[Record Error Details]
    Partial3 --> Record3[Record Error Details]
    Partial4 --> Record4[Record Error Details]
    
    Record1 --> Response[Return to Caller]
    Record2 --> Response
    Record3 --> Response
    Record4 --> Response
    Complete --> Response
    
    Exception1 --> Handler[Error Handler]
    Exception2 --> Handler
    
    Handler --> Log[Log Error]
    Log --> UserMessage[Send User Message]
    UserMessage --> Response
```

## Monitoring Workflow

```mermaid
flowchart TB
    Start[Application Running] --> Logs[Structured Logs]
    
    Logs --> LogLevel{Log Level}
    
    LogLevel -->|INFO| Info[Normal Operations]
    LogLevel -->|WARNING| Warn[Potential Issues]
    LogLevel -->|ERROR| Error[Failures]
    
    Info --> Collect[Log Aggregation]
    Warn --> Collect
    Error --> Collect
    
    Collect --> Analyze[Log Analysis]
    
    Analyze --> Metrics[Extract Metrics]
    Metrics --> Dashboard[Monitoring Dashboard]
    
    Dashboard --> Alert{Threshold Exceeded?}
    
    Alert -->|Yes| Notify[Send Alert]
    Alert -->|No| Continue[Continue Monitoring]
    
    Notify --> Investigate[Investigate Issue]
    Continue --> Start
```

## Backup and Recovery Workflow

```mermaid
flowchart TB
    Start[Scheduled Backup] --> CheckPVC[Check PVC Mount]
    
    CheckPVC --> BackupDB[Backup SQLite Database]
    BackupDB --> BackupImages[Backup Binary Storage]
    
    BackupImages --> Compress[Compress Archives]
    Compress --> Upload[Upload to S3/Backup Storage]
    
    Upload --> Verify[Verify Backup]
    Verify --> Success{Success?}
    
    Success -->|Yes| Log[Log Success]
    Success -->|No| Alert[Alert Failure]
    
    Log --> Cleanup[Cleanup Old Backups]
    Cleanup --> Complete[Backup Complete]
    
    Alert --> Retry{Retry?}
    Retry -->|Yes| BackupDB
    Retry -->|No| Fail[Backup Failed]
```
