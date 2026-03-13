# Interfaces and APIs

## Public Package APIs

### passport-core

#### PassportWorkflow API

```python
from passport_core import PassportWorkflow, Settings

# Initialize
settings = Settings()
workflow = PassportWorkflow(settings=settings)

# Process from file/URL
result = workflow.process_source("path/to/passport.jpg")

# Process from bytes
result = workflow.process_bytes(
    image_bytes=bytes,
    filename="passport.jpg",
    mime_type="image/jpeg",
    source="telegram://file/123"
)

# Stage-by-stage processing
loaded = workflow.load_source("path/to/passport.jpg")
validation = workflow.validate_passport(loaded)
face = workflow.detect_face(loaded, validation.page_quad)
crop = workflow.crop_face(loaded, face.bbox_original)
data = workflow.extract_data(loaded)

# Cleanup
workflow.close()
```

#### PassportWorkflowResult

```python
@dataclass
class PassportWorkflowResult:
    source: str
    filename: str
    mime_type: str
    image_bytes: bytes
    loaded: LoadedImage | None
    validation: ValidationResult | None
    face: FaceDetectionResult | None
    face_crop: FaceCropResult | None
    data: PassportData | None
    
    @property
    def is_complete(self) -> bool:
        """True when validation, face crop, and extraction all succeed"""
    
    @property
    def has_face_crop(self) -> bool:
        """True when face crop is available"""
    
    @property
    def face_crop_bytes(self) -> bytes | None:
        """Cropped face image bytes"""
```

#### PassportData

```python
class PassportData(BaseModel):
    PassportNumber: str | None
    CountryCode: str | None
    MrzLine1: str | None
    MrzLine2: str | None
    SurnameAr: str | None
    GivenNamesAr: str | None
    SurnameEn: str | None
    GivenNamesEn: str | None
    DateOfBirth: str | None
    PlaceOfBirthAr: str | None
    PlaceOfBirthEn: str | None
    Sex: str | None
    DateOfIssue: str | None
    DateOfExpiry: str | None
    ProfessionAr: str | None
    ProfessionEn: str | None
    IssuingAuthorityAr: str | None
    IssuingAuthorityEn: str | None
```

#### Settings

```python
class Settings(BaseSettings):
    # Paths
    template_path: Path
    face_model_path: Path
    
    # Storage
    storage_backend: Literal["local", "s3"]
    local_storage_dir: Path
    s3_bucket: str | None
    s3_region: str | None
    
    # Data store
    data_store_backend: Literal["sqlite", "json", "csv"]
    data_store_path: Path
    
    # LLM
    llm_model: str
    requesty_api_key: str
    requesty_base_url: str
    
    # Validation
    min_match_count: int
    match_ratio_threshold: float
    
    # Face detection
    face_score_threshold: float
    face_nms_threshold: float
    face_crop_padding: float
    
    # Limits
    max_download_bytes: int
    
    # Logging
    log_level: str
    log_json: bool
```

---

### passport-platform

#### ProcessingService API

```python
from passport_platform import ProcessingService, ProcessUploadCommand

# Initialize
service = ProcessingService(
    users=user_service,
    quotas=quota_service,
    uploads=upload_service,
    workflow=passport_workflow
)

# Process upload
command = ProcessUploadCommand(
    image_bytes=bytes,
    filename="passport.jpg",
    mime_type="image/jpeg",
    source_ref="telegram://file/123",
    channel=ChannelName.TELEGRAM,
    external_provider=ExternalProvider.TELEGRAM,
    external_identity="user_123"
)

result = service.process_bytes(command)

# Cleanup
service.close()
```

#### TrackedProcessingResult

```python
@dataclass
class TrackedProcessingResult:
    upload_id: int
    user_id: int
    success: bool
    workflow_result: PassportWorkflowResult
    usage_tokens: int | None
    error_code: str | None
```

#### UserService API

```python
from passport_platform import UserService, EnsureUserCommand

# Get or create user
command = EnsureUserCommand(
    external_provider=ExternalProvider.TELEGRAM,
    external_identity="user_123"
)
user = user_service.get_or_create_user(command)

# Change status
user_service.change_status(user_id=1, status=UserStatus.BLOCKED)

# Change plan
user_service.change_plan(user_id=1, plan=PlanName.PRO)
```

#### QuotaService API

```python
from passport_platform import QuotaService

# Check quota
decision = quota_service.evaluate_user_quota(
    user_id=1,
    plan=PlanName.FREE,
    month_window=(start_date, end_date)
)

# Assert can upload (raises QuotaExceededError if exceeded)
quota_service.assert_can_upload(user_id=1, plan=PlanName.FREE)
```

#### UploadService API

```python
from passport_platform import UploadService, RegisterUploadCommand

# Register upload
command = RegisterUploadCommand(
    user_id=1,
    source_ref="telegram://file/123",
    channel=ChannelName.TELEGRAM
)
upload = upload_service.register_upload(command)

# Mark processing
upload_service.mark_processing(upload_id=1)

# Record result
result_command = RecordProcessingResultCommand(
    upload_id=1,
    success=True,
    workflow_result=workflow_result,
    usage_tokens=1500
)
upload_service.record_processing_result(result_command)
```

#### Database API

```python
from passport_platform import Database, PlatformSettings

# Initialize
settings = PlatformSettings()
db = Database.from_settings(settings)
db.initialize()

# Transaction context
with db.transaction() as conn:
    # Execute queries
    conn.execute("INSERT INTO users ...")
```

---

### passport-telegram

#### Bot Application

```python
from passport_telegram import build_application, TelegramSettings

# Build application
settings = TelegramSettings()
application = build_application(settings)

# Run bot
application.run_polling()
```

#### TelegramSettings

```python
class TelegramSettings(BaseSettings):
    bot_token: str
    core_env_file: Path
    platform_env_file: Path
    allowed_chat_ids: str | None
    album_collection_window_seconds: float
    max_images_per_batch: int
    log_level: str
    
    def allowed_chat_id_set(self) -> set[int]:
        """Parse comma-separated chat IDs"""
```

---

## Internal Interfaces

### Repository Interfaces

#### UsersRepository

```python
class UsersRepository:
    def create(self, user: User) -> User
    def get_by_id(self, user_id: int) -> User | None
    def get_by_external_identity(
        self, provider: ExternalProvider, identity: str
    ) -> User | None
    def update_status(self, user_id: int, status: UserStatus) -> None
    def update_plan(self, user_id: int, plan: PlanName) -> None
```

#### UploadsRepository

```python
class UploadsRepository:
    def create(self, upload: Upload) -> Upload
    def get_by_id(self, upload_id: int) -> Upload | None
    def get_by_source_ref(self, source_ref: str) -> Upload | None
    def update_status(self, upload_id: int, status: UploadStatus) -> None
    def create_processing_result(
        self, result: ProcessingResult
    ) -> ProcessingResult
    def get_processing_result(
        self, upload_id: int
    ) -> ProcessingResult | None
```

#### UsageRepository

```python
class UsageRepository:
    def record(self, entry: UsageLedgerEntry) -> UsageLedgerEntry
    def sum_units_for_period(
        self,
        user_id: int,
        event_type: UsageEventType,
        start: datetime,
        end: datetime
    ) -> int
```

---

## CLI Interfaces

### passport-core CLI

```bash
# Process files
passport-core process <files...> [options]

# Process directory
passport-core process-dir <directory> [options]

# Crop face only
passport-core crop-face <file> [options]

# Simulate agency batch
passport-core simulate-agency <files...> [options]

Options:
  --pretty              Pretty-print JSON output
  --out-json PATH       Export results to JSON
  --csv-output PATH     Export to Enjaz CSV format
  --recursive           Process directories recursively
```

### passport-benchmark CLI

```bash
passport-benchmark [options]

Options:
  --models MODELS       Comma-separated model names
  --api-key KEY         Requesty API key
  --pricing-json PATH   Pricing metadata file
  --out-json PATH       Output results file
```

### passport-telegram CLI

```bash
passport-telegram

# Reads configuration from environment or .env file
```

---

## Error Interfaces

### passport-core Errors

```python
class PassportCoreError(Exception):
    """Base error"""

class InputLoadError(PassportCoreError):
    """Failed to load image"""

class ValidationError(PassportCoreError):
    """Passport validation failed"""

class FaceDetectionError(PassportCoreError):
    """Face detection failed"""

class ExtractionError(PassportCoreError):
    """LLM extraction failed"""

class StorageError(PassportCoreError):
    """Storage operation failed"""
```

### passport-platform Errors

```python
class PlatformError(Exception):
    """Base error"""

class UserBlockedError(PlatformError):
    """User is blocked"""

class QuotaExceededError(PlatformError):
    """Quota limit reached"""
    quota_decision: QuotaDecision

class UnsupportedExternalProviderError(PlatformError):
    """Unknown external provider"""

class UnsupportedChannelError(PlatformError):
    """Unknown channel"""

class ProcessingFailedError(PlatformError):
    """Processing failed"""
    error_code: str
```

---

## Integration Points

### Requesty AI Router

```python
# HTTP POST to Requesty
POST {requesty_base_url}/chat/completions
Headers:
  Authorization: Bearer {api_key}
  Content-Type: application/json

Body:
{
  "model": "openai-responses/gpt-5-mini",
  "messages": [
    {
      "role": "user",
      "content": [
        {"type": "text", "text": "..."},
        {"type": "image_url", "image_url": {"url": "data:image/jpeg;base64,..."}}
      ]
    }
  ]
}

Response:
{
  "choices": [
    {
      "message": {
        "content": "{...passport data JSON...}"
      }
    }
  ],
  "usage": {
    "total_tokens": 1500
  }
}
```

### Telegram Bot API

```python
# python-telegram-bot wrapper
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler

# Handlers
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE)
async def image_message_handler(update: Update, context: ContextTypes.DEFAULT_TYPE)

# Download file
file = await context.bot.get_file(photo.file_id)
bytes_io = BytesIO()
await file.download_to_memory(bytes_io)
image_bytes = bytes_io.getvalue()

# Send media group
await context.bot.send_media_group(
    chat_id=chat_id,
    media=[
        InputMediaPhoto(original_bytes, caption="..."),
        InputMediaPhoto(face_bytes)
    ]
)
```

### SQLite Database

```python
# Connection
conn = sqlite3.connect(db_path)
conn.row_factory = sqlite3.Row

# Transactions
with conn:
    conn.execute("INSERT INTO users ...")

# Queries
cursor = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,))
row = cursor.fetchone()
```

---

## Configuration Interfaces

### Environment Variables

All packages use environment-based configuration with prefixes:
- `PASSPORT_*` - passport-core settings
- `PASSPORT_PLATFORM_*` - passport-platform settings
- `PASSPORT_TELEGRAM_*` - passport-telegram settings

### Kubernetes ConfigMap

```yaml
apiVersion: v1
kind: ConfigMap
metadata:
  name: passport-telegram-config
data:
  PASSPORT_STORAGE_BACKEND: "local"
  PASSPORT_DATA_STORE_BACKEND: "sqlite"
  PASSPORT_LLM_MODEL: "openai-responses/gpt-5-mini"
  # ... more settings
```

### Kubernetes Secret

```yaml
apiVersion: v1
kind: Secret
metadata:
  name: passport-telegram-secret
type: Opaque
stringData:
  PASSPORT_TELEGRAM_BOT_TOKEN: "..."
  PASSPORT_REQUESTY_API_KEY: "..."
```
