# Persistence Module

This module provides data persistence for MediaCopier, allowing jobs, statistics, and UI state to be saved and restored across application sessions.

## Features

### 1. Job Persistence (`JobStorage`)
- **Auto-save**: Jobs are automatically saved every 60 seconds
- **Save on exit**: Pending jobs are saved when the application closes
- **Restore on startup**: Pending jobs are automatically restored when the application starts
- **Smart filtering**: Only pending and running jobs are saved (completed and error jobs are excluded)
- **Status conversion**: Running jobs are converted to pending on restore

### 2. Statistics Persistence (`StatsStorage`)
- **History tracking**: Maintains a history of up to 100 burning operations
- **Summary statistics**: Provides aggregated statistics (total jobs, files, bytes)
- **Timestamped entries**: Each entry includes a timestamp for tracking

### 3. UI State Persistence (`UIStateStorage`)
- **Window geometry**: Remembers window size and position
- **User preferences**: Saves last used paths and settings
- **Auto-refresh state**: Remembers auto-refresh enabled/disabled state

## Storage Locations

### Windows
```
%APPDATA%\MediaCopier\
├── pending_jobs.json      # Saved jobs
├── burning_stats.json     # Statistics history
└── ui_state.json          # UI preferences
```

### Linux/macOS
```
~/.config/MediaCopier/
├── pending_jobs.json      # Saved jobs
├── burning_stats.json     # Statistics history
└── ui_state.json          # UI preferences
```

## Usage

### Automatic Usage

The persistence layer is automatically integrated into the MediaCopier UI:

```python
# In window.py, persistence is initialized automatically
app = MediaCopierUI()
app.mainloop()  # Jobs are auto-saved every 60 seconds and on exit
```

### Manual Usage

You can also use the persistence modules directly:

```python
from mediacopier.persistence import JobStorage, StatsStorage, UIStateStorage
from mediacopier.ui.job_queue import Job, JobStatus

# Job Storage
storage = JobStorage()
jobs = [...]  # Your jobs
storage.save_jobs(jobs)
loaded_jobs = storage.load_jobs()

# Stats Storage
stats_storage = StatsStorage(storage.storage_dir)
stats_storage.save_stats({"files_copied": 10, "bytes_copied": 1024})
summary = stats_storage.get_summary()

# UI State Storage
ui_storage = UIStateStorage(storage.storage_dir)
ui_storage.save_state({"window_geometry": "1200x800"})
state = ui_storage.load_state()
```

## Implementation Details

### Job Storage
- Jobs are serialized using the `Job.to_dict()` method
- Only jobs with status `PENDING`, `RUNNING`, `PAUSED`, or `STOPPED` are saved
- Jobs with status `COMPLETED` or `ERROR` are excluded from persistence
- Running jobs are automatically converted to `PENDING` status on restore

### Auto-Save Mechanism
- Triggered every 60 seconds via `_start_autosave()` method
- Logs the number of pending jobs being saved (at DEBUG level)
- Gracefully handles errors without crashing the application

### Restore Process
1. On application startup, `_restore_pending_jobs()` is called
2. Saved jobs are loaded from disk
3. Completed and error jobs are filtered out
4. Running jobs are converted to pending status
5. Jobs are added to the job queue
6. The queue panel is refreshed to show restored jobs

## Error Handling

All persistence operations include error handling:
- Failed saves are logged but don't crash the application
- Corrupted files are handled gracefully with defaults
- Missing files return empty lists/default states

## Testing

The module includes comprehensive test coverage:
- 20 unit tests for individual storage modules
- 7 integration tests for window.py integration
- Manual test script for verification

Run tests with:
```bash
pytest tests/test_persistence.py -v
pytest tests/test_persistence_integration.py -v
```

## Logging

Persistence operations are logged at appropriate levels:
- `DEBUG`: Auto-save operations
- `INFO`: Restore operations when no jobs found
- `OK`: Successful restoration of jobs
- `WARN`: Errors during save/restore operations
