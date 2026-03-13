# Components

## Package Components

### passport-core

#### PassportWorkflow
**Purpose**: Public adapter-facing API for passport processing

**Responsibilities**:
- Load images from files, URLs, or bytes
- Validate passport using SIFT feature matching
- Detect faces using YuNet model
- Crop faces with bounding box mapping
- Extract structured data via LLM
- Return unified workflow results

**Key Methods**:
- `process_source(path)` - Process from file/URL
- `process_bytes(bytes, filename, mime_type, source)` - Process from bytes
- `load_source(path)` - Load image
- `validate_passport(loaded)` - Validate passport
- `detect_face(loaded, page_quad)` - Detect face
- `crop_face(loaded, bbox)` - Crop face
- `extract_data(loaded)` - Extract fields

**Dependencies**: Settings, ImageLoader, PassportFeatureValidator, PassportFaceDetector, PassportFaceCropper, PassportExtractor

---

#### PassportCoreService
**Purpose**: Internal CLI pipeline orchestration

**Responsibilities**:
- Batch processing of multiple sources
- Binary artifact persistence
- Result record storage
- Error accumulation
- CSV export for Enjaz integration

**Key Methods**:
- `process_source(source)` - Process single source
- `process_sources(sources)` - Batch processing
- `export_results_csv(path)` - Export to CSV
- `crop_face(source)` - Face crop only

**Note**: Adapters should use `PassportWorkflow`, not this service.

---

#### PassportFeatureValidator
**Purpose**: Validate passport using SIFT feature matching

**Responsibilities**:
- Load and mask passport template
- Detect SIFT keypoints and descriptors
- Match features between template and input
- Calculate match confidence
- Detect page quadrilateral

**Configuration**:
- `PASSPORT_TEMPLATE_PATH` - Template image path
- `PASSPORT_MIN_MATCH_COUNT` - Minimum matches (default: 10)
- `PASSPORT_MATCH_RATIO_THRESHOLD` - Match quality (default: 0.7)

---

#### PassportFaceDetector
**Purpose**: Detect faces using YuNet ONNX model

**Responsibilities**:
- Load YuNet face detection model
- Detect faces in images
- Map bounding boxes from cropped regions
- Return face coordinates

**Configuration**:
- `PASSPORT_FACE_MODEL_PATH` - YuNet model path
- `PASSPORT_FACE_SCORE_THRESHOLD` - Detection confidence (default: 0.6)
- `PASSPORT_FACE_NMS_THRESHOLD` - Non-max suppression (default: 0.3)

---

#### PassportFaceCropper
**Purpose**: Crop detected faces with padding

**Responsibilities**:
- Crop face region from image
- Apply configurable padding
- Clip to image boundaries
- Return cropped face bytes

**Configuration**:
- `PASSPORT_FACE_CROP_PADDING` - Padding ratio (default: 0.2)

---

#### PassportExtractor (PydanticAIRequestyExtractor)
**Purpose**: Extract structured passport fields using LLM

**Responsibilities**:
- Format extraction prompt with rules
- Call Requesty AI router
- Parse LLM response into PassportData
- Normalize dates and sex values
- Handle extraction errors

**Configuration**:
- `PASSPORT_REQUESTY_API_KEY` - API key (required)
- `PASSPORT_REQUESTY_BASE_URL` - Router URL
- `PASSPORT_LLM_MODEL` - Model name (default: openai-responses/gpt-5-mini)

**Extracted Fields**:
- PassportNumber, CountryCode
- MrzLine1, MrzLine2
- SurnameAr, GivenNamesAr, SurnameEn, GivenNamesEn
- DateOfBirth, PlaceOfBirthAr, PlaceOfBirthEn
- Sex, DateOfIssue, DateOfExpiry
- ProfessionAr, ProfessionEn
- IssuingAuthorityAr, IssuingAuthorityEn

---

#### ImageLoader
**Purpose**: Load images from various sources

**Responsibilities**:
- Load from local files
- Download from HTTP/HTTPS URLs
- Enforce size limits
- Block localhost URLs
- Decode images
- Detect MIME types

**Configuration**:
- `PASSPORT_MAX_DOWNLOAD_BYTES` - Download limit (default: 10MB)

---

#### BinaryStore (LocalFileStore / S3FileStore)
**Purpose**: Store binary artifacts (images, face crops)

**Responsibilities**:
- Save original images
- Save cropped faces
- Generate unique filenames
- Organize by date (YYYYMMDD)
- Return storage URIs

**Configuration**:
- `PASSPORT_STORAGE_BACKEND` - local or s3
- `PASSPORT_LOCAL_STORAGE_DIR` - Local directory (default: data)
- `PASSPORT_S3_BUCKET` - S3 bucket name
- `PASSPORT_S3_REGION` - S3 region
- `PASSPORT_S3_ACCESS_KEY_ID` - AWS access key
- `PASSPORT_S3_SECRET_ACCESS_KEY` - AWS secret key

---

#### ResultStore (SqliteResultStore / JsonResultStore / CsvResultStore)
**Purpose**: Persist processing results

**Responsibilities**:
- Save processing results
- Fetch results by ID
- Support multiple backends
- Export to CSV

**Configuration**:
- `PASSPORT_DATA_STORE_BACKEND` - sqlite, json, or csv
- `PASSPORT_DATA_STORE_PATH` - Storage path (default: data)

---

### passport-platform

#### ProcessingService
**Purpose**: Orchestrate processing with user/quota/upload tracking

**Responsibilities**:
- Resolve or create users
- Check quotas before processing
- Register uploads
- Execute passport-core workflow
- Record processing results
- Update usage ledger
- Handle errors with proper codes

**Key Methods**:
- `process_bytes(command)` - Process upload with tracking

**Dependencies**: UserService, QuotaService, UploadService, PassportWorkflow

---

#### UserService
**Purpose**: Manage users and external identities

**Responsibilities**:
- Get or create users by external identity
- Map external providers (telegram, api)
- Change user status (active, blocked)
- Change user plans (free, pro, enterprise)

**Key Methods**:
- `get_or_create_user(command)` - Ensure user exists
- `get_by_external_identity(provider, identity)` - Lookup user
- `change_status(user_id, status)` - Update status
- `change_plan(user_id, plan)` - Update plan

**Dependencies**: UsersRepository

---

#### QuotaService
**Purpose**: Enforce plan-based usage limits

**Responsibilities**:
- Evaluate monthly quotas
- Check upload limits
- Check success limits
- Return quota decisions with remaining counts

**Key Methods**:
- `evaluate_user_quota(user_id, plan, month_window)` - Check quota
- `assert_can_upload(user_id, plan)` - Raise if exceeded

**Dependencies**: UsageRepository, PlanPolicy

---

#### UploadService
**Purpose**: Track uploads and processing results

**Responsibilities**:
- Register new uploads
- Get upload by source reference
- Mark uploads as processing
- Record processing results
- Update upload status
- Record usage events

**Key Methods**:
- `register_upload(command)` - Create upload record
- `get_upload(upload_id)` - Fetch upload
- `mark_processing(upload_id)` - Update status
- `record_processing_result(command)` - Save result

**Dependencies**: UploadsRepository, UsageRepository

---

#### UsersRepository
**Purpose**: Data access for users table

**Responsibilities**:
- CRUD operations on users
- Query by external identity
- Update status and plan

**Key Methods**:
- `create(user)` - Insert user
- `get_by_id(user_id)` - Fetch by ID
- `get_by_external_identity(provider, identity)` - Fetch by external ID
- `update_status(user_id, status)` - Update status
- `update_plan(user_id, plan)` - Update plan

---

#### UploadsRepository
**Purpose**: Data access for uploads and processing results

**Responsibilities**:
- CRUD operations on uploads
- CRUD operations on processing_results
- Query by source reference
- Update upload status

**Key Methods**:
- `create(upload)` - Insert upload
- `get_by_id(upload_id)` - Fetch upload
- `get_by_source_ref(source_ref)` - Fetch by reference
- `update_status(upload_id, status)` - Update status
- `create_processing_result(result)` - Insert result
- `get_processing_result(upload_id)` - Fetch result

---

#### UsageRepository
**Purpose**: Data access for usage ledger

**Responsibilities**:
- Record usage events
- Sum usage units for time periods
- Support quota calculations

**Key Methods**:
- `record(entry)` - Insert usage entry
- `sum_units_for_period(user_id, event_type, start, end)` - Aggregate usage

---

#### PlanPolicy
**Purpose**: Define plan limits and features

**Responsibilities**:
- Define monthly upload limits
- Define monthly success limits
- Support plan upgrades

**Plans**:
- **Free**: 10 uploads/month, 5 successes/month
- **Pro**: 100 uploads/month, 50 successes/month
- **Enterprise**: Unlimited

---

### passport-telegram

#### BotServices
**Purpose**: Manage bot lifecycle and dependencies

**Responsibilities**:
- Initialize processing service
- Initialize database connection
- Provide cleanup on shutdown

**Key Methods**:
- `__init__()` - Setup services
- `close()` - Cleanup resources

**Dependencies**: Database, ProcessingService, Settings

---

#### MediaGroupCollector
**Purpose**: Collect and batch media group uploads

**Responsibilities**:
- Collect images from media groups
- Wait for collection window
- Flush batches for processing
- Handle timeouts

**Configuration**:
- `PASSPORT_TELEGRAM_ALBUM_COLLECTION_WINDOW_SECONDS` - Wait time (default: 2)
- `PASSPORT_TELEGRAM_MAX_IMAGES_PER_BATCH` - Batch limit (default: 10)

**Key Methods**:
- `add(media_group_id, upload)` - Add to group
- `pop(media_group_id)` - Get and remove group
- `flush_media_group(media_group_id)` - Process batch

---

#### Message Handlers
**Purpose**: Handle Telegram bot commands and messages

**Handlers**:
- `start_command` - Welcome message
- `help_command` - Help text
- `image_message_handler` - Process image uploads
- `telegram_error_handler` - Handle errors

**Responsibilities**:
- Validate chat authorization
- Download image bytes
- Collect media groups
- Process uploads
- Format responses in Arabic
- Send media groups with captions

---

#### Message Formatters
**Purpose**: Format bot responses in Arabic

**Functions**:
- `welcome_text()` - Welcome message
- `help_text()` - Help instructions
- `batch_started_text(count)` - Batch processing notification
- `format_success_text(data)` - Success response with fields
- `format_failure_text(result)` - Error messages
- `unsupported_file_text()` - Unsupported file type
- `unauthorized_text()` - Unauthorized chat
- `processing_error_text()` - Generic error
- `quota_exceeded_text(decision)` - Quota limit reached
- `user_blocked_text()` - Blocked user

---

## Component Interaction Patterns

### Adapter → Platform → Core
```
passport-telegram
  ↓ (process_bytes)
passport-platform.ProcessingService
  ↓ (process_bytes)
passport-core.PassportWorkflow
  ↓ (returns)
PassportWorkflowResult
```

### Service → Repository → Database
```
UserService
  ↓ (get_by_external_identity)
UsersRepository
  ↓ (SQL query)
SQLite Database
```

### Workflow Stages
```
PassportWorkflow
  → load_source()
  → validate_passport()
  → detect_face()
  → crop_face()
  → extract_data()
  → PassportWorkflowResult
```

## Component Testing Strategies

### passport-core
- **Unit Tests**: Mock dependencies, test individual components
- **Contract Tests**: Golden samples with expected outputs
- **Integration Tests**: End-to-end workflow with real models

### passport-platform
- **Unit Tests**: Test services with fake repositories
- **Integration Tests**: Test with real SQLite database
- **Quota Tests**: Verify plan limits and enforcement

### passport-telegram
- **Unit Tests**: Test message formatting
- **Integration Tests**: Test bot handlers with fake services
- **Media Group Tests**: Test collection and batching logic
