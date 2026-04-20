# Telegram Queue UX — Rate-Limit-Safe Batch Processing

**Branch:** `enhance/ux-optimizations`
**Author:** kiro
**Created:** 2026-04-20

---

## Problem Analysis

### Root Cause — Confirmed

When a user sends 27 images, Telegram delivers them as media groups of ≤10.
The current bot receives 3 groups (10 + 10 + 7) and each group triggers an
independent `process_upload_batch()` call. These run concurrently because:

1. `flush_media_group` fires independently per `media_group_id` — each album
   gets its own timer and its own `process_upload_batch` invocation.
2. `InflightLimiter` has 20 global slots (`max_inflight_upload_batches=20`),
   so all 3 batches acquire permits simultaneously.
3. Inside each batch, results are sent via `send_message` / `send_photo`
   **immediately** after each extraction completes — no throttle.

Result: 3 concurrent loops fire Telegram API calls as fast as extraction
finishes. With 27 images, the bot can attempt 27+ messages (success photos +
batch-started texts) in rapid succession to the **same chat**. Telegram's
per-chat rate limit is ~1 msg/sec (20 msgs/min to same chat, 30 msgs/sec
globally). The bot gets throttled, `python-telegram-bot` retries with
exponential backoff, and delivery degrades to minutes between messages.

### Secondary Issues

- **No unified feedback**: Each batch sends its own "تم استلام X صور" message.
  User sees 3 separate "batch started" messages, then results interleaved
  randomly from all 3 concurrent batches. Confusing.
- **No progress visibility**: User has no idea what's happening, what's done,
  what failed, or how long to wait.
- **No per-user queuing**: If user A sends 27 images and user B sends 5, both
  compete for the same Telegram API budget.
- **Error messages are scattered**: Each failure sends a separate message,
  adding to the rate-limit pressure.

---

## Design

### Core Principle: Per-Chat Serial Queue with Live Status Message

Instead of N concurrent batch processors per user, we introduce a **per-chat
processing queue** with a single **live status message** that gets edited
in-place as processing progresses.

### Architecture

```
image_message_handler
        │
        ▼
  MediaGroupCollector (unchanged — still collects albums)
        │
        ▼
  flush_media_group
        │
        ▼
  ChatQueue.enqueue(uploads)  ← NEW: appends to per-chat queue
        │
        ▼
  ChatQueueWorker (one per active chat)  ← NEW: serial processor
        │
        ├─ Creates/edits a single status message
        ├─ Processes images one-by-one
        ├─ Edits status message after each completion
        ├─ Respects Telegram rate limits (≥1s between edits)
        └─ Sends inline keyboard buttons when actionable
```

### Key Components

#### 1. `ChatQueue` — Per-Chat FIFO Queue

```
chat_queues: dict[int, ChatQueue]  # keyed by chat_id
```

- Holds pending `TelegramImageUpload` items for a specific chat.
- When new uploads arrive and a worker is already running, they're appended.
- The worker picks them up in order — no concurrent processing per chat.

#### 2. `ChatQueueWorker` — Serial Processor

One asyncio task per active chat. Responsibilities:
- Drain the queue sequentially.
- Maintain a single "status message" via `edit_message_text`.
- Rate-limit outbound edits to ≥1.0s apart (safe margin under Telegram's
  ~1 msg/s per-chat limit).
- When queue is fully drained, send final summary and stop.

#### 3. Live Status Message

A single message that gets edited in-place. Structure:

```
📋 معالجة 27 جواز

✅ 1. محمد أحمد العلي — جاهز
✅ 2. فاطمة سعيد — جاهز
⏳ 3. جاري المعالجة...
⬚ 4–27: في الانتظار

❌ فشل: 0

[📥 عرض النتائج الجاهزة (2)]  [❌ تقرير الأخطاء]
```

As each image completes:
- Its line updates from ⬚ → ⏳ → ✅/❌
- The message is edited (throttled to 1 edit/sec)
- Inline keyboard buttons appear/update as results accumulate

#### 4. Inline Keyboard Interactions

**"عرض النتائج الجاهزة" button:**
- Sends individual result messages (photo + extracted data) for all completed
  passports, one per second, below the status message.
- Each result message matches the current format (photo + caption with
  extracted fields).
- Button label updates with count: `📥 عرض النتائج (5)` → `📥 عرض النتائج (12)`
- After clicking, results sent so far are marked as "delivered" — next click
  only sends new results since last click.

**"تقرير الأخطاء" button (appears only when failures exist):**
- Sends a single consolidated message listing all failures with:
  - Image number / filename
  - Short failure reason (not a passport, unclear image, processing error)
- If clicked again later, updates to include any new failures.
- PDF report is deferred to a future iteration — a clean text summary is
  sufficient and avoids complexity.

**"إيقاف المعالجة" button (optional, appears during processing):**
- Lets user cancel remaining queue items.
- Already-processed results are kept.

#### 5. Global Fairness — Round-Robin Across Chats

When multiple users are active simultaneously:
- A global worker pool (configurable, default 4 concurrent extractions).
- Workers pull from active chat queues in round-robin order.
- This ensures user B's 5 images don't wait behind user A's remaining 20.
- Telegram API calls are rate-limited per-chat (1/sec) AND globally (≤25/sec
  with safety margin).

#### 6. Rate Limiter

Simple token-bucket per chat_id:
- 1 message/edit per second per chat (Telegram's actual limit is ~20/min,
  so 1/sec = 60/min, but edits are cheaper — Telegram counts them less
  strictly; 1/sec is safe).
- Global: ≤25 API calls/sec across all chats.

---

## Status Message Lifecycle

```
1. First image(s) arrive → create status message:
   "📋 تم استلام 10 جوازات — جاري المعالجة..."

2. More images arrive (second album) → edit status message:
   "📋 تم استلام 20 جواز — جاري المعالجة..."
   (queue grows, worker keeps going)

3. Third album arrives → edit again:
   "📋 معالجة 27 جواز"
   + progress lines

4. As each completes → edit with updated progress

5. All done → final edit:
   "✅ اكتملت معالجة 27 جواز
    ✅ ناجح: 24  ❌ فشل: 3

    [📥 عرض جميع النتائج (24)]  [❌ تفاصيل الأخطاء (3)]"
```

---

## Implementation Plan

### Phase 1: Core Queue Infrastructure
**Files:** `bot.py`, `config.py`

- [ ] 1.1 — Add `ChatQueue` dataclass: per-chat FIFO + status message ID +
  result tracking (successes list, failures list, delivered set).
- [ ] 1.2 — Add `ChatQueueManager`: manages `dict[int, ChatQueue]`, handles
  enqueue, worker lifecycle, cleanup.
- [ ] 1.3 — Add rate limiter: per-chat edit throttle (1/sec) using
  `asyncio.Event` + timestamp tracking.
- [ ] 1.4 — Add config fields to `TelegramSettings`:
  - `max_concurrent_extractions: int = 4`
  - `chat_message_interval_seconds: float = 1.0`
- [ ] 1.5 — Replace direct `process_upload_batch` calls with
  `ChatQueueManager.enqueue()` in `flush_media_group` and
  `image_message_handler`.
- [ ] 1.6 — Implement `ChatQueueWorker`: serial drain loop with status
  message creation/editing.

### Phase 2: Live Status Message
**Files:** `bot.py`, `messages.py`

- [ ] 2.1 — Add status message builder functions to `messages.py`:
  - `queue_status_text(total, completed, failed, processing_index, names)`
  - `queue_complete_text(total, success_count, fail_count)`
- [ ] 2.2 — Implement status message create → edit cycle in worker.
- [ ] 2.3 — Handle Telegram `MessageNotModified` error gracefully (skip
  edit if content unchanged).
- [ ] 2.4 — Compact display: show individual names for ≤15 items, summary
  counts for larger batches.

### Phase 3: Inline Keyboard & Result Delivery
**Files:** `bot.py`, `messages.py`

- [ ] 3.1 — Add `CallbackQueryHandler` for result/error button presses.
- [ ] 3.2 — Implement "عرض النتائج الجاهزة" callback: sends result messages
  (photo + caption) for un-delivered successes, rate-limited at 1/sec.
- [ ] 3.3 — Implement "تقرير الأخطاء" callback: sends consolidated failure
  summary message.
- [ ] 3.4 — Track delivered results per queue to avoid re-sending.
- [ ] 3.5 — Update inline keyboard after each callback (remove button if
  nothing new to show, update counts).

### Phase 4: Global Fairness
**Files:** `bot.py`

- [ ] 4.1 — Replace `InflightLimiter` with a global extraction semaphore
  (bounds concurrent `process_bytes` calls across all chats).
- [ ] 4.2 — Round-robin scheduling: when a worker awaits the semaphore, it
  yields to let other chat workers proceed.

### Phase 5: Edge Cases & Polish
**Files:** `bot.py`, `messages.py`

- [ ] 5.1 — Handle user sending new batch while previous is still processing
  (append to existing queue, update status message).
- [ ] 5.2 — Handle quota exhaustion mid-queue (stop processing, update status,
  inform user).
- [ ] 5.3 — Handle user block mid-queue.
- [ ] 5.4 — Cleanup: remove chat queue after idle timeout (5 min).
- [ ] 5.5 — Graceful shutdown: drain or cancel active workers on bot stop.

---

## What Gets Removed / Replaced

| Current | Replacement |
|---|---|
| `InflightLimiter` (global semaphore, 20 slots) | Global extraction semaphore (4 slots) + per-chat serial queue |
| `process_upload_batch()` (processes entire batch inline) | `ChatQueueWorker` (serial, rate-limited) |
| Direct `send_message`/`send_photo` per result | Single editable status message + on-demand result delivery |
| `batch_started_text()` | `queue_status_text()` (live-updating) |
| Scattered error messages | Consolidated in status message + error report button |

## What Stays Unchanged

- `MediaGroupCollector` — still needed to collect album images before queuing
- `_extract_upload`, `_download_upload` — upload handling logic is fine
- `ProcessingService.process_bytes` — core extraction is untouched
- All command handlers (`/start`, `/help`, `/me`, `/token`, `/masar`, `/extension`)
- `messages.py` success/failure formatting — reused in result delivery
- Platform layer — no changes needed

---

## Telegram Rate Limit Reference

| Scope | Limit |
|---|---|
| Same chat | ~20 messages/minute (~1/3sec, but edits are cheaper) |
| Global (all chats) | ~30 messages/second |
| Inline keyboard callbacks | No separate limit, counts as message |
| `editMessageText` | Counts toward chat limit but less strictly enforced |

Our design targets 1 edit/sec per chat (well within limits) and ≤25 global
API calls/sec (safe margin).

---

## Config Defaults (New)

```python
max_concurrent_extractions: int = 4        # global extraction parallelism
chat_message_interval_seconds: float = 1.0 # min seconds between edits to same chat
queue_idle_cleanup_seconds: float = 300.0  # remove idle chat queues after 5 min
```
