# Plan: Android MVP — Local-LLM Gmail Tagger

**Status:** Not started  
**Napkin item:** `[ ] [2026-05-22] Android app: local-LLM Gmail tagger`

## Goal

Build an Android app replicating `tagger_flask.py` features (email fetch, auto-tag review, commit) but using a local LLM (TinyLlama) for reasoning instead of a remote API. Users can review Gmail emails and apply tags/delete decisions entirely on-device.

## OAuth Setup (Reuse Existing Google Cloud Project)

You already have a Google Cloud project (`luizwagnerlwtn`) registered. No new setup needed — just add Android as a platform:

### 1. Get Android Signing Key SHA-1

```bash
# For debug builds (development)
keytool -list -v -keystore ~/.android/debug.keystore -alias androiddebugkey \
  -storepass android -keypass android | grep SHA1

# For release builds (when ready to ship)
keytool -list -v -keystore /path/to/your/keystore.jks -alias release_key -storepass <password>
```

Copy the SHA-1 value (format: `XX:XX:XX:...`).

### 2. Configure in Google Cloud Console

1. Go to [console.cloud.google.com](https://console.cloud.google.com)
2. Select project `luizwagnerlwtn`
3. Navigate to **APIs & Services** → **Credentials**
4. Find your existing OAuth 2.0 Client ID (`64767593908-...`)
5. Click it to open the details page
6. Scroll to **Authorized platforms** / **Android**
7. Click **Add** and paste your SHA-1 from step 1
8. Save

### 3. Use Client ID in Android App

```gradle
// In build.gradle (or AndroidManifest.xml)
// No need to change — use the same client_id: 64767593908-fh73f9k5ue98epeta0u2ro2m8mjmkoq5.apps.googleusercontent.com
```

The same OAuth credentials work for both desktop and Android. Token storage is separate (desktop uses `token.json`, Android uses `CredentialManager` or `EncryptedSharedPreferences`).

---

## Key Design Principles

- **On-device inference**: TinyLlama (GGUF ~600MB) bundled locally via `llama.cpp` Android NDK or MediaPipe LLM runtime — no API calls for reasoning
- **Feature parity with Flask UI**: Email list with swipe actions, tag picker modal, commit button, visual states (pending, accepted, deleted, committed)
- **Offline-capable**: Queue commits locally if no network; sync when connectivity returns
- **Examples sync**: Import/export `examples.json` from desktop Flask session to seed training data on mobile

## Architecture

### Tech Stack
- **Language**: Kotlin
- **UI**: Jetpack Compose (single activity, reactive state)
- **Gmail API**: Google Sign-In SDK + Gmail API client library for Android
- **Local LLM**: TinyLlama (GGUF) via:
  - Option A: `llama.cpp` JNI/NDK bindings (fast, full control)
  - Option B: MediaPipe LLM Inference API (managed, simpler integration)
- **Local storage**: Android DataStore or Room DB (for `examples.json` equivalents, pending commits queue)
- **Threading**: Coroutines for async LLM inference, API calls, file I/O

### File Structure
```
android/
├── build.gradle.kts (project config)
├── app/build.gradle.kts
├── app/src/main/
│   ├── kotlin/com/example/gmailtagger/
│   │   ├── MainActivity.kt
│   │   ├── auth/
│   │   │   ├── GoogleSignInManager.kt
│   │   │   └── TokenCache.kt
│   │   ├── api/
│   │   │   ├── GmailApiClient.kt
│   │   │   └── EmailModel.kt
│   │   ├── llm/
│   │   │   ├── LlamaInference.kt (wrapper around llama.cpp JNI)
│   │   │   ├── AutoTagger.kt (Kotlin port of auto_tag_email logic)
│   │   │   └── PromptBuilder.kt (few-shot prompt from examples.json)
│   │   ├── storage/
│   │   │   ├── ExamplesRepository.kt (load/save examples.json)
│   │   │   ├── PendingCommitsQueue.kt (queue for offline commits)
│   │   │   └── CacheManager.kt (TinyLlama GGUF file management)
│   │   ├── ui/
│   │   │   ├── EmailListScreen.kt (email list with row actions)
│   │   │   ├── TagPickerModal.kt (modal with chosen/available sections)
│   │   │   ├── RowState.kt (data class for email row state)
│   │   │   └── MainViewModel.kt (state management)
│   │   └── MainApp.kt (App composable, theme)
│   └── res/
│       ├── values/strings.xml
│       ├── assets/models/tinyllama.gguf (~600MB)
│       └── drawable/ (icons, etc.)
├── llama_cpp_jni/
│   ├── build.gradle.kts
│   └── src/main/cpp/
│       ├── llama_inference.cpp
│       └── CMakeLists.txt
└── test/ (unit tests for AutoTagger, PromptBuilder, etc.)
```

## Implementation Phases

### Phase 1: Foundation (Weeks 1–2)
- [ ] **Pre-requisite**: Complete "OAuth Setup" section above (add Android platform to Google Cloud, get SHA-1)
- [ ] Project setup: Gradle, Kotlin, Jetpack Compose, AndroidX
- [ ] Google Sign-In + Gmail API client library (read emails, list labels)
- [ ] Fetch first batch of unread emails (paginated, like `fetch_emails.py`)
- [ ] Store OAuth tokens securely (Encrypted Shared Preferences or CredentialManager)
- [ ] Build MainViewModel for email list state

**Deliverable**: App can authenticate and display 10 unread emails in a list.

### Phase 2: LLM Integration (Weeks 3–4)
- [ ] Download and bundle TinyLlama GGUF (~600MB) into APK `assets/models/`
- [ ] Integrate `llama.cpp` JNI bindings:
  - Option A: Use existing Android binding (e.g., `llama-android` library if available)
  - Option B: Compile llama.cpp via NDK, wrap in Kotlin
- [ ] Implement `LlamaInference.kt` wrapper with async inference (coroutines)
- [ ] Port `auto_tag_email()` logic from Python → Kotlin (label scoring, delete detection)
- [ ] Implement `PromptBuilder.kt` to format few-shot examples + current email into prompt
- [ ] Test inference latency and memory footprint

**Deliverable**: App can auto-tag the first email using on-device LLM. Output shows action + reasoning.

### Phase 3: UI Review & Actions (Weeks 5–6)
- [ ] Build `EmailListScreen.kt`:
  - Row layout: # | From | Subject | Snippet | Suggestion | Actions | Status
  - Action buttons: ✓ (accept) | 🗑 (delete) | 🏷 (tag picker) | → (skip)
  - Row background color for pending/accepted/deleted/committed states
- [ ] Implement swipe gestures (optional: swipe-left to delete, swipe-right to accept)
- [ ] Build tag picker modal:
  - Chosen section (tags selected, click ✕ to remove)
  - Available list (click + to add, filter by name)
  - Frequent labels first, then A–Z with separator
  - Pre-populate with LLM suggestion
- [ ] Implement `acceptRow()`, `deleteRow()`, `tagRow()`, `skipRow()` in ViewModel

**Deliverable**: Full email review UI matching Flask dashboard UX. Can manually override LLM suggestions and visually confirm state changes.

### Phase 4: Persistence & Offline (Weeks 7–8)
- [ ] Implement `ExamplesRepository.kt`:
  - Load/save `examples_{project_id}.json` to app-specific directory
  - Schema: `{ id, from, subject, snippet, action, reasoning }`
- [ ] Implement `PendingCommitsQueue.kt`:
  - Queue decisions locally (Room DB table: email_id, action, from, subject, snippet, status)
  - Mark rows as "⏳ queued" in UI when network unavailable
- [ ] Implement commit flow:
  - Build list of pending decisions (ViewModel filters rows with status = accepted/delete/tagged)
  - Call Gmail API to apply labels / trash messages
  - On success: move to "committed" status, delete from queue
  - On failure: retry logic (exponential backoff) or keep in queue for manual retry
- [ ] Add import/export UI:
  - Menu option "Import examples from desktop" → load `examples.json` via file picker
  - Menu option "Export examples" → save to external storage or share

**Deliverable**: App persists training data and can queue commits offline. Committed decisions saved to `examples.json` and sync'd to desktop on next export.

### Phase 5: Polish & Testing (Week 9)
- [ ] Loading states and error handling:
  - Show spinner during LLM inference
  - Show progress during email fetch
  - Toast notifications for commit success/error
- [ ] Settings screen (optional):
  - Toggle LLM inference on/off (fallback to zero-shot if disabled)
  - Delete cached model to free space
  - Adjust inference temperature/token limit
- [ ] Accessibility: content descriptions, keyboard navigation
- [ ] Unit tests for:
  - `AutoTagger` (mock LLM, check label scoring)
  - `PromptBuilder` (check few-shot format matches Python)
  - `PendingCommitsQueue` (check retry/offline logic)
- [ ] Integration test: end-to-end auth → fetch → tag → commit

**Deliverable**: Polished, testable MVP ready for alpha release.

## Stretch Goals (Post-MVP)

- [ ] On-device body summarization (post-commit, reusing TinyLlama)
- [ ] Swipe gestures for quick actions (swipe-left delete, swipe-right accept)
- [ ] Sync examples with desktop via Firebase or WebDAV
- [ ] Background batch inference (load next batch while user reviews current batch)
- [ ] Custom model support (allow user to swap TinyLlama for different GGUF)

## Key Considerations

### Model Size & Performance
- TinyLlama (600MB GGUF) is large for APK — consider:
  - First run: download model from server instead of bundling (lazy load)
  - Or split APK into multiple size buckets (Google Play's dynamic delivery)
  - Test on low-end devices (< 2GB RAM)
- Inference latency: ~1–2s per email on modern phone (Snapdragon 8+)
  - May be too slow for batch auto-tagging; show "Loading…" spinner
  - Consider quantized variants (q4, q5) if latency is prohibitive

### Gmail API Scopes
- `https://www.googleapis.com/auth/gmail.readonly` — read emails, list labels
- `https://www.googleapis.com/auth/gmail.modify` — apply labels, trash messages
- Same scopes as desktop (`auth_test.py`); no additional API setup needed
- Scope approval required on first sign-in; clearly explain to user why app needs read/modify access

### OAuth Token Management
- Store refresh token in CredentialManager (Android 13+) or Encrypted Shared Preferences (< Android 13)
- Refresh token automatically before expiry
- Clear token on sign-out

### Examples.json Compatibility
- Maintain same schema as Python Flask `examples.json`:
  ```json
  [
    {
      "id": "email_id",
      "from": "sender@example.com",
      "subject": "Email subject",
      "snippet": "First 200 chars…",
      "action": "delete" | ["tag:Label1", "tag:Label2"],
      "reasoning": "Model's explanation"
    }
  ]
  ```
- Seed from desktop: user exports `examples_projectid.json` and imports via file picker

### Testing Strategy
- **Unit**: AutoTagger logic, PromptBuilder format, queue retry logic
- **Integration**: Auth flow, email fetch, LLM inference (mock or slow-running)
- **E2E**: Full happy path on emulator (or real device with test Gmail account)
- **Performance**: Measure inference latency and memory usage on mid-range device

## Files to Check/Reference in Desktop Codebase

- `auto_tagger.py` — Label scoring, reasoning logic
- `fetch_emails.py` — Gmail API pagination, message parsing
- `templates/dashboard.html` — UI layout and state management patterns
- `review_emails.py` — Label ordering, few-shot prompt format
- `examples.json` — Training data schema

## Success Criteria

1. ✓ App authenticates via Google Sign-In
2. ✓ App fetches and displays unread emails
3. ✓ LLM auto-tags emails with reasoning (on-device)
4. ✓ User can manually override suggestions via tag picker modal
5. ✓ Commit applies changes to Gmail API
6. ✓ Training data persists to `examples_projectid.json`
7. ✓ Offline commit queue works (changes queued locally, synced when online)
8. ✓ Can import/export `examples.json` from/to desktop
9. ✓ App handles network failures gracefully (timeouts, offline, API errors)
10. ✓ Unit tests for core logic (AutoTagger, PromptBuilder, queue)
